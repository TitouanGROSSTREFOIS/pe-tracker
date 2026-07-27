"""
batch_processor.py — Traitement par lots async d'URLs cibles M&A.

Accepte une liste d'URLs, lance un scan sourcing complet pour chacune
via le pipeline existant (run_full_sourcing_scan).

Point d'entrée :
    async def process_url_batch(urls, min_revenue, max_revenue) -> dict

Patterns clés :
  - Session DB auto-gérée (AsyncSessionLocal) pour chaque URL
  - Logging détaillé avec loguru
  - Tolérance aux erreurs individuelles (une URL qui plante ne casse pas le batch)

Usage depuis un routeur FastAPI (BackgroundTasks) :
    from api.services.ma_engine.batch_processor import process_url_batch
    background_tasks.add_task(process_url_batch, urls)
"""

from __future__ import annotations

from loguru import logger

from api.database import AsyncSessionLocal
from api.services.ma_engine.sourcing_pipeline import run_full_sourcing_scan


# ============================================================
# Point d'entrée principal
# ============================================================

async def process_url_batch(
    urls: list[str],
    *,
    min_revenue: int | None = None,
    max_revenue: int | None = None,
) -> dict:
    """Lance un scan sourcing complet pour chaque URL de la liste.

    Chaque URL est traitée séquentiellement avec sa propre session DB
    (requise par le pattern BackgroundTasks de FastAPI).

    Args:
        urls:        Liste d'URLs de plateformes à scanner.
        min_revenue: Borne basse filtre LBO en € (optionnel).
        max_revenue: Borne haute filtre LBO en € (optionnel).

    Returns:
        Dict récapitulatif :
            - total_urls (int)
            - processed (int)
            - failed (int)
            - results (list[dict])  — un résumé par URL
            - errors (list[dict])   — URLs en erreur
    """
    total = len(urls)
    logger.info("=" * 60)
    logger.info("🔄 BATCH PROCESSOR — {} URLs à traiter", total)
    logger.info("=" * 60)

    results: list[dict] = []
    errors: list[dict] = []
    processed = 0

    for idx, url in enumerate(urls, start=1):
        url = url.strip()
        if not url:
            continue

        logger.info("─" * 40)
        logger.info("📡 [{}/{}] Traitement de : {}", idx, total, url)

        try:
            # Session auto-gérée — même pattern que _run_scan_background
            async with AsyncSessionLocal() as db:
                scan_result = await run_full_sourcing_scan(
                    db,
                    url,
                    min_revenue=min_revenue,
                    max_revenue=max_revenue,
                )
                results.append({
                    "url": url,
                    "status": "success",
                    "targets_saved": scan_result.get("targets_saved", 0),
                    "targets_scored": scan_result.get("targets_scored", 0),
                    "error": scan_result.get("error"),
                })
                processed += 1

        except Exception as e:
            logger.error("❌ Échec pour {} : {}", url, e)
            errors.append({"url": url, "error": str(e)})

    # ── Bilan ─────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("🏁 BATCH TERMINÉ — {}/{} URLs traitées, {} erreurs",
                processed, total, len(errors))
    logger.info("=" * 60)

    return {
        "total_urls": total,
        "processed": processed,
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }
