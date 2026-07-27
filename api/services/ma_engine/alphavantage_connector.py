"""
alphavantage_connector.py — Connecteur Alpha Vantage pour le Comps Engine
(Tâche B.4, A.2/A.3), source de repli pour le chiffre d'affaires (`revenue`).

⚠️ COUVERTURE RÉELLE DU PLAN GRATUIT (vérifiée empiriquement le 2026-07-21,
sur la clé PE_ALPHAVANTAGE_API_KEY configurée dans ce projet, sur les 14
tickers TIC de la Tâche B.1, cf. scripts/benchmark_market_data.py) :

    - `SYMBOL_SEARCH` et `GLOBAL_QUOTE` reconnaissent bien les tickers
      internationaux avec le suffixe de place Alpha Vantage (ex.
      `BVI.PAR` pour Bureau Veritas Paris — confirmé retrouvé via
      SYMBOL_SEARCH à partir du nom "Bureau Veritas", et son cours du jour
      obtenu via GLOBAL_QUOTE).
    - MAIS `OVERVIEW` (fondamentaux : capitalisation, EBITDA, CA, actions en
      circulation) renvoie `{}` (vide) pour LES 11 TICKERS NON-US, alors
      même que le symbole existe et que le cours fonctionne. Confirmé aussi
      directement sur `INCOME_STATEMENT` pour `BVI.PAR` → `{}`. Seuls les 3
      tickers US (MG, CLB, J) renvoient un OVERVIEW complet et exploitable
      (ex. MG : MarketCapitalization=488386000, EBITDA=83266000,
      RevenueTTM=731443000, SharesOutstanding=31816700 — valeurs absolues
      directement en dollars, aucune conversion d'unité nécessaire).
    - Quota : 25 requêtes/jour sur le plan gratuit (documenté par Alpha
      Vantage ; aucun message de dépassement "Information"/"Note" déclenché
      dans ce projet sur ~20 appels cumulés lors du banc d'essai B.4, donc
      quota non entièrement consommé, mais TRÈS étroit comparé à Finnhub
      60/min). ⚠️ NE PAS appeler ce connecteur en boucle sur une liste de
      tickers au-delà de quelques unités par jour — pas de retry, pas de
      fallback automatique en cas de quota atteint (le payload devient vide
      silencieusement, indiscernable d'un ticker non couvert : cf. le champ
      `quota_suspected` renvoyé ci-dessous pour au moins le signaler).

    CONSÉQUENCE : ce connecteur ne sert, dans la hiérarchie de repli du
    Comps Engine (voir data_ingestion.py), qu'à renseigner `revenue` pour
    les tickers déjà identifiés comme couverts par Finnhub (enterprise_value
    + ebitda) — c'est-à-dire, sur les 14 tickers testés, les 3 mêmes
    tickers US. Pour les 11 comparables européens/canadiens/australiens, il
    renvoie None, comme les deux autres sources — aucune estimation de
    substitution.
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from api.config import get_settings


ALPHAVANTAGE_BASE_URL: str = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT: float = 15.0


async def fetch_alphavantage_financials(ticker: str) -> dict[str, Any] | None:
    """Récupère le CA (RevenueTTM) et quelques fondamentaux via `OVERVIEW`.

    ⚠️ Consomme 1 requête du quota journalier de 25. À n'appeler que pour un
    nombre restreint de tickers (voir avertissement de module).

    Returns:
        {"revenue": float, "ebitda": float | None, "market_cap": float | None,
         "shares_outstanding": float | None, "quota_suspected": bool} ou None
        si le ticker n'est pas couvert par ce plan (payload vide — cas normal
        pour les tickers non-US, voir module docstring).
    """
    settings = get_settings()
    if not settings.alphavantage_api_key:
        logger.warning("[AlphaVantage] PE_ALPHAVANTAGE_API_KEY non configurée — skip.")
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                ALPHAVANTAGE_BASE_URL,
                params={"function": "OVERVIEW", "symbol": ticker, "apikey": settings.alphavantage_api_key},
                timeout=REQUEST_TIMEOUT,
            )
    except httpx.HTTPError as e:
        logger.warning("[AlphaVantage] Erreur réseau OVERVIEW({}) : {}", ticker, e)
        return None

    if resp.status_code != 200:
        logger.warning("[AlphaVantage] OVERVIEW({}) : HTTP {}", ticker, resp.status_code)
        return None

    data = resp.json()
    if not isinstance(data, dict):
        return None

    quota_suspected = "Information" in data or "Note" in data
    if quota_suspected:
        logger.warning("[AlphaVantage] OVERVIEW({}) : quota probablement atteint — {}",
                        ticker, data.get("Information") or data.get("Note"))
        return None

    revenue_raw = data.get("RevenueTTM")
    if not data.get("Symbol") or not revenue_raw:
        logger.info("[AlphaVantage] OVERVIEW({}) : ticker non couvert par ce plan (payload vide).", ticker)
        return None

    def _f(key: str) -> float | None:
        v = data.get(key)
        try:
            return float(v) if v not in (None, "None", "") else None
        except (ValueError, TypeError):
            return None

    return {
        "revenue": _f("RevenueTTM"),
        "ebitda": _f("EBITDA"),
        "market_cap": _f("MarketCapitalization"),
        "shares_outstanding": _f("SharesOutstanding"),
        "quota_suspected": False,
    }
