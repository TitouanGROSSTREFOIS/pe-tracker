"""
purge_offthesis_b2.py — Purge et archivage des données hors thèse (Tâche B.2, Étape 1).

Exécuté UNE FOIS le 2026-07-21. Conservé pour traçabilité et rejouabilité en cas
de restauration/re-seed, PAS destiné à être relancé en routine (il échouera
silencieusement — via des DELETE à 0 ligne — si les IDs ne matchent plus).

Actions :
    - SUPPRIME  : les 13 companies mega-cap US/globales (+ leurs financials et
                  financial_ratios, cascade ORM), les 12 deals large-cap non-TIC
                  (+ leurs deal_activities, cascade ORM), les 4 comp_sets
                  mega-cap (+ leurs comp_set_members, cascade ORM).
    - SUPPRIME  : les 2 sourced_targets de test (id=1 "Test A", id=17
                  "Projet Optimus").
    - ARCHIVE (status="Archived", PAS de suppression) : les 14 sourced_targets
                  du cluster "CF Compagnie Fiduciaire" (cabinets d'expertise
                  comptable / conseil patrimonial), via le service
                  update_target existant.
                  NOTE : pipeline_stage reste "Passed" (pas "Archived") — le
                  schema Pydantic PipelineStage (api/schemas/sourcing.py) est
                  un Literal fermé qui ne contient pas cette valeur, et
                  l'élargir sans validation est hors périmètre autorisé pour
                  cette tâche (modification du modèle/schéma SourcedTarget
                  explicitement interdite sans validation). "Passed" est la
                  valeur existante la plus proche sémantiquement. Voir
                  RAPPORT B.2 § PROPOSITIONS DE SCHÉMA pour la proposition
                  d'ajouter une vraie valeur "Archived" au Literal.
    - NE TOUCHE PAS : sourced_target id=2 "Cleaq" — hors thèse mais hors du
                  périmètre exact "cabinets d'expertise comptable" décrit dans
                  la tâche ; laissé en l'état par discipline de périmètre.
    - NE TOUCHE PAS : portfolio_companies (Cecca, Gt Expertise) et leurs
                  monthly_kpis — CONSERVÉS tels quels (ils référencent les
                  sourced_targets archivés id=3/id=4, d'où l'archivage plutôt
                  que la suppression : une suppression aurait cassé cette
                  relation).

Sauvegarde préalable obligatoire (faite hors de ce script, voir RAPPORT B.2) :
    ~/pe_tracker_db_backups/pe_intelligence_pre_B2_purge_<timestamp>.db
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from loguru import logger

from api.database import AsyncSessionLocal
from api.models.company import Company
from api.models.deal import Deal
from api.models.comps import CompSet
from api.models.sourcing import SourcedTarget
from api.schemas.sourcing import SourcedTargetUpdate
from api.services.sourcing_service import update_target


MEGACAP_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "JPM", "GS",
    "JNJ", "UNH", "TTE", "MC.PA", "BRK-B",
]

MEGACAP_DEAL_PAIRS = [
    ("Broadcom Inc.", "VMware, Inc."),
    ("Exxon Mobil Corporation", "Pioneer Natural Resources"),
    ("Capital One Financial", "Discover Financial Services"),
    ("Mars, Incorporated", "Kellanova"),
    ("Synopsys, Inc.", "Ansys, Inc."),
    ("Johnson & Johnson", "Intra-Cellular Therapies"),
    ("Bain Capital", "Envestnet, Inc."),
    ("Thoma Bravo", "Darktrace plc"),
    ("Blackstone Inc.", "Tropical Smoothie Cafe"),
    ("Hellman & Friedman", "Worldpay"),
    ("Reddit, Inc.", None),
    ("Astera Labs", None),
]

MEGACAP_COMPSET_NAMES = ["US Tech Mega Cap", "Mega Tech"]

TEST_TARGET_IDS = [1, 17]  # "Test A", "Projet Optimus"

ARCHIVE_TARGET_IDS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]


async def purge() -> None:
    async with AsyncSessionLocal() as db:
        # ── 1. Comp sets mega-cap (cascade → comp_set_members) ──
        result = await db.execute(
            select(CompSet).where(CompSet.name.in_(MEGACAP_COMPSET_NAMES))
        )
        comp_sets = list(result.scalars().all())
        logger.info("CompSets à supprimer : {}", [(c.id, c.name) for c in comp_sets])
        for cs in comp_sets:
            await db.delete(cs)

        # ── 2. Deals mega-cap (cascade → deal_activities) ──
        result = await db.execute(select(Deal))
        all_deals = list(result.scalars().all())
        deals_to_delete = [
            d for d in all_deals
            if (d.acquirer_name, d.target_name) in MEGACAP_DEAL_PAIRS
        ]
        logger.info(
            "Deals à supprimer : {}",
            [(d.id, d.acquirer_name, d.target_name) for d in deals_to_delete],
        )
        if len(deals_to_delete) != len(MEGACAP_DEAL_PAIRS):
            logger.error(
                "❌ Mismatch : {} deals attendus, {} trouvés. Abandon (rollback).",
                len(MEGACAP_DEAL_PAIRS), len(deals_to_delete),
            )
            await db.rollback()
            return
        for d in deals_to_delete:
            await db.delete(d)

        # ── 3. Companies mega-cap (cascade → financials, financial_ratios) ──
        result = await db.execute(
            select(Company).where(Company.ticker.in_(MEGACAP_TICKERS))
        )
        companies = list(result.scalars().all())
        logger.info("Companies à supprimer : {}", [(c.id, c.ticker) for c in companies])
        if len(companies) != len(MEGACAP_TICKERS):
            logger.error(
                "❌ Mismatch : {} companies attendues, {} trouvées. Abandon (rollback).",
                len(MEGACAP_TICKERS), len(companies),
            )
            await db.rollback()
            return
        for c in companies:
            await db.delete(c)

        # ── 4. Sourced targets de test → suppression ──
        for tid in TEST_TARGET_IDS:
            target = await db.get(SourcedTarget, tid)
            if target is None:
                logger.warning("  ⚠️ SourcedTarget id={} introuvable (déjà supprimé ?).", tid)
                continue
            logger.info("  🗑️ Suppression sourced_target id={} '{}'", tid, target.company_name)
            await db.delete(target)

        await db.commit()
        logger.info("✅ Phase suppression commit.")

    # ── 5. Archivage (pas de suppression) via le service update_target ──
    async with AsyncSessionLocal() as db:
        archived = 0
        for tid in ARCHIVE_TARGET_IDS:
            target = await update_target(
                db, tid,
                SourcedTargetUpdate(status="Archived", pipeline_stage="Passed"),
            )
            if target is None:
                logger.warning("  ⚠️ SourcedTarget id={} introuvable pour archivage.", tid)
                continue
            logger.info("  📦 Archivé : id={} '{}'", tid, target.company_name)
            archived += 1
        await db.commit()
        logger.info("✅ {} cible(s) archivée(s) (status=Archived).", archived)


if __name__ == "__main__":
    asyncio.run(purge())
