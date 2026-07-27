"""
api.services.ma_engine — M&A Financial Engines & Sourcing Pipeline.

Modules :
  - valuation_engine     : Paper LBO standalone (5-year model)
  - buildup_engine       : Buy & Build / Multiple Arbitrage simulator
  - website_scraper      : Async multi-page crawler (httpx)
  - openai_analyzer      : Async NLP — business DNA extraction (AsyncOpenAI)
  - google_radar         : Async target discovery via Serper.dev
  - deep_researcher      : Async Deep Research / Pré-Due Diligence
  - financial_estimator  : Async financial sizing (API Gouv + LinkedIn OSINT)
  - similarity_scorer    : Hybrid TF-IDF + LLM scoring
  - sourcing_pipeline    : Grand orchestrator — end-to-end scan + DB persistence
  - ic_deck_generator    : IC deck PowerPoint generation (post-promotion — D42, seul export PPTX du produit)
  - batch_processor      : Async batch URL processing
  - exporter             : CSV / HTML export (BytesIO)

Usage (from routers):
    from api.services.ma_engine.valuation_engine import run_lbo_model
    from api.services.ma_engine.buildup_engine import calculate_buildup
    from api.services.ma_engine.sourcing_pipeline import run_full_sourcing_scan
    from api.services.ma_engine.ic_deck_generator import generate_ic_deck
    from api.services.ma_engine.batch_processor import process_url_batch
    from api.services.ma_engine.exporter import export_targets_csv, export_targets_html
"""

from api.services.ma_engine.valuation_engine import (
    run_lbo_model,
    calculate_valuation,
    generate_sensitivity_matrix,
    LBO_PROFILES,
    NAF_TO_PROFILE,
)
from api.services.ma_engine.buildup_engine import calculate_buildup
from api.services.ma_engine.sourcing_pipeline import run_full_sourcing_scan

__all__ = [
    # Engines
    "run_lbo_model",
    "calculate_valuation",
    "generate_sensitivity_matrix",
    "calculate_buildup",
    "LBO_PROFILES",
    "NAF_TO_PROFILE",
    # Pipeline
    "run_full_sourcing_scan",
]
