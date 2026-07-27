"""
LBO Scenario Service — persistance des scénarios LBO (D23, Tâche B.8).

CRUD minimal, pas de recalcul : un scénario sauvegardé est un instantané
figé (`assumptions_json` + `result_json`), rechargé tel quel.
"""
from __future__ import annotations
from dataclasses import replace as _replace
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.deal import Deal
from api.models.lbo_scenario import LBOScenario
from api.services.ma_engine.valuation_engine import (
    run_lbo_model,
    resolve_profile_key,
    LBO_PROFILES,
    SMALL_CAP_REVENUE_THRESHOLD,
    SMALL_CAP_DEFAULT_LEVERAGE,
)
from api.services.ma_engine.sector_calibration import (
    compute_sector_calibration,
    TIC_COMP_SET_ID,
    DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT,
    CALIBRATED_SECTOR_PROFILE_KEY,
)
from api.services.deals_service import compute_deal_multiples
from api.schemas.provenance import DataProvenance, FieldProvenance, field_provenance_from_json, weakest_provenance

BASE_CASE_LABEL = "Base case (auto)"
DOWNSIDE_CASE_LABEL = "Downside case (auto)"

# Tâche "P2 : crédibilité de la thèse" (Partie B) — hypothèses par défaut du
# cas baissier, appliquées au même moteur (`run_lbo_model`), aucune formule
# nouvelle : CA d'entrée réduit et multiple de sortie dégradé vs le base
# case, tout le reste (secteur, calibrage, levier, marge) reste identique —
# ce sont les deux seuls leviers de stress que Partie B autorise.
DOWNSIDE_REVENUE_HAIRCUT_PCT = 0.10   # CA Année 0 : -10% vs base case
DOWNSIDE_EXIT_MULTIPLE_DELTA = -1.0   # Multiple de sortie : -1.0x vs base case

# Tâche "P2" (Partie A) — sous ce seuil de CA, le levier par défaut passe à
# SMALL_CAP_DEFAULT_LEVERAGE (dette bancaire senior seule, pas de mezzanine)
# et le scénario est étiqueté "indicatif" partout où il est affiché (mémo,
# deck, Excel, écran) : un LBO standalone à ce niveau de CA n'est pas
# réaliste en pratique — la structure réaliste est un bolt-on adossé à une
# plateforme existante (voir Buy & Build), pas un LBO mezzanine autonome.
SIZING_NOTE_INDICATIVE = (
    "At this size, a standalone mezzanine LBO is not realistically financeable in the "
    "French market — real senior bank debt capacity here is roughly 2.0-2.5x EBITDA, with "
    "no mezzanine layer. This model uses a conservative bank-debt-only leverage and is "
    "shown for INDICATIVE purposes only, not a financeable standalone structure. A "
    "realistic structure at this size is a bolt-on add-on to an existing platform (see the "
    "Buy & Build module), financed with bank debt at the platform level — not a standalone "
    "mezzanine LBO."
)


# D45 (Tâche Finalisation, Partie F) — la provenance des hypothèses d'un
# scénario base-case (multiple d'entrée, marge EBITDA, CA de départ) existait
# déjà en pratique (calcul réel via compute_sector_calibration, D22), mais
# jamais exposée sous la forme normalisée `dict[str, FieldProvenance]` que le
# reste du projet utilise partout ailleurs (Deal.financial_provenance,
# CompsTableRow.financial_provenance) — elle restait enfouie dans
# `result["calibration"]`, un format propre à ce sous-objet. Cette fonction
# NE RECALCULE RIEN (aucune formule du moteur LBO ni du service de calibrage
# touchée) : elle repackage des valeurs déjà produites par
# `compute_sector_calibration`/`Deal.financial_provenance` dans le format
# `FieldProvenance` partagé, en pure lecture/exposition.
def _build_scenario_provenance(
    deal: Deal,
    calibration_result,
    calibrated_profile,
    generic_profile_name: str,
    override_entry_ebitda: float | None = None,
) -> dict[str, dict]:
    prov: dict[str, dict] = {}

    # Le CA de départ du scénario EST deal.target_revenue — sa provenance est
    # donc, par construction, celle déjà tracée sur le deal (jamais une
    # provenance distincte inventée pour le scénario).
    deal_prov = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
    revenue_prov = field_provenance_from_json(deal_prov, "target_revenue")
    prov["revenue"] = (
        revenue_prov.model_dump(mode="json") if revenue_prov
        else FieldProvenance(provenance=DataProvenance.UNKNOWN, reference="Deal revenue provenance not tracked").model_dump(mode="json")
    )

    # Le multiple d'entrée reste TOUJOURS piloté par le calibrage sectoriel
    # (ou le profil générique) — inchangé par l'EBITDA réel (Tâche "Le moteur
    # LBO accepte un EBITDA réel en entrée" : seul l'EBITDA de départ change
    # de source, jamais le multiple).
    if calibrated_profile is not None and calibration_result is not None and calibration_result.sufficient:
        # D46 (Tâche Finalisation, Partie 1) : toujours ESTIMATE — un multiple
        # dérivé (médiane + décote) n'est jamais un fait documenté, même
        # quand les comparables sources sont eux-mêmes MARKET/DOCUMENT (voir
        # sector_calibration.py::entry_multiple_provenance).
        prov["entry_multiple"] = calibration_result.entry_multiple_provenance()
    else:
        generic_ref = f"Generic sector profile assumption ({generic_profile_name}) — not derived from real comparables"
        prov["entry_multiple"] = FieldProvenance(provenance=DataProvenance.ESTIMATE, reference=generic_ref).model_dump(mode="json")

    if override_entry_ebitda is not None:
        # L'EBITDA de départ est le chiffre RÉEL du deal (DOCUMENT/REGISTRY),
        # pas une hypothèse — la marge affichée est désormais IMPLIQUÉE
        # (EBITDA réel ÷ CA) et hérite de la provenance la plus faible entre
        # les deux (même convention que compute_deal_multiples), jamais
        # ESTIMATE : ce n'est plus une supposition sectorielle.
        ebitda_prov = field_provenance_from_json(deal_prov, "target_ebitda")
        margin_provenance = weakest_provenance(
            revenue_prov.provenance if revenue_prov else None,
            ebitda_prov.provenance if ebitda_prov else None,
        )
        prov["ebitda_margin"] = FieldProvenance(
            provenance=margin_provenance,
            reference=(
                f"Implied margin: deal's own real EBITDA (€{override_entry_ebitda:,.0f}) ÷ revenue "
                f"— the deal has a documented/registry EBITDA figure, used directly as the LBO "
                f"entry EBITDA instead of a sector-margin estimate."
            ),
        ).model_dump(mode="json")
    elif calibrated_profile is not None and calibration_result is not None and calibration_result.sufficient:
        prov["ebitda_margin"] = calibration_result.ebitda_margin_provenance()
    else:
        generic_ref = f"Generic sector profile assumption ({generic_profile_name}) — not derived from real comparables"
        prov["ebitda_margin"] = FieldProvenance(provenance=DataProvenance.ESTIMATE, reference=generic_ref).model_dump(mode="json")

    return prov


# Tâche "Unifier l'EBITDA estimé entre le deal et le LBO" — le constat : le
# scan de sourcing (similarity_scorer.py) calcule `SourcedTarget.ebitda_estimate`
# via `run_lbo_model(revenue, company_dna_sector)` SANS calibrage (le CompSet
# n'existe/n'est pertinent qu'au niveau du deal, pas encore connu au moment du
# scan) — ce chiffre est ensuite copié tel quel sur `Deal.target_ebitda` par
# `sourcing_service.promote_target_to_deal`. Le scénario LBO de référence,
# construit juste après par `build_base_case_scenario` ci-dessous, recalcule
# SA PROPRE entry_ebitda = revenue × marge — calibrée sur le CompSet réel si le
# secteur s'y prête, sinon la même marge générique, mais dans TOUS les cas une
# marge distincte de celle utilisée au moment du scan. Les deux chiffres
# mesurent le même concept (l'EBITDA de la cible) avec deux marges différentes
# — contrairement au cas des deux multiples (deux concepts distincts), ceci
# est un vrai défaut à corriger, pas une divergence légitime à documenter.
#
# Point d'unification retenu : ICI, juste après que `result` (donc la marge
# réellement utilisée par le scénario, calibrée ou générique) est connu — sans
# toucher aux formules de `run_lbo_model`/`compute_sector_calibration`, on
# réaligne `Deal.target_ebitda` sur cette même marge. Ne touche JAMAIS un
# EBITDA réel (DOCUMENT/REGISTRY) : le moteur LBO n'a de toute façon aucun
# paramètre pour accepter un EBITDA réel en entrée (il recalcule toujours
# revenue × marge) — si un tel cas existe un jour, il doit être signalé plutôt
# que corrigé ici (toucherait `run_lbo_model`, hors périmètre).
def ebitda_margin_reference_from_result(result: dict) -> str:
    """Builds the FieldProvenance.reference text for a unified deal-level
    EBITDA, from a (live or persisted) LBO scenario `result` dict — pure
    formatting, reusable by the live promotion path AND the backfill script
    against already-saved `LBOScenario.result_json` without recomputing
    anything.

    Tâche "P0 : un seul deal dans les 3 documents" (Partie D) : ce texte est
    cité VERBATIM dans le mémo/deck client (qualify_amount affiche
    `reference` telle quelle) — la version précédente contenait un renvoi à
    un rapport interne ("RAPPORT B.6 §Étape 6"), un tag interne ("(D22)") et
    du jargon technique ("OSINT") visibles par un lecteur externe. Reformulé
    en langage naturel, sans référence interne — le contenu factuel (méthode
    d'estimation, cohérence avec le scénario LBO) est conservé à l'identique.
    """
    calib = result.get("calibration") or {}
    if calib.get("applicable") and calib.get("sufficient"):
        return (
            f"Estimated using the EBITDA margin derived from comparable listed companies "
            f"(comparables set '{calib.get('comp_set_name', 'N/A')}', median margin "
            f"{(calib.get('median_ebitda_margin') or 0) * 100:.2f}%) — the same margin used "
            f"in the reference LBO scenario. No real EBITDA is available from free public "
            f"sources for a non-listed French company."
        )
    return (
        f"Estimated using a generic sector profile's EBITDA margin "
        f"({result.get('sector_profile', 'N/A')}, {(result.get('ebitda_margin') or 0) * 100:.2f}%) "
        f"— the same margin used in the reference LBO scenario. No real EBITDA is available "
        f"from free public sources for a non-listed French company."
    )


def sync_deal_ebitda_with_scenario(deal: Deal, new_ebitda: float | None, reference: str) -> bool:
    """Reassigns `Deal.target_ebitda` to `new_ebitda` (the LBO scenario's own
    entry EBITDA) IF the deal's current EBITDA is itself an ESTIMATE (or
    untracked) — never overwrites a real, documented figure (DOCUMENT /
    REGISTRY). Returns True if it changed anything, False otherwise (already
    aligned, no valid new figure, or a real EBITDA was protected)."""
    raw_prov = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
    ebitda_prov = field_provenance_from_json(raw_prov, "target_ebitda")

    if ebitda_prov is not None and ebitda_prov.provenance != DataProvenance.ESTIMATE:
        # Tâche "Le moteur LBO accepte un EBITDA réel en entrée" : depuis
        # cette tâche, `build_base_case_scenario` passe déjà ce même EBITDA
        # réel en `override_entry_ebitda` à `run_lbo_model` — `new_ebitda`
        # (l'entry_ebitda du scénario) devrait donc déjà être identique par
        # construction. Ne JAMAIS écraser la donnée réelle dans tous les cas
        # ; un écart ici ne serait plus l'attendu mais un vrai bug (l'override
        # n'aurait pas été appliqué quelque part) — à investiguer, jamais à
        # masquer en forçant deal.target_ebitda à changer.
        if new_ebitda is not None and deal.target_ebitda is not None and abs(new_ebitda - deal.target_ebitda) > 0.01:
            logger.warning(
                "[EBITDA unification] Deal {} a un EBITDA réel ({}, {}) mais le scénario LBO a "
                "calculé une entry_ebitda différente ({}) — l'override entry_ebitda ne semble pas "
                "avoir été appliqué. À investiguer ; la donnée réelle du deal n'est PAS écrasée.",
                deal.id, deal.target_ebitda, ebitda_prov.provenance, new_ebitda,
            )
        return False

    if not new_ebitda or new_ebitda <= 0:
        return False
    if deal.target_ebitda is not None and abs(deal.target_ebitda - new_ebitda) < 0.01:
        return False

    deal.target_ebitda = new_ebitda
    updated_prov = dict(raw_prov)
    updated_prov["target_ebitda"] = FieldProvenance(
        provenance=DataProvenance.ESTIMATE, reference=reference,
    ).model_dump(mode="json")
    deal.financial_provenance = updated_prov
    compute_deal_multiples(deal)
    logger.info(
        "[EBITDA unification] Deal {} — target_ebitda aligné sur le scénario LBO : {}.",
        deal.id, new_ebitda,
    )
    return True


async def create_scenario(
    db: AsyncSession, *, deal_id: int, label: str,
    assumptions: dict[str, Any], result: dict[str, Any],
) -> LBOScenario:
    scenario = LBOScenario(
        deal_id=deal_id, label=label.strip(),
        assumptions_json=assumptions, result_json=result,
    )
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return scenario


async def list_scenarios_for_deal(db: AsyncSession, deal_id: int) -> list[LBOScenario]:
    result = await db.execute(
        select(LBOScenario)
        .where(LBOScenario.deal_id == deal_id)
        .order_by(LBOScenario.created_at.desc())
    )
    return list(result.scalars().all())


async def get_scenario(db: AsyncSession, scenario_id: int) -> LBOScenario | None:
    result = await db.execute(select(LBOScenario).where(LBOScenario.id == scenario_id))
    return result.scalar_one_or_none()


async def delete_scenario(db: AsyncSession, scenario_id: int) -> bool:
    scenario = await get_scenario(db, scenario_id)
    if not scenario:
        return False
    await db.delete(scenario)
    await db.commit()
    return True


async def get_reference_scenario(db: AsyncSession, deal_id: int) -> LBOScenario | None:
    """Scénario cité par le générateur de mémo IC (Étape 5) : celui dont le
    libellé contient « base » (insensible à la casse), sinon le plus
    récemment sauvegardé. Heuristique documentée — pas de champ dédié
    « scénario de référence » sur `Deal` (hors périmètre de cette tâche)."""
    scenarios = await list_scenarios_for_deal(db, deal_id)
    if not scenarios:
        return None
    for s in scenarios:
        if "base" in s.label.lower():
            return s
    return scenarios[0]


async def get_downside_scenario(db: AsyncSession, deal_id: int) -> LBOScenario | None:
    """Tâche "P2 : crédibilité de la thèse" (Partie B) — même heuristique que
    `get_reference_scenario` (libellé contenant "downside", insensible à la
    casse) ; retourne None si aucun cas baissier n'a été généré pour ce deal
    (ex. deals promus avant cette tâche) — jamais un scénario inventé."""
    scenarios = await list_scenarios_for_deal(db, deal_id)
    for s in scenarios:
        if "downside" in s.label.lower():
            return s
    return None


async def _resolve_calibration_and_profile(db: AsyncSession, sector_or_naf: str):
    """Shared by the base case and the downside case: resolves the SAME
    calibrated profile (or None) for a given sector — the two scenarios of
    one deal must never silently use two different calibrations."""
    if resolve_profile_key(sector_or_naf) != CALIBRATED_SECTOR_PROFILE_KEY:
        return None, None
    calibration_result = await compute_sector_calibration(
        db, comp_set_id=TIC_COMP_SET_ID, discount=DEFAULT_SIZE_ILLIQUIDITY_DISCOUNT,
    )
    if not calibration_result.sufficient:
        return None, calibration_result
    generic = LBO_PROFILES[CALIBRATED_SECTOR_PROFILE_KEY]
    calibrated_profile = _replace(
        generic,
        name=f"{generic.name} (calibré — CompSet '{calibration_result.comp_set_name}')",
        ebitda_margin=calibration_result.median_ebitda_margin,
        entry_multiple=calibration_result.derived_entry_multiple,
    )
    return calibrated_profile, calibration_result


def _resolve_override_ebitda(deal: Deal) -> float | None:
    """Shared by the base case and the downside case — a real (DOCUMENT/
    REGISTRY) EBITDA drives entry EBITDA in BOTH scenarios identically,
    never a sector-margin estimate in one and a real figure in the other."""
    deal_prov = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
    ebitda_prov = field_provenance_from_json(deal_prov, "target_ebitda")
    if (
        ebitda_prov is not None
        and ebitda_prov.provenance in (DataProvenance.DOCUMENT, DataProvenance.REGISTRY)
        and deal.target_ebitda and deal.target_ebitda > 0
    ):
        return deal.target_ebitda
    return None


def _attach_calibration_and_provenance(
    result: dict, deal: Deal, sector_or_naf: str,
    calibration_result, calibrated_profile, override_entry_ebitda: float | None,
) -> None:
    """Shared by the base case and the downside case — mutates `result` in
    place with the same "calibration"/"financial_provenance" blocks
    `build_base_case_scenario` always attached, extracted so both scenarios
    get byte-identical provenance/calibration text for the same deal."""
    if calibration_result is not None:
        # "applicable" (par opposition à "sufficient") suit la même convention
        # que api/routers/lbo.py::_resolve_calibration — le secteur résolu
        # correspond au CompSet calibré, que l'échantillon soit suffisant ou non.
        result["calibration"] = {**calibration_result.to_dict(), "applicable": True}
    else:
        # Tâche "P0 : un seul deal dans les 3 documents" (Partie D) : ce
        # texte est cité VERBATIM dans le deck client (slide Deal Terms &
        # Structure) — la version précédente était en français dans un
        # document anglais et interpolait la clé Python interne
        # CALIBRATED_SECTOR_PROFILE_KEY ("'professional_svc' attendu"),
        # visible telle quelle par un lecteur externe (cas Ingebime, secteur
        # non calibré). Reformulé en anglais, sans référence interne — cite
        # le nom lisible du profil générique réellement utilisé.
        fallback_profile_name = LBO_PROFILES[resolve_profile_key(sector_or_naf)].name
        result["calibration"] = {
            "applicable": False,
            "sufficient": False,
            "fallback_reason": (
                f"This sector is not covered by the calibrated comparables set — a generic "
                f"sector profile was used instead ({fallback_profile_name})."
            ),
        }

    # D45 (Tâche Finalisation, Partie F) : exposition normalisée de la
    # provenance des hypothèses du scénario — voir docstring de
    # _build_scenario_provenance. Aucune formule touchée, pure lecture des
    # valeurs déjà calculées ci-dessus.
    resolved_profile_name = LBO_PROFILES[resolve_profile_key(sector_or_naf)].name
    result["financial_provenance"] = _build_scenario_provenance(
        deal, calibration_result, calibrated_profile, resolved_profile_name,
        override_entry_ebitda=override_entry_ebitda,
    )


async def build_base_case_scenario(db: AsyncSession, deal: Deal) -> LBOScenario | None:
    """Calcule et persiste un scénario LBO base-case à la promotion d'une
    cible en deal (D27, Tâche Review Produit — Partie B). Réutilise le même
    calibrage sectoriel (D22) et le même moteur (`run_lbo_model`) que le
    calcul manuel via `POST /lbo/calculate?use_sector_calibration=true` —
    aucune logique de calcul dupliquée, seule l'orchestration est nouvelle.

    Best-effort et non bloquant : si le deal n'a pas de CA connu, il n'y a
    rien à modéliser et la fonction retourne None sans lever — la promotion
    de la cible ne doit jamais échouer à cause d'un scénario auto qui ne
    peut pas être construit.

    Provenance : `assumptions_json.auto_generated=True` signale explicitement
    que ce scénario n'a jamais été revu par un humain (hypothèses ESTIMATE
    ou calibrées sur le CompSet réel, jamais une saisie manuelle) — distinct
    de tout scénario sauvegardé volontairement via le bouton du calculateur.

    Tâche "P2 : crédibilité de la thèse" (Partie A) : sous
    `SMALL_CAP_REVENUE_THRESHOLD` de CA, le levier par défaut passe à
    `SMALL_CAP_DEFAULT_LEVERAGE` (dette bancaire senior seule — un LBO
    standalone mezzanine à 4,0x n'est pas finançable en pratique à cette
    taille) et le scénario est étiqueté "indicatif" (`sizing_tier`) partout
    où il est affiché. Seule la valeur par défaut passée à
    `override_leverage` change — aucune formule du moteur n'est modifiée.
    """
    if not deal.target_revenue or deal.target_revenue <= 0:
        logger.info(
            "[LBO base-case auto] Deal {} sans CA connu — scénario non généré.", deal.id,
        )
        return None

    sector_or_naf = deal.sector or ""
    calibrated_profile, calibration_result = await _resolve_calibration_and_profile(db, sector_or_naf)
    override_entry_ebitda = _resolve_override_ebitda(deal)

    is_small_cap = deal.target_revenue < SMALL_CAP_REVENUE_THRESHOLD
    override_leverage = SMALL_CAP_DEFAULT_LEVERAGE if is_small_cap else None

    result = run_lbo_model(
        revenue=deal.target_revenue,
        sector_or_naf=sector_or_naf,
        calibrated_profile=calibrated_profile,
        override_entry_ebitda=override_entry_ebitda,
        override_leverage=override_leverage,
    )
    _attach_calibration_and_provenance(
        result, deal, sector_or_naf, calibration_result, calibrated_profile, override_entry_ebitda,
    )

    # Réaligne Deal.target_ebitda sur la marge réellement utilisée par ce
    # scénario (calibrée ou générique) — voir docstring de
    # sync_deal_ebitda_with_scenario. Doit s'exécuter AVANT la persistance du
    # scénario pour que le premier mémo/deck généré pour ce deal ne voie
    # jamais l'ancien écart.
    sync_deal_ebitda_with_scenario(
        deal, result.get("entry_ebitda"), ebitda_margin_reference_from_result(result),
    )

    assumptions = {
        "revenue": deal.target_revenue,
        "sector_or_naf": sector_or_naf,
        "sizing_tier": "indicative_bolt_on" if is_small_cap else "standalone",
        "sizing_note": SIZING_NOTE_INDICATIVE if is_small_cap else None,
        "use_sector_calibration": calibrated_profile is not None,
        "auto_generated": True,
        "auto_generated_reason": (
            "D27 — base-case généré automatiquement à la promotion de la "
            "cible, hypothèses ESTIMATE/calibrées, non revu par un humain."
        ),
    }

    scenario = await create_scenario(
        db, deal_id=deal.id, label=BASE_CASE_LABEL,
        assumptions=assumptions, result=result,
    )
    logger.info(
        "[LBO base-case auto] Deal {} — scénario #{} créé (IRR={}, MOIC={}).",
        deal.id, scenario.id, result.get("irr"), result.get("moic"),
    )
    return scenario


async def build_downside_scenario(db: AsyncSession, deal: Deal, base_result: dict) -> LBOScenario | None:
    """Tâche "P2 : crédibilité de la thèse" (Partie B) — génère et persiste
    un scénario 'Downside case (auto)' pour le même deal, en plus du base
    case : "un mémo d'IC mono-scénario n'existe pas" était le constat de la
    revue IC externe. Même secteur/calibrage/levier/marge que le base case
    (le même profil figé — jamais une redérivation indépendante qui
    risquerait de diverger) : seuls le CA d'entrée (-10%) et le multiple de
    sortie (-1,0x, lu depuis `base_result["exit_multiple"]` pour ne jamais
    diverger du multiple réellement retenu par le base case) sont dégradés —
    les deux seuls leviers de stress que Partie B autorise. Calculé par le
    même moteur (`run_lbo_model`), aucune formule nouvelle. Best-effort,
    comme `build_base_case_scenario` — ne doit jamais faire échouer
    l'appelant."""
    if not deal.target_revenue or deal.target_revenue <= 0:
        return None
    base_exit_mult = base_result.get("exit_multiple")
    if not base_exit_mult:
        return None

    sector_or_naf = deal.sector or ""
    calibrated_profile, calibration_result = await _resolve_calibration_and_profile(db, sector_or_naf)
    override_entry_ebitda = _resolve_override_ebitda(deal)

    is_small_cap = deal.target_revenue < SMALL_CAP_REVENUE_THRESHOLD
    override_leverage = SMALL_CAP_DEFAULT_LEVERAGE if is_small_cap else None

    downside_revenue = deal.target_revenue * (1 - DOWNSIDE_REVENUE_HAIRCUT_PCT)
    downside_exit_mult = max(0.1, base_exit_mult + DOWNSIDE_EXIT_MULTIPLE_DELTA)

    result = run_lbo_model(
        revenue=downside_revenue,
        sector_or_naf=sector_or_naf,
        calibrated_profile=calibrated_profile,
        override_entry_ebitda=override_entry_ebitda,
        override_leverage=override_leverage,
        override_exit_mult=downside_exit_mult,
    )
    _attach_calibration_and_provenance(
        result, deal, sector_or_naf, calibration_result, calibrated_profile, override_entry_ebitda,
    )

    assumptions = {
        "revenue": downside_revenue,
        "sector_or_naf": sector_or_naf,
        "sizing_tier": "indicative_bolt_on" if is_small_cap else "standalone",
        "sizing_note": SIZING_NOTE_INDICATIVE if is_small_cap else None,
        "use_sector_calibration": calibrated_profile is not None,
        "auto_generated": True,
        "auto_generated_reason": (
            f"P2 — cas baissier généré automatiquement : CA d'entrée -"
            f"{DOWNSIDE_REVENUE_HAIRCUT_PCT * 100:.0f}% et multiple de sortie "
            f"{DOWNSIDE_EXIT_MULTIPLE_DELTA:+.1f}x vs le base case du même deal — même "
            f"secteur, levier et calibrage que le base case, non revu par un humain."
        ),
        "downside_of_revenue": deal.target_revenue,
        "downside_revenue_haircut_pct": DOWNSIDE_REVENUE_HAIRCUT_PCT,
        "downside_exit_multiple_delta": DOWNSIDE_EXIT_MULTIPLE_DELTA,
    }

    scenario = await create_scenario(
        db, deal_id=deal.id, label=DOWNSIDE_CASE_LABEL,
        assumptions=assumptions, result=result,
    )
    logger.info(
        "[LBO downside auto] Deal {} — scénario #{} créé (IRR={}, MOIC={}).",
        deal.id, scenario.id, result.get("irr"), result.get("moic"),
    )
    return scenario
