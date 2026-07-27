"""
LBO Router — /lbo endpoints (V3)

Endpoints:
  POST  /lbo/calculate     Run a full LBO model (V3 — multi-tranche, waterfall)
  POST  /lbo/export-excel  Run model & return auditable .xlsx workbook
  POST  /lbo/buildup       Run a Buy & Build / Multiple Arbitrage simulation
"""
from __future__ import annotations
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.lbo import (
    DebtTranche,
    ManagementPackage,
    SectorCalibrationOut,
    LBOScenarioCreate,
    LBOScenarioOut,
    LBOScenarioListItem,
)
from api.services.ma_engine.valuation_engine import run_lbo_model, resolve_profile_key, LBO_PROFILES
from api.services.ma_engine.sector_calibration import (
    compute_sector_calibration,
    TIC_COMP_SET_ID,
    DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT,
    CALIBRATED_SECTOR_PROFILE_KEY,
)
from api.services.ma_engine.buildup_engine import calculate_buildup
from api.services.ma_engine.excel_generator import generate_lbo_model_excel
from api.services import lbo_scenario_service


router = APIRouter(prefix="/lbo", tags=["LBO Engine"])


# ============================================================
# Request / Response schemas
# ============================================================

class LBOCalculateRequest(BaseModel):
    """Payload for POST /lbo/calculate — Paper LBO V3."""
    revenue: float = Field(..., gt=0, description="CA estimé Année 0 (€)")
    sector_or_naf: str = Field("", description="Secteur libre ou code NAF")
    holding_period: int = Field(5, ge=1, le=15, description="Horizon en années")
    override_entry_mult: float | None = Field(None, description="Multiple d'entrée (override)")
    override_exit_mult: float | None = Field(None, description="Multiple de sortie (override)")
    override_leverage: float | None = Field(None, description="Levier dette/EBITDA (override, ignoré si debt_structure)")

    # D22, Tâche B.8 — calibrage sectoriel dérivé du CompSet réel
    use_sector_calibration: bool = Field(
        False, description="Si vrai, dérive marge EBITDA & multiple d'entrée du CompSet réel (D22) au lieu du profil générique"
    )
    size_illiquidity_discount: float | None = Field(
        None, ge=0, le=0.9, description="Décote taille/illiquidité (défaut 35%) — voir sector_calibration.py"
    )

    # V3
    debt_structure: list[DebtTranche] = Field(
        default_factory=list,
        description="Multi-tranche debt structure (optional — overrides leverage)",
    )
    management_package: ManagementPackage | None = Field(
        None, description="Sweet equity & ratchet (optional)"
    )


class AddonTarget(BaseModel):
    """Schema pour une cible add-on dans le build-up."""
    url: str = ""
    estimated_revenue: float = 0
    ebitda: float = 0
    ev: float = 0
    entry_multiple: float = 0
    irr: float = 0
    moic: float = 0


class BuildupRequest(BaseModel):
    """Payload for POST /lbo/buildup — Buy & Build.

    Toutes les hypothèses (capex_pct, wcr_pct, leverage_turns,
    growth_override) sont optionnelles : si omises, le moteur applique le
    profil sectoriel TIC calibré (`professional_svc`) — le secteur réel de
    toutes les cibles sourcées par ce projet (D37, Revue Produit)."""
    platform_target: dict[str, Any] = Field(
        ..., description="Dict de la cible plateforme (url, estimated_revenue, ebitda, ev, entry_multiple, irr, moic, lbo_projections)"
    )
    addon_targets: list[dict[str, Any]] = Field(
        default_factory=list, description="Liste des cibles add-on"
    )
    synergy_pct: float = Field(0.05, ge=0, le=0.5, description="% synergies CA consolidé")
    capex_pct: float | None = Field(None, ge=0, le=0.5, description="Capex % CA — défaut : profil sectoriel TIC (2%)")
    wcr_pct: float | None = Field(None, ge=0, le=1.0, description="BFR % de ΔCA — défaut : profil sectoriel TIC (15%)")
    leverage_turns: float | None = Field(None, ge=0, le=8.0, description="Levier d'entrée ×EBITDA — défaut : 4.0x (partagé LBO standalone)")
    growth_override: float | None = Field(None, ge=-0.5, le=0.5, description="Force la croissance annuelle du CA consolidé (sinon inférée des projections réelles)")


# ============================================================
# D22 — Calibrage sectoriel
# ============================================================

async def _resolve_calibration(
    db: AsyncSession, sector_or_naf: str, discount: float | None,
) -> SectorCalibrationOut:
    """Calcule la calibration pour le secteur résolu. Ne s'applique QUE si le
    secteur résolu est celui du CompSet calibré (`CALIBRATED_SECTOR_PROFILE_KEY`)
    — sinon `applicable=False`, signalé explicitement, jamais silencieux."""
    profile_key = resolve_profile_key(sector_or_naf)
    if profile_key != CALIBRATED_SECTOR_PROFILE_KEY:
        # D34 (Tâche Review Produit — Partie D) : message reformulé pour un
        # utilisateur non technique — auparavant il exposait les clés Python
        # internes brutes ("resolved profile for this input: 'software_it'"),
        # incompréhensibles hors du code. On cite le nom lisible du secteur
        # calibré et celui réellement résolu (`SectorProfile.name`, pas la
        # clé), et on explique explicitement CE QUI EST FAIT à la place —
        # jamais juste "non applicable" sans suite.
        resolved_name = LBO_PROFILES[profile_key].name
        calibrated_name = LBO_PROFILES[CALIBRATED_SECTOR_PROFILE_KEY].name
        return SectorCalibrationOut(
            sufficient=False,
            applicable=False,
            fallback_reason=(
                f"Calibrage non applicable : il s'appuie sur un panel réel de comparables cotés du "
                f"secteur « {calibrated_name} » (TIC — Test, Inspection, Certification). Le secteur "
                f"résolu pour cette cible, « {resolved_name} », n'en fait pas partie. Un profil "
                f"générique documenté (hypothèses de marge et de multiple par défaut, non dérivées "
                f"de comparables réels) est utilisé à la place."
            ),
            size_illiquidity_discount=discount if discount is not None else DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT,
        )

    calib = await compute_sector_calibration(
        db, comp_set_id=TIC_COMP_SET_ID,
        discount=discount if discount is not None else DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT,
    )
    return SectorCalibrationOut(**calib.to_dict(), applicable=True)


def _calibrated_profile_override(calibration: SectorCalibrationOut):
    """Construit un SectorProfile calibré (marge + multiple d'entrée dérivés
    du CompSet) en conservant les autres paramètres du profil générique
    'professional_svc' inchangés — pas de mutation de LBO_PROFILES lui-même."""
    if not calibration.applicable or not calibration.sufficient:
        return None
    generic = LBO_PROFILES[CALIBRATED_SECTOR_PROFILE_KEY]
    return replace(
        generic,
        name=f"{generic.name} (calibré — CompSet '{calibration.comp_set_name}')",
        ebitda_margin=calibration.median_ebitda_margin,
        entry_multiple=calibration.derived_entry_multiple,
    )


@router.get("/calibration", response_model=SectorCalibrationOut, summary="Chaîne de calibrage sectoriel (D22)")
async def lbo_calibration(
    sector_or_naf: str = "",
    size_illiquidity_discount: float | None = None,
    db: AsyncSession = Depends(get_db),
) -> SectorCalibrationOut:
    """
    Calcule la chaîne de calibrage du multiple d'entrée pour un secteur donné :
    médiane des comparables cotés du CompSet réel − décote taille/illiquidité.

    `applicable=False` si le secteur résolu n'est pas couvert par un CompSet
    calibré ; `sufficient=False` si le CompSet existe mais n'a pas assez de
    membres avec un EBITDA réel — dans les deux cas le calculateur doit
    utiliser le profil sectoriel générique et le signaler à l'utilisateur.
    """
    return await _resolve_calibration(db, sector_or_naf, size_illiquidity_discount)


# ============================================================
# Endpoints
# ============================================================

@router.post("/calculate", summary="Paper LBO Model V3")
async def lbo_calculate(body: LBOCalculateRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Exécute un modèle Paper LBO complet (V3).

    Supporte :
    - Multi-tranche debt (Senior A/B, Mezzanine…) avec profil in fine / amortissable
    - Management Package (sweet equity + ratchet)
    - Waterfall de distribution Fund vs Management à la sortie
    - Calibrage sectoriel dérivé du CompSet réel (D22, si `use_sector_calibration`)

    Rétro-compatible : sans debt_structure ni management_package, se comporte
    comme le Paper LBO V2 (4× EBITDA senior @ 7%).
    """
    # Serialize debt_structure to list[dict] for the engine
    debt_struct = [t.model_dump() for t in body.debt_structure] if body.debt_structure else None
    mgmt_pkg = body.management_package.model_dump() if body.management_package else None

    calibration: SectorCalibrationOut | None = None
    calibrated_profile = None
    if body.use_sector_calibration:
        calibration = await _resolve_calibration(db, body.sector_or_naf, body.size_illiquidity_discount)
        calibrated_profile = _calibrated_profile_override(calibration)

    result = run_lbo_model(
        revenue=body.revenue,
        sector_or_naf=body.sector_or_naf,
        holding_period=body.holding_period,
        override_entry_mult=body.override_entry_mult,
        override_exit_mult=body.override_exit_mult,
        override_leverage=body.override_leverage,
        debt_structure=debt_struct,
        management_package=mgmt_pkg,
        calibrated_profile=calibrated_profile,
    )
    if calibration is not None:
        result["calibration"] = calibration.model_dump()
    return result


@router.post(
    "/export-excel",
    summary="Export LBO Model as auditable Excel (.xlsx)",
    response_class=StreamingResponse,
)
async def lbo_export_excel(body: LBOCalculateRequest, db: AsyncSession = Depends(get_db)):
    """
    Exécute le modèle LBO V3 puis génère un fichier Excel (.xlsx) à formules
    vivantes (D24, Tâche B.9) : Assumptions (entrées bleues, y compris la
    chaîne de calibrage D22 si demandée), P&L & Cash Flow, Debt Schedule
    (si multi-tranche, entièrement formulé), Returns & Waterfall.

    Retourne un StreamingResponse (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet).
    """
    debt_struct = [t.model_dump() for t in body.debt_structure] if body.debt_structure else None
    mgmt_pkg = body.management_package.model_dump() if body.management_package else None

    calibration: SectorCalibrationOut | None = None
    calibrated_profile = None
    if body.use_sector_calibration:
        calibration = await _resolve_calibration(db, body.sector_or_naf, body.size_illiquidity_discount)
        calibrated_profile = _calibrated_profile_override(calibration)

    result = run_lbo_model(
        revenue=body.revenue,
        sector_or_naf=body.sector_or_naf,
        holding_period=body.holding_period,
        override_entry_mult=body.override_entry_mult,
        override_exit_mult=body.override_exit_mult,
        override_leverage=body.override_leverage,
        debt_structure=debt_struct,
        management_package=mgmt_pkg,
        calibrated_profile=calibrated_profile,
    )
    if calibration is not None:
        result["calibration"] = calibration.model_dump()

    excel_buf = generate_lbo_model_excel(result)

    # Build a meaningful filename — Content-Disposition headers must be latin-1
    # encodable; a calibrated profile name can contain "—" (D22, Tâche B.8:
    # "professional_svc (calibré — CompSet '...')"), which is NOT latin-1 and
    # previously crashed this endpoint with a 500 (UnicodeEncodeError). Strip
    # to ASCII rather than assume the profile name is header-safe.
    sector_raw = result.get("sector_profile", "model").split(" (")[0]  # drop "(calibré — ...)" suffix
    sector = sector_raw.encode("ascii", "ignore").decode("ascii").replace(" ", "_").replace("/", "-") or "model"
    rev_m = round(body.revenue / 1_000_000, 1)
    filename = f"LBO_Model_{sector}_{rev_m}M_EUR.xlsx"

    return StreamingResponse(
        excel_buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/buildup", summary="Buy & Build / Multiple Arbitrage")
async def lbo_buildup(body: BuildupRequest) -> dict:
    """
    Simule une stratégie Buy & Build : consolidation plateforme + add-ons,
    synergies, financement, exit avec multiple arbitrage.

    Retourne : consolidation Y0, financement, projections 5 ans,
    rendements build-up vs standalone, delta IRR.
    """
    result = calculate_buildup(
        platform_target=body.platform_target,
        addon_targets=body.addon_targets,
        synergy_pct=body.synergy_pct,
        capex_pct=body.capex_pct,
        wcr_pct=body.wcr_pct,
        leverage_turns=body.leverage_turns,
        growth_override=body.growth_override,
    )
    return result


# ============================================================
# D23, Tâche B.8 — Persistance des scénarios LBO
# ============================================================

@router.post("/scenarios", response_model=LBOScenarioOut, status_code=201, summary="Enregistrer un scénario LBO")
async def create_scenario(body: LBOScenarioCreate, db: AsyncSession = Depends(get_db)) -> LBOScenarioOut:
    """Sauvegarde explicite d'un scénario LBO (action utilisateur — jamais
    automatique). Le calculateur reste utilisable sans deal ni sauvegarde ;
    cet endpoint n'est appelé que sur clic du bouton « Enregistrer »."""
    scenario = await lbo_scenario_service.create_scenario(
        db, deal_id=body.deal_id, label=body.label,
        assumptions=body.assumptions, result=body.result,
    )
    return LBOScenarioOut.model_validate(scenario)


@router.get("/scenarios", response_model=list[LBOScenarioListItem], summary="Lister les scénarios LBO d'un deal")
async def list_scenarios(deal_id: int, db: AsyncSession = Depends(get_db)) -> list[LBOScenarioListItem]:
    scenarios = await lbo_scenario_service.list_scenarios_for_deal(db, deal_id)
    items = []
    for s in scenarios:
        r = s.result_json or {}
        items.append(LBOScenarioListItem(
            id=s.id, deal_id=s.deal_id, label=s.label, created_at=s.created_at,
            entry_multiple=r.get("entry_multiple"), exit_multiple=r.get("exit_multiple"),
            irr=r.get("irr"), moic=r.get("moic"),
        ))
    return items


@router.get("/scenarios/{scenario_id}", response_model=LBOScenarioOut, summary="Détail d'un scénario LBO (rechargement)")
async def get_scenario(scenario_id: int, db: AsyncSession = Depends(get_db)) -> LBOScenarioOut:
    scenario = await lbo_scenario_service.get_scenario(db, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return LBOScenarioOut.model_validate(scenario)


@router.delete("/scenarios/{scenario_id}", summary="Supprimer un scénario LBO")
async def delete_scenario(scenario_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    ok = await lbo_scenario_service.delete_scenario(db, scenario_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"status": "deleted", "id": scenario_id}
