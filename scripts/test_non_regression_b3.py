"""
test_non_regression_b3.py — Test de non-régression obligatoire (Tâche B.3, Étape 2).

Vérifie que la voie de qualification registre (D10) qualifie positivement les
5 sociétés de référence explicitement exigées par la tâche : DEKRA, Qualiconsult,
SGS France, Bureau Alpes Contrôles, BTP Consultants.

CA et SIREN réels, vérifiés (recherche-entreprises.api.gouv.fr, 2026-07-21).
URLs choisies pour leur contenu descriptif suffisant : SGS France en
particulier nécessite la page "/en/our-company" plutôt que la racine
sgs.com (page d'accueil dominée par navigation/actualités, insuffisamment
descriptive pour une évaluation LLM fiable — testé, cause documentée dans
sirene_sourcing_pipeline.py).

Usage :
    source .venv/bin/activate
    python -m scripts.test_non_regression_b3
"""
from __future__ import annotations

import asyncio
import sys

from loguru import logger

from api.services.ma_engine.sirene_sourcing_pipeline import _qualify_registry_candidate


REFERENCE_COMPANIES: list[dict] = [
    {
        "denomination": "DEKRA INDUSTRIAL", "siren": "433250834",
        "url": "https://www.dekra.fr",
        "finances": {"2024": {"ca": 267_280_605}},
    },
    {
        "denomination": "QUALICONSULT", "siren": "401449855",
        "url": "https://www.groupe-qualiconsult.fr",
        "finances": {"2024": {"ca": 109_035_051}},
    },
    {
        "denomination": "SGS FRANCE", "siren": "552031650",
        "url": "https://www.sgs.com/en/our-company",
        "finances": {"2024": {"ca": 191_967_957}},
    },
    {
        "denomination": "BUREAU ALPES CONTROLES", "siren": "351812698",
        "url": "https://www.alpes-controles.fr",
        "finances": {"2024": {"ca": 91_240_062}},
    },
    {
        "denomination": "BTP CONSULTANTS", "siren": "408422525",
        "url": "https://www.btp-consultants.fr",
        "finances": {"2022": {"ca": 61_078_515}},
    },
]


async def main() -> int:
    failures: list[str] = []

    for candidate in REFERENCE_COMPANIES:
        result, reason = await _qualify_registry_candidate(candidate)
        if result is None:
            failures.append(f"{candidate['denomination']} — REJETÉ ({reason})")
            logger.error("❌ ÉCHEC — {} rejeté : {}", candidate["denomination"], reason)
        else:
            logger.info(
                "✅ OK — {} [{}] LLM={} final={}",
                candidate["denomination"], result["target_type"],
                result["llm_score"], result["final_score"],
            )

    if failures:
        logger.error("=" * 60)
        logger.error("TEST DE NON-RÉGRESSION ÉCHOUÉ : {}", failures)
        return 1

    logger.info("=" * 60)
    logger.info("✅ TEST DE NON-RÉGRESSION RÉUSSI — 5/5 sociétés qualifiées.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
