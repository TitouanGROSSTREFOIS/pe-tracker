"""
website_scraper.py — Smart Crawler async : scraping multi-pages d'un site cible.

Utilise **httpx.AsyncClient** + BeautifulSoup pour extraire le texte brut
des pages stratégiques d'une entreprise (accueil + about, pricing, produits…).

Pipeline :
    1. Scraping de la page d'accueil.
    2. Détection de 3 liens internes stratégiques (about, pricing, produits).
    3. Scraping concurrent des sous-pages identifiées.
    4. Concaténation et troncature du corpus final.

Adapted from the original sync module for the pe_tracker FastAPI backend.
All I/O is fully async (httpx).
"""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Comment
from loguru import logger


# ============================================================
# Constantes
# ============================================================

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

REQUEST_TIMEOUT: float = 15.0
SUBPAGE_TIMEOUT: float = 5.0

CONTENT_TAGS: list[str] = ["h1", "h2", "h3", "p", "li"]

NOISE_TAGS: list[str] = [
    "script", "style", "nav", "footer", "header",
    "aside", "form", "noscript", "svg", "iframe",
]

MAX_SUBPAGES: int = 3
MAX_CORPUS_CHARS: int = 20_000

STRATEGIC_KEYWORDS: list[str] = [
    # À propos / Équipe
    "about", "propos", "qui-sommes", "equipe", "team", "histoire",
    "notre-mission", "mission", "valeurs",
    # Pricing / Tarifs
    "pricing", "tarifs", "tarif", "prix", "plans", "offres", "formules",
    # Produit / Services
    "produit", "product", "features", "fonctionnalites",
    "solution", "services", "plateforme", "platform",
    # Cas d'usage
    "use-case", "cas-usage", "clients", "temoignages",
]


# ============================================================
# Fonction principale — Smart Crawler multi-pages (async)
# ============================================================

async def extract_text_from_url(url: str) -> str:
    """Extrait le texte des pages stratégiques d'un site web (multi-pages).

    Pipeline :
        1. Scraping de la page d'accueil.
        2. Détection des liens internes stratégiques (about, pricing…).
        3. Scraping concurrent des sous-pages (max 3, timeout court).
        4. Concaténation et troncature à MAX_CORPUS_CHARS.

    Args:
        url: URL complète de la page d'accueil du site.

    Returns:
        Corpus multi-pages nettoyé. Chaîne vide si échec.
    """
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
    ) as client:
        # --- Étape 1 : Page d'accueil ---
        homepage_html = await _fetch_html(client, url, timeout=REQUEST_TIMEOUT)
        if not homepage_html:
            return ""

        homepage_text = _parse_and_extract(homepage_html)
        corpus_parts: list[str] = [f"[PAGE: Accueil]\n{homepage_text}"]

        # --- Étape 2 : Détection des liens stratégiques ---
        strategic_links = _get_strategic_links(homepage_html, url)

        if strategic_links:
            logger.info(
                "[CRAWLER] {} sous-pages stratégiques détectées.", len(strategic_links)
            )

        # --- Étape 3 : Scraping concurrent des sous-pages ---
        subpage_tasks = [
            _fetch_html(client, link, timeout=SUBPAGE_TIMEOUT)
            for link in strategic_links
        ]
        subpage_results = await asyncio.gather(*subpage_tasks, return_exceptions=True)

        for link, result in zip(strategic_links, subpage_results):
            if isinstance(result, Exception) or not result:
                continue
            subpage_text = _parse_and_extract(result)
            if len(subpage_text) >= 50:
                path = urlparse(link).path.strip("/") or "sous-page"
                corpus_parts.append(f"[PAGE: {path}]\n{subpage_text}")

    # --- Étape 4 : Concaténation et troncature ---
    full_corpus = "\n\n".join(corpus_parts)

    if len(full_corpus) > MAX_CORPUS_CHARS:
        truncated = full_corpus[:MAX_CORPUS_CHARS]
        last_nl = truncated.rfind("\n")
        if last_nl > 0:
            truncated = truncated[:last_nl]
        logger.info(
            "[CRAWLER] Corpus tronqué : {} → {} caractères.",
            len(full_corpus), len(truncated),
        )
        return truncated

    return full_corpus


async def extract_single_page(url: str) -> str:
    """Extrait le texte d'une seule page (sans crawler les sous-pages).

    Utile pour scraper rapidement la page d'accueil d'une cible
    pendant le scoring.

    Args:
        url: URL de la page.

    Returns:
        Texte nettoyé. Chaîne vide si échec.
    """
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
    ) as client:
        html = await _fetch_html(client, url, timeout=REQUEST_TIMEOUT)
        if not html:
            return ""
        return _parse_and_extract(html)


# ============================================================
# Détection des liens stratégiques
# ============================================================

def _get_strategic_links(html_content: str, base_url: str) -> list[str]:
    """Identifie les liens internes stratégiques d'un site.

    Parse les <a href="..."> et filtre par :
        1. Lien interne (même domaine).
        2. Présence d'un mot-clé stratégique dans l'URL ou le texte du lien.
        3. Pas de doublon, pas d'ancre (#), pas de fichier média.

    Returns:
        Liste de max MAX_SUBPAGES URLs absolues.
    """
    soup = BeautifulSoup(html_content, "lxml")
    base_domain = urlparse(base_url).netloc.lower()

    seen: set[str] = set()
    strategic: list[str] = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()

        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        if parsed.netloc.lower() != base_domain:
            continue

        if any(
            clean_url.lower().endswith(ext)
            for ext in (".pdf", ".jpg", ".png", ".svg", ".css", ".js")
        ):
            continue

        if clean_url.rstrip("/") == base_url.rstrip("/"):
            continue

        if clean_url in seen:
            continue
        seen.add(clean_url)

        link_text = a_tag.get_text(strip=True).lower()
        url_path = parsed.path.lower()

        is_strategic = any(
            kw in url_path or kw in link_text for kw in STRATEGIC_KEYWORDS
        )

        if is_strategic:
            strategic.append(clean_url)

        if len(strategic) >= MAX_SUBPAGES:
            break

    return strategic


# ============================================================
# Fonctions de base (fetch async, parse, extract)
# ============================================================

async def _fetch_html(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = REQUEST_TIMEOUT,
) -> str | None:
    """Effectue la requête HTTP async et retourne le HTML brut.

    Args:
        client: Instance httpx.AsyncClient réutilisée.
        url:    URL à récupérer.
        timeout: Timeout en secondes.

    Returns:
        Le HTML brut, ou None en cas d'erreur.
    """
    try:
        response = await client.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text

    except httpx.TimeoutException:
        logger.warning("[TIMEOUT] Page non répondue en {}s : {}", timeout, url)
    except httpx.ConnectError:
        logger.warning("[CONNEXION] Impossible de joindre : {}", url)
    except httpx.HTTPStatusError as e:
        logger.warning("[HTTP {}] Erreur pour : {}", e.response.status_code, url)
    except httpx.HTTPError as e:
        logger.warning("[ERREUR] Requête échouée pour {} : {}", url, e)

    return None


def _parse_and_extract(html: str) -> str:
    """Parse le HTML et extrait le texte utile."""
    soup = BeautifulSoup(html, "lxml")
    _remove_noise(soup)
    return _extract_content(soup)


def _remove_noise(soup: BeautifulSoup) -> None:
    """Supprime les balises HTML générant du bruit (in-place)."""
    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()


def _extract_content(soup: BeautifulSoup) -> str:
    """Extrait et nettoie le texte des balises de contenu."""
    lines: list[str] = []
    for tag in soup.find_all(CONTENT_TAGS):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) >= 10:
            lines.append(text)
    return "\n".join(lines)
