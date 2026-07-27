"""
seed_tic_universe.py — Reconstruction rejouable de l'univers de données
sectoriel "Test, Inspection, Certification (TIC) et ingénierie technique"
(Tâche B.1).

Ce script n'écrit AUCUNE donnée financière en dur. Il ne contient que :
  - une liste de tickers boursiers (comparables cotés, Étape 2),
  - une liste d'URLs de sociétés françaises réelles utilisées comme
    "seeds" du pipeline de sourcing OSINT (Étape 3).

Toute donnée (CA, EBITDA, effectifs, multiples, signaux OSINT...) est
produite EN DIRECT par les services existants de l'application au moment de
l'exécution :
  - api.services.comps_service.create_comp_set()  → yfinance + comps engine
  - api.services.ma_engine.sourcing_pipeline.run_full_sourcing_scan()
    → scraping + OpenAI + Serper (Google Radar) + scoring + estimation NAF

Si tu relances ce script, il est sûr de le faire : `create_comp_set` ré-ingère
les tickers déjà en base sans les dupliquer (upsert par ticker), et
`run_full_sourcing_scan` déduplique par URL (voir sourcing_service.py).

Prérequis (voir RUNBOOK.md) :
  - api/.env avec au minimum PE_OPENAI_API_KEY et PE_SERPER_API_KEY valides.
  - yfinance doit pouvoir joindre Yahoo Finance (v10/quoteSummary). Au moment
    de l'écriture de ce script (2026-07-20), Yahoo bloquait cet endpoint
    (HTTP 429 persistant depuis cette machine) — la phase Comps Engine a donc
    été écrite et testée dans sa mécanique, mais PAS validée de bout en bout
    avec des données réelles. Voir AI_MASTER_CONTEXT.md / rapport Tâche B.1.

Usage :
    source .venv/bin/activate
    python -m scripts.seed_tic_universe                # tout (comps + sourcing)
    python -m scripts.seed_tic_universe --comps-only
    python -m scripts.seed_tic_universe --sourcing-only
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger

from api.database import AsyncSessionLocal
from api.schemas.comps import CompSetCreate
from api.services.comps_service import create_comp_set
from api.services.ma_engine.sourcing_pipeline import run_full_sourcing_scan


# ============================================================
# Étape 2 — Univers de comparables cotés (TIC & Ingénierie technique)
# ============================================================
# Tickers vérifiés manuellement le 2026-07-20 (voir rapport Tâche B.1) :
# existence, place de cotation et statut (coté / délisté) confirmés par
# recherche web avant inclusion. Format Yahoo Finance (suffixe de place).
#
# EXCLUS et documentés (ne pas réintroduire sans revérifier) :
#   - Applus Services (ex-Bourse de Madrid) — délistée le 27/11/2024,
#     rachetée par Amber EquityCo (ex-Apollo).
#   - Ricardo plc (ex-LSE) — acquise par WSP Global, closing mars 2026,
#     délistée.
TIC_COMP_TICKERS: list[str] = [
    # -- TIC pur --
    "BVI.PA",   # Bureau Veritas (Euronext Paris)
    "SGSN.SW",  # SGS SA (SIX Swiss Exchange)
    "ERF.PA",   # Eurofins Scientific (Euronext Paris)
    "ITRK.L",   # Intertek Group (London Stock Exchange)
    "ALQ.AX",   # ALS Limited (ASX)
    "MG",       # Mistras Group (NYSE)
    "CLB",      # Core Laboratories (NYSE) — oilfield services, TIC adjacent
    # -- Ingénierie / services techniques --
    "ATE.PA",   # Alten (Euronext Paris)
    "ASY.PA",   # Assystem (Euronext Paris)
    "SPIE.PA",  # SPIE (Euronext Paris)
    "WSP.TO",   # WSP Global (Toronto Stock Exchange)
    "STN.TO",   # Stantec (Toronto Stock Exchange)
    "ATRL.TO",  # AtkinsRéalis (Toronto Stock Exchange)
    "J",        # Jacobs Solutions (NYSE)
]

TIC_COMPSET_NAME = "TIC & Ingénierie technique — Europe/Global"
TIC_COMPSET_DESCRIPTION = (
    "Comparables cotés pour la thèse buy-and-build TIC/ingénierie technique "
    "France-Europe (Tâche B.1). Tickers vérifiés manuellement le 2026-07-20."
)


async def seed_comps() -> None:
    logger.info("=" * 60)
    logger.info("ÉTAPE 2 — Création du CompSet '{}' ({} tickers)", TIC_COMPSET_NAME, len(TIC_COMP_TICKERS))
    logger.info("=" * 60)

    async with AsyncSessionLocal() as db:
        body = CompSetCreate(
            name=TIC_COMPSET_NAME,
            description=TIC_COMPSET_DESCRIPTION,
            tickers=TIC_COMP_TICKERS,
            base_year=2025,
        )
        try:
            comp_set, member_count = await create_comp_set(body, db)
            await db.commit()
            logger.info(
                "✅ CompSet créé : id={} — {}/{} tickers ingérés avec succès.",
                comp_set.id, member_count, len(TIC_COMP_TICKERS),
            )
            if member_count < len(TIC_COMP_TICKERS):
                logger.warning(
                    "⚠️ {} ticker(s) n'ont pas pu être ingérés (yfinance indisponible "
                    "ou ticker introuvable) — voir les logs ci-dessus pour le détail "
                    "par ticker.",
                    len(TIC_COMP_TICKERS) - member_count,
                )
        except Exception as exc:
            await db.rollback()
            logger.error("❌ Échec de la création du CompSet : {}", exc)


# ============================================================
# Étape 3 — Univers de cibles françaises (Sourcing OSINT)
# ============================================================
# URLs de sociétés françaises réelles du secteur TIC/ingénierie technique,
# identifiées manuellement le 2026-07-20 (recherche web, chiffre d'affaires
# vérifié quand disponible — voir rapport Tâche B.1). Utilisées comme
# "seeds" : le pipeline extrait l'ADN business de chaque seed puis
# DÉCOUVRE et score des cibles similaires via Google Radar — la seed
# elle-même n'est pas automatiquement ajoutée à sourced_targets (c'est un
# choix de conception du pipeline existant, non modifié ici).
#
# IMPORTANT : le pipeline appelle Serper.dev avec 5 requêtes par scan.
# Un compte Serper gratuit rejette les scans lancés en rafale trop proche
# (voir google_radar.py, SERPER_NUM_RESULTS corrigé à 10 en Tâche B.1).
# Ce script exécute donc les scans STRICTEMENT en séquence, avec un délai
# entre chaque, pour rester dans les clous d'un plan gratuit.
TIC_SOURCING_SEED_URLS: list[str] = [
    "https://www.alpes-controles.fr",      # Bureau de contrôle technique — CA 91M€ (2024, vérifié)
    "https://www.edeis.com",               # Bureau d'études ingénierie — CA 55.6M€ (2024, vérifié)
    "https://www.isgroupe.com",            # Institut de Soudure — CND, groupe ~100M€ (2021, vérifié)
    "https://www.ginger-cebtp.com",        # Laboratoire d'essais géotechnique/matériaux (Groupe GINGER)
    "https://ingebime.fr",                 # Bureau d'études structure
    "https://www.rincent.fr",              # Laboratoire indépendant BTP
    "https://www.lpgm-ingenierie.com",     # Laboratoire génie civil / géotechnique
    "https://www.mageo-fr.com",            # Laboratoire d'essais indépendant BTP
    "https://masterdiag.fr",               # Laboratoire indépendant BTP
    "https://lerm.fr",                     # Ingénierie des matériaux
    "https://www.groupe-qualiconsult.com", # Bureau de contrôle technique — CA ~203-220M€ (au-dessus de la thèse, testé pour comparaison)
    "https://www.cte-sa.com",              # Bureau d'études bâtiment / génie civil
]

SEED_DELAY_SECONDS = 15  # espacement entre scans, cf. limite Serper plan gratuit


async def seed_sourcing() -> None:
    logger.info("=" * 60)
    logger.info("ÉTAPE 3 — Sourcing OSINT séquentiel ({} seeds)", len(TIC_SOURCING_SEED_URLS))
    logger.info("=" * 60)

    for i, url in enumerate(TIC_SOURCING_SEED_URLS, start=1):
        logger.info("[{}/{}] Scan seed : {}", i, len(TIC_SOURCING_SEED_URLS), url)
        async with AsyncSessionLocal() as db:
            try:
                result = await run_full_sourcing_scan(db, url)
                await db.commit()
                logger.info("  → {} cible(s) sauvegardée(s).", result.get("targets_saved", "?"))
            except Exception as exc:
                await db.rollback()
                logger.error("  ❌ Échec du scan pour {} : {}", url, exc)

        if i < len(TIC_SOURCING_SEED_URLS):
            logger.info("  ⏳ Pause de {}s avant le prochain scan (quota Serper)…", SEED_DELAY_SECONDS)
            await asyncio.sleep(SEED_DELAY_SECONDS)


# ============================================================
# Entrée principale
# ============================================================

async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comps-only", action="store_true", help="N'exécuter que l'Étape 2 (comps cotés)")
    parser.add_argument("--sourcing-only", action="store_true", help="N'exécuter que l'Étape 3 (sourcing OSINT)")
    args = parser.parse_args()

    run_comps = not args.sourcing_only
    run_sourcing = not args.comps_only

    if run_comps:
        await seed_comps()
    if run_sourcing:
        await seed_sourcing()

    logger.info("=" * 60)
    logger.info("🏁 Reconstruction de l'univers TIC terminée.")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
