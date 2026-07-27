"""
google_radar.py — Moteur async de découverte de cibles via Serper.dev.

Utilise les search_keywords issus de l'analyse NLP pour scanner Google
et identifier des entreprises similaires / concurrentes à la plateforme.

Pipeline :
    1. Extraction des mots-clés depuis le dict company_dna.
    2. Construction de requêtes Google combinatoires (paires de keywords).
    3. Appel concurrent API Serper.dev via httpx.AsyncClient.
    4. Filtrage anti-bruit (blacklist annuaires, presse, réseaux sociaux).
    5. Déduplication et extraction des domaines racines.

Adapted from the original sync module for the pe_tracker FastAPI backend.
All I/O is fully async (httpx).
"""

from __future__ import annotations

import asyncio
from itertools import combinations
from urllib.parse import urlparse

import httpx
from loguru import logger

from api.config import get_settings


# ============================================================
# Constantes
# ============================================================

SERPER_URL: str = "https://google.serper.dev/search"

MAX_RESULTS: int = 15
# Plafonné à 10 : au-delà, l'API Serper rejette la requête sur un plan
# gratuit ("Query pattern not allowed for free accounts", HTTP 400) — voir
# Tâche B.1, Étape 0/3. Vérifié empiriquement le 2026-07-20.
SERPER_NUM_RESULTS: int = 10
REQUEST_TIMEOUT: float = 15.0

DOMAIN_BLACKLIST: frozenset[str] = frozenset({
    # Réseaux sociaux
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "tiktok.com",
    # Annuaires & registres
    "pagesjaunes.fr", "kompass.com", "societe.com", "pappers.fr",
    "infogreffe.fr", "verif.com", "manageo.fr", "annuaire.com",
    # Presse & médias
    "lesechos.fr", "forbes.fr", "forbes.com", "lemonde.fr",
    "lefigaro.fr", "bfmtv.com", "maddyness.com", "frenchweb.fr",
    "journaldunet.com", "usinenouvelle.com",
    # Comparateurs & avis
    "capterra.fr", "capterra.com", "trustpilot.com", "g2.com",
    "getapp.com", "appvizer.fr",
    # Encyclopédies & généralistes
    "wikipedia.org", "wikiwand.com",
    # App stores
    "apps.apple.com", "play.google.com",
    # Autre bruit
    "crunchbase.com", "glassdoor.fr", "glassdoor.com",
    "indeed.com", "indeed.fr",
})


# ============================================================
# Fonction principale (async)
# ============================================================

async def find_potential_targets(company_dna: dict, platform_url: str = "") -> list[str]:
    """Recherche des entreprises similaires à la plateforme via Google.

    Pipeline :
        1. Extrait les search_keywords du dict company_dna.
        2. Génère des requêtes combinatoires (paires de keywords).
        3. Appelle Serper.dev en parallèle pour chaque requête.
        4. Filtre, déduplique et retourne les URLs propres.

    Args:
        company_dna: Dict issu de extract_company_dna() contenant au minimum
                     la clé 'search_keywords' (list[str]).
        platform_url: URL de la plateforme scannée (D47, Tâche Finalisation,
                     Partie A) — sert à exclure la plateforme elle-même de
                     ses propres résultats de recherche (voir
                     _filter_and_deduplicate ci-dessous).

    Returns:
        Liste d'URLs de domaines racines (max MAX_RESULTS), dédupliquée.
    """
    keywords = company_dna.get("search_keywords", [])

    if not keywords:
        logger.warning("[RADAR] Aucun mot-clé fourni dans company_dna.")
        return []

    # --- Étape 1 : Construire les requêtes ---
    queries = _build_queries(keywords)
    logger.info(
        "[RADAR] {} requêtes générées à partir de {} mots-clés.",
        len(queries), len(keywords),
    )

    # --- Étape 2 : Lancer les recherches en parallèle ---
    raw_urls = await _search_all(queries)
    logger.info("[RADAR] {} URLs brutes récupérées.", len(raw_urls))

    # --- Étape 3 : Filtrer et dédupliquer ---
    clean_urls = _filter_and_deduplicate(raw_urls, platform_url)
    logger.info("[RADAR] {} cibles propres après filtrage.", len(clean_urls))

    return clean_urls[:MAX_RESULTS]


# ============================================================
# Construction des requêtes
# ============================================================

def _build_queries(keywords: list[str]) -> list[str]:
    """Génère des requêtes Google combinatoires (paires de keywords).

    Limité à 5 requêtes max pour économiser le quota Serper.
    """
    queries: list[str] = []
    for kw1, kw2 in combinations(keywords, 2):
        queries.append(f'"{kw1}" "{kw2}"')
    return queries[:5]


# ============================================================
# Appels API Serper (async)
# ============================================================

async def _search_serper(
    client: httpx.AsyncClient,
    query: str,
    api_key: str,
) -> list[dict]:
    """Effectue une recherche Google via l'API Serper.dev (async).

    Args:
        client:  Instance httpx.AsyncClient réutilisée.
        query:   Requête de recherche.
        api_key: Clé API Serper.

    Returns:
        Liste de résultats organiques. Liste vide en cas d'erreur.
    """
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "gl": "fr",
        "hl": "fr",
        "num": SERPER_NUM_RESULTS,
    }

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
        logger.warning("[TIMEOUT] Serper non répondu pour : {}…", query[:50])
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            logger.error("[RATE LIMIT] Quota Serper dépassé.")
        elif status == 401:
            logger.error("[AUTH] Clé API Serper invalide.")
        else:
            logger.warning("[HTTP {}] Erreur Serper pour : {}…", status, query[:50])
    except httpx.ConnectError:
        logger.warning("[CONNEXION] Impossible de joindre Serper.dev")
    except httpx.HTTPError as e:
        logger.warning("[ERREUR] Requête Serper échouée : {}", e)

    return []


async def _search_all(queries: list[str]) -> list[str]:
    """Lance toutes les requêtes en parallèle et agrège les URLs.

    Returns:
        Liste brute d'URLs (avec doublons possibles).
    """
    settings = get_settings()
    api_key = settings.serper_api_key

    if not api_key:
        logger.error("[RADAR] serper_api_key non définie. Configure PE_SERPER_API_KEY dans .env")
        return []

    all_urls: list[str] = []

    async with httpx.AsyncClient() as client:
        tasks = [
            _search_serper(client, query, api_key)
            for query in queries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("[SEARCH {}/{}] Exception : {}", i + 1, len(queries), result)
                continue
            for item in result:
                link = item.get("link", "")
                if link:
                    all_urls.append(link)

    return all_urls


# ============================================================
# Filtrage & déduplication (CPU pur — sync)
# ============================================================

def _extract_root_domain(url: str) -> str:
    """Extrait le domaine racine d'une URL complète.

    Ex : 'https://www.shine.fr/blog/compte-pro' → 'https://www.shine.fr'
    """
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return url


def _is_blacklisted(url: str) -> bool:
    """Vérifie si une URL appartient à un domaine blacklisté."""
    try:
        hostname = urlparse(url).hostname or ""
        for blocked in DOMAIN_BLACKLIST:
            if hostname == blocked or hostname.endswith(f".{blocked}"):
                return True
        return False
    except Exception:
        return True


def _bare_hostname(url: str) -> str:
    """Hostname normalisé (minuscules, sans 'www.') pour comparer deux URLs
    par identité de domaine plutôt que par égalité de chaîne brute."""
    hostname = (urlparse(url).hostname or "").lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def _filter_and_deduplicate(urls: list[str], platform_url: str) -> list[str]:
    """Filtre les URLs brutes et retourne une liste propre et dédupliquée.

    Filtres :
        1. Suppression des domaines blacklistés.
        2. Suppression du domaine de la plateforme elle-même.
        3. Extraction des domaines racines.
        4. Déduplication (un seul résultat par domaine).

    D47 (Tâche Finalisation, Partie A) : le filtre #2 comparait auparavant
    `company_dna["company_name"].lower() in hostname` — un test de
    sous-chaîne sur le NOM de la société, qui échoue silencieusement dès
    que ce nom contient un espace ("Groupe Qualiconsult" ne peut jamais
    être une sous-chaîne d'un hostname, qui n'a pas d'espaces) ou diffère
    légèrement du nom de domaine réel. Repro réelle : un scan sur
    qualiconsult.fr a laissé passer "Groupe Qualiconsult" comme cible
    scorée à 74.89, la plateforme se retrouvant dans ses propres
    résultats. Comparaison désormais sur le HOSTNAME exact de
    `platform_url` (même normalisation que la déduplication ci-dessous)
    — robuste au nom, jamais un faux négatif ni un faux positif par
    collision de mot.
    """
    seen_domains: set[str] = set()
    clean: list[str] = []
    platform_hostname = _bare_hostname(platform_url) if platform_url else ""

    for url in urls:
        if _is_blacklisted(url):
            continue

        if platform_hostname and _bare_hostname(url) == platform_hostname:
            continue

        root = _extract_root_domain(url)

        if root in seen_domains:
            continue

        seen_domains.add(root)
        clean.append(root)

    return clean
