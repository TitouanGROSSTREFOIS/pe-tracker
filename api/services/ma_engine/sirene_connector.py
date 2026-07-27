"""
sirene_connector.py — Découverte d'univers d'entreprises françaises par code
NAF via les données Sirene (INSEE), pour le sourcing M&A (Tâche B.2, D5/Étape 2).

⚠️ SUBSTITUTION DE SOURCE DOCUMENTÉE (vérifiée empiriquement le 2026-07-21) :
    Le portail officiel INSEE Sirene (https://api.insee.fr/entreprises/sirene/V3.11)
    exige une clé API. Ce projet n'en possède aucune (aucune variable
    PE_INSEE_*/PE_SIRENE_* dans api/.env) — testé en direct : réponse
    HTTP 401 "Unauthorized" sans clé, confirmant que l'accès est bien
    verrouillé et non un problème de configuration locale.

    Ce connecteur utilise donc à la place l'API publique et gratuite
    **recherche-entreprises.api.gouv.fr**, qui EST une base Sirene/INSEE
    (mêmes données officielles), exposée sans clé par la DINUM. Vérifié
    empiriquement que cette API supporte : filtre par code NAF
    (`activite_principale`, format pointé "71.20B"), filtre par catégorie
    d'entreprise (`categorie_entreprise`), filtre par tranche d'effectif
    (`tranche_effectif_salarie`, codes INSEE), filtre par état administratif
    (`etat_administratif`), et pagination (`page`/`per_page`, max 25/page).

    Bonus constaté en testant (non demandé mais utile pour Étape 4) : chaque
    résultat inclut parfois un objet `finances` avec CA et résultat net —
    mais ce connecteur ne fait AUCUNE estimation ni interprétation de ce
    champ : il le restitue tel quel (ou None si absent). L'estimation par
    ratio NAF/effectif reste la responsabilité de financial_estimator.py,
    non modifié ici.

Rate limit : aucune limite officiellement documentée n'a été trouvée pour
cette API précise (contrairement au 30 req/min de l'API Sirene officielle
citée dans la tâche). Par prudence et pour respecter la lettre de la
consigne, ce connecteur applique la même limite stricte de 30 req/min via
un vrai rate limiter à fenêtre glissante (pas un sleep approximatif).

Pipeline (D7) : ce module ne fait AUCUN scoring, AUCUNE estimation
financière au-delà de ce que l'API restitue brut. Il produit uniquement
l'univers brut (candidats). Le scoring/qualification reste en aval,
inchangé (D7).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, AsyncIterator

import httpx
from loguru import logger


# ============================================================
# Constantes — Endpoint & pagination
# ============================================================

SIRENE_BASE_URL: str = "https://recherche-entreprises.api.gouv.fr/search"
REQUEST_TIMEOUT: float = 15.0
MAX_PER_PAGE: int = 25  # plafond constaté empiriquement (HTTP 400 au-delà)

# ============================================================
# Rate limiter — fenêtre glissante stricte (pas un sleep approximatif)
# ============================================================

RATE_LIMIT_MAX_CALLS: int = 30
RATE_LIMIT_PERIOD_SECONDS: float = 60.0


class SlidingWindowRateLimiter:
    """Limiteur de débit à fenêtre glissante, async-safe.

    Garantit qu'au plus `max_calls` appels sont effectués sur toute fenêtre
    de `period_seconds` secondes, en bloquant (await asyncio.sleep) le temps
    exact nécessaire — contrairement à un simple `sleep(2)` entre appels qui
    ne garantit rien sur des rafales.
    """

    def __init__(self, max_calls: int, period_seconds: float) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._evict_expired(now)

            if len(self._timestamps) >= self.max_calls:
                wait_for = self.period_seconds - (now - self._timestamps[0])
                if wait_for > 0:
                    logger.debug(
                        "[SIRENE] Rate limit atteint ({}/{} sur {}s) — pause {:.1f}s.",
                        len(self._timestamps), self.max_calls, self.period_seconds, wait_for,
                    )
                    await asyncio.sleep(wait_for)
                now = time.monotonic()
                self._evict_expired(now)

            self._timestamps.append(now)

    def _evict_expired(self, now: float) -> None:
        while self._timestamps and (now - self._timestamps[0]) >= self.period_seconds:
            self._timestamps.popleft()


_rate_limiter = SlidingWindowRateLimiter(RATE_LIMIT_MAX_CALLS, RATE_LIMIT_PERIOD_SECONDS)


# ============================================================
# Codes NAF — cœur de thèse TIC / Ingénierie technique
# ============================================================

# Format pointé requis par l'API (ex: "71.20B", pas "7120B").
CORE_NAF_CODES: dict[str, str] = {
    "71.20B": "Analyses, essais et inspections techniques",
    "71.12B": "Ingénierie, études techniques",
}

# Codes secondaires — configurables mais NON activés par défaut (cf. tâche).
SECONDARY_NAF_CODES: dict[str, str] = {
    "71.20A": "Contrôle technique automobile",
    "71.12A": "Activités des géomètres",
}

# Tranches d'effectif INSEE correspondant à "20 salariés et plus"
# (12=20-49, 21=50-99, 22=100-199, 31=200-249, 32=250-499, 41=500-999,
#  42=1000-1999, 51=2000-4999, 52=5000-9999, 53=10000+).
TRANCHE_EFFECTIF_20_PLUS: list[str] = [
    "12", "21", "22", "31", "32", "41", "42", "51", "52", "53",
]

DEFAULT_CATEGORIES: list[str] = ["PME", "ETI"]
DEFAULT_ETAT_ADMINISTRATIF: str = "A"  # actif uniquement


# ============================================================
# Appel API bas niveau (async, rate-limité)
# ============================================================

async def _call_sirene_api(client: httpx.AsyncClient, params: dict[str, Any]) -> dict | None:
    await _rate_limiter.acquire()
    try:
        resp = await client.get(SIRENE_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        logger.warning("[SIRENE] Timeout après {:.0f}s — params={}", REQUEST_TIMEOUT, params)
    except httpx.HTTPStatusError as e:
        logger.warning("[SIRENE] HTTP {} — {} — params={}", e.response.status_code, e.response.text[:200], params)
    except httpx.HTTPError as e:
        logger.warning("[SIRENE] Erreur réseau — {}", e)
    return None


def _normalize_result(raw: dict) -> dict[str, Any]:
    """Normalise un résultat brut de l'API en dict propre pour le pipeline.

    Champs Sirene purs uniquement — aucune estimation, aucun calcul.
    """
    return {
        "siren": raw.get("siren"),
        "denomination": raw.get("nom_complet") or raw.get("nom_raison_sociale"),
        "naf": raw.get("activite_principale"),
        "tranche_effectif_salarie": raw.get("tranche_effectif_salarie"),
        "annee_tranche_effectif_salarie": raw.get("annee_tranche_effectif_salarie"),
        "categorie_entreprise": raw.get("categorie_entreprise"),
        "commune": (raw.get("siege") or {}).get("libelle_commune"),
        "code_postal": (raw.get("siege") or {}).get("code_postal"),
        "date_creation": raw.get("date_creation"),
        "etat_administratif": raw.get("etat_administratif"),
        # Bonus non garanti — voir avertissement en tête de module.
        "finances": raw.get("finances") or None,
        "source": "sirene_insee_via_recherche_entreprises",
    }


# ============================================================
# Découverte par NAF — génération paginée (async)
# ============================================================

async def search_sirene_universe(
    naf_codes: list[str] | None = None,
    *,
    categories: list[str] | None = None,
    tranche_effectif_codes: list[str] | None = None,
    etat_administratif: str = DEFAULT_ETAT_ADMINISTRATIF,
    max_results: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Itère sur l'univers d'entreprises françaises matchant les filtres.

    Args:
        naf_codes:              codes NAF pointés (ex: ["71.20B", "71.12B"]).
                                 Défaut : CORE_NAF_CODES.
        categories:              ["PME", "ETI"] par défaut (GE exclu).
        tranche_effectif_codes:  codes INSEE de tranche d'effectif. Défaut :
                                 TRANCHE_EFFECTIF_20_PLUS (20 salariés et +).
        etat_administratif:      "A" (actif) par défaut.
        max_results:             plafond optionnel (arrête la pagination).

    Yields:
        Dicts normalisés (voir _normalize_result).
    """
    naf_codes = naf_codes or list(CORE_NAF_CODES.keys())
    categories = categories if categories is not None else DEFAULT_CATEGORIES
    tranche_effectif_codes = (
        tranche_effectif_codes if tranche_effectif_codes is not None
        else TRANCHE_EFFECTIF_20_PLUS
    )

    params: dict[str, Any] = {
        "activite_principale": ",".join(naf_codes),
        "etat_administratif": etat_administratif,
        "per_page": MAX_PER_PAGE,
    }
    if categories:
        params["categorie_entreprise"] = ",".join(categories)
    if tranche_effectif_codes:
        params["tranche_effectif_salarie"] = ",".join(tranche_effectif_codes)

    yielded = 0
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            data = await _call_sirene_api(client, {**params, "page": page})
            if data is None:
                logger.error("[SIRENE] Échec page {} — arrêt de la pagination.", page)
                return

            total = data.get("total_results", 0)
            results = data.get("results", [])
            if page == 1:
                logger.info(
                    "[SIRENE] Univers total pour NAF={} / cat={} / effectif={} / état={} : {} entités.",
                    naf_codes, categories, "20+" if tranche_effectif_codes else "tous",
                    etat_administratif, total,
                )

            if not results:
                return

            for raw in results:
                yield _normalize_result(raw)
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return

            # Fin de pagination : moins d'une page pleine, ou plafond ES atteint.
            if len(results) < MAX_PER_PAGE:
                return
            page += 1


async def count_universe(
    naf_codes: list[str] | None = None,
    *,
    categories: list[str] | None = None,
    tranche_effectif_codes: list[str] | None = None,
    etat_administratif: str = DEFAULT_ETAT_ADMINISTRATIF,
) -> int:
    """Retourne uniquement le nombre total d'entités matchant les filtres
    (1 seul appel API, per_page=1) — utile pour dimensionner l'univers sans
    tout paginer.
    """
    naf_codes = naf_codes or list(CORE_NAF_CODES.keys())
    categories = categories if categories is not None else DEFAULT_CATEGORIES
    tranche_effectif_codes = (
        tranche_effectif_codes if tranche_effectif_codes is not None
        else TRANCHE_EFFECTIF_20_PLUS
    )

    params: dict[str, Any] = {
        "activite_principale": ",".join(naf_codes),
        "etat_administratif": etat_administratif,
        "per_page": 1,
    }
    if categories:
        params["categorie_entreprise"] = ",".join(categories)
    if tranche_effectif_codes:
        params["tranche_effectif_salarie"] = ",".join(tranche_effectif_codes)

    async with httpx.AsyncClient() as client:
        data = await _call_sirene_api(client, params)
    return data.get("total_results", 0) if data else 0


# ============================================================
# Lookup ponctuel par SIREN (réutilisable pour l'enrichissement)
# ============================================================

async def get_company_by_siren(siren: str) -> dict[str, Any] | None:
    """Récupère la fiche Sirene d'une entreprise précise par son SIREN.

    Utilisé pour l'enrichissement financier (D8, source 1) — mêmes données,
    même endpoint, un seul résultat.
    """
    async with httpx.AsyncClient() as client:
        data = await _call_sirene_api(client, {"q": siren, "per_page": 1})

    if not data:
        return None
    results = data.get("results", [])
    if not results:
        return None
    return _normalize_result(results[0])
