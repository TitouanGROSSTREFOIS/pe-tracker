"""
Tâche B.6, Étape 5 — Reprise rétrospective de la provenance des données
financières déjà en base (D18).

Portée : uniquement les `Deal` existants (le modèle `Company`/`Financial` du
Comps Engine — "données de marché des 14 comparables" — n'est PAS traité ici :
"Comps Engine" est explicitement hors périmètre autorisé pour cette tâche.
Voir RAPPORT SPRINT B.6 pour la question bloquante correspondante.

État constaté avant exécution (vérifié) :
  - deal id=1 "BTP Consultants" : aucune donnée financière (target_revenue/
    target_ebitda/enterprise_value tous NULL) — rien à qualifier.
  - deal id=2 "BTP CONSULTANTS" : créé par promote_target_to_deal() AVANT
    l'ajout du renseignement automatique de provenance (Tâche B.6) — porte
    des données financières réelles sans aucune provenance attachée.

Ce script est un correctif ponctuel, pas un mécanisme permanent : le
renseignement automatique (Étape 2) couvre déjà tous les nouveaux deals.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from api.database import AsyncSessionLocal, init_db
from api.models.deal import Deal
from api.models.sourcing import SourcedTarget
from api.schemas.provenance import DataProvenance, FieldProvenance
from api.services.deals_service import compute_deal_multiples
from api.services.sourcing_service import _fetch_registry_exercise_year, _ESTIMATE_METHOD_REF


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Deal))
        deals = list(result.scalars().all())

        for deal in deals:
            has_any_financial = any([deal.target_revenue, deal.target_ebitda, deal.enterprise_value])
            if not has_any_financial:
                print(f"Deal #{deal.id} ({deal.target_name}) : aucune donnée financière — rien à qualifier.")
                continue

            if deal.financial_provenance:
                print(f"Deal #{deal.id} ({deal.target_name}) : provenance déjà renseignée — inchangé.")
                continue

            target: SourcedTarget | None = None
            if deal.sourced_target_id:
                target = await db.get(SourcedTarget, deal.sourced_target_id)

            provenance: dict[str, dict] = {}

            if deal.target_revenue is not None:
                if target and target.source == "registry":
                    as_of = await _fetch_registry_exercise_year(target.siren) if target.siren else None
                    provenance["target_revenue"] = FieldProvenance(
                        provenance=DataProvenance.REGISTRY,
                        as_of=as_of,
                        reference="Sirene / recherche-entreprises.api.gouv.fr"
                                  + (f", SIREN {target.siren}" if target.siren else ""),
                    ).model_dump(mode="json")
                elif target and target.source == "google_radar":
                    provenance["target_revenue"] = FieldProvenance(
                        provenance=DataProvenance.ESTIMATE,
                        reference="OSINT waterfall (see financial_estimator.py) — exact method not tracked at source.",
                    ).model_dump(mode="json")
                else:
                    provenance["target_revenue"] = FieldProvenance(
                        provenance=DataProvenance.UNKNOWN,
                        reference="Deal predates automatic provenance tracking (Tâche B.6) and has no "
                                  "linked sourcing target from which to determine the exact origin.",
                    ).model_dump(mode="json")

            if deal.target_ebitda is not None:
                provenance["target_ebitda"] = FieldProvenance(
                    provenance=DataProvenance.ESTIMATE, reference=_ESTIMATE_METHOD_REF,
                ).model_dump(mode="json")

            if deal.enterprise_value is not None:
                provenance["enterprise_value"] = FieldProvenance(
                    provenance=DataProvenance.ESTIMATE, reference=_ESTIMATE_METHOD_REF,
                ).model_dump(mode="json")

            deal.financial_provenance = provenance
            compute_deal_multiples(deal)  # recalcule aussi la provenance des multiples
            print(f"Deal #{deal.id} ({deal.target_name}) : provenance rétroactivement renseignée.")
            print(json.dumps(deal.financial_provenance, indent=2, ensure_ascii=False))

        await db.commit()


asyncio.run(main())
