"""
similarity_scorer.py — Scoring hybride async TF-IDF + LLM des cibles d'acquisition.

Combine deux approches complémentaires :
    - TF-IDF + cosine similarity (score lexical rapide, filtre anti-bruit).
    - GPT-4o-mini en mode analyste M&A (score stratégique + justification).

Score final = 0.4 × TF-IDF + 0.6 × LLM (pondération sémantique > lexicale).

Fonctions principales (async) :
    - calculate_nlp_score(source_text, target_text) -> float          [CPU-bound, sync interne]
    - get_llm_strategic_fit(company_dna, target_text, research) -> dict [async — AsyncOpenAI]
    - rank_targets(platform_text, company_dna, target_urls, ...) -> list[dict] [async orchestrator]

Ce module ne fait **aucune** persistence : il calcule et retourne les scores.
La sauvegarde en DB est déléguée au pipeline (sourcing_pipeline.py).

Adapted from the original sync module for the pe_tracker FastAPI backend.
LLM calls use **openai.AsyncOpenAI** — fully non-blocking.
"""

from __future__ import annotations

import json

from openai import (
    AsyncOpenAI,
    RateLimitError,
    APIError,
    APIConnectionError,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from loguru import logger

from api.config import get_settings
from api.services.ma_engine.website_scraper import extract_single_page
from api.services.ma_engine.financial_estimator import (
    estimate_company_size,
    extract_name_from_url,
    is_lbo_compatible,
    format_revenue,
    LBO_CA_MIN,
    LBO_CA_MAX,
)
from api.services.ma_engine.deep_researcher import run_deep_research
from api.services.ma_engine.valuation_engine import run_lbo_model


# ============================================================
# Constantes
# ============================================================

# Seuil minimum de similarité (sur 100) pour valider une cible
MIN_SCORE_THRESHOLD: float = 10.0

# Paramètres TF-IDF
TFIDF_MAX_FEATURES: int = 5000
TFIDF_NGRAM_RANGE: tuple = (1, 2)
TFIDF_MIN_DF: int = 1
TFIDF_SUBLINEAR_TF: bool = True

# Texte minimum exploitable (en caractères)
MIN_TEXT_LENGTH: int = 100

# Pondération du score final hybride
WEIGHT_TFIDF: float = 0.4
WEIGHT_LLM: float = 0.6

# Limite de caractères pour le texte cible envoyé au LLM
MAX_TARGET_CHARS: int = 8_000

LLM_SYSTEM_PROMPT: str = """Tu es un analyste senior en Fusions & Acquisitions (M&A) dans un fonds de \
Private Equity spécialisé en stratégie Buy & Build.

On te présente une entreprise "plateforme" et les données extraites du site et d'une pré-due diligence \
d'une cible potentielle.
Tu dois évaluer si cette cible serait une acquisition pertinente pour compléter la plateforme.

Critères d'évaluation :
- Proximité sectorielle et synergies (marché, technologie)
- Compatibilité de la cible client
- Absence de red flags majeurs (filtrer les risques liés aux ressources humaines, réputation)
- Évaluation des signaux de croissance (levée de fonds, recrutement)
- Paysage concurrentiel limitrophe

IMPORTANT : Si la cible est un média, blog, comparateur ou annuaire (et non une entreprise \
avec un produit/service propre), attribue un score de 0.

Tu DOIS retourner strictement un JSON avec :
- "llm_score" (int, 0 à 100) : pertinence stratégique de l'acquisition.
- "strategic_fit" (str) : 2 phrases percutantes justifiant pourquoi c'est un bon/mauvais fit.
- "growth_signals" (str) : Courte synthèse des signaux positifs et de croissance.
- "red_flags" (str) : Courte synthèse des risques potentiels (ou 'Aucun risque majeur détecté').
- "competitors" (list[str]) : Liste des concurrents ou alternatives repérées."""

LLM_USER_TEMPLATE: str = """PLATEFORME DE RÉFÉRENCE :
- Nom : {company_name}
- Secteur : {sector}
- Business Model : {business_model}
- Cible client : {target_audience}

CONTEXTE DE DUE DILIGENCE EXTERNE (DEEP RESEARCH) SUR LA CIBLE :
- Signaux de croissance : {growth_context}
- Red Flags / Alertes : {red_flags_context}
- Concurrence identifiée : {competitors_context}

TEXTE DU SITE DE LA CIBLE POTENTIELLE :
--- DÉBUT ---
{target_text}
--- FIN ---

Évalue cette cible pour un Build-up de la plateforme. Retourne ton analyse en JSON."""


# ============================================================
# Client AsyncOpenAI (singleton lazy)
# ============================================================

_llm_client: AsyncOpenAI | None = None


def _get_llm_client() -> AsyncOpenAI:
    """Retourne le client AsyncOpenAI (singleton lazy)."""
    global _llm_client
    if _llm_client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("[ERREUR] openai_api_key non définie dans la config.")
        _llm_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _llm_client


# ============================================================
# Scoring NLP — Similarité TF-IDF + Cosinus (CPU-bound, sync)
# ============================================================

def calculate_nlp_score(source_text: str, target_text: str) -> float:
    """Calcule un score de similarité NLP entre deux textes via TF-IDF + cosinus.

    CPU-bound (sklearn) — pas de I/O, reste sync.

    Args:
        source_text: Texte de référence (la plateforme).
        target_text: Texte de la cible candidate.

    Returns:
        Score de similarité entre 0.0 et 100.0 (arrondi à 2 décimales).
    """
    if not source_text or len(source_text.strip()) < MIN_TEXT_LENGTH:
        logger.warning("Texte source trop court pour le scoring.")
        return 0.0

    if not target_text or len(target_text.strip()) < MIN_TEXT_LENGTH:
        logger.warning("Texte cible trop court pour le scoring.")
        return 0.0

    try:
        vectorizer = TfidfVectorizer(
            max_features=TFIDF_MAX_FEATURES,
            ngram_range=TFIDF_NGRAM_RANGE,
            min_df=TFIDF_MIN_DF,
            sublinear_tf=TFIDF_SUBLINEAR_TF,
            stop_words=None,
        )

        tfidf_matrix = vectorizer.fit_transform([source_text, target_text])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
        score = round(float(similarity[0][0]) * 100, 2)
        return score

    except ValueError as e:
        logger.error("Erreur TF-IDF : {}", e)
        return 0.0


# ============================================================
# Scoring LLM — Évaluation stratégique M&A (async)
# ============================================================

async def get_llm_strategic_fit(
    company_dna: dict,
    target_text: str,
    research_context: dict,
) -> dict:
    """Demande au LLM d'évaluer la pertinence stratégique d'une cible (async).

    Args:
        company_dna:     Dict ADN de la plateforme.
        target_text:     Texte brut extrait du site de la cible.
        research_context: Contexte Deep Research (red flags, growth, competitors).

    Returns:
        Dict étendu: llm_score, strategic_fit, growth_signals, red_flags, competitors.
    """
    fallback = {
        "llm_score": 0,
        "strategic_fit": "Évaluation LLM indisponible.",
        "growth_signals": "N/A",
        "red_flags": "N/A",
        "competitors": [],
    }

    settings = get_settings()

    # Troncature du texte cible
    text = target_text[:MAX_TARGET_CHARS] if len(target_text) > MAX_TARGET_CHARS else target_text

    user_prompt = LLM_USER_TEMPLATE.format(
        company_name=company_dna.get("company_name", "N/A"),
        sector=company_dna.get("sector", "N/A"),
        business_model=company_dna.get("business_model", "N/A"),
        target_audience=company_dna.get("target_audience", "N/A"),
        growth_context=research_context.get("raw_growth_signals", "N/A"),
        red_flags_context=research_context.get("raw_red_flags", "N/A"),
        competitors_context=research_context.get("raw_competitors", "N/A"),
        target_text=text,
    )

    try:
        client = _get_llm_client()
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=256,
            temperature=settings.openai_temperature,
        )

        content = response.choices[0].message.content
        usage = response.usage
        logger.info("  LLM tokens : {} in / {} out",
                     usage.prompt_tokens, usage.completion_tokens)

        data = json.loads(content)
        llm_score = max(0, min(100, int(data.get("llm_score", 0))))
        strategic_fit = data.get("strategic_fit", data.get("justification", "Pas de justification."))
        growth_signals = data.get("growth_signals", "Non évalué")
        red_flags = data.get("red_flags", "Non évalué")
        competitors = data.get("competitors", [])

        return {
            "llm_score": llm_score,
            "strategic_fit": strategic_fit,
            "growth_signals": growth_signals,
            "red_flags": red_flags,
            "competitors": competitors,
        }

    except (RateLimitError, APIConnectionError, APIError) as e:
        logger.warning("  LLM indisponible : {}", e)
        return fallback
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("  Réponse LLM invalide : {}", e)
        return fallback
    except Exception as e:
        logger.warning("  Erreur LLM inattendue : {}", e)
        return fallback


# ============================================================
# Chef d'orchestre — Ranking hybride des cibles (async)
# ============================================================

async def rank_targets(
    platform_text: str,
    target_urls: list[str],
    company_dna: dict | None = None,
    min_revenue: int | None = None,
    max_revenue: int | None = None,
    known_revenues: dict[str, float] | None = None,
) -> list[dict]:
    """Score et classe les cibles par pertinence (hybride TF-IDF + LLM, async).

    Pipeline pour chaque URL :
        1. Scraping async du contenu textuel.
        2. Calcul du score TF-IDF vs la plateforme.
        3. Filtrage par seuil MIN_SCORE_THRESHOLD.
        4. Estimation financière async + filtre LBO.
        5. Valorisation Paper LBO 5 ans.
        6. Deep Research async (red flags, growth, concurrence).
        7. Évaluation stratégique LLM async.
        8. Calcul du score final pondéré.

    Ce module **ne sauvegarde rien** — la persistence est déléguée
    au pipeline (sourcing_pipeline.py) via sourcing_service.

    Args:
        platform_text: Texte de référence de la plateforme.
        target_urls:   Liste d'URLs candidates du Google Radar.
        company_dna:   Dict ADN de la plateforme (active le scoring LLM).
        min_revenue:   Borne basse filtre LBO en € (défaut: LBO_CA_MIN).
        max_revenue:   Borne haute filtre LBO en € (défaut: LBO_CA_MAX).
        known_revenues: CA déjà connu par URL (D12, Tâche B.3) — court-circuite
                       l'estimation OSINT pour les URLs présentes dans ce dict.

    Returns:
        Liste de dicts triée par final_score desc.
    """
    if not platform_text:
        logger.error("Texte de la plateforme vide. Scoring impossible.")
        return []

    if not target_urls:
        logger.error("Aucune URL cible à scorer.")
        return []

    use_llm = company_dna is not None
    results: list[dict] = []
    total = len(target_urls)

    _lbo_min = min_revenue if min_revenue is not None else LBO_CA_MIN
    _lbo_max = max_revenue if max_revenue is not None else LBO_CA_MAX

    logger.info("Début du scoring de {} cibles (mode {})…",
                total, "hybride TF-IDF + LLM" if use_llm else "TF-IDF seul")
    logger.info("-" * 50)

    for i, url in enumerate(target_urls, 1):
        logger.info("[{}/{}] Scraping → {}", i, total, url)

        # --- Étape 1 : Scraping async de la cible ---
        target_text = await extract_single_page(url)

        if not target_text or len(target_text.strip()) < MIN_TEXT_LENGTH:
            logger.warning("[{}/{}] SKIP — Contenu insuffisant.", i, total)
            continue

        logger.info("[{}/{}] {} caractères extraits.", i, total, len(target_text))

        # --- Étape 2 : Score TF-IDF (CPU, sync) ---
        tfidf_score = calculate_nlp_score(platform_text, target_text)

        # --- Étape 3 : Filtrage par seuil TF-IDF ---
        if tfidf_score < MIN_SCORE_THRESHOLD:
            logger.info("[{}/{}] REJETÉ — TF-IDF {:.1f} < seuil {:.1f}",
                        i, total, tfidf_score, MIN_SCORE_THRESHOLD)
            continue

        # --- Étape 4 : Estimation financière (async) ---
        estimation: dict = {
            "estimated_revenue": 0,
            "estimated_employees": 0,
            "estimation_source": "N/A",
        }
        target_name = extract_name_from_url(url)

        if use_llm:
            known_rev = known_revenues.get(url) if known_revenues else None
            estimation = await estimate_company_size(url, target_name, company_dna, known_revenue=known_rev)

            # Filtre LBO
            lbo_ok, lbo_reason = is_lbo_compatible(
                estimation, min_ca=_lbo_min, max_ca=_lbo_max,
            )
            if not lbo_ok:
                logger.info("[{}/{}] REJETÉ (LBO) — {}", i, total, lbo_reason)
                continue
            else:
                logger.info("[{}/{}] 💰 {}", i, total, lbo_reason)

        # --- Étape 5 : Valorisation M&A (Paper LBO 5 ans, sync) ---
        valo: dict = {
            "ebitda": 0.0, "ev": 0.0, "debt_capacity": 0.0,
            "required_equity": 0.0, "irr": 0.0, "moic": 0.0,
            "entry_multiple": 0.0, "projections": [],
        }
        if use_llm and estimation["estimated_revenue"] > 0:
            valo = run_lbo_model(
                estimation["estimated_revenue"],
                company_dna.get("sector", ""),
            )

        # --- Étape 6 : Deep Research async ---
        research_context: dict = {}
        if use_llm:
            research_context = await run_deep_research(target_name, url)

        # --- Étape 7 : Score LLM async ---
        llm_score = 0
        justification = "Scoring LLM non activé."
        growth_signals = ""
        red_flags = ""
        competitors: list = []

        if use_llm:
            logger.info("[{}/{}] Évaluation stratégique LLM…", i, total)
            llm_result = await get_llm_strategic_fit(
                company_dna, target_text, research_context,
            )
            llm_score = llm_result["llm_score"]
            justification = llm_result["strategic_fit"]
            growth_signals = llm_result["growth_signals"]
            red_flags = llm_result["red_flags"]
            competitors = llm_result["competitors"]

        # --- Étape 8 : Score final pondéré ---
        final_score = (
            round(WEIGHT_TFIDF * tfidf_score + WEIGHT_LLM * llm_score, 2)
            if use_llm
            else tfidf_score
        )

        logger.info(
            "[{}/{}] ✅ VALIDÉ — TF-IDF: {:.1f} | LLM: {} | Final: {:.1f} | CA: {}",
            i, total, tfidf_score, llm_score, final_score,
            format_revenue(estimation["estimated_revenue"]),
        )

        results.append({
            "url": url,
            "target_name": target_name,
            "tfidf_score": tfidf_score,
            "llm_score": llm_score,
            "final_score": final_score,
            "justification": justification,
            "estimated_revenue": estimation["estimated_revenue"],
            "estimated_employees": estimation["estimated_employees"],
            "estimation_source": estimation["estimation_source"],
            "growth_signals": growth_signals,
            "red_flags": red_flags,
            "competitors": competitors,
            "ebitda": valo.get("ebitda", 0.0),
            "ev": valo.get("ev", 0.0),
            "debt": valo.get("debt_capacity", 0.0),
            "equity": valo.get("required_equity", 0.0),
            "irr": valo.get("irr", 0.0),
            "moic": valo.get("moic", 0.0),
            "entry_multiple": valo.get("entry_multiple", 0.0),
            "lbo_projections": valo.get("projections", []),
        })

    # --- Tri décroissant par score final ---
    results.sort(key=lambda x: x["final_score"], reverse=True)

    logger.info("-" * 50)
    logger.info("Scoring terminé : {}/{} cibles retenues.", len(results), total)

    return results
