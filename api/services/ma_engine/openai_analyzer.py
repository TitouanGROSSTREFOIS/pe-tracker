"""
openai_analyzer.py — Analyse NLP async du business model via AsyncOpenAI.

Utilise gpt-4o-mini pour comprendre le positionnement, le secteur,
et les caractéristiques clés d'une entreprise cible.

Fonction principale :
    - extract_company_dna(raw_text) → dict structuré (ADN business)

Adapted from the original sync module for the pe_tracker FastAPI backend.
Uses **openai.AsyncOpenAI** — fully non-blocking.
"""

from __future__ import annotations

import json

from openai import (
    AsyncOpenAI,
    RateLimitError,
    APIError,
    APIConnectionError,
)
from loguru import logger

from api.config import get_settings


# ============================================================
# Constantes
# ============================================================

MAX_INPUT_CHARS: int = 15_000

SYSTEM_PROMPT: str = """Tu es un Directeur de Participation senior dans un fonds de Private Equity \
spécialisé en stratégie Buy & Build. Tu analyses des entreprises non-cotées pour identifier \
leur positionnement stratégique.

À partir du texte extrait du site web d'une entreprise, tu dois produire une fiche d'identité \
business structurée. Sois factuel, précis, et technique. Ne devine pas : si une information \
n'est pas disponible dans le texte, indique "Non identifié".

Tu DOIS retourner strictement un objet JSON avec les clés suivantes :

- "company_name" (str) : Nom de l'entreprise.
- "sector" (str) : Secteur d'activité précis (ex: "B2B SaaS - Fintech", "Industrie - Métallurgie", "Santé - Medtech").
- "business_model" (str) : Modèle de revenus (ex: "Abonnement SaaS", "Marketplace transactionnelle", "Vente directe", "Licence + maintenance").
- "value_proposition" (str) : Proposition de valeur principale en une phrase.
- "target_audience" (str) : Cible client (ex: "TPE/PME < 250 salariés", "Grands Comptes CAC40", "Professions libérales").
- "geographic_focus" (str) : Zone géographique cible (ex: "France", "Europe", "Monde").
- "search_keywords" (list[str]) : 5 à 7 mots-clés ULTRA-SPÉCIFIQUES et TECHNIQUES qui permettraient \
  de trouver des concurrents directs ou des entreprises jumelles sur Google. \
  INTERDIT : mots génériques comme "innovation", "qualité", "performance", "solution", "digital". \
  REQUIS : termes métier précis, noms de niches, technologies spécifiques, cas d'usage concrets."""

USER_PROMPT_TEMPLATE: str = """Analyse le texte suivant extrait du site web d'une entreprise et retourne \
la fiche d'identité business au format JSON.

--- DÉBUT DU TEXTE ---
{text}
--- FIN DU TEXTE ---"""

# Expected keys in the LLM response
_EXPECTED_KEYS: frozenset[str] = frozenset({
    "company_name", "sector", "business_model",
    "value_proposition", "target_audience",
    "geographic_focus", "search_keywords",
})


# ============================================================
# Client AsyncOpenAI (lazy singleton)
# ============================================================

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Return the async OpenAI client (lazy-init singleton)."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError(
                "[ERREUR] openai_api_key non définie. "
                "Configure PE_OPENAI_API_KEY dans .env ou l'environnement."
            )
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# ============================================================
# Fonction principale (async)
# ============================================================

async def extract_company_dna(raw_text: str) -> dict:
    """Analyse le texte brut d'un site web et retourne l'ADN business structuré.

    Pipeline :
        1. Troncature du texte si > MAX_INPUT_CHARS.
        2. Appel async à l'API OpenAI (JSON mode).
        3. Parsing et validation du JSON retourné.

    Args:
        raw_text: Texte brut extrait du site web de l'entreprise.

    Returns:
        Dict contenant les clés : company_name, sector, business_model,
        value_proposition, target_audience, geographic_focus, search_keywords.
        Dict vide en cas d'erreur.
    """
    if not raw_text or not raw_text.strip():
        logger.warning("Texte vide fourni à l'analyseur NLP.")
        return {}

    text = _truncate_text(raw_text)
    raw_response = await _call_openai(text)
    if not raw_response:
        return {}

    return _parse_response(raw_response)


# ============================================================
# Fonctions internes
# ============================================================

def _truncate_text(text: str) -> str:
    """Tronque le texte à MAX_INPUT_CHARS sur une frontière de ligne."""
    if len(text) <= MAX_INPUT_CHARS:
        return text

    truncated = text[:MAX_INPUT_CHARS]
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline]

    logger.info("[NLP] Texte tronqué : {} → {} caractères", len(text), len(truncated))
    return truncated


async def _call_openai(text: str) -> str | None:
    """Envoie le texte au LLM et retourne la réponse brute (async).

    Returns:
        Contenu de la réponse (str) ou None en cas d'erreur.
    """
    settings = get_settings()
    client = _get_client()
    user_prompt = USER_PROMPT_TEMPLATE.format(text=text)

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=settings.openai_max_tokens,
            temperature=settings.openai_temperature,
        )

        content = response.choices[0].message.content
        usage = response.usage
        logger.info(
            "[NLP] Tokens : {} in / {} out",
            usage.prompt_tokens, usage.completion_tokens,
        )
        return content

    except RateLimitError:
        logger.error("[RATE LIMIT] Quota OpenAI dépassé.")
    except APIConnectionError:
        logger.error("[CONNEXION] Impossible de joindre l'API OpenAI.")
    except APIError as e:
        logger.error("[API ERROR] Erreur OpenAI : {}", e.message)
    except Exception as e:
        logger.error("[ERREUR] Appel LLM échoué : {}", e)

    return None


def _parse_response(raw_json: str) -> dict:
    """Parse la réponse JSON du LLM et valide la structure.

    Returns:
        Dict structuré ou dict vide si le parsing échoue.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.error("Réponse LLM non-JSON valide : {}", e)
        return {}

    missing = _EXPECTED_KEYS - set(data.keys())
    if missing:
        logger.warning("Clés manquantes dans la réponse LLM : {}", missing)

    return data
