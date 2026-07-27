"""
PE Intelligence Platform — Configuration
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# ── Resolve .env relative to this file (api/.env) ──
_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "PE Intelligence Platform"
    app_version: str = "1.0.0"
    debug: bool = True

    # --- Database ---
    # SQLite for dev, PostgreSQL for prod
    # PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/pe_intelligence
    database_url: str = "sqlite+aiosqlite:///./pe_intelligence.db"
    database_echo: bool = False

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 1000
    openai_temperature: float = 0.3

    # --- Serper.dev (Google Search) ---
    serper_api_key: str = ""

    # --- BuiltWith (Tech Stack / Digital DD) ---
    builtwith_api_key: str = ""

    # --- Pappers (Legal & Corporate Watch) — obsolète, voir RUNBOOK § 5 ter ---
    pappers_api_key: str = ""

    # --- Financial Modeling Prep (Comps Engine, primaire — D13, Tâche B.3) ---
    fmp_api_key: str = ""

    # --- Finnhub (Comps Engine, banc d'essai — Tâche B.4) ---
    finnhub_api_key: str = ""

    # --- Alpha Vantage (Comps Engine, banc d'essai — Tâche B.4) ---
    alphavantage_api_key: str = ""

    # --- Adzuna (Talent & HR Intelligence) ---
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Data ingestion ---
    yfinance_max_concurrent: int = 5
    default_history_years: int = 5

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_prefix="PE_",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
