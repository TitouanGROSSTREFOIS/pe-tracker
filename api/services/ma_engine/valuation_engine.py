"""
valuation_engine.py — Paper LBO Engine v2 (FastAPI edition).

Modélise un investissement LBO standalone sur un horizon configurable :

    1. Hypothèses d'entrée (Assumptions)
       Mapping par code NAF 2-digit → profil sectoriel (22 profils).
       Chaque profil définit : marge EBITDA, multiple EV/EBITDA d'entrée,
       croissance organique du CA, Capex (% CA), BFR (% ΔCA).

    2. Sources & Uses (Année 0)
       EV = EBITDA₀ × Multiple d'entrée
       Dette Senior = min(4.0 × EBITDA₀, 60% × EV)
       Equity = EV − Dette

    3. Cash-Flow Sweep (Années 1-N)
       Pour chaque année t :
         CA_t      = CA_{t-1} × (1 + croissance)
         EBITDA_t  = CA_t × marge
         Intérêts  = Dette_{t-1} × 7 %
         Capex     = CA_t × capex_%
         ΔBFR      = (CA_t − CA_{t-1}) × bfr_%
         IS (25 %) = max(0, (EBITDA − Intérêts) × 25 %)
         FCF       = EBITDA − Intérêts − IS − Capex − ΔBFR
         Remboursement = min(max(0, FCF), Dette_{t-1})

    4. Sortie & Rendements (Année N)
       Exit EV     = EBITDA_N × Multiple de sortie
       Exit Equity  = Exit EV − Dette restante
       MoIC / IRR

Adapted from the original standalone module for integration into the
pe_tracker FastAPI backend.  All functions are **synchronous** (CPU-bound,
sub-ms) and can be called from async routers via asyncio.to_thread or
directly (FastAPI handles sync deps in a threadpool automatically).

Async wrappers are provided for convenience.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

from loguru import logger


# ============================================================
# Constantes globales du modèle LBO
# ============================================================

HOLDING_PERIOD: int = 5           # Horizon d'investissement (années)
SENIOR_DEBT_TURN: float = 4.0     # Levier dette senior (× EBITDA)
MAX_LEVERAGE_PCT: float = 0.60    # Plafond dette / EV (60 %)
INTEREST_RATE: float = 0.07       # Taux d'intérêt dette senior (7 %)
TAX_RATE: float = 0.25            # IS France (25 %)
MAX_GROWTH_RATE: float = 0.50     # Garde-fou : croissance max ± 50 %/an

# Tâche "P1 : physique financière du modèle LBO" (Partie E) — Sources &
# Uses réels. Hypothèses ESTIMATE, conventions de marché mid-market
# standard (à défaut d'un mandat réel avec des frais négociés) :
TRANSACTION_FEE_PCT: float = 0.02   # Frais de transaction (conseil M&A/legal/DD), % de l'EV
FINANCING_FEE_PCT: float = 0.015    # Frais de financement (arrangement/OID), % de la dette levée
MIN_CASH_PCT: float = 0.01          # Cash minimum opérationnel financé à la clôture, % du CA Année 0

# Tâche "P1" (Partie D) — DSCR réel & covenant de levier. Seuils ESTIMATE,
# conventions standard de documentation de crédit mid-market :
DSCR_COVENANT_MIN: float = 1.10                # DSCR minimum (covenant)
LEVERAGE_COVENANT_STEPDOWN_PCT: float = 0.05    # Réduction annuelle du plafond de levier net, vs levier d'entrée

# Tâche "P2 : crédibilité de la thèse" (Partie A) — en-dessous de ce seuil de
# CA, un LBO standalone à effet de levier "mid-market" (4,0x, mezzanine
# incluse) n'est PAS finançable en pratique sur le marché bancaire français
# (réel : dette senior bancaire seule, 2,0-2,5x EBITDA) — une revue IC
# externe a signalé ce point sur Ingebime (1,7 M€ de CA). Ce ne sont que des
# hypothèses PAR DÉFAUT pour la génération du scénario de base (voir
# lbo_scenario_service.build_base_case_scenario) — aucune formule du moteur
# n'est modifiée : `override_leverage` existe déjà, seule la valeur passée
# par défaut change selon la taille de la cible.
SMALL_CAP_REVENUE_THRESHOLD: float = 10_000_000.0   # Seuil CA (€) : en-dessous, LBO standalone jugé non réaliste
SMALL_CAP_DEFAULT_LEVERAGE: float = 2.25            # Levier par défaut réaliste (dette bancaire senior seule, 2,0-2,5x)


# ============================================================
# Profils sectoriels — Hypothèses LBO par famille NAF
#
# Sources croisées :
#   - Argos Index® Mid-Market (EV/EBITDA medians, 2024)
#   - EY Private Equity Barometer Europe 2024
#   - Xerfi Specific « Profils sectoriels PME France »
#   - INSEE « Tableaux de l'Économie Française » 2023-2024
#   - Bain & Company Global PE Report 2024 (margin benchmarks)
#
# ⚠ Hypothèses conservatrices, calibrées pour des PME/ETI
#   mid-market européennes (CA 2-50 M€, EBITDA 0.5-10 M€).
# ============================================================

@dataclass(frozen=True)
class SectorProfile:
    """Paramètres LBO pour un secteur donné."""

    name: str               # Libellé humain
    ebitda_margin: float     # Marge EBITDA (décimal, ex : 0.20 = 20 %)
    entry_multiple: float    # Multiple EV/EBITDA à l'entrée
    revenue_growth: float    # Croissance organique annuelle du CA
    capex_pct: float         # Capex en % du CA
    wcr_pct: float           # BFR en % de la variation annuelle du CA


LBO_PROFILES: dict[str, SectorProfile] = {
    # ── Primaire ─────────────────────────────────────────────
    "agriculture": SectorProfile(
        "Agriculture, Sylviculture & Pêche",
        ebitda_margin=0.08, entry_multiple=5.0,
        revenue_growth=0.02, capex_pct=0.06, wcr_pct=0.20,
    ),
    # ── Industrie alimentaire ────────────────────────────────
    "food_bev": SectorProfile(
        "Agroalimentaire & Boissons",
        ebitda_margin=0.09, entry_multiple=6.5,
        revenue_growth=0.03, capex_pct=0.05, wcr_pct=0.18,
    ),
    # ── Textile & Mode ───────────────────────────────────────
    "textile": SectorProfile(
        "Textile, Habillement & Cuir",
        ebitda_margin=0.10, entry_multiple=5.5,
        revenue_growth=0.02, capex_pct=0.04, wcr_pct=0.22,
    ),
    # ── Industrie lourde (chimie, métal, plasturgie …) ───────
    "heavy_industry": SectorProfile(
        "Industrie & Manufacture",
        ebitda_margin=0.10, entry_multiple=5.5,
        revenue_growth=0.025, capex_pct=0.06, wcr_pct=0.20,
    ),
    # ── Pharma & Biotech ─────────────────────────────────────
    "pharma": SectorProfile(
        "Pharmacie & Biotechnologie",
        ebitda_margin=0.20, entry_multiple=9.0,
        revenue_growth=0.06, capex_pct=0.08, wcr_pct=0.15,
    ),
    # ── Électronique, optique, équipements ───────────────────
    "hightech_mfg": SectorProfile(
        "Électronique & Équipements high-tech",
        ebitda_margin=0.13, entry_multiple=7.0,
        revenue_growth=0.04, capex_pct=0.05, wcr_pct=0.18,
    ),
    # ── Énergie, eau, déchets ────────────────────────────────
    "energy": SectorProfile(
        "Énergie & Environnement",
        ebitda_margin=0.15, entry_multiple=7.0,
        revenue_growth=0.02, capex_pct=0.08, wcr_pct=0.10,
    ),
    # ── BTP & Construction ───────────────────────────────────
    "construction": SectorProfile(
        "BTP & Construction",
        ebitda_margin=0.08, entry_multiple=5.0,
        revenue_growth=0.025, capex_pct=0.04, wcr_pct=0.25,
    ),
    # ── Commerce (gros & détail) ─────────────────────────────
    "wholesale_retail": SectorProfile(
        "Commerce & Distribution",
        ebitda_margin=0.06, entry_multiple=5.5,
        revenue_growth=0.025, capex_pct=0.03, wcr_pct=0.22,
    ),
    # ── Transport & Logistique ───────────────────────────────
    "transport": SectorProfile(
        "Transport & Logistique",
        ebitda_margin=0.09, entry_multiple=6.0,
        revenue_growth=0.03, capex_pct=0.07, wcr_pct=0.15,
    ),
    # ── Hôtellerie & Restauration ────────────────────────────
    "hospitality": SectorProfile(
        "Hôtellerie & Restauration",
        ebitda_margin=0.12, entry_multiple=6.5,
        revenue_growth=0.03, capex_pct=0.06, wcr_pct=0.08,
    ),
    # ── Médias & Télécoms ────────────────────────────────────
    "media_telecom": SectorProfile(
        "Médias & Télécommunications",
        ebitda_margin=0.15, entry_multiple=7.5,
        revenue_growth=0.04, capex_pct=0.05, wcr_pct=0.12,
    ),
    # ── Logiciel & IT ────────────────────────────────────────
    "software_it": SectorProfile(
        "Logiciel & Services IT",
        ebitda_margin=0.20, entry_multiple=10.0,
        revenue_growth=0.08, capex_pct=0.03, wcr_pct=0.10,
    ),
    # ── Services financiers ──────────────────────────────────
    "finance": SectorProfile(
        "Services Financiers & Assurance",
        ebitda_margin=0.25, entry_multiple=8.5,
        revenue_growth=0.04, capex_pct=0.02, wcr_pct=0.05,
    ),
    # ── Immobilier ───────────────────────────────────────────
    "real_estate": SectorProfile(
        "Activités Immobilières",
        ebitda_margin=0.30, entry_multiple=8.0,
        revenue_growth=0.02, capex_pct=0.03, wcr_pct=0.05,
    ),
    # ── Conseil & Services spécialisés ───────────────────────
    "professional_svc": SectorProfile(
        "Conseil, Juridique & Ingénierie",
        ebitda_margin=0.15, entry_multiple=7.0,
        revenue_growth=0.04, capex_pct=0.02, wcr_pct=0.15,
    ),
    # ── Services aux entreprises ─────────────────────────────
    "business_svc": SectorProfile(
        "Services aux Entreprises",
        ebitda_margin=0.12, entry_multiple=6.5,
        revenue_growth=0.035, capex_pct=0.03, wcr_pct=0.15,
    ),
    # ── Enseignement & Formation ─────────────────────────────
    "education": SectorProfile(
        "Enseignement & Formation",
        ebitda_margin=0.12, entry_multiple=7.0,
        revenue_growth=0.04, capex_pct=0.04, wcr_pct=0.10,
    ),
    # ── Santé & Action sociale ───────────────────────────────
    "healthcare": SectorProfile(
        "Santé & Action Sociale",
        ebitda_margin=0.14, entry_multiple=8.0,
        revenue_growth=0.05, capex_pct=0.05, wcr_pct=0.12,
    ),
    # ── Loisirs & Divertissement ─────────────────────────────
    "leisure": SectorProfile(
        "Loisirs, Sport & Culture",
        ebitda_margin=0.10, entry_multiple=6.0,
        revenue_growth=0.03, capex_pct=0.05, wcr_pct=0.10,
    ),
    # ── Autres services ──────────────────────────────────────
    "other_services": SectorProfile(
        "Autres Services",
        ebitda_margin=0.10, entry_multiple=5.5,
        revenue_growth=0.025, capex_pct=0.03, wcr_pct=0.12,
    ),
    # ── Profil par défaut (secteur non identifié) ────────────
    "default": SectorProfile(
        "Généraliste Mid-Market",
        ebitda_margin=0.12, entry_multiple=6.0,
        revenue_growth=0.03, capex_pct=0.04, wcr_pct=0.15,
    ),
}


# ============================================================
# Mapping NAF 2-digit → Clé de profil sectoriel
# ============================================================

NAF_TO_PROFILE: dict[str, str] = {
    # Agriculture / Pêche
    "01": "agriculture", "02": "agriculture", "03": "agriculture",
    # Industrie alimentaire
    "10": "food_bev", "11": "food_bev", "12": "food_bev",
    # Textile / Habillement / Cuir
    "13": "textile", "14": "textile", "15": "textile",
    # Bois / Papier / Imprimerie / Chimie
    "16": "heavy_industry", "17": "heavy_industry", "18": "heavy_industry",
    "20": "heavy_industry",
    # Pharma
    "21": "pharma",
    # Plastique / Minéraux / Métallurgie
    "22": "heavy_industry", "23": "heavy_industry",
    "24": "heavy_industry", "25": "heavy_industry",
    # Électronique / Optique / Équipements
    "26": "hightech_mfg", "27": "hightech_mfg", "28": "hightech_mfg",
    # Automobile / Autres transports / Autres industries
    "29": "heavy_industry", "30": "heavy_industry",
    "31": "heavy_industry", "32": "heavy_industry", "33": "heavy_industry",
    # Énergie / Eau / Déchets
    "35": "energy", "36": "energy", "37": "energy",
    "38": "energy", "39": "energy",
    # BTP
    "41": "construction", "42": "construction", "43": "construction",
    # Commerce
    "45": "wholesale_retail", "46": "wholesale_retail", "47": "wholesale_retail",
    # Transport / Logistique
    "49": "transport", "50": "transport", "51": "transport",
    "52": "transport", "53": "transport",
    # Hébergement / Restauration
    "55": "hospitality", "56": "hospitality",
    # Médias / Télécoms
    "58": "media_telecom", "59": "media_telecom",
    "60": "media_telecom", "61": "media_telecom",
    # Logiciel / IT
    "62": "software_it", "63": "software_it",
    # Finance / Assurance
    "64": "finance", "65": "finance", "66": "finance",
    # Immobilier
    "68": "real_estate",
    # Services spécialisés / Conseil / Ingénierie
    "69": "professional_svc", "70": "professional_svc",
    "71": "professional_svc", "72": "professional_svc",
    "73": "professional_svc", "74": "professional_svc",
    "75": "professional_svc",
    # Services aux entreprises
    "77": "business_svc", "78": "business_svc", "79": "business_svc",
    "80": "business_svc", "81": "business_svc", "82": "business_svc",
    # Enseignement
    "85": "education",
    # Santé / Action sociale
    "86": "healthcare", "87": "healthcare", "88": "healthcare",
    # Loisirs / Culture
    "90": "leisure", "91": "leisure", "92": "leisure", "93": "leisure",
    # Autres services
    "94": "other_services", "95": "other_services", "96": "other_services",
}


# ============================================================
# Résolution textuelle (fallback si pas de code NAF)
# ============================================================

_KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["saas", "logiciel", "software", "it service", "informatique",
      "cloud", "programmation", "erp", "crm", "cybersécurité"], "software_it"),
    (["fintech", "banque", "paiement", "assurance", "finance",
      "crédit", "banking", "néobanque", "regtech"], "finance"),
    (["pharma", "biotech", "médicament", "drug", "biopharma"], "pharma"),
    (["santé", "health", "médical", "clinique", "ehpad",
      "soin", "medtech", "e-santé", "diagnostic"], "healthcare"),
    (["immobilier", "real estate", "foncier", "promotion immobilière"], "real_estate"),
    (["télécom", "telecom", "média", "édition", "broadcast",
      "streaming", "audiovisuel", "podcast"], "media_telecom"),
    (["btp", "construction", "bâtiment", "génie civil", "travaux"], "construction"),
    (["agroalimentaire", "alimentaire", "boisson", "food",
      "beverage", "restauration collective"], "food_bev"),
    (["commerce", "retail", "distribution", "e-commerce",
      "wholesale", "négoce", "marketplace"], "wholesale_retail"),
    (["transport", "logistique", "logistics", "fret",
      "livraison", "delivery", "supply chain"], "transport"),
    (["hôtel", "hotel", "restauration", "restaurant",
      "hébergement", "tourisme", "voyage"], "hospitality"),
    (["conseil", "consulting", "audit", "cabinet", "juridique",
      "avocat", "comptab", "ingénierie", "expertise",
      # TIC (Testing, Inspection, Certification) — secteur du CompSet calibré
      # (D22, Tâche B.8). Termes composés uniquement (pas de sigle "tic" nu :
      # matcherait "logistique", "domestique"… en sous-chaîne).
      "contrôle technique", "inspection", "certification",
      "essai technique", "vérification technique"], "professional_svc"),
    (["énergie", "energy", "renouvelable", "solaire", "éolien",
      "utilities", "déchet", "recyclage", "cleantech"], "energy"),
    (["textile", "mode", "fashion", "habillement", "luxe", "cuir"], "textile"),
    (["agriculture", "agri", "élevage", "pêche", "sylviculture"], "agriculture"),
    (["électronique", "electronic", "optique", "équipement",
      "instrumentation", "semi-conducteur", "iot"], "hightech_mfg"),
    (["industrie", "manufacturing", "usine", "fabrication",
      "métallurgie", "chimie", "plasturgie", "mécanique"], "heavy_industry"),
    (["formation", "enseignement", "éducation", "edtech",
      "école", "e-learning", "mooc"], "education"),
    (["loisir", "sport", "culture", "divertissement",
      "jeu", "gaming", "spectacle", "événement"], "leisure"),
    (["service", "externalisation", "outsourcing", "intérim",
      "sécurité", "nettoyage", "facility management"], "business_svc"),
]

# D34 (Tâche Review Produit — Partie D) : la résolution reposait sur un
# simple `in` (sous-chaîne) — fragile par construction, ex. le mot-clé "iot"
# matchait à tort "patriotique" ou "biotique" (sous-chaîne, pas un mot).
# Bascule vers une correspondance par FRONTIÈRE DE MOT (regex \b...\b,
# compilée une fois au chargement du module) : un mot-clé ne matche
# désormais que comme mot ou expression complète — avec un 's' ou 'x' final
# optionnel pour absorber les pluriels réguliers ET les pluriels irréguliers
# français en -eu/-au/-eau ("jeu"→"jeux") SANS rouvrir le risque de
# fragment : `\bjeu[sx]?\b` ne matche jamais "jeune" (rien entre "jeu" et la
# frontière ne peut être "n"), contrairement à un simple préfixe `\bjeu`.
# Vérifié en testant les 12 libellés du sélecteur secteur du LBO Calculator
# (`SECTORS` dans LBOCalculator.tsx) : "Services B2B" ne résolvait plus sans
# ce `[sx]?` (le mot-clé "service" ne matchait pas "Services" au pluriel).
# Le mapping mots-clés → profil lui-même n'est pas modifié, seule la façon
# dont un mot-clé est recherché dans le texte l'est — aucun changement de
# LOGIQUE DE CALCUL.
_COMPILED_KEYWORD_RULES: list[tuple[list[re.Pattern], str]] = [
    ([re.compile(r"\b" + re.escape(kw) + r"[sx]?\b") for kw in keywords], profile_key)
    for keywords, profile_key in _KEYWORD_RULES
]

_NAF_REGEX = re.compile(r"\b(\d{2})(?:\.\d{2}[A-Z]?)?\b")


# ============================================================
# Helpers internes (exportés pour buildup_engine)
# ============================================================

def _extract_naf_2digit(text: str) -> str | None:
    """Extrait les 2 premiers chiffres d'un code NAF."""
    if not text:
        return None
    m = _NAF_REGEX.search(text.strip())
    return m.group(1) if m else None


def resolve_profile_key(sector_or_naf: str) -> str:
    """Résout un texte sectoriel ou un code NAF en clé de profil LBO
    (`LBO_PROFILES`). Waterfall : NAF 2-digit → mots-clés → "default"."""
    text = str(sector_or_naf).strip()

    naf_2 = _extract_naf_2digit(text)
    if naf_2 and naf_2 in NAF_TO_PROFILE:
        return NAF_TO_PROFILE[naf_2]

    text_lower = text.lower()
    for patterns, profile_key in _COMPILED_KEYWORD_RULES:
        if any(p.search(text_lower) for p in patterns):
            return profile_key

    return "default"


def resolve_profile(sector_or_naf: str) -> SectorProfile:
    """Résout un texte sectoriel ou un code NAF en profil LBO.

    Waterfall : NAF 2-digit → mots-clés → profil par défaut.
    """
    return LBO_PROFILES[resolve_profile_key(sector_or_naf)]


def compute_irr(cash_flows: list[float]) -> float:
    """Calcule le TRI d'une série de cash-flows.

    Utilise numpy-financial si disponible, sinon calcul analytique
    pour le cas simplifié (entrée à t=0, sortie à t=N).
    """
    if len(cash_flows) < 2:
        return 0.0

    if (
        cash_flows[0] < 0
        and cash_flows[-1] > 0
        and all(cf == 0.0 for cf in cash_flows[1:-1])
    ):
        n = len(cash_flows) - 1
        moic = cash_flows[-1] / (-cash_flows[0])
        try:
            return moic ** (1.0 / n) - 1.0
        except (OverflowError, ZeroDivisionError):
            return 0.0

    try:
        import numpy_financial as npf  # type: ignore[import-untyped]

        result = npf.irr(cash_flows)
        if result is None or math.isnan(result) or math.isinf(result):
            return 0.0
        return float(result)
    except ImportError:
        logger.warning("numpy-financial not installed — analytical IRR only.")
        return 0.0
    except Exception:
        return 0.0


def round2(value: float) -> float:
    """Arrondi à 2 décimales, protégé NaN/Inf."""
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return round(value, 2)


def round4(value: float) -> float:
    """Arrondi à 4 décimales (taux), protégé NaN/Inf."""
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return round(value, 4)


def _empty_result() -> dict:
    """Dictionnaire résultat vide (edge case / erreur)."""
    return {
        "ebitda": 0.0, "ev": 0.0, "debt_capacity": 0.0,
        "required_equity": 0.0, "ebitda_margin": 0.0, "multiple": 0.0,
        "sector_profile": "N/A", "revenue_growth": 0.0,
        "capex_pct": 0.0, "wcr_pct": 0.0,
        "interest_rate": INTEREST_RATE, "tax_rate": TAX_RATE,
        "holding_period": HOLDING_PERIOD,
        "entry_revenue": 0.0, "entry_ebitda": 0.0, "entry_ev": 0.0,
        "entry_transaction_fees": 0.0, "entry_financing_fees": 0.0,
        "entry_min_cash": 0.0, "entry_uses_total": 0.0,
        "entry_debt": 0.0, "entry_equity": 0.0, "leverage_entry": 0.0,
        "exit_revenue": 0.0, "exit_ebitda": 0.0, "exit_ev": 0.0,
        "exit_debt": 0.0, "exit_cash": 0.0, "exit_net_debt": 0.0,
        "exit_equity": 0.0, "leverage_exit": 0.0,
        "moic": 0.0, "irr": 0.0, "projections": [],
        "debt_tranches_detail": [], "waterfall": None,
    }


# ============================================================
# Dataclass interne — état d'une tranche de dette pendant la sim
# ============================================================

@dataclass
class _TrancheState:
    """Mutable state for one debt tranche during the LBO simulation."""
    name: str
    balance: float          # Outstanding principal
    rate: float             # Annual interest rate
    is_bullet: bool         # True = in fine, False = amortizing
    initial_amount: float   # Original size at entry
    annual_amort: float     # Fixed annual repayment (amortizing only)


# ============================================================
# Fonction principale — Paper LBO Engine V3
# ============================================================

def run_lbo_model(
    revenue: float,
    sector_or_naf: str = "",
    *,
    holding_period: int = HOLDING_PERIOD,
    override_entry_mult: float | None = None,
    override_exit_mult: float | None = None,
    override_leverage: float | None = None,
    debt_structure: list[dict] | None = None,
    management_package: dict | None = None,
    calibrated_profile: SectorProfile | None = None,
    override_entry_ebitda: float | None = None,
) -> dict:
    """Exécute un modèle Paper LBO complet (V3).

    Args:
        revenue:              CA estimé Année 0 (€).
        sector_or_naf:        Secteur libre ou code NAF.
        holding_period:       Horizon en années (défaut : 5).
        override_entry_mult:  Remplace le multiple d'entrée sectoriel.
        override_exit_mult:   Remplace le multiple de sortie.
        override_leverage:    Remplace le levier dette / EBITDA (V2 mode only).
        debt_structure:       V3 — List of tranche dicts (name, amount_turns, interest_rate, amortization).
        management_package:   V3 — Dict with sweet_equity_pct, ratchet_irr_threshold, ratchet_bonus_pct.
        calibrated_profile:   Tâche B.8 (D22) — profil dérivé du CompSet réel
                               (voir `sector_calibration.py`), utilisé à la
                               place de `resolve_profile(sector_or_naf)` quand
                               fourni. `override_entry_mult`/`override_exit_mult`
                               restent prioritaires si également fournis.
        override_entry_ebitda: Tâche "Le moteur LBO accepte un EBITDA réel en
                               entrée" — quand fourni (EBITDA réel du deal,
                               provenance DOCUMENT/REGISTRY), remplace
                               `revenue × marge` comme EBITDA d'entrée Année 0.
                               La marge affichée (`ebitda_margin` du résultat)
                               devient alors la marge IMPLIQUÉE (EBITDA réel ÷
                               revenue) et pilote aussi les années 1..N — le
                               multiple d'entrée (sectoriel/calibré) et toutes
                               les formules de dette/waterfall/retours restent
                               inchangés. Absent (défaut) : comportement
                               identique à avant cette tâche.

    Returns:
        dict JSON-sérialisable (Sources & Uses, Projections, Exit, Returns, Waterfall).
    """
    if not revenue or revenue <= 0.0:
        return _empty_result()
    if holding_period < 1:
        holding_period = HOLDING_PERIOD

    try:
        return _build_lbo(
            revenue, sector_or_naf, holding_period,
            override_entry_mult=override_entry_mult,
            override_exit_mult=override_exit_mult,
            override_leverage=override_leverage,
            debt_structure=debt_structure,
            management_package=management_package,
            calibrated_profile=calibrated_profile,
            override_entry_ebitda=override_entry_ebitda,
        )
    except Exception as e:
        logger.warning("Erreur dans le modèle LBO : {}", e)
        return _empty_result()


def _build_lbo(
    revenue: float,
    sector_or_naf: str,
    n_years: int,
    *,
    override_entry_mult: float | None = None,
    override_exit_mult: float | None = None,
    override_leverage: float | None = None,
    debt_structure: list[dict] | None = None,
    management_package: dict | None = None,
    calibrated_profile: SectorProfile | None = None,
    override_entry_ebitda: float | None = None,
) -> dict:
    """Construction interne du modèle LBO (V3)."""
    profile = calibrated_profile if calibrated_profile is not None else resolve_profile(sector_or_naf)

    # ── 1. Hypothèses ───────────────────────────────────────
    margin = profile.ebitda_margin
    mult = (
        override_entry_mult
        if override_entry_mult and override_entry_mult > 0
        else profile.entry_multiple
    )
    exit_mult = (
        override_exit_mult
        if override_exit_mult and override_exit_mult > 0
        else mult
    )
    growth = max(-MAX_GROWTH_RATE, min(MAX_GROWTH_RATE, profile.revenue_growth))
    capex_pct = profile.capex_pct
    wcr_pct = profile.wcr_pct

    # ── 2. Sources & Uses (Année 0) ─────────────────────────
    # Tâche "Le moteur LBO accepte un EBITDA réel en entrée" : un EBITDA réel
    # (DOCUMENT/REGISTRY) pilote l'EBITDA de départ directement, au lieu du
    # revenue × marge sectorielle. La marge est alors recalculée en sens
    # inverse (EBITDA réel ÷ revenue) — purement pour que le résultat affiche
    # une marge cohérente avec le chiffre réel — et cette marge implicite
    # continue de piloter les années 1..N EXACTEMENT comme avant (même
    # formule `ebitda_t = rev_t * margin`) : aucune formule de projection, de
    # dette ou de retours n'est modifiée, seule la source de l'EBITDA Année 0.
    if override_entry_ebitda is not None and override_entry_ebitda > 0:
        entry_ebitda = override_entry_ebitda
        if revenue > 0:
            margin = entry_ebitda / revenue
    else:
        entry_ebitda = revenue * margin
    if entry_ebitda <= 0.0:
        return _empty_result()

    entry_ev = entry_ebitda * mult

    # ── 2b. Build debt tranches ──────────────────────────────
    use_multi_tranche = bool(debt_structure)

    tranches: list[_TrancheState] = []
    debt_tranches_detail: list[dict] = []

    if use_multi_tranche:
        for t in debt_structure:
            amt = entry_ebitda * t["amount_turns"]
            is_bullet = t.get("amortization", "bullet") == "bullet"
            ts = _TrancheState(
                name=t["name"],
                balance=amt,
                rate=t["interest_rate"],
                is_bullet=is_bullet,
                initial_amount=amt,
                annual_amort=0.0 if is_bullet else (amt / n_years),
            )
            tranches.append(ts)
            debt_tranches_detail.append({
                "name": t["name"],
                "amount": round2(amt),
                "turns": t["amount_turns"],
                "interest_rate": t["interest_rate"],
                "amortization": t.get("amortization", "bullet"),
            })
        entry_debt = sum(ts.balance for ts in tranches)
        # Cap total debt at MAX_LEVERAGE_PCT of EV
        if entry_debt > entry_ev * MAX_LEVERAGE_PCT:
            scale = (entry_ev * MAX_LEVERAGE_PCT) / entry_debt
            for ts in tranches:
                ts.balance *= scale
                ts.initial_amount *= scale
                ts.annual_amort *= scale
            entry_debt = entry_ev * MAX_LEVERAGE_PCT
            for d in debt_tranches_detail:
                d["amount"] = round2(d["amount"] * scale)
        # Weighted average interest rate for display
        wavg_rate = (
            sum(ts.balance * ts.rate for ts in tranches) / entry_debt
            if entry_debt > 0 else INTEREST_RATE
        )
    else:
        # V2 fallback — single tranche
        leverage_turns = (
            override_leverage
            if override_leverage is not None and override_leverage >= 0
            else SENIOR_DEBT_TURN
        )
        raw_debt = entry_ebitda * leverage_turns
        entry_debt = min(raw_debt, entry_ev * MAX_LEVERAGE_PCT)
        wavg_rate = INTEREST_RATE
        # Create single implicit tranche for uniform simulation
        tranches = [_TrancheState(
            name="Senior Debt",
            balance=entry_debt,
            rate=INTEREST_RATE,
            is_bullet=False,
            initial_amount=entry_debt,
            annual_amort=0.0,  # Repaid via cash sweep (legacy behaviour)
        )]

    # ── 2c. Uses (EV + frais réels) & Sources (dette + equity plug) ─────
    # Tâche "P1 : physique financière du modèle LBO" (Partie E) — Uses
    # n'est plus l'EV seul : frais de transaction (conseil M&A/legal/DD, %
    # de l'EV), frais de financement (arrangement/OID, % de la dette
    # levée) et un cash minimum opérationnel financé À LA CLÔTURE (pas un
    # excédent généré en cours de vie) s'ajoutent à l'EV. L'equity sponsor
    # (plug) absorbe ce total réel. La formule elle-même (equity = Uses −
    # Dette) reste par construction toujours vraie — c'est précisément
    # pourquoi le check "Sources = Uses" est RETIRÉ en Partie F (un plug
    # équilibre toujours son propre total, quoi qu'il contienne) plutôt que
    # "corrigé" : ce n'est pas ce calcul qui manquait de rigueur, c'est le
    # contenu de Uses qui était incomplet (EV seul).
    entry_transaction_fees = entry_ev * TRANSACTION_FEE_PCT
    entry_financing_fees = entry_debt * FINANCING_FEE_PCT
    entry_min_cash = revenue * MIN_CASH_PCT
    entry_uses_total = entry_ev + entry_transaction_fees + entry_financing_fees + entry_min_cash

    entry_equity = entry_uses_total - entry_debt
    if entry_equity <= 0.0:
        return _empty_result()

    leverage_entry = entry_debt / entry_ebitda if entry_ebitda > 0 else 0.0

    # ── 3. Projections annuelles (Cash-Flow Sweep + Trésorerie) ─────────
    projections: list[dict] = []
    # Partie B/E — le cash minimum financé à la clôture EST le solde de
    # trésorerie de départ (Année 0) : un actif réel, financé comme le
    # reste des Uses, pas un excédent d'exploitation.
    cash_balance = entry_min_cash

    projections.append({
        "year": 0,
        "revenue": round2(revenue),
        "ebitda": round2(entry_ebitda),
        "da": 0.0, "ebit": 0.0,
        "interest": 0.0, "capex": 0.0, "delta_wcr": 0.0,
        "taxable_income": 0.0, "tax": 0.0, "fcf": 0.0,
        "debt_paydown": 0.0, "debt_eoy": round2(entry_debt),
        "cash_eoy": round2(cash_balance),
        "net_debt_eoy": round2(entry_debt - cash_balance),
        "debt_service_shortfall": 0.0, "dscr": None,
        "net_leverage": round2((entry_debt - cash_balance) / entry_ebitda) if entry_ebitda > 0 else 0.0,
        "leverage_covenant_cap": None, "covenant_breach": False,
        "tranches": [
            {"name": ts.name, "interest": 0.0, "amortization": 0.0,
             "balance_eoy": round2(ts.balance)}
            for ts in tranches
        ],
    })

    prev_revenue = revenue

    for year in range(1, n_years + 1):
        rev_t = prev_revenue * (1.0 + growth)
        ebitda_t = rev_t * margin

        # ── Interest cascade (senior → junior), sur solde d'OUVERTURE ──
        # (évite la circularité intérêt↔FCF↔remboursement↔solde de
        # clôture — un solde de clôture dépendrait du FCF, qui dépend de
        # l'intérêt, qui dépendrait du solde de clôture. Choix déjà en
        # place avant cette tâche, documenté ici car Partie B demande
        # explicitement de le conserver et de l'expliquer.)
        total_interest = 0.0
        tranche_year_data: list[dict] = []
        for ts in tranches:
            interest_i = ts.balance * ts.rate
            total_interest += interest_i
            tranche_year_data.append({
                "name": ts.name,
                "interest": round2(interest_i),
                "amortization": 0.0,  # filled below
                "balance_eoy": 0.0,   # filled below
            })

        capex_t = rev_t * capex_pct
        delta_wcr_t = max(0.0, (rev_t - prev_revenue) * wcr_pct)

        # ── D&A et bouclier fiscal (Partie C) ──────────────────────────
        # Hypothèse ESTIMATE, documentée : ce moteur ne modélise pas de
        # tableau d'immobilisations séparé — à défaut d'un plan
        # d'investissement détaillé, la convention retenue est un D&A en
        # régime stationnaire égal au Capex (l'actif immobilisé se
        # renouvelle au même rythme qu'il s'amortit). Le D&A ne sort pas
        # une seconde fois du FCF (le Capex, seule sortie de cash réelle,
        # le fait déjà) — il sert UNIQUEMENT à réduire la base imposable
        # (bouclier fiscal), l'unique mécanique que Partie C corrige :
        # avant, l'impôt était calculé sur EBITDA − Intérêts, traitant
        # l'EBITDA comme un EBIT et perdant le bouclier fiscal du D&A.
        da_t = capex_t
        ebit_t = ebitda_t - da_t

        taxable_income = ebit_t - total_interest
        tax_t = max(0.0, taxable_income * TAX_RATE)

        fcf_t = ebitda_t - total_interest - tax_t - capex_t - delta_wcr_t

        # ── Service de la dette : échéancier contractuel puis cash sweep ──
        remaining_cash = max(0.0, fcf_t)
        total_contractual_due = 0.0
        total_contractual_paid = 0.0
        total_paydown = 0.0

        for idx, ts in enumerate(tranches):
            if not ts.is_bullet and ts.annual_amort > 0:
                # Erreur 2 (rapport IC) — le montant CONTRACTUELLEMENT dû
                # est distingué du montant réellement payé (capé par le
                # cash disponible) : si le cash ne couvre pas l'échéance,
                # l'écart est un vrai manquement (`debt_service_shortfall`
                # ci-dessous), jamais absorbé en silence par un simple
                # MIN(...) qu'aucun check ne regardait.
                due_i = min(ts.annual_amort, ts.balance)
                paid_i = min(due_i, remaining_cash)
                ts.balance -= paid_i
                remaining_cash -= paid_i
                total_paydown += paid_i
                total_contractual_due += due_i
                total_contractual_paid += paid_i
                tranche_year_data[idx]["amortization"] = round2(paid_i)

        # Cash sweep (Partie B) — s'applique désormais UNIFORMÉMENT en
        # mode V2 legacy ET V3 multi-tranche (avant : bloqué par un `if
        # not use_multi_tranche`, si bien qu'en V3 tout FCF résiduel
        # au-delà de l'amortissement contractuel programmé s'évaporait
        # purement et simplement, y compris sur des tranches bullet —
        # Erreur 1 du rapport IC). Cascade par séniorité (ordre du
        # tableau = ordre de séniorité), bullet compris : une clause de
        # cash sweep à 100% ne dispense pas une tranche in fine d'un
        # remboursement anticipé, elle la dispense seulement d'un
        # ÉCHÉANCIER fixe.
        for idx, ts in enumerate(tranches):
            sweep = min(remaining_cash, ts.balance)
            if sweep > 0:
                ts.balance -= sweep
                remaining_cash -= sweep
                total_paydown += sweep
                tranche_year_data[idx]["amortization"] = round2(
                    tranche_year_data[idx]["amortization"] + sweep
                )

        # Tout cash non absorbé (dette intégralement remboursée) ne
        # s'évapore plus : il s'accumule dans un solde de trésorerie
        # cumulé (Partie B). Ce modèle ne pioche PAS dans ce solde pour
        # combler une insuffisance de cash de service de la dette une
        # autre année — traitement conservateur documenté : il expose un
        # manquement plutôt que de le masquer avec une réserve non prévue
        # à cet effet.
        cash_balance += remaining_cash

        debt_service_shortfall = round2(max(0.0, total_contractual_due - total_contractual_paid))

        total_debt_eoy = 0.0
        for idx, ts in enumerate(tranches):
            tranche_year_data[idx]["balance_eoy"] = round2(ts.balance)
            total_debt_eoy += ts.balance

        # ── DSCR réel (Partie D) — un vrai ratio, jamais une identité ──
        # CFADS = EBITDA − Capex − ΔBFR − Impôt (cash disponible pour le
        # service de la dette, AVANT intérêts/principal). Debt Service =
        # Intérêts + amortissement CONTRACTUELLEMENT dû (pas le montant
        # réellement payé, qui est capé par le cash disponible — sinon on
        # retombe dans l'identité CFADS=CFADS de l'ancien modèle où
        # "payé" ÉTAIT "disponible" par construction). En mode V2/bullet
        # pur (aucun échéancier fixe), le service dû se réduit aux
        # intérêts — un ratio de couverture des intérêts qui varie bien
        # dans le temps (contrairement à l'identité qu'il remplace) et
        # peut passer sous le seuil de covenant si le CFADS se dégrade.
        cfads_t = ebitda_t - capex_t - delta_wcr_t - tax_t
        debt_service_due_t = total_interest + total_contractual_due
        dscr_t = round2(cfads_t / debt_service_due_t) if debt_service_due_t > 0 else None

        # ── Covenant de levier à plafond décroissant (Partie D) ──
        net_debt_t = total_debt_eoy - cash_balance
        net_leverage_t = net_debt_t / ebitda_t if ebitda_t > 0 else 0.0
        covenant_cap_t = max(0.5, leverage_entry * (1 - LEVERAGE_COVENANT_STEPDOWN_PCT * year))
        covenant_breach_t = net_leverage_t > covenant_cap_t

        projections.append({
            "year": year,
            "revenue": round2(rev_t),
            "ebitda": round2(ebitda_t),
            "da": round2(da_t),
            "ebit": round2(ebit_t),
            "interest": round2(total_interest),
            "capex": round2(capex_t),
            "delta_wcr": round2(delta_wcr_t),
            "taxable_income": round2(taxable_income),
            "tax": round2(tax_t),
            "fcf": round2(fcf_t),
            "debt_paydown": round2(total_paydown),
            "debt_eoy": round2(total_debt_eoy),
            "cash_eoy": round2(cash_balance),
            "net_debt_eoy": round2(net_debt_t),
            "debt_service_shortfall": debt_service_shortfall,
            "dscr": dscr_t,
            "net_leverage": round2(net_leverage_t),
            "leverage_covenant_cap": round2(covenant_cap_t),
            "covenant_breach": covenant_breach_t,
            "tranches": tranche_year_data,
        })
        prev_revenue = rev_t

    # ── 4. Exit & Returns (Gross) ───────────────────────────
    exit_year = projections[-1]
    exit_revenue = exit_year["revenue"]
    exit_ebitda = exit_year["ebitda"]
    exit_debt = exit_year["debt_eoy"]
    exit_cash = exit_year["cash_eoy"]
    exit_net_debt = exit_year["net_debt_eoy"]
    exit_ev = exit_ebitda * exit_mult
    # Partie B — Exit Equity = Exit EV − dette NETTE (dette brute résiduelle
    # − cash accumulé) : le cash que le cash sweep laisse désormais
    # s'accumuler (au lieu de s'évaporer) appartient au sponsor à la
    # sortie, exactement comme une dette évitée.
    exit_equity = max(0.0, exit_ev - exit_net_debt)
    leverage_exit = exit_net_debt / exit_ebitda if exit_ebitda > 0 else 0.0

    moic = exit_equity / entry_equity if entry_equity > 0 else 0.0
    cash_flows = [-entry_equity] + [0.0] * (n_years - 1) + [exit_equity]
    irr = compute_irr(cash_flows)

    # ── 5. Waterfall (Management Package) ───────────────────
    # Tâche "P0 : un seul deal dans les 3 documents" (Partie C) — fix : le
    # fonds n'investit PAS 100% de l'entry_equity quand le management
    # co-investit sa "sweet equity" (sweet_pct × entry_equity est une mise de
    # fonds RÉELLE du management, déjà utilisée telle quelle pour calculer
    # management_moic ci-dessous) — le MOIC/IRR du fonds doit donc être
    # rapporté au capital RÉELLEMENT apporté par le fonds
    # (entry_equity − mgmt_invested), jamais à l'entry_equity complet. La
    # version précédente débitait le fonds de 100% de l'equity tout en ne
    # lui reversant que (1 − management_total_pct) du produit de sortie —
    # sous-évaluant le MOIC fonds d'environ le ratio 1/(1−sweet_pct) (~18%
    # pour sweet_pct=15%). Formules de dette/cash-flow/TRI BRUT (ci-dessus)
    # non touchées — uniquement la répartition fonds/management.
    #
    # Le mécanisme hurdle+ratchet (ratchet_irr_threshold/ratchet_bonus_pct)
    # est RÉEL et fonctionnel (bonus de management déclenché si le TRI brut
    # franchit le seuil) — conservé tel quel, pas une couche décorative.
    waterfall = None
    if management_package:
        sweet_pct = management_package.get("sweet_equity_pct", 0.0)
        ratchet_threshold = management_package.get("ratchet_irr_threshold", 0.25)
        ratchet_bonus = management_package.get("ratchet_bonus_pct", 0.0)

        ratchet_triggered = irr >= ratchet_threshold
        mgmt_total_pct = sweet_pct + (ratchet_bonus if ratchet_triggered else 0.0)
        mgmt_total_pct = min(mgmt_total_pct, 0.50)  # Hard cap at 50%

        mgmt_proceeds = exit_equity * mgmt_total_pct
        fund_proceeds = exit_equity - mgmt_proceeds

        # Management's real cash co-investment at entry (sweet equity) —
        # computed BEFORE the fund's own denominator, since the fund only
        # funds what management doesn't.
        mgmt_invested = entry_equity * sweet_pct if sweet_pct > 0 else 0.0
        fund_invested = entry_equity - mgmt_invested

        fund_moic = fund_proceeds / fund_invested if fund_invested > 0 else 0.0
        fund_cf = [-fund_invested] + [0.0] * (n_years - 1) + [fund_proceeds]
        fund_irr = compute_irr(fund_cf)

        # Management MOIC: sweet equity invested at entry = sweet_pct × entry_equity
        mgmt_moic = mgmt_proceeds / mgmt_invested if mgmt_invested > 0 else 0.0

        waterfall = {
            "total_exit_equity": round2(exit_equity),
            "management_sweet_pct": round4(sweet_pct),
            "ratchet_triggered": ratchet_triggered,
            "management_total_pct": round4(mgmt_total_pct),
            "management_proceeds": round2(mgmt_proceeds),
            "fund_proceeds": round2(fund_proceeds),
            "fund_invested": round2(fund_invested),
            "fund_moic": round2(fund_moic),
            "fund_irr": round4(fund_irr),
            "management_invested": round2(mgmt_invested),
            "management_moic": round2(mgmt_moic),
        }

    # ── 6. Assemblage ───────────────────────────────────────
    return {
        # Retro-compatible
        "ebitda": round2(entry_ebitda),
        "ev": round2(entry_ev),
        "debt_capacity": round2(entry_debt),
        "required_equity": round2(entry_equity),
        "ebitda_margin": round4(margin),
        "multiple": round2(mult),
        "entry_multiple": round2(mult),
        "exit_multiple": round2(exit_mult),
        # Params
        "sector_profile": profile.name,
        "revenue_growth": round4(growth),
        "capex_pct": round4(capex_pct),
        "wcr_pct": round4(wcr_pct),
        "interest_rate": round4(wavg_rate),
        "tax_rate": round4(TAX_RATE),
        "holding_period": n_years,
        # Sources & Uses
        "entry_revenue": round2(revenue),
        "entry_ebitda": round2(entry_ebitda),
        "entry_ev": round2(entry_ev),
        "entry_transaction_fees": round2(entry_transaction_fees),
        "entry_financing_fees": round2(entry_financing_fees),
        "entry_min_cash": round2(entry_min_cash),
        "entry_uses_total": round2(entry_uses_total),
        "entry_debt": round2(entry_debt),
        "entry_equity": round2(entry_equity),
        "leverage_entry": round2(leverage_entry),
        # V3: tranche detail
        "debt_tranches_detail": debt_tranches_detail,
        # Exit
        "exit_revenue": round2(exit_revenue),
        "exit_ebitda": round2(exit_ebitda),
        "exit_ev": round2(exit_ev),
        "exit_debt": round2(exit_debt),
        "exit_cash": round2(exit_cash),
        "exit_net_debt": round2(exit_net_debt),
        "exit_equity": round2(exit_equity),
        "leverage_exit": round2(leverage_exit),
        # Returns (gross, pre-waterfall)
        "moic": round2(moic),
        "irr": round4(irr),
        # V3: Waterfall
        "waterfall": waterfall,
        # Projections
        "projections": projections,
    }


# ============================================================
# Alias rétro-compatible
# ============================================================

def calculate_valuation(estimated_revenue: float, sector_or_naf: str = "") -> dict:
    """Wrapper rétro-compatible — délègue à run_lbo_model()."""
    return run_lbo_model(estimated_revenue, sector_or_naf)


# ============================================================
# Matrice de sensibilité IRR
# ============================================================

def generate_sensitivity_matrix(
    revenue: float,
    sector_or_naf: str,
    base_entry: float,
    base_exit: float,
    base_leverage: float,
    *,
    entry_range: float = 1.0,
    exit_range: float = 1.0,
    step: float = 0.5,
) -> dict[str, dict[str, float]]:
    """Génère une matrice de sensibilité IRR (Entry × Exit multiples).

    Returns:
        Nested dict : matrix[entry_label][exit_label] = IRR float.
        Retourne {} si les inputs sont invalides.
    """
    if revenue <= 0 or base_entry <= 0 or base_exit <= 0:
        return {}

    entry_mults = [
        round(base_entry + i * step, 1)
        for i in range(int(-entry_range / step), int(entry_range / step) + 1)
    ]
    entry_mults = [m for m in entry_mults if m > 0]

    exit_mults = [
        round(base_exit + i * step, 1)
        for i in range(int(-exit_range / step), int(exit_range / step) + 1)
    ]
    exit_mults = [m for m in exit_mults if m > 0]

    if not entry_mults or not exit_mults:
        return {}

    matrix: dict[str, dict[str, float]] = {}
    for em in entry_mults:
        row_label = f"{em:.1f}x"
        matrix[row_label] = {}
        for xm in exit_mults:
            result = run_lbo_model(
                revenue, sector_or_naf,
                override_entry_mult=em,
                override_exit_mult=xm,
                override_leverage=base_leverage,
            )
            matrix[row_label][f"{xm:.1f}x"] = result.get("irr", 0.0)

    return matrix


# ============================================================
# Async wrappers (pour appels directs depuis les routeurs FastAPI)
# ============================================================

async def async_run_lbo_model(
    revenue: float,
    sector_or_naf: str = "",
    *,
    holding_period: int = HOLDING_PERIOD,
    override_entry_mult: float | None = None,
    override_exit_mult: float | None = None,
    override_leverage: float | None = None,
    debt_structure: list[dict] | None = None,
    management_package: dict | None = None,
    calibrated_profile: SectorProfile | None = None,
    override_entry_ebitda: float | None = None,
) -> dict:
    """Async wrapper autour de run_lbo_model V3 (CPU sub-ms, pas de to_thread)."""
    return run_lbo_model(
        revenue, sector_or_naf,
        holding_period=holding_period,
        override_entry_mult=override_entry_mult,
        override_exit_mult=override_exit_mult,
        override_leverage=override_leverage,
        debt_structure=debt_structure,
        management_package=management_package,
        calibrated_profile=calibrated_profile,
        override_entry_ebitda=override_entry_ebitda,
    )


async def async_generate_sensitivity_matrix(
    revenue: float,
    sector_or_naf: str,
    base_entry: float,
    base_exit: float,
    base_leverage: float,
    *,
    entry_range: float = 1.0,
    exit_range: float = 1.0,
    step: float = 0.5,
) -> dict[str, dict[str, float]]:
    """Async wrapper autour de generate_sensitivity_matrix."""
    return generate_sensitivity_matrix(
        revenue, sector_or_naf,
        base_entry, base_exit, base_leverage,
        entry_range=entry_range, exit_range=exit_range, step=step,
    )
