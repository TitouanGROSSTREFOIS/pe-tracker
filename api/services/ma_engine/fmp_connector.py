"""
fmp_connector.py — Connecteur Financial Modeling Prep (FMP) pour le Comps
Engine, source PRIMAIRE remplaçant yfinance (D13, Tâche B.3).

⚠️ COUVERTURE RÉELLE DU PLAN GRATUIT (vérifiée empiriquement le 2026-07-21,
sur la clé PE_FMP_API_KEY configurée dans ce projet, sur les 14 tickers TIC
de la Tâche B.1 + AAPL comme contrôle) :

    - Les endpoints `/api/v3/*` ("Legacy Endpoints") renvoient tous HTTP 403
      "Legacy Endpoint... only available for legacy users" — dépréciés pour
      toute clé créée après le 31/08/2025.
    - Les endpoints `/stable/*` sont la nouvelle API. Testés :
        - `/stable/profile`            → HTTP 200 pour LES 14 TICKERS (dont
          tous les tickers non-US : BVI.PA, SGSN.SW, ERF.PA, ITRK.L, ALQ.AX,
          ATE.PA, ASY.PA, SPIE.PA, WSP.TO, STN.TO, ATRL.TO). Champs
          disponibles : symbol, price, marketCap, companyName, sector,
          industry, country, description, website, fullTimeEmployees,
          exchange, exchangeFullName, currency, ipoDate, isActivelyTrading.
          PAS de enterpriseValue ni sharesOutstanding dans ce payload.
        - `/stable/quote`, `/stable/key-metrics`, `/stable/income-statement`,
          `/stable/balance-sheet-statement`, `/stable/cash-flow-statement`,
          `/stable/enterprise-values`, `/stable/ratios` → HTTP 402 "Premium
          Query Parameter... not available under your current subscription"
          pour LES 14 TICKERS, systématiquement. Fonctionnent uniquement
          pour un petit nombre de tickers "démo" (AAPL confirmé fonctionnel,
          utilisé ici uniquement comme témoin pour distinguer une
          restriction de plan d'une restriction par ticker).
        - Quota journalier : non mesuré par épuisement volontaire (pour
          préserver le quota nécessaire à l'ingestion réelle de l'Étape 4).
          Aucun header `X-RateLimit-*` n'a été observé sur les réponses.

    CONSÉQUENCE : ce connecteur ne peut alimenter QUE les champs `Company`
    (profil, prix, market cap) — PAS les états financiers (`Financial`),
    donc PAS les multiples EV/EBITDA calculés dessus, sur ce plan et ces
    tickers. `data_ingestion.ingest_company()` retombe sur yfinance pour
    cette partie (repli D13), lui-même bloqué au moment de cette tâche (voir
    RAPPORT B.3). C'est documenté honnêtement, pas contourné par une
    estimation.
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from api.config import get_settings


FMP_BASE_URL: str = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT: float = 15.0


async def fetch_fmp_profile(ticker: str) -> dict[str, Any] | None:
    """Récupère le profil FMP d'un ticker (`/stable/profile`).

    Returns:
        Dict normalisé (clés compatibles avec ce que data_ingestion.py
        attend déjà de l'`info` dict yfinance) si succès, None sinon
        (ticker non couvert, HTTP != 200, erreur réseau).
    """
    settings = get_settings()
    if not settings.fmp_api_key:
        logger.warning("[FMP] PE_FMP_API_KEY non configurée — skip.")
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{FMP_BASE_URL}/profile",
                params={"symbol": ticker, "apikey": settings.fmp_api_key},
                timeout=REQUEST_TIMEOUT,
            )
    except httpx.HTTPError as e:
        logger.warning("[FMP] Erreur réseau profile({}) : {}", ticker, e)
        return None

    if resp.status_code == 402:
        logger.warning("[FMP] profile({}) : HTTP 402 — non couvert par ce plan.", ticker)
        return None
    if resp.status_code != 200:
        logger.warning("[FMP] profile({}) : HTTP {}", ticker, resp.status_code)
        return None

    data = resp.json()
    if not isinstance(data, list) or not data:
        logger.warning("[FMP] profile({}) : réponse vide/inattendue.", ticker)
        return None

    p = data[0]
    return {
        "shortName": p.get("companyName"),
        "longName": p.get("companyName"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "country": p.get("country"),
        "exchange": p.get("exchangeFullName") or p.get("exchange"),
        "currency": p.get("currency"),
        "marketCap": p.get("marketCap"),
        "enterpriseValue": None,  # non exposé par /stable/profile sur ce plan
        "longBusinessSummary": p.get("description"),
        "fullTimeEmployees": p.get("fullTimeEmployees"),
        "website": p.get("website"),
        "currentPrice": p.get("price"),
        "regularMarketPrice": p.get("price"),
        "sharesOutstanding": None,  # non exposé par /stable/profile sur ce plan
    }


async def fetch_fmp_financials(ticker: str) -> dict[str, Any] | None:
    """Tente de récupérer les états financiers FMP (income-statement).

    Sur le plan gratuit testé, retourne systématiquement None pour les
    tickers non-démo (HTTP 402) — voir avertissement en tête de module.
    Conservé comme point d'extension si le plan est mis à niveau.
    """
    settings = get_settings()
    if not settings.fmp_api_key:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{FMP_BASE_URL}/income-statement",
                params={"symbol": ticker, "apikey": settings.fmp_api_key},
                timeout=REQUEST_TIMEOUT,
            )
    except httpx.HTTPError as e:
        logger.warning("[FMP] Erreur réseau income-statement({}) : {}", ticker, e)
        return None

    if resp.status_code != 200:
        logger.info("[FMP] income-statement({}) : HTTP {} — non disponible sur ce plan.",
                     ticker, resp.status_code)
        return None

    data = resp.json()
    if not isinstance(data, list) or not data:
        return None
    return {"income_statement": data}
