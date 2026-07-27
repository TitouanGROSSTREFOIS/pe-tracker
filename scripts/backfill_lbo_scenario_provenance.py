"""
Tâche Finalisation, Partie 4 (D46) — Backfill de `financial_provenance` sur
les scénarios LBO sauvegardés avant l'introduction de ce champ (D45).

Les 3 scénarios base-case existants (BTP Consultants, Ingebime, Bureau Alpes
Controles, tous créés le 22/07/2026) ont été générés avant que
`lbo_scenario_service._build_scenario_provenance` existe — leur
`result_json` n'a donc pas de clé `financial_provenance`, contrairement à
tout scénario généré depuis (voir promotion, `build_base_case_scenario`).

Ce script NE RECALCULE AUCUNE VALEUR DU MOTEUR LBO NI DU CALIBRAGE : il pose
uniquement `financial_provenance` sur les scénarios qui en sont dépourvus, à
partir des chiffres DÉJÀ stockés dans leur propre `result_json["calibration"]`
(snapshot figé au moment de la promotion) — jamais d'un recalcul en direct,
qui pourrait diverger du chiffre déjà affiché comme `entry_multiple`/
`ebitda_margin` si le CompSet a changé depuis. Le format produit est
strictement celui de `_build_scenario_provenance` (mêmes clés, même
distinction calibré/générique, provenance ESTIMATE pour un multiple/marge
dérivé — cohérente avec la correction D46 Partie 1 de
`sector_calibration.py`), pour que scénarios anciens et nouveaux soient
indiscernables côté frontend.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from api.database import AsyncSessionLocal, init_db
from api.models.deal import Deal
from api.models.lbo_scenario import LBOScenario
from api.schemas.provenance import DataProvenance, FieldProvenance, field_provenance_from_json
from api.services.ma_engine.valuation_engine import resolve_profile


def _build_provenance_from_snapshot(deal: Deal, calib: dict) -> dict[str, dict]:
    """Équivalent de lbo_scenario_service._build_scenario_provenance, mais
    lisant les chiffres de calibrage déjà figés dans result_json["calibration"]
    au lieu d'appeler compute_sector_calibration en direct — pour ne jamais
    produire un texte de provenance qui décrit un chiffre différent de celui
    réellement stocké sur le scénario (risque si le CompSet a évolué depuis)."""
    prov: dict[str, dict] = {}

    deal_prov = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
    revenue_prov = field_provenance_from_json(deal_prov, "target_revenue")
    prov["revenue"] = (
        revenue_prov.model_dump(mode="json") if revenue_prov
        else FieldProvenance(provenance=DataProvenance.UNKNOWN, reference="Deal revenue provenance not tracked").model_dump(mode="json")
    )

    if calib.get("applicable") and calib.get("sufficient"):
        sample_label = f"n={calib.get('sample_size')}, FY{'-'.join(str(y) for y in sorted(set(calib.get('fiscal_years') or [])))}"
        discount_pct = (calib.get("size_illiquidity_discount") or 0) * 100
        prov["entry_multiple"] = FieldProvenance(
            provenance=DataProvenance.ESTIMATE,
            reference=(
                f"Calculated: {calib['median_ev_ebitda']:.2f}x listed comparables median "
                f"(CompSet '{calib.get('comp_set_name')}', {sample_label}) "
                f"− {discount_pct:.0f}% size & illiquidity discount, French mid-market "
                f"= {calib['derived_entry_multiple']:.2f}x"
            ),
        ).model_dump(mode="json")
        prov["ebitda_margin"] = FieldProvenance(
            provenance=DataProvenance.ESTIMATE,
            reference=(
                f"Median EBITDA margin of listed comparables (CompSet '{calib.get('comp_set_name')}', "
                f"{sample_label}) = {calib['median_ebitda_margin'] * 100:.2f}%. Listed comparables in "
                f"this CompSet are global TIC/engineering leaders — their EBITDA margin is "
                f"structurally higher than a French mid-market SME/ETI. Used as a DEFAULT value "
                f"only, always editable."
            ),
        ).model_dump(mode="json")
    else:
        generic_name = resolve_profile(deal.sector or "").name
        generic_ref = f"Generic sector profile assumption ({generic_name}) — not derived from real comparables"
        prov["entry_multiple"] = FieldProvenance(provenance=DataProvenance.ESTIMATE, reference=generic_ref).model_dump(mode="json")
        prov["ebitda_margin"] = FieldProvenance(provenance=DataProvenance.ESTIMATE, reference=generic_ref).model_dump(mode="json")

    return prov


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(LBOScenario))
        scenarios = list(result.scalars().all())
        print(f"{len(scenarios)} scenario(s) in DB.")

        for scenario in scenarios:
            result_json = scenario.result_json or {}
            if "financial_provenance" in result_json:
                print(f"scenario #{scenario.id} (deal #{scenario.deal_id}): already has financial_provenance — skipped.")
                continue

            deal = await db.get(Deal, scenario.deal_id)
            if deal is None:
                print(f"scenario #{scenario.id}: deal #{scenario.deal_id} not found — skipped.")
                continue

            calib = result_json.get("calibration") or {}
            provenance = _build_provenance_from_snapshot(deal, calib)
            # `result_json` est une colonne JSON brute (pas MutableDict) :
            # muter le dict en place puis le raffecter à lui-même ne déclenche
            # PAS le suivi de modification de SQLAlchemy (constaté : le premier
            # essai de ce script n'a rien persisté). Un nouvel objet dict force
            # la détection du changement.
            scenario.result_json = {**result_json, "financial_provenance": provenance}
            print(f"scenario #{scenario.id} ({deal.target_name}): financial_provenance backfilled.")

        await db.commit()


asyncio.run(main())
