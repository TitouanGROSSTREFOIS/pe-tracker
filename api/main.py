"""
PE Intelligence Platform — FastAPI Application

Capital IQ / PitchBook-style backend for M&A analysis,
private equity, and corporate finance.

Modules:
  • Company Intelligence   /company, /companies
  • Screening Engine       /screener
  • Trading Comps          /comps
  • M&A / Deal Database    /deals
  • Analytics & Valuation  /analytics
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.config import get_settings
from api.database import init_db

# ── Routers ──────────────────────────────────
from api.routers.company import router as company_router
from api.routers.screener import router as screener_router
from api.routers.comps import router as comps_router
from api.routers.deals import router as deals_router
from api.routers.analytics import router as analytics_router
from api.routers.sourcing import router as sourcing_router
from api.routers.documents import router as documents_router
from api.routers.lbo import router as lbo_router
from api.routers.portfolio import router as portfolio_router

settings = get_settings()


# ── Lifespan (startup / shutdown) ────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting PE Intelligence Platform…")
    await init_db()
    logger.info("✅ Database initialised")

    # ── Validate API keys at startup ──
    _s = get_settings()
    if _s.openai_api_key and len(_s.openai_api_key) > 10:
        logger.info("🔑 PE_OPENAI_API_KEY chargée ({}…)", _s.openai_api_key[:12])
    else:
        logger.warning("⚠️  PE_OPENAI_API_KEY manquante ou vide — le scan OSINT ne fonctionnera PAS")
    if _s.serper_api_key and len(_s.serper_api_key) > 5:
        logger.info("🔑 PE_SERPER_API_KEY chargée ({}…)", _s.serper_api_key[:8])
    else:
        logger.warning("⚠️  PE_SERPER_API_KEY manquante ou vide — Google Radar désactivé")
    logger.info("📂 env_file résolu : {}", _s.model_config.get('env_file', 'N/A'))

    yield
    logger.info("👋 Shutting down")


# ── Application ─────────────────────────────
app = FastAPI(
    title="PE Intelligence Platform",
    description=(
        "Capital IQ / PitchBook-style API — Company Intelligence, "
        "Screening, Trading Comps, Deal Database, Valuation Analytics."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ────────────────────────
app.include_router(company_router)
app.include_router(screener_router)
app.include_router(comps_router)
app.include_router(deals_router)
app.include_router(analytics_router)
app.include_router(sourcing_router)
app.include_router(documents_router)
app.include_router(lbo_router)
app.include_router(portfolio_router)


# ── Health check ─────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", tags=["System"])
async def root():
    return {
        "name": "PE Intelligence Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "modules": [
            "Company Intelligence — /company/{ticker}",
            "Screening Engine   — /screener",
            "Trading Comps       — /comps",
            "Deal Database       — /deals",
            "Analytics           — /analytics",
            "Sourcing M&A        — /sourcing",
            "LBO Engine          — /lbo",
            "Portfolio Monitoring — /portfolio",
        ],
    }
