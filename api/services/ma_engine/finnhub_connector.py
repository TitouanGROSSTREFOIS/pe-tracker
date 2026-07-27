"""
finnhub_connector.py — Connecteur Finnhub pour le Comps Engine (Tâche B.4, A.2/A.3).

⚠️ COUVERTURE RÉELLE DU PLAN GRATUIT (vérifiée empiriquement le 2026-07-21,
sur la clé PE_FINNHUB_API_KEY configurée dans ce projet, sur les 14 tickers
TIC de la Tâche B.1, cf. scripts/benchmark_market_data.py) :

    - `/stock/profile2` et `/stock/metric?metric=all` renvoient HTTP 403
      "You don't have access to this resource" pour LES 11 TICKERS NON-US
      (BVI.PA, SGSN.SW, ERF.PA, ITRK.L, ALQ.AX, ATE.PA, ASY.PA, SPIE.PA,
      WSP.TO, STN.TO, ATRL.TO) — le plan gratuit est strictement limité aux
      valeurs cotées aux États-Unis, y compris pour l'identité de base
      (contrairement à FMP, qui couvre les 14 en profil).
    - Pour les 3 tickers US (MG, CLB, J) : HTTP 200 partout, y compris
      `/stock/financials-reported` (états financiers déposés SEC, 13
      rapports annuels/trimestriels pour MG). `/stock/metric?metric=all`
      expose surtout des ratios/métriques par action ; les valeurs absolues
      directement exploitables sans dérivation sont `metric.enterpriseValue`
      et `metric.marketCapitalization` (en millions de la devise de cotation)
      et `series.annual.ebitda[].v` (EBITDA annuel en millions, par exercice).
      Il n'existe PAS de série "revenue" en valeur absolue dans ce payload
      (seulement `revenuePerShareTTM`) — ce connecteur ne renseigne donc PAS
      le CA, laissé à Alpha Vantage (`alphavantage_connector.py`) qui
      l'expose directement en dollars/euros bruts.
    - Quota constaté : aucune limite atteinte sur ~20 appels en quelques
      secondes (plan gratuit documenté à 60 requêtes/minute) — largement
      suffisant pour de l'ingestion interactive ou en lot raisonnable,
      contrairement à Alpha Vantage (25 requêtes/jour, voir l'autre module).

    CONSÉQUENCE : ce connecteur est la source la plus fiable pour
    `enterprise_value` (`Company`) et `ebitda` (`Financial`, exercice le
    plus récent uniquement — pas d'historique multi-année exploité ici),
    mais UNIQUEMENT pour les tickers cotés aux États-Unis. Pour les 11
    comparables européens/canadiens/australiens du CompSet TIC, il renvoie
    None de façon identique à FMP et Alpha Vantage — aucune estimation de
    substitution n'est produite (voir RAPPORT SPRINT B.4, section A.4).
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from api.config import get_settings


FINNHUB_BASE_URL: str = "https://finnhub.io/api/v1"
REQUEST_TIMEOUT: float = 15.0


async def fetch_finnhub_profile(ticker: str) -> dict[str, Any] | None:
    """Récupère le profil Finnhub d'un ticker (`/stock/profile2`).

    Returns:
        Dict normalisé (clés compatibles avec l'`info` dict yfinance déjà
        consommé par data_ingestion.py) si succès, None sinon (ticker non
        couvert par le plan gratuit — non-US — HTTP != 200, erreur réseau).
    """
    settings = get_settings()
    if not settings.finnhub_api_key:
        logger.warning("[Finnhub] PE_FINNHUB_API_KEY non configurée — skip.")
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{FINNHUB_BASE_URL}/stock/profile2",
                params={"symbol": ticker, "token": settings.finnhub_api_key},
                timeout=REQUEST_TIMEOUT,
            )
    except httpx.HTTPError as e:
        logger.warning("[Finnhub] Erreur réseau profile2({}) : {}", ticker, e)
        return None

    if resp.status_code == 403:
        logger.info("[Finnhub] profile2({}) : HTTP 403 — non couvert par le plan gratuit (hors US).", ticker)
        return None
    if resp.status_code != 200:
        logger.warning("[Finnhub] profile2({}) : HTTP {}", ticker, resp.status_code)
        return None

    p = resp.json()
    if not isinstance(p, dict) or not p.get("name"):
        return None

    return {
        "shortName": p.get("name"),
        "longName": p.get("name"),
        "sector": p.get("finnhubIndustry"),
        "industry": p.get("finnhubIndustry"),
        "country": p.get("country"),
        "exchange": p.get("exchange"),
        "currency": p.get("currency"),
        "marketCap": (p["marketCapitalization"] * 1_000_000) if p.get("marketCapitalization") else None,
        "enterpriseValue": None,  # non fourni par /stock/profile2, voir fetch_finnhub_financials
        "longBusinessSummary": None,
        "fullTimeEmployees": None,
        "website": p.get("weburl"),
        "currentPrice": None,
        "regularMarketPrice": None,
        "sharesOutstanding": (p["shareOutstanding"] * 1_000_000) if p.get("shareOutstanding") else None,
    }


async def fetch_finnhub_financials(ticker: str) -> dict[str, Any] | None:
    """Récupère EV et EBITDA (exercice le plus récent) via `/stock/metric?metric=all`.

    Ne renseigne PAS le chiffre d'affaires (non exposé en valeur absolue par
    cet endpoint — voir avertissement en tête de module). Retourne None si le
    ticker n'est pas couvert (hors US, plan gratuit) ou si les champs
    attendus sont absents.

    Returns:
        {"fiscal_year": int, "enterprise_value": float, "market_cap": float,
         "ebitda": float} — toutes les valeurs en devise de cotation brute
        (converties depuis les millions renvoyés par Finnhub) — ou None.
    """
    settings = get_settings()
    if not settings.finnhub_api_key:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{FINNHUB_BASE_URL}/stock/metric",
                params={"symbol": ticker, "metric": "all", "token": settings.finnhub_api_key},
                timeout=REQUEST_TIMEOUT,
            )
    except httpx.HTTPError as e:
        logger.warning("[Finnhub] Erreur réseau metric({}) : {}", ticker, e)
        return None

    if resp.status_code != 200:
        logger.info("[Finnhub] metric({}) : HTTP {} — non disponible sur ce plan.", ticker, resp.status_code)
        return None

    data = resp.json()
    metric = data.get("metric") or {}
    ebitda_series = (data.get("series") or {}).get("annual", {}).get("ebitda") or []

    ev = metric.get("enterpriseValue")
    mcap = metric.get("marketCapitalization")
    if not ebitda_series or ev is None:
        logger.info("[Finnhub] metric({}) : série EBITDA ou enterpriseValue absente.", ticker)
        return None

    latest = ebitda_series[0]  # la série est renvoyée triée du plus récent au plus ancien
    fiscal_year = int(str(latest["period"])[:4])

    return {
        "fiscal_year": fiscal_year,
        "enterprise_value": ev * 1_000_000,
        "market_cap": (mcap * 1_000_000) if mcap is not None else None,
        "ebitda": latest["v"] * 1_000_000,
    }
