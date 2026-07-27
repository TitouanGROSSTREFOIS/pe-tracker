"""
sourcing_pipeline.py — Chef d'orchestre async du pipeline M&A Deal Sourcing.

Assemble toutes les briques de la chaîne OSINT → NLP → Scoring → LBO
et persiste les résultats en base via le CRUD sourcing_service.

Pipeline complet :
    1. Scraper le site de la plateforme (extract_text_from_url).
    2. Extraire l'ADN business via GPT-4o-mini (extract_company_dna).
    3. Trouver des cibles via Google / Serper (find_potential_targets).
    4. Scorer les cibles — TF-IDF + estimation + Deep Research + LLM (rank_targets).
    5. Sauvegarder chaque cible validée → sourced_targets (sourcing_service.create_target).

Point d'entrée unique :
    async def run_full_sourcing_scan(db, platform_url) -> dict

Usage depuis un routeur FastAPI :
    from api.services.ma_engine.sourcing_pipeline import run_full_sourcing_scan
    result = await run_full_sourcing_scan(db, "https://www.qonto.com")
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from api.schemas.sourcing import SourcedTargetCreate
from api.services.sourcing_service import create_target, get_target_by_url

# ── Pipeline bricks ──
from api.services.ma_engine.website_scraper import extract_text_from_url
from api.services.ma_engine.openai_analyzer import extract_company_dna
from api.services.ma_engine.google_radar import find_potential_targets, _bare_hostname
from api.services.ma_engine.similarity_scorer import rank_targets


# ============================================================
# Mapping — Scorer result dict → Pydantic SourcedTargetCreate
# ============================================================

def _map_to_schema(scored: dict, company_dna: dict) -> SourcedTargetCreate:
    """Convertit un dict de scoring en SourcedTargetCreate pour le CRUD.

    Le mapping couvre les champs d'identification, de financials estimés,
    les signaux OSINT, et les métriques LBO.
    """
    # Résoudre le nom : scorer peut avoir target_name, sinon URL
    name = scored.get("target_name") or scored.get("url", "Inconnu")

    # Convertir les champs list/string en list[str] propres
    growth_raw = scored.get("growth_signals", "")
    red_raw = scored.get("red_flags", "")
    competitors_raw = scored.get("competitors", [])

    growth_list = (
        growth_raw if isinstance(growth_raw, list)
        else [growth_raw] if growth_raw and growth_raw != "N/A" else []
    )
    red_list = (
        red_raw if isinstance(red_raw, list)
        else [red_raw] if red_raw and red_raw != "N/A" else []
    )
    competitors_list = (
        competitors_raw if isinstance(competitors_raw, list) else []
    )

    # Keywords depuis l'ADN de la plateforme (contexte)
    keywords = company_dna.get("search_keywords", [])

    # Projections LBO → dict pour la colonne JSON
    projections = scored.get("lbo_projections", [])
    lbo_proj_dict = {"years": projections} if projections else None

    return SourcedTargetCreate(
        company_name=name,
        url=scored["url"],
        business_summary=scored.get("justification", ""),
        keywords=keywords if keywords else None,
        score=scored.get("final_score"),

        # Financials estimés
        revenue_estimate=scored.get("estimated_revenue") or None,
        ebitda_estimate=scored.get("ebitda") or None,
        enterprise_value=scored.get("ev") or None,

        # OSINT signals
        growth_signals=growth_list if growth_list else None,
        red_flags=red_list if red_list else None,
        competitors=competitors_list if competitors_list else None,

        # LBO quick-screen
        lbo_irr=scored.get("irr") or None,
        lbo_moic=scored.get("moic") or None,
        entry_multiple=scored.get("entry_multiple") or None,
        lbo_projections=lbo_proj_dict,

        # Pipeline
        status="Watchlist",

        # D47 (Tâche Finalisation, Partie C) : jamais renseigné jusqu'ici —
        # toutes les cibles issues de ce pipeline (scan unique ou batch CSV,
        # process_url_batch réutilise cette même fonction) restaient
        # `source=NULL`, indiscernables d'une origine "manuelle" ou
        # indéterminée. La voie registre (sirene_sourcing_pipeline.py) posait
        # déjà `source="registry"` correctement — seule cette voie manquait.
        source="google_radar",
    )


# ============================================================
# Pipeline principal
# ============================================================

async def run_full_sourcing_scan(
    db: AsyncSession,
    platform_url: str,
    *,
    min_revenue: int | None = None,
    max_revenue: int | None = None,
) -> dict:
    """Exécute un scan M&A complet : OSINT → NLP → Scoring → LBO → DB.

    Args:
        db:           Session SQLAlchemy async (injectée par Depends).
        platform_url: URL du site de la plateforme (ex: https://www.qonto.com).
        min_revenue:  Borne basse filtre LBO en € (optionnel).
        max_revenue:  Borne haute filtre LBO en € (optionnel).

    Returns:
        Dict récapitulatif :
            - platform_url (str)
            - company_dna (dict)
            - targets_found (int)  — nombre d'URLs Google Radar
            - targets_scored (int) — nombre de cibles après scoring
            - targets_saved (int)  — nombre de cibles insérées en DB
            - targets_skipped (int) — nombre de doublons (URL déjà en base)
            - results (list[dict]) — résumé de chaque cible sauvegardée
    """
    logger.info("=" * 60)
    logger.info("🚀 SOURCING PIPELINE — Démarrage pour {}", platform_url)
    logger.info("=" * 60)

    # Vérification upfront des clés API
    from api.config import get_settings
    _s = get_settings()
    if not _s.openai_api_key:
        logger.error("❌ PE_OPENAI_API_KEY est VIDE — le pipeline va échouer sur l'étape NLP.")
    else:
        logger.info("  🔑 OpenAI key OK ({}…)", _s.openai_api_key[:12])
    if not _s.serper_api_key:
        logger.warning("⚠️  PE_SERPER_API_KEY est VIDE — Google Radar sera désactivé.")
    else:
        logger.info("  🔑 Serper key OK ({}…)", _s.serper_api_key[:8])

    try:
        # ── 1. Scraping du site plateforme ───────────────────────
        logger.info("📄 Étape 1/5 — Scraping de la plateforme…")
        platform_text = await extract_text_from_url(platform_url)

        if not platform_text or len(platform_text.strip()) < 200:
            logger.error("❌ Contenu de la plateforme insuffisant. Abandon.")
            return {
                "platform_url": platform_url,
                "company_dna": {},
                "targets_found": 0,
                "targets_scored": 0,
                "targets_saved": 0,
                "targets_skipped": 0,
                "results": [],
                "error": "Contenu plateforme insuffisant",
            }

        logger.info("  ✅ {} caractères extraits du site plateforme.", len(platform_text))

        # ── 2. Extraction de l'ADN business (GPT-4o-mini) ───────
        logger.info("🧬 Étape 2/5 — Extraction de l'ADN business via LLM…")
        company_dna = await extract_company_dna(platform_text)

        if not company_dna or not company_dna.get("company_name"):
            logger.error("❌ Impossible d'extraire l'ADN. Abandon.")
            return {
                "platform_url": platform_url,
                "company_dna": company_dna or {},
                "targets_found": 0,
                "targets_scored": 0,
                "targets_saved": 0,
                "targets_skipped": 0,
                "results": [],
                "error": "Extraction ADN échouée",
            }

        logger.info("  ✅ ADN extrait : {} — {}", company_dna["company_name"],
                     company_dna.get("sector", "N/A"))

        # ── 3. Découverte de cibles (Google Radar / Serper) ──────
        logger.info("🔎 Étape 3/5 — Recherche de cibles via Google Radar…")
        target_urls = await find_potential_targets(company_dna, platform_url)

        if not target_urls:
            logger.warning("⚠️ Aucune cible trouvée par le Google Radar.")
            return {
                "platform_url": platform_url,
                "company_dna": company_dna,
                "targets_found": 0,
                "targets_scored": 0,
                "targets_saved": 0,
                "targets_skipped": 0,
                "results": [],
            }

        logger.info("  ✅ {} URLs candidates identifiées.", len(target_urls))

        # ── 4. Scoring hybride (TF-IDF + Estimation + Deep Research + LLM) ──
        logger.info("📊 Étape 4/5 — Scoring hybride des {} cibles…", len(target_urls))
        scored_targets = await rank_targets(
            platform_text=platform_text,
            target_urls=target_urls,
            company_dna=company_dna,
            min_revenue=min_revenue,
            max_revenue=max_revenue,
        )

        if not scored_targets:
            logger.warning("⚠️ Aucune cible n'a passé le scoring.")
            return {
                "platform_url": platform_url,
                "company_dna": company_dna,
                "targets_found": len(target_urls),
                "targets_scored": 0,
                "targets_saved": 0,
                "targets_skipped": 0,
                "results": [],
            }

        logger.info("  ✅ {} cibles retenues après scoring.", len(scored_targets))

        # ── 5. Persistence en DB via sourcing_service CRUD ───────
        logger.info("💾 Étape 5/5 — Sauvegarde des cibles en base…")

        saved_count = 0
        skipped_count = 0
        saved_results: list[dict] = []
        platform_hostname = _bare_hostname(platform_url)

        for scored in scored_targets:
            url = scored["url"]

            # D47 (Tâche Finalisation, Partie A) : garde-fou de second niveau —
            # le filtrage par hostname dans google_radar.py exclut déjà la
            # plateforme scannée de ses propres résultats (corrigé ici même,
            # l'ancien filtre par sous-chaîne de nom échouait silencieusement
            # sur les noms à espaces, ex. "Groupe Qualiconsult"). Ce second
            # contrôle, juste avant la persistance, garantit qu'aucune
            # régression future dans le radar ne peut faire réapparaître le
            # seed comme "cible découverte" — jamais compté ni sauvegardé.
            if platform_hostname and _bare_hostname(url) == platform_hostname:
                # Ni compté dans saved_count ni dans skipped_count ("doublon")
                # — ce n'est ni une cible sauvegardée, ni une cible déjà en
                # base, juste le seed lui-même. Un compteur à part éviterait
                # de fausser le "{skipped} déjà existants" du bandeau de scan.
                logger.info("  ⏭️ SKIP (c'est la plateforme scannée elle-même) — {}.", url)
                continue

            # Déduplication : vérifier si l'URL existe déjà
            existing = await get_target_by_url(db, url)
            if existing:
                logger.info("  ⏭️ SKIP (doublon) — {} déjà en base (id={}).",
                             url, existing.id)
                skipped_count += 1
                continue

            # Mapper vers le schema Pydantic
            target_create = _map_to_schema(scored, company_dna)

            try:
                target = await create_target(db, target_create)
                await db.commit()
                saved_count += 1

                logger.info("  💾 Sauvegardé : {} (id={}, score={:.1f})",
                             target.company_name, target.id, target.score or 0)

                saved_results.append({
                    "id": target.id,
                    "company_name": target.company_name,
                    "url": target.url,
                    "score": target.score,
                    "revenue_estimate": target.revenue_estimate,
                    "lbo_irr": target.lbo_irr,
                    "lbo_moic": target.lbo_moic,
                    "status": target.status,
                })

            except Exception as e:
                logger.error("  ❌ Erreur sauvegarde {} : {}", url, e)
                await db.rollback()

        # ── Résumé final ─────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("🏁 PIPELINE TERMINÉ — {}", platform_url)
        logger.info("  Plateforme  : {} ({})", company_dna["company_name"],
                     company_dna.get("sector", "N/A"))
        logger.info("  URLs trouvées  : {}", len(target_urls))
        logger.info("  Cibles scorées : {}", len(scored_targets))
        logger.info("  Sauvegardées   : {}", saved_count)
        logger.info("  Doublons skip  : {}", skipped_count)
        logger.info("=" * 60)

        return {
            "platform_url": platform_url,
            "company_dna": company_dna,
            "targets_found": len(target_urls),
            "targets_scored": len(scored_targets),
            "targets_saved": saved_count,
            "targets_skipped": skipped_count,
            "results": saved_results,
        }

    except Exception as exc:
        import traceback
        logger.error("💥 PIPELINE CRASH — {}", platform_url)
        logger.error(traceback.format_exc())
        return {
            "platform_url": platform_url,
            "company_dna": {},
            "targets_found": 0,
            "targets_scored": 0,
            "targets_saved": 0,
            "targets_skipped": 0,
            "results": [],
            "error": str(exc),
        }
