"""
Tâche "Unifier l'EBITDA estimé entre le deal et le LBO" — Étape 3.

Les 3 deals canoniques (BTP Consultants, Ingebime, Bureau Alpes Controles) ont
été promus AVANT que `lbo_scenario_service.sync_deal_ebitda_with_scenario`
existe : leur `Deal.target_ebitda` porte encore la marge sectorielle générique
utilisée par le scan de sourcing (similarity_scorer.py), alors que leur
scénario LBO de référence (déjà sauvegardé) a recalculé sa propre entry_ebitda
avec la marge calibrée du CompSet réel quand le secteur s'y prête, sinon la
même marge générique.

Ce script NE RECALCULE RIEN : il réutilise la marge/entry_ebitda déjà figée
dans `LBOScenario.result_json` de chaque deal (jamais un nouvel appel à
`compute_sector_calibration`/`run_lbo_model`, qui pourrait diverger du chiffre
déjà affiché si le CompSet a changé depuis) et réaligne `Deal.target_ebitda`
dessus, via la même fonction que le chemin live (`promote` -> `build_base_case_
scenario`) utilise désormais pour tout NOUVEAU deal.

Protège explicitement tout EBITDA réel (DOCUMENT/REGISTRY) — aucun des 3
deals canoniques n'en a un à ce jour (vérifié : les 3 sont ESTIMATE), mais la
garde reste active si ce script est rejoué plus tard sur d'autres deals.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import AsyncSessionLocal, init_db
from api.models.deal import Deal
from api.services import lbo_scenario_service

CANONICAL_DEAL_IDS = (2, 3, 4)


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        for deal_id in CANONICAL_DEAL_IDS:
            deal = await db.get(Deal, deal_id)
            if deal is None:
                print(f"deal #{deal_id}: not found — skipped.")
                continue

            scenario = await lbo_scenario_service.get_reference_scenario(db, deal_id)
            if scenario is None:
                print(f"deal #{deal_id} ({deal.target_name}): no reference LBO scenario — skipped.")
                continue

            result = scenario.result_json or {}
            before_ebitda = deal.target_ebitda
            new_ebitda = result.get("entry_ebitda")
            reference = lbo_scenario_service.ebitda_margin_reference_from_result(result)

            changed = lbo_scenario_service.sync_deal_ebitda_with_scenario(deal, new_ebitda, reference)
            if changed:
                print(
                    f"deal #{deal_id} ({deal.target_name}): target_ebitda {before_ebitda:,.2f} "
                    f"-> {deal.target_ebitda:,.2f} (scenario '{scenario.label}')."
                )
            else:
                print(
                    f"deal #{deal_id} ({deal.target_name}): no change "
                    f"(already aligned at {before_ebitda:,.2f}, or a real EBITDA was protected)."
                )

        await db.commit()


asyncio.run(main())
