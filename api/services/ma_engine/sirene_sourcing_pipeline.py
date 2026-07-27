"""
sirene_sourcing_pipeline.py — Orchestration du sourcing M&A avec Sirene comme
source PRIMAIRE de constitution de l'univers (Tâche B.2, D5/D6/D7 ; qualification
registre revue en Tâche B.3, D10/D11/D12).

    1. DÉCOUVERTE (D5, source 1) — sirene_connector.search_sirene_universe()
       filtre l'univers officiel Sirene par code NAF + taille. Aucune IA,
       aucun scoring à ce stade (D7).
    2. DÉDUPLICATION (D6) — par SIREN, colonne dédiée (Tâche B.3 ; auparavant
       un préfixe texte dans business_summary, migré — voir RAPPORT B.3).
    3. RÉSOLUTION D'URL — un candidat Sirene n'a pas de site web ; une requête
       Serper légère (1 requête/candidat) tente de résoudre son domaine
       officiel. Les candidats sans URL résolue sont écartés et comptés.
    4. QUALIFICATION REGISTRE (D10, Tâche B.3) — le TF-IDF (similarity_scorer.
       rank_targets) est COURT-CIRCUITÉ pour cette voie : la pertinence
       sectorielle est acquise par le code NAF (déterministe, garanti par la
       découverte à l'étape 1), la taille vient du CA réel du registre (D11),
       et seule la note LLM (similarity_scorer.get_llm_strategic_fit, RÉUTILISÉE
       SANS MODIFICATION DE PROMPT) évalue la pertinence business. Voir
       _qualify_registry_candidate() et RAPPORT B.3 § FORMULE DE SCORE.
    5. PERSISTENCE — via sourcing_service.create_target, avec siren/source/
       target_type en colonnes dédiées (Tâche B.3).

Le flux Google Radar (sourcing_pipeline.run_full_sourcing_scan) reste
disponible séparément, inchangé, TF-IDF actif (D10, "voie Radar").
"""
from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from api.config import get_settings
from api.models.sourcing import SourcedTarget
from api.schemas.sourcing import SourcedTargetCreate
from api.services.sourcing_service import create_target, get_target_by_url
from api.services.ma_engine.sirene_connector import search_sirene_universe
from api.services.ma_engine.google_radar import (
    SERPER_URL,
    SERPER_NUM_RESULTS,
    REQUEST_TIMEOUT as RADAR_REQUEST_TIMEOUT,
    _is_blacklisted,
    _extract_root_domain,
)
from api.services.ma_engine.website_scraper import extract_text_from_url
from api.services.ma_engine.similarity_scorer import get_llm_strategic_fit


URL_RESOLUTION_DELAY_SECONDS = 3.0  # entre 2 requêtes Serper de résolution d'URL

# ============================================================
# D10/D11 — Qualification registre (Tâche B.3)
# ============================================================

# Bornes CA (D11) — cœur de la thèse. Au-delà, "platform" ; en-deçà, rejeté.
TARGET_CA_MIN: float = 10_000_000
TARGET_CA_MAX: float = 100_000_000

# Seuil minimal de note LLM pour qualifier (D10). Le prompt existant
# (similarity_scorer.LLM_SYSTEM_PROMPT, INCHANGÉ) attribue déjà 0 aux
# médias/blogs/annuaires — ce seuil filtre juste le bruit résiduel sans
# durcir excessivement, la pertinence sectorielle étant déjà acquise par NAF.
QUALIFICATION_LLM_MIN: float = 20.0

# Poids de la formule de score final (voir RAPPORT B.3 § FORMULE DE SCORE) :
#   final_score = SCORE_WEIGHT_LLM * llm_score + SCORE_WEIGHT_SIZE * size_fit_score
# size_fit_score = 100 si target_type == "target" (cœur de thèse, 10-100M€),
#                  70  si target_type == "platform" (>100M€, toujours pertinent
#                       comme plateforme de consolidation, mais pas une CIBLE).
SCORE_WEIGHT_LLM: float = 0.75
SCORE_WEIGHT_SIZE: float = 0.25
SIZE_FIT_TARGET: float = 100.0
SIZE_FIT_PLATFORM: float = 70.0

MIN_SCRAPE_CHARS: int = 200

# Domaines constatés en test comme faux positifs de résolution d'URL —
# annuaires/portails publics qui ne sont blacklistés nulle part ailleurs car
# google_radar.py cible un cas d'usage différent (découverte par mots-clés,
# pas résolution de nom d'entreprise).
URL_RESOLUTION_EXTRA_BLACKLIST: frozenset[str] = frozenset({
    "data.gouv.fr", "service-public.fr", "impots.gouv.fr", "legifrance.gouv.fr",
    "insee.fr", "bodacc.fr", "annuaire-entreprises.data.gouv.fr",
})

# ADN de thèse statique — sert de "plateforme de référence" au LLM existant
# (similarity_scorer.get_llm_strategic_fit, RÉUTILISÉ SANS MODIFICATION), à la
# place d'un site scrapé.
#
# ⚠️ HISTORIQUE (Tâche B.2 → B.3) : ce module utilisait auparavant aussi
# similarity_scorer.rank_targets (TF-IDF + LLM) pour qualifier les candidats
# Sirene. Constat empirique en B.2 : le TF-IDF, conçu pour comparer deux
# pages web scrapées entre elles, rejetait des acteurs évidents du secteur
# (DEKRA, Qualiconsult) car comparés à un texte de thèse synthétique. La
# Tâche B.3 (D10) court-circuite désormais le TF-IDF pour la voie registre :
# la pertinence sectorielle est déjà garantie par le code NAF (déterministe),
# et seule la note LLM sur le descriptif d'activité reste utile ici. Voir
# _qualify_registry_candidate() plus bas.
THESIS_DNA: dict = {
    "company_name": "Thèse Buy & Build TIC/Ingénierie Technique",
    "sector": "Test, Inspection, Certification (TIC) & Ingénierie technique",
    "business_model": (
        "Bureaux de contrôle technique, laboratoires d'essais indépendants, "
        "bureaux d'études et d'ingénierie technique, sociétés de contrôle "
        "non destructif (CND), organismes d'inspection réglementaire."
    ),
    "value_proposition": (
        "Expertise technique réglementée, indépendance vis-à-vis des maîtres "
        "d'ouvrage, récurrence liée aux obligations légales de contrôle."
    ),
    "target_audience": "Maîtres d'ouvrage BTP/industrie, promoteurs, industriels, collectivités.",
    "geographic_focus": "France, avec optionnalité d'expansion Europe.",
    "search_keywords": [
        "contrôle technique", "essais et inspections", "ingénierie technique",
        "bureau d'études", "contrôle non destructif", "laboratoire d'essais",
    ],
}

# ============================================================
# Étape 2 — Déduplication par SIREN (D6, colonne dédiée depuis la Tâche B.3)
# ============================================================

async def _get_known_sirens(db: AsyncSession) -> set[str]:
    result = await db.execute(select(SourcedTarget.siren).where(SourcedTarget.siren.is_not(None)))
    return {row[0] for row in result.all()}


# ============================================================
# Étape 3 — Résolution d'URL (Serper, 1 requête légère par candidat)
# ============================================================

async def _resolve_website_url(client: httpx.AsyncClient, denomination: str) -> str | None:
    settings = get_settings()
    if not settings.serper_api_key:
        return None

    query = f'"{denomination}" site officiel'
    try:
        resp = await client.post(
            SERPER_URL,
            json={"q": query, "gl": "fr", "hl": "fr", "num": SERPER_NUM_RESULTS},
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            timeout=RADAR_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        logger.warning("  [URL-RESOLVE] Échec Serper pour '{}' — {}", denomination, e)
        return None

    for item in data.get("organic", []):
        link = item.get("link", "")
        if not link or _is_blacklisted(link):
            continue
        hostname = httpx.URL(link).host or ""
        if any(hostname == d or hostname.endswith(f".{d}") for d in URL_RESOLUTION_EXTRA_BLACKLIST):
            continue
        return _extract_root_domain(link)
    return None


# ============================================================
# Pipeline principal — Sirene primaire (D5/D6/D7)
# ============================================================

def _classify_target_type(real_ca: float | None) -> str | None:
    """D11 — typologie par taille, à partir du CA réel (registre) uniquement."""
    if real_ca is None:
        return None
    if real_ca < TARGET_CA_MIN:
        return None  # hors thèse, non retenu
    return "platform" if real_ca > TARGET_CA_MAX else "target"


async def _qualify_registry_candidate(candidate: dict) -> tuple[dict | None, str | None]:
    """Qualifie un candidat issu du registre Sirene (D10, Tâche B.3).

    Qualification = 3 critères explicites :
      1. Pertinence sectorielle — ACQUISE par le code NAF (déterministe,
         garantie par search_sirene_universe en amont). Aucun recalcul ici.
      2. Taille — CA RÉEL du registre (D12 : jamais redécouvert par OSINT),
         classé selon D11 (_classify_target_type). CA absent ou < 10M€ →
         rejeté ici, avant tout appel LLM (économie de budget).
      3. Note LLM — similarity_scorer.get_llm_strategic_fit(), RÉUTILISÉE SANS
         MODIFICATION DE PROMPT. Seule adaptation : le texte cible est scrapé
         via website_scraper.extract_text_from_url() (crawl multi-pages) et
         non extract_single_page() (utilisé par rank_targets/voie Radar) —
         testé empiriquement : une page d'accueil scrapée seule (souvent
         dominée par la navigation/actualités) produit de faux négatifs LLM
         (ex: SGS France jugé "média" à tort sur son homepage seule, score
         0 → 80 avec le crawl multi-pages). C'est un choix d'orchestration
         (quel texte on scrape), pas une modification du prompt ni du moteur.

    Retourne (résultat, None) si qualifié, ou (None, raison) sinon — raison ∈
    {"ca_out_of_range", "scrape_insufficient", "llm_below_threshold"}.
    """
    sirene_finances = candidate.get("finances") or {}
    real_ca = None
    if sirene_finances:
        latest_year = sorted(sirene_finances.keys(), reverse=True)[0]
        real_ca = sirene_finances[latest_year].get("ca")

    target_type = _classify_target_type(real_ca)
    if target_type is None:
        return None, "ca_out_of_range"  # CA inconnu ou < 10M€ (D11)

    text = await extract_text_from_url(candidate["url"])
    if not text or len(text.strip()) < MIN_SCRAPE_CHARS:
        logger.info("  ⚠️ Scraping insuffisant pour '{}' — non qualifiable.", candidate["denomination"])
        return None, "scrape_insufficient"

    llm_result = await get_llm_strategic_fit(THESIS_DNA, text, {})
    llm_score = llm_result["llm_score"]

    if llm_score < QUALIFICATION_LLM_MIN:
        logger.info("  ❌ REJETÉ (LLM) — '{}' score={} < seuil {}",
                     candidate["denomination"], llm_score, QUALIFICATION_LLM_MIN)
        return None, "llm_below_threshold"

    size_fit = SIZE_FIT_TARGET if target_type == "target" else SIZE_FIT_PLATFORM
    final_score = round(SCORE_WEIGHT_LLM * llm_score + SCORE_WEIGHT_SIZE * size_fit, 2)

    logger.info("  ✅ QUALIFIÉ — '{}' [{}] CA={:,.0f}€ LLM={} → final={}",
                 candidate["denomination"], target_type, real_ca, llm_score, final_score)

    return {
        "llm_score": llm_score,
        "justification": llm_result["strategic_fit"],
        "growth_signals": llm_result["growth_signals"],
        "red_flags": llm_result["red_flags"],
        "competitors": llm_result["competitors"],
        "final_score": final_score,
        "target_type": target_type,
        "real_ca": real_ca,
    }, None


async def run_sirene_sourcing_scan(
    db: AsyncSession,
    *,
    naf_codes: list[str] | None = None,
    categories: list[str] | None = None,
    tranche_effectif_codes: list[str] | None = None,
    max_candidates: int = 20,
    enable_google_radar: bool = False,  # D5 : Radar rétrogradé, option explicite
) -> dict:
    """Exécute un scan de sourcing Sirene-first : Découverte → Dédup SIREN →
    Résolution URL → Qualification registre (D10) → DB.

    `enable_google_radar` est accepté pour respecter la consigne "Radar
    disponible en option explicite", mais n'est PAS implémenté dans cette
    fonction (fusionner un flux Radar-additionnel dans ce même run toucherait la
    logique d'assemblage des candidats bien au-delà du périmètre minimal
    autorisé). Le flux Radar existant (sourcing_pipeline.run_full_sourcing_scan)
    reste utilisable séparément et inchangé, TF-IDF actif (D10, "voie Radar").
    """
    if enable_google_radar:
        logger.warning(
            "[SIRENE-PIPELINE] enable_google_radar=True demandé mais non implémenté "
            "dans cette fonction — utiliser sourcing_pipeline.run_full_sourcing_scan "
            "séparément pour un scan Google Radar (D5, source 2)."
        )

    logger.info("=" * 60)
    logger.info("🚀 SOURCING PIPELINE (Sirene primaire) — Démarrage")
    logger.info("=" * 60)

    known_sirens = await _get_known_sirens(db)
    logger.info("  {} SIREN déjà en base (dédup D6).", len(known_sirens))

    stats = {
        "sirene_candidates_seen": 0,
        "duplicates_skipped": 0,
        "url_resolution_failed": 0,
        "url_resolved": 0,
        "rejected_ca_out_of_range": 0,
        "rejected_llm": 0,
        "rejected_scrape_insufficient": 0,
        "targets_saved": 0,
        "targets_by_type": {"target": 0, "platform": 0},
        "results": [],
    }

    # max_candidates borne le nombre de CANDIDATS SIRENE BRUTS EXAMINÉS (pas
    # le nombre qualifié à l'arrivée) — c'est la lecture littérale de
    # l'Étape 3 ("échantillon de 100 unités légales"), et ça borne le temps
    # d'exécution indépendamment du taux de réussite de résolution d'URL
    # (constaté variable et parfois faible sur la longue traîne du registre —
    # voir RAPPORT B.3).
    to_qualify: list[dict] = []

    async with httpx.AsyncClient() as client:
        async for candidate in search_sirene_universe(
            naf_codes=naf_codes,
            categories=categories,
            tranche_effectif_codes=tranche_effectif_codes,
            max_results=max_candidates,
        ):
            stats["sirene_candidates_seen"] += 1

            siren = candidate["siren"]
            if not siren or siren in known_sirens:
                stats["duplicates_skipped"] += 1
                continue

            url = await _resolve_website_url(client, candidate["denomination"])
            await asyncio.sleep(URL_RESOLUTION_DELAY_SECONDS)

            if not url:
                stats["url_resolution_failed"] += 1
                logger.info("  ⚠️ URL non résolue pour '{}' (SIREN {}) — écarté.",
                             candidate["denomination"], siren)
                continue

            existing = await get_target_by_url(db, url)
            if existing:
                stats["duplicates_skipped"] += 1
                continue

            stats["url_resolved"] += 1
            to_qualify.append({**candidate, "url": url})

    logger.info("  {} candidats Sirene avec URL résolue, prêts pour qualification registre (D10).",
                 len(to_qualify))

    if not to_qualify:
        logger.warning("  Aucun candidat à qualifier — arrêt.")
        return stats

    # ── Qualification registre (D10) — voir _qualify_registry_candidate() ──
    for candidate in to_qualify:
        siren = candidate["siren"]
        naf = candidate.get("naf", "?")

        qualification, rejection_reason = await _qualify_registry_candidate(candidate)
        if qualification is None:
            if rejection_reason == "ca_out_of_range":
                stats["rejected_ca_out_of_range"] += 1
            elif rejection_reason == "scrape_insufficient":
                stats["rejected_scrape_insufficient"] += 1
            else:
                stats["rejected_llm"] += 1
            continue

        target_create = SourcedTargetCreate(
            company_name=candidate.get("denomination", "Inconnu"),
            url=candidate["url"],
            siren=siren,
            source="registry",
            target_type=qualification["target_type"],
            business_summary=qualification["justification"],
            keywords=THESIS_DNA["search_keywords"],
            score=qualification["final_score"],
            revenue_estimate=qualification["real_ca"],
            growth_signals=[qualification["growth_signals"]] if qualification.get("growth_signals") else None,
            red_flags=[qualification["red_flags"]] if qualification.get("red_flags") else None,
            competitors=qualification.get("competitors") or None,
            status="Watchlist",
        )

        try:
            target = await create_target(db, target_create)
            await db.commit()
            stats["targets_saved"] += 1
            stats["targets_by_type"][qualification["target_type"]] += 1
            stats["results"].append({
                "id": target.id, "siren": siren, "company_name": target.company_name,
                "url": target.url, "score": target.score, "revenue_estimate": target.revenue_estimate,
                "target_type": qualification["target_type"],
            })
            logger.info("  💾 Sauvegardé : {} (SIREN {}, id={}, type={}, score={})",
                         target.company_name, siren, target.id, qualification["target_type"], target.score)
        except Exception as e:
            await db.rollback()
            logger.error("  ❌ Erreur sauvegarde SIREN {} : {}", siren, e)

    logger.info("=" * 60)
    logger.info("🏁 PIPELINE SIRENE TERMINÉ — {} sauvegardées / {} candidats vus",
                 stats["targets_saved"], stats["sirene_candidates_seen"])
    logger.info("=" * 60)

    return stats
