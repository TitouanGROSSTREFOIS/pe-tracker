"""
deep_researcher.py — Module async de Deep Research (Pré-Due Diligence).

Enrichit l'analyse des cibles validées en interrogeant Google
via Serper.dev pour chercher des signaux faibles spécifiques, découpés en 3 axes :
    - Red Flags (risques, prudence, problèmes légaux ou avis négatifs)
    - Growth Signals (levées de fonds, recrutements, expansion)
    - Concurrence (alternatives, paysage concurrentiel)

Pipeline :
    1. Construction de 3 requêtes thématiques (red flags / growth / competition).
    2. Appel **concurrent** des 3 requêtes via asyncio.gather + httpx / Serper.
    3. Compilation des snippets pour chaque axe.

Adapted from the original sync module for the pe_tracker FastAPI backend.
All I/O is fully async (httpx).
"""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

from api.config import get_settings


# ============================================================
# Constantes
# ============================================================

SERPER_URL: str = "https://google.serper.dev/search"
REQUEST_TIMEOUT: float = 15.0
MAX_SNIPPETS: int = 5


# ============================================================
# Helpers
# ============================================================

def _compile_snippets(results: list[dict], max_items: int = MAX_SNIPPETS) -> str:
    """Compile les snippets des résultats de recherche en texte lisible."""
    if not results:
        return "Aucun résultat probant trouvé sur ce sujet."

    compiled: list[str] = []
    for r in results[:max_items]:
        title = r.get("title", "").replace("\n", " ").strip()
        snippet = r.get("snippet", "").replace("\n", " ").strip()
        if snippet:
            compiled.append(f"- {title} : {snippet}")

    if not compiled:
        return "Aucun résultat probant trouvé sur ce sujet."

    return "\n".join(compiled)


async def _search_serper(
    client: httpx.AsyncClient,
    query: str,
    api_key: str,
) -> list[dict]:
    """Effectue une recherche Serper async et retourne les résultats organiques."""
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "gl": "fr", "hl": "fr", "num": 10}

    try:
        response = await client.post(
            SERPER_URL,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("organic", [])

    except httpx.TimeoutException:
        logger.warning("[TIMEOUT] Serper → {}…", query[:60])
    except httpx.HTTPStatusError as e:
        logger.warning("[HTTP {}] Serper → {}…", e.response.status_code, query[:60])
    except httpx.ConnectError:
        logger.warning("[CONNECT] Serper injoignable → {}…", query[:60])
    except Exception as e:
        logger.error("[ERROR] Serper → {}", e)

    return []


# ============================================================
# Fonction principale — Deep Research en parallèle
# ============================================================

async def run_deep_research(target_name: str, target_url: str) -> dict:
    """Consolide la pré-due diligence sur 3 axes via Serper (async, parallel).

    Les 3 requêtes (red flags, growth, concurrence) sont lancées
    simultanément via asyncio.gather pour une latence minimale.

    Args:
        target_name: Nom estimé de la cible.
        target_url:  URL de la cible.

    Returns:
        Dict avec 3 clés textuelles :
            raw_red_flags, raw_growth_signals, raw_competitors.
    """
    settings = get_settings()
    api_key = settings.serper_api_key

    empty = {
        "raw_red_flags": "Aucun résultat probant trouvé sur ce sujet.",
        "raw_growth_signals": "Aucun résultat probant trouvé sur ce sujet.",
        "raw_competitors": "Aucun résultat probant trouvé sur ce sujet.",
    }

    if not api_key:
        logger.warning("[Deep Research] SERPER_API_KEY absente → skip.")
        return empty

    logger.info("    🔍 [Deep Research] Analyse externe pour {}…", target_name)

    # ── 3 requêtes thématiques ──
    q_red_flags = (
        f'{target_name} (scandale OR redressement OR '
        f'"prud\'hommes" OR avis OR plainte OR arnaque)'
    )
    q_growth = (
        f'{target_name} ("levée de fonds" OR "recrutement" OR "croissance")'
    )
    q_comp = (
        f'related:{target_url} OR "{target_name} concurrents" '
        f'OR "alternatives à {target_name}"'
    )

    async with httpx.AsyncClient() as client:
        res_red, res_growth, res_comp = await asyncio.gather(
            _search_serper(client, q_red_flags, api_key),
            _search_serper(client, q_growth, api_key),
            _search_serper(client, q_comp, api_key),
        )

    return {
        "raw_red_flags": _compile_snippets(res_red),
        "raw_growth_signals": _compile_snippets(res_growth),
        "raw_competitors": _compile_snippets(res_comp),
    }
