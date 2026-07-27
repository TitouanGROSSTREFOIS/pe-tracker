"""
financial_estimator.py — Estimation async de la taille financière des cibles non-cotées.

Logique de triangulation en cascade (Waterfall) — 100 % gratuit :

    Étape 1 — Vérité Légale (API Gouv)
        Appel GET à recherche-entreprises.api.gouv.fr/search?q={name}
        Récupère activite_principale (code NAF).
        Tente d'extraire le chiffre_affaires.  Si CA > 0 → Source = "API Gouv (Exact)".

    Étape 2 — Proxy Légal (Ratio basé sur le vrai code NAF)
        CA absent mais tranche_effectif_salarie connue →
        Médiane tranche × ratio NAF → CA proxy.

    Étape 3 — Proxy Digital (OSINT via Serper)
        Entreprise absente de l'API Gouv →
        Requête Serper LinkedIn → Regex employés → CA proxy.

    Filtres LBO : CA < 1 M€ (trop petit) ou > 50 M€ (trop gros) → rejeté.

Adapted from the original sync module for the pe_tracker FastAPI backend.
All I/O is fully async (httpx.AsyncClient).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from loguru import logger

from api.config import get_settings


# ============================================================
# Constantes — URLs & Timeouts
# ============================================================

API_GOUV_SEARCH_URL: str = "https://recherche-entreprises.api.gouv.fr/search"
SERPER_SEARCH_URL: str = "https://google.serper.dev/search"

API_GOUV_TIMEOUT: float = 10.0
SERPER_TIMEOUT: float = 10.0


# ============================================================
# Dictionnaire NAF (2 chiffres) → Ratio CA / ETP (€ / an)
#
# Sources croisées :
#   - INSEE « Tableaux de l'économie française » 2023-2024
#   - Xerfi Specific « Profils sectoriels PME »
#   - EY PE Barometer Europe 2024
# ============================================================

NAF_REVENUE_RATIOS: dict[str, tuple[int, str]] = {
    # ── Agriculture / Pêche ──────────────────────────────────
    "01": (110_000, "Culture et production animale"),
    "02": (100_000, "Sylviculture"),
    "03": (120_000, "Pêche et aquaculture"),
    # ── Industrie alimentaire ────────────────────────────────
    "10": (220_000, "Industrie alimentaire"),
    "11": (280_000, "Fabrication de boissons"),
    "12": (300_000, "Fabrication de produits à base de tabac"),
    # ── Textile / Habillement / Cuir ─────────────────────────
    "13": (130_000, "Fabrication de textiles"),
    "14": (140_000, "Industrie de l'habillement"),
    "15": (160_000, "Industrie du cuir et de la chaussure"),
    # ── Bois / Papier / Imprimerie ───────────────────────────
    "16": (170_000, "Travail du bois"),
    "17": (200_000, "Industrie du papier et du carton"),
    "18": (150_000, "Imprimerie et reproduction"),
    # ── Chimie / Pharma ──────────────────────────────────────
    "20": (280_000, "Industrie chimique"),
    "21": (350_000, "Industrie pharmaceutique"),
    # ── Plastique / Minéraux non métalliques ─────────────────
    "22": (200_000, "Fabrication de produits en caoutchouc/plastique"),
    "23": (190_000, "Fabrication d'autres produits minéraux non métalliques"),
    # ── Métallurgie ──────────────────────────────────────────
    "24": (250_000, "Métallurgie"),
    "25": (180_000, "Fabrication de produits métalliques"),
    # ── Électronique / Optique ───────────────────────────────
    "26": (220_000, "Fabrication de produits informatiques, électroniques"),
    "27": (210_000, "Fabrication d'équipements électriques"),
    "28": (200_000, "Fabrication de machines et équipements"),
    # ── Transport / Construction automobile ───────────────────
    "29": (300_000, "Industrie automobile"),
    "30": (250_000, "Fabrication d'autres matériels de transport"),
    # ── Autres industries ────────────────────────────────────
    "31": (150_000, "Fabrication de meubles"),
    "32": (160_000, "Autres industries manufacturières"),
    "33": (130_000, "Réparation et installation de machines"),
    # ── Énergie / Eau / Déchets ──────────────────────────────
    "35": (400_000, "Production et distribution d'électricité/gaz"),
    "36": (200_000, "Captage, traitement et distribution d'eau"),
    "37": (160_000, "Collecte et traitement des eaux usées"),
    "38": (170_000, "Collecte, traitement et élimination des déchets"),
    "39": (150_000, "Dépollution et autres services de gestion des déchets"),
    # ── BTP / Construction ───────────────────────────────────
    "41": (200_000, "Construction de bâtiments"),
    "42": (210_000, "Génie civil"),
    "43": (150_000, "Travaux de construction spécialisés"),
    # ── Commerce (gros / détail) ─────────────────────────────
    "45": (350_000, "Commerce et réparation d'automobiles"),
    "46": (450_000, "Commerce de gros"),
    "47": (200_000, "Commerce de détail"),
    # ── Transport / Entreposage ──────────────────────────────
    "49": (180_000, "Transports terrestres"),
    "50": (250_000, "Transports par eau"),
    "51": (300_000, "Transports aériens"),
    "52": (200_000, "Entreposage et services auxiliaires des transports"),
    "53": (120_000, "Activités de poste et de courrier"),
    # ── Hébergement / Restauration ───────────────────────────
    "55": (80_000,  "Hébergement"),
    "56": (70_000,  "Restauration"),
    # ── Édition / Audiovisuel / Télécom ──────────────────────
    "58": (180_000, "Édition (dont édition de logiciels)"),
    "59": (150_000, "Production de films cinématographiques / audiovisuel"),
    "60": (160_000, "Programmation et diffusion"),
    "61": (300_000, "Télécommunications"),
    # ── Informatique / Programmation ─────────────────────────
    "62": (130_000, "Programmation, conseil et autres activités informatiques"),
    "63": (160_000, "Services d'information"),
    # ── Finance / Assurance ──────────────────────────────────
    "64": (350_000, "Activités des services financiers (hors assurance)"),
    "65": (300_000, "Assurance"),
    "66": (200_000, "Activités auxiliaires de services financiers"),
    # ── Immobilier ───────────────────────────────────────────
    "68": (250_000, "Activités immobilières"),
    # ── Activités spécialisées, scientifiques, techniques ────
    "69": (130_000, "Activités juridiques et comptables"),
    "70": (150_000, "Activités des sièges sociaux ; conseil de gestion"),
    "71": (120_000, "Activités d'architecture et d'ingénierie"),
    "72": (140_000, "Recherche-développement scientifique"),
    "73": (130_000, "Publicité et études de marché"),
    "74": (110_000, "Autres activités spécialisées, scientifiques et techniques"),
    "75": (100_000, "Activités vétérinaires"),
    # ── Services administratifs / Soutien ────────────────────
    "77": (200_000, "Activités de location et location-bail"),
    "78": (100_000, "Activités liées à l'emploi"),
    "79": (150_000, "Activités des agences de voyage et voyagistes"),
    "80": (120_000, "Enquêtes et sécurité"),
    "81": (70_000,  "Services relatifs aux bâtiments et aménagement paysager"),
    "82": (100_000, "Activités administratives et autres activités de soutien"),
    # ── Enseignement ─────────────────────────────────────────
    "85": (80_000,  "Enseignement"),
    # ── Santé / Action sociale ───────────────────────────────
    "86": (120_000, "Activités pour la santé humaine"),
    "87": (80_000,  "Hébergement médico-social et social"),
    "88": (60_000,  "Action sociale sans hébergement"),
    # ── Arts / Loisirs ───────────────────────────────────────
    "90": (100_000, "Activités créatives, artistiques et de spectacle"),
    "91": (80_000,  "Bibliothèques, archives, musées"),
    "92": (200_000, "Organisation de jeux de hasard et d'argent"),
    "93": (90_000,  "Activités sportives, récréatives et de loisirs"),
    # ── Autres services ──────────────────────────────────────
    "94": (80_000,  "Activités des organisations associatives"),
    "95": (100_000, "Réparation d'ordinateurs et de biens personnels"),
    "96": (70_000,  "Autres services personnels"),
}

# Ratio moyen global — fallback LinkedIn (Étape 3)
GLOBAL_FALLBACK_RATIO: int = 150_000


# ============================================================
# Mapping des tranches d'effectifs INSEE (codes numériques)
# ============================================================

INSEE_TRANCHE_MAP: dict[str, tuple[int, int]] = {
    "00": (0, 0),
    "01": (1, 2),
    "02": (3, 5),
    "03": (6, 9),
    "11": (10, 19),
    "12": (20, 49),
    "21": (50, 99),
    "22": (100, 199),
    "31": (200, 249),
    "32": (250, 499),
    "41": (500, 999),
    "42": (1_000, 1_999),
    "51": (2_000, 4_999),
    "52": (5_000, 9_999),
    "53": (10_000, 10_000),
}

_TRANCHE_TEXT_MAP: dict[str, tuple[int, int]] = {
    "0 salarié":                (0, 0),
    "1 ou 2 salariés":          (1, 2),
    "1 à 2 salariés":           (1, 2),
    "3 à 5 salariés":           (3, 5),
    "6 à 9 salariés":           (6, 9),
    "10 à 19 salariés":         (10, 19),
    "20 à 49 salariés":         (20, 49),
    "50 à 99 salariés":         (50, 99),
    "100 à 199 salariés":       (100, 199),
    "200 à 249 salariés":       (200, 249),
    "250 à 499 salariés":       (250, 499),
    "500 à 999 salariés":       (500, 999),
    "1 000 à 1 999 salariés":   (1_000, 1_999),
    "2 000 à 4 999 salariés":   (2_000, 4_999),
    "5 000 à 9 999 salariés":   (5_000, 9_999),
    "10 000 salariés et plus":  (10_000, 10_000),
}


# ============================================================
# Filtres LBO : bornes de CA pour un bolt-on build-up
# ============================================================

LBO_CA_MIN: int = 1_000_000     # 1 M€ — trop petit
LBO_CA_MAX: int = 50_000_000    # 50 M€ — trop gros pour bolt-on


# ============================================================
# Regex LinkedIn — Extraction de la tranche d'employés
# ============================================================

LINKEDIN_EMP_REGEX = re.compile(
    r"(\d[\d\s.,]*)\s*[-\u2013\u2014]\s*(\d[\d\s.,]*)"
    r"\s*(?:employees?|employ[ée]s?|salari[ée]s?|collaborateurs?)",
    re.IGNORECASE,
)

LINKEDIN_EMP_PLUS_REGEX = re.compile(
    r"(\d[\d\s.,]*)\s*\+\s*(?:employees?|employ[ée]s?|salari[ée]s?|collaborateurs?)",
    re.IGNORECASE,
)


# ============================================================
# Noms trop génériques (polluent les recherches API Gouv)
# ============================================================

GENERIC_NAME_BLACKLIST: frozenset[str] = frozenset({
    "finance", "services", "solutions", "digital", "tech",
    "group", "consulting", "pro", "online", "web", "net",
    "info", "data", "cloud", "app", "media", "market",
    "capital", "partners", "ventures", "holdings",
})


# ============================================================
# Helpers internes — Pure functions (pas d'I/O)
# ============================================================

def _clean_number(s: str) -> int:
    """Nettoie une chaîne numérique (espaces, virgules, points) → int."""
    return int(re.sub(r"[\s.,]", "", s))


def _parse_tranche_code(code: str) -> tuple[float, str]:
    """Convertit un code INSEE de tranche en médiane et label."""
    code = str(code).strip()
    bounds = INSEE_TRANCHE_MAP.get(code)
    if bounds:
        low, high = bounds
        median = (low + high) / 2
        label = f"INSEE {code} ({low}-{high} sal.)"
        return median, label
    return 0.0, ""


def _parse_tranche_text(text: str) -> float:
    """Fallback : extrait la médiane d'une chaîne textuelle (ancien format)."""
    if not text:
        return 0.0

    text_lower = text.lower().strip()
    for key, (low, high) in _TRANCHE_TEXT_MAP.items():
        if key.lower() in text_lower:
            return (low + high) / 2

    numbers = re.findall(r"\d+", text.replace(" ", ""))
    if len(numbers) >= 2:
        return (int(numbers[0]) + int(numbers[1])) / 2
    if len(numbers) == 1:
        return float(numbers[0])

    return 0.0


def _is_generic_name(name: str) -> bool:
    """Vérifie si le nom est trop générique pour une recherche fiable."""
    clean = name.lower().strip()
    if len(clean) <= 2:
        return True
    return clean in GENERIC_NAME_BLACKLIST


def _naf_to_ratio(naf_code: str | None) -> tuple[int, str]:
    """Convertit un code NAF complet en ratio CA/ETP."""
    if not naf_code:
        return GLOBAL_FALLBACK_RATIO, "Code NAF inconnu"

    digits = re.sub(r"[^0-9]", "", naf_code)
    naf_2 = digits[:2] if len(digits) >= 2 else ""

    entry = NAF_REVENUE_RATIOS.get(naf_2)
    if entry:
        ratio, label = entry
        return ratio, f"NAF {naf_code} → {naf_2} ({label})"

    return GLOBAL_FALLBACK_RATIO, f"NAF {naf_code} → {naf_2} (non répertorié, ratio global)"


def _extract_naf_code(gouv_data: dict) -> str | None:
    """Extrait le code NAF (activite_principale) depuis la réponse API Gouv."""
    naf = gouv_data.get("activite_principale")
    if naf and isinstance(naf, str) and len(naf) >= 2:
        return naf
    return None


def _extract_ca_from_gouv(gouv_data: dict) -> float | None:
    """Extrait le CA depuis l'objet finances (dict ou list par année).

    Prend l'année la plus récente avec ca > 0.
    """
    finances = gouv_data.get("finances")

    # Structure principale : dict par année
    if isinstance(finances, dict) and finances:
        years = sorted(finances.keys(), reverse=True)
        for year in years:
            year_data = finances[year]
            if not isinstance(year_data, dict):
                continue
            ca = year_data.get("ca") or year_data.get("chiffre_affaires")
            if ca is not None and isinstance(ca, (int, float)) and ca > 0:
                logger.info("  Finances {} : CA = {:,.0f} €", year, ca)
                return float(ca)

    # Structure alternative : liste de dicts
    if isinstance(finances, list) and finances:
        for entry in finances:
            if not isinstance(entry, dict):
                continue
            ca = entry.get("ca") or entry.get("chiffre_affaires")
            if ca is not None and isinstance(ca, (int, float)) and ca > 0:
                return float(ca)

    # Champ direct (très rare)
    ca_direct = gouv_data.get("chiffre_affaires")
    if ca_direct is not None and isinstance(ca_direct, (int, float)) and ca_direct > 0:
        return float(ca_direct)

    return None


def _extract_effectif_from_gouv(gouv_data: dict) -> tuple[float, str]:
    """Extrait les effectifs depuis la réponse API Gouv (cascade 5 sources)."""
    # 1) Code INSEE au niveau unité légale
    tranche_code = gouv_data.get("tranche_effectif_salarie", "")
    if tranche_code and isinstance(tranche_code, str) and tranche_code != "NN":
        median, label = _parse_tranche_code(tranche_code)
        if median > 0:
            return median, label

    # 2) Code INSEE dans le siège
    siege = gouv_data.get("siege", {})
    if isinstance(siege, dict):
        siege_code = siege.get("tranche_effectif_salarie", "")
        if siege_code and isinstance(siege_code, str) and siege_code != "NN":
            median, label = _parse_tranche_code(siege_code)
            if median > 0:
                return median, f"{label} (siège)"

    # 3) Établissements rattachés
    matching = gouv_data.get("matching_etablissements", [])
    if isinstance(matching, list):
        for etab in matching[:5]:
            if isinstance(etab, dict):
                etab_code = etab.get("tranche_effectif_salarie", "")
                if etab_code and isinstance(etab_code, str) and etab_code != "NN":
                    median, label = _parse_tranche_code(etab_code)
                    if median > 0:
                        return median, f"{label} (établissement)"

    # 4) Nombre exact d'employés
    for field in ("nombre_employes", "effectif", "nb_employes"):
        val = gouv_data.get(field)
        if val is not None and isinstance(val, (int, float)) and val > 0:
            return float(val), f"{int(val)} (exact)"

    # 5) Champs textuels hérités
    for field in ("tranche_effectifs_unite_legale", "tranche_effectif"):
        text = gouv_data.get(field, "")
        if text and isinstance(text, str):
            median = _parse_tranche_text(text)
            if median > 0:
                return median, text

    return 0.0, ""


# ============================================================
# Étape 1 & 2 — API Gouv (async httpx)
# ============================================================

async def _query_api_gouv(target_name: str) -> dict | None:
    """Appelle l'API ouverte du gouvernement français (async).

    Endpoint : recherche-entreprises.api.gouv.fr/search
    Aucune clé API requise.
    """
    if _is_generic_name(target_name):
        logger.info("  API Gouv : nom '{}' trop générique → skip.", target_name)
        return None

    params = {"q": target_name, "page": 1, "per_page": 1}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                API_GOUV_SEARCH_URL,
                params=params,
                timeout=API_GOUV_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.info("  API Gouv : aucun résultat pour '{}'.", target_name)
            return None

        return results[0]

    except httpx.TimeoutException:
        logger.warning("  API Gouv : timeout après {:.0f}s.", API_GOUV_TIMEOUT)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("  API Gouv : HTTP {} — {}", e.response.status_code, target_name)
        return None
    except httpx.ConnectError:
        logger.warning("  API Gouv : connexion impossible.")
        return None
    except Exception as e:
        logger.warning("  API Gouv : erreur — {}", e)
        return None


# ============================================================
# Étape 3 — Proxy Digital (LinkedIn via Serper, async)
# ============================================================

async def _estimate_via_linkedin_serper(
    target_name: str,
    company_dna: dict,
) -> dict:
    """Fallback : estimation via snippet LinkedIn trouvé par Serper (async).

    Requête Serper : site:linkedin.com/company/ "{target_name}"
    Extrait la tranche d'employés du snippet Google via regex.
    Multiplie par le ratio moyen global (150 000 €/ETP).
    """
    empty_result = {
        "estimated_revenue": 0,
        "estimated_employees": 0,
        "estimation_source": "LinkedIn (Aucune donnée)",
    }

    settings = get_settings()
    if not settings.serper_api_key:
        logger.warning("  SERPER_API_KEY absente → skip LinkedIn fallback.")
        return empty_result

    query = f'site:linkedin.com/company/ "{target_name}"'
    logger.info("  🔍 Serper LinkedIn : {}", query)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SERPER_SEARCH_URL,
                json={"q": query, "gl": "fr", "hl": "fr", "num": 5},
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json",
                },
                timeout=SERPER_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

    except httpx.HTTPStatusError as e:
        logger.warning("  Serper LinkedIn : HTTP {} — {}", e.response.status_code, target_name)
        return empty_result
    except Exception as e:
        logger.warning("  Serper LinkedIn : erreur réseau — {}", e)
        return empty_result

    organic = data.get("organic", [])
    if not organic:
        logger.info("  Serper LinkedIn : aucun résultat organique.")
        return empty_result

    for result in organic[:5]:
        snippet = result.get("snippet", "")
        title = result.get("title", "")
        combined = f"{title} {snippet}"

        # Tentative 1 : fourchette "11-50 employees"
        match = LINKEDIN_EMP_REGEX.search(combined)
        if match:
            try:
                low = _clean_number(match.group(1))
                high = _clean_number(match.group(2))
            except (ValueError, IndexError):
                continue

            if low > high:
                low, high = high, low

            median_fte = (low + high) / 2
            ratio = GLOBAL_FALLBACK_RATIO
            estimated_revenue = round(median_fte * ratio, 2)

            logger.info("  ✅ LinkedIn snippet → {}-{} employés → médiane {:.0f} ETP",
                        low, high, median_fte)
            logger.info("  📊 CA estimé = {:.0f} ETP × {} €/ETP = {:,.0f} €",
                        median_fte, ratio, estimated_revenue)

            return {
                "estimated_revenue": estimated_revenue,
                "estimated_employees": int(median_fte),
                "estimation_source": "LinkedIn Snippet (OSINT)",
            }

        # Tentative 2 : "1000+ employees"
        match_plus = LINKEDIN_EMP_PLUS_REGEX.search(combined)
        if match_plus:
            try:
                base = _clean_number(match_plus.group(1))
            except (ValueError, IndexError):
                continue

            estimated_fte = int(base * 1.25)
            ratio = GLOBAL_FALLBACK_RATIO
            estimated_revenue = round(estimated_fte * ratio, 2)

            logger.info("  ✅ LinkedIn snippet → {}+ employés → estimé {} ETP",
                        base, estimated_fte)
            logger.info("  📊 CA estimé = {} ETP × {} €/ETP = {:,.0f} €",
                        estimated_fte, ratio, estimated_revenue)

            return {
                "estimated_revenue": estimated_revenue,
                "estimated_employees": estimated_fte,
                "estimation_source": "LinkedIn Snippet (OSINT)",
            }

    logger.info("  Serper LinkedIn : aucune tranche d'effectifs dans les snippets.")
    return empty_result


# ============================================================
# Fonction principale — Cascade Waterfall (async)
# ============================================================

async def estimate_company_size(
    target_url: str,
    target_name: str,
    company_dna: dict,
    known_revenue: float | None = None,
) -> dict:
    """Estime la taille financière d'une cible non-cotée via triangulation async.

    Cascade Waterfall (100 % gratuit) :
        0. CA connu transmis par l'appelant (D12, Tâche B.3) → court-circuite
           toute la cascade OSINT. C'est le cas du pipeline registre Sirene,
           qui connaît déjà le CA exact au moment de la découverte et ne doit
           plus le laisser être "redécouvert" (et potentiellement perdu/mal
           extrait) par ce module.
        1. CA exact API Gouv      → si public dans l'objet finances.
        2. Effectifs API Gouv × ratio NAF → si CA confidentiel.
        3. LinkedIn snippet via Serper × ratio global → si absent API Gouv.

    Args:
        target_url:    URL du site de la cible.
        target_name:   Nom de l'entreprise.
        company_dna:   Dict ADN de la plateforme (pour le secteur).
        known_revenue: CA déjà connu avec certitude (ex: registre Sirene).
                       Si fourni, aucune estimation OSINT n'est tentée.

    Returns:
        Dict :
            - estimated_revenue  (float) : CA estimé en €.
            - estimated_employees (int)  : Effectifs estimés.
            - estimation_source  (str)   : Méthode d'estimation utilisée.
    """
    if known_revenue is not None and known_revenue > 0:
        logger.info("  💰 CA connu transmis par l'appelant : {:,.0f} € (pas d'estimation OSINT).",
                     known_revenue)
        return {
            "estimated_revenue": known_revenue,
            "estimated_employees": 0,
            "estimation_source": "Registre (connu, transmis — D12)",
        }

    logger.info("  💰 Estimation financière : '{}'", target_name)

    # ── Étape 1 & 2 : Interroger l'API Gouv ─────────────────
    gouv_data = await _query_api_gouv(target_name)

    if gouv_data is not None:
        nom_complet = gouv_data.get("nom_complet", target_name)
        siren = gouv_data.get("siren", "?")
        naf_code = _extract_naf_code(gouv_data)
        logger.info("  API Gouv match : {} (SIREN: {}, NAF: {})",
                     nom_complet, siren, naf_code or "N/A")

        # ── Étape 1 : CA exact ? ────────────────────────────
        ca_exact = _extract_ca_from_gouv(gouv_data)
        if ca_exact is not None and ca_exact > 0:
            effectif, eff_label = _extract_effectif_from_gouv(gouv_data)
            logger.info("  ✅ CA exact trouvé : {:,.0f} € (effectif: {})",
                        ca_exact, eff_label if eff_label else "inconnu")
            return {
                "estimated_revenue": ca_exact,
                "estimated_employees": int(effectif) if effectif > 0 else 0,
                "estimation_source": f"API Gouv (Exact, NAF {naf_code or '?'})",
            }

        # ── Étape 2 : Effectifs connus → proxy NAF ─────────
        median_fte, tranche_label = _extract_effectif_from_gouv(gouv_data)

        if median_fte > 0:
            ratio, naf_label = _naf_to_ratio(naf_code)
            estimated_revenue = round(median_fte * ratio, 2)

            logger.info("  Tranche effectif : '{}' → médiane {:.1f} ETP",
                        tranche_label, median_fte)
            logger.info("  Ratio NAF : {} → {} €/ETP", naf_label, ratio)
            logger.info("  📊 CA estimé = {:.0f} ETP × {} €/ETP = {:,.0f} €",
                        median_fte, ratio, estimated_revenue)

            return {
                "estimated_revenue": estimated_revenue,
                "estimated_employees": int(median_fte),
                "estimation_source": f"API Gouv (Ratio {naf_label})",
            }

        logger.info("  API Gouv : ni CA ni effectifs exploitables (tranche = '{}').",
                     gouv_data.get("tranche_effectif_salarie", "?"))

    # ── Étape 3 : Fallback LinkedIn via Serper ───────────────
    return await _estimate_via_linkedin_serper(target_name, company_dna)


# ============================================================
# Filtre LBO — Validation de la taille pour un build-up
# ============================================================

def is_lbo_compatible(
    estimation: dict,
    min_ca: int | None = None,
    max_ca: int | None = None,
) -> tuple[bool, str]:
    """Vérifie si la cible entre dans les bornes LBO d'un build-up.

    Règles :
        - CA inconnu (= 0) → on laisse passer.
        - CA < min_ca → trop petit.
        - CA > max_ca → trop gros pour bolt-on.
    """
    _min = min_ca if min_ca is not None else LBO_CA_MIN
    _max = max_ca if max_ca is not None else LBO_CA_MAX

    revenue = estimation.get("estimated_revenue", 0)

    if revenue <= 0:
        return True, "CA inconnu — non filtré."

    if revenue < _min:
        return (
            False,
            f"CA estimé {format_revenue(revenue)} < {format_revenue(_min)} (trop petit pour build-up).",
        )

    if revenue > _max:
        return (
            False,
            f"CA estimé {format_revenue(revenue)} > {format_revenue(_max)} (trop gros pour bolt-on).",
        )

    return True, f"CA estimé {format_revenue(revenue)} — compatible build-up."


# ============================================================
# Formatage du CA pour affichage
# ============================================================

def format_revenue(revenue: float) -> str:
    """Formate un CA en chaîne lisible (1.5 M€, 250 K€, N/A…)."""
    if revenue <= 0:
        return "N/A"
    if revenue >= 1_000_000:
        return f"{revenue / 1_000_000:.1f} M€"
    elif revenue >= 1_000:
        return f"{revenue / 1_000:.0f} K€"
    else:
        return f"{revenue:.0f} €"


# ============================================================
# Helper — Extraction du nom depuis une URL
# ============================================================

def extract_name_from_url(url: str) -> str:
    """Extrait un nom d'entreprise probable depuis une URL.

    Exemples :
        https://www.heropay.eu    → "Heropay"
        https://www.shine.fr      → "Shine"
        https://finance-heros.fr  → "Finance Heros"
    """
    try:
        domain = urlparse(url).netloc
        domain = domain.replace("www.", "")
        name = domain.split(".")[0]
        name = name.replace("-", " ").replace("_", " ").title()
        return name
    except Exception:
        return "Inconnu"
