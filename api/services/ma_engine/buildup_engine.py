"""
buildup_engine.py — Moteur de Build-up / Multiple Arbitrage (FastAPI edition).

Simule une stratégie Buy & Build :
    1. Sélection d'une plateforme (cible principale) et de N add-ons.
    2. Consolidation des revenus et EBITDA + synergies d'économies d'échelle.
    3. Projection sur N ans de l'EBITDA consolidé.
    4. Exit au multiple de la plateforme (Multiple Arbitrage).
    5. Calcul du MoIC et de l'IRR consolidés, comparaison avec le standalone.

Ce module est une **surcouche** qui ne modifie rien au LBO standalone.
Il importe les constantes et helpers partagés depuis valuation_engine
au lieu de les dupliquer.

Revue produit (D37) — hypothèses par défaut auparavant arbitraires et non
documentées (capex 4 %, BFR 15 %, croissance 3 %, levier 4.0x codés en dur
localement) ont été remplacées par les valeurs du profil sectoriel
`professional_svc` ("Conseil, Juridique & Ingénierie") de `LBO_PROFILES` —
c'est le SEUL profil calibré sur un CompSet réel (D22) et, plus important,
TOUTES les cibles sourcées par ce projet appartiennent par construction à ce
secteur (le pipeline de sourcing filtre sur les codes NAF 71.20B/71.12B —
Contrôle Technique / Ingénierie, voir `sourcing_service.py`). Ce n'est donc
pas un choix arbitraire : c'est LE secteur réel de 100 % des plateformes et
add-ons manipulables dans l'app. Ces valeurs restent des PARAMÈTRES NOMMÉS,
tous surchageables via les champs optionnels de `calculate_buildup()`
(exposés côté API par `BuildupRequest` et éditables dans l'UI).

Adapted from the original standalone module for the pe_tracker FastAPI backend.
"""

from __future__ import annotations

import json
import math

from loguru import logger

# ── Imports partagés depuis le moteur LBO standalone ────────
from api.services.ma_engine.valuation_engine import (
    HOLDING_PERIOD,
    INTEREST_RATE,
    LBO_PROFILES,
    MAX_LEVERAGE_PCT,
    SENIOR_DEBT_TURN,
    TAX_RATE,
    compute_irr,
    round2,
    round4,
)
# CALIBRATED_SECTOR_PROFILE_KEY vit dans sector_calibration.py (D22) — c'est
# la seule constante qui relie "professional_svc" au CompSet TIC réel.
from api.services.ma_engine.sector_calibration import CALIBRATED_SECTOR_PROFILE_KEY

# ── Profil sectoriel de référence (D37) — voir docstring module ────────
_SECTOR_DEFAULT = LBO_PROFILES[CALIBRATED_SECTOR_PROFILE_KEY]

DEFAULT_GROWTH: float = _SECTOR_DEFAULT.revenue_growth      # 4 % (profil TIC)
DEFAULT_MARGIN: float = _SECTOR_DEFAULT.ebitda_margin        # 15 % (profil TIC)
DEFAULT_CAPEX_PCT: float = _SECTOR_DEFAULT.capex_pct         # 2 % du CA (profil TIC)
DEFAULT_WCR_PCT: float = _SECTOR_DEFAULT.wcr_pct             # 15 % de ΔCA (profil TIC)
DEFAULT_ENTRY_MULTIPLE: float = _SECTOR_DEFAULT.entry_multiple  # 7.0x (profil TIC)
DEFAULT_LEVERAGE_TURNS: float = SENIOR_DEBT_TURN              # 4.0x EBITDA (partagé LBO standalone)


# ============================================================
# Helpers internes
# ============================================================

def _safe_float(target: dict, key: str, fallback: float = 0.0) -> float:
    """Extrait un float depuis un dict cible, robuste aux None / str / 0."""
    val = target.get(key)
    if val is None:
        return fallback
    try:
        return float(val)
    except (ValueError, TypeError):
        return fallback


def _resolve_target_financials(target: dict) -> tuple[float, float, float, bool]:
    """Résout (ebitda, ev, entry_multiple, estimated) pour une cible.

    Certaines cibles réelles en base (ex. les plateformes marché type
    Artelia/Dekra, ajoutées par la voie sourcing "grands groupes" plutôt que
    par le quick-screen OSINT) n'ont qu'un CA estimé, sans EBITDA/EV/
    multiple — le quick-screen n'a jamais tourné dessus. Auparavant, une
    cible sans EBITDA/EV était soit rejetée (plateforme → résultat vide),
    soit silencieusement exclue (add-on → `continue` sans le signaler),
    rendant la fonctionnalité inutilisable sur les vraies plateformes du
    projet. On applique ici EXACTEMENT la même formule que le quick-screen
    OSINT utilise déjà pour toutes les autres cibles du projet (voir
    `sourcing_service.py` : ebitda = CA × marge secteur, EV = ebitda ×
    multiple secteur, profil `professional_svc` — vérifié empiriquement :
    100 % des cibles quick-screenées en base ont un ratio EBITDA/CA = 15 %
    et EV/EBITDA = 7.0x, exactement `DEFAULT_MARGIN`/`DEFAULT_ENTRY_MULTIPLE`
    ci-dessus). `estimated=True` signale à l'appelant (routeur/UI) que ces
    chiffres sont une estimation sectorielle par défaut, pas une donnée
    propre à la cible — jamais affiché comme un fait sans le dire.
    """
    revenue = _safe_float(target, "estimated_revenue")
    ebitda = _safe_float(target, "ebitda")
    ev = _safe_float(target, "ev")
    multiple = _safe_float(target, "entry_multiple") or _safe_float(target, "multiple")
    estimated = False

    if ebitda <= 0 and revenue > 0:
        ebitda = revenue * DEFAULT_MARGIN
        estimated = True
    if ev <= 0 and ebitda > 0:
        mult = multiple if multiple > 0 else DEFAULT_ENTRY_MULTIPLE
        ev = ebitda * mult
        estimated = True
    if multiple <= 0 and ev > 0 and ebitda > 0:
        multiple = ev / ebitda

    return ebitda, ev, multiple, estimated


def _extract_growth_from_projections(target: dict) -> float:
    """Extrait le taux de croissance implicite depuis les projections LBO."""
    proj_raw = target.get("lbo_projections") or target.get("projections") or []
    if isinstance(proj_raw, str):
        try:
            proj_raw = json.loads(proj_raw)
        except (json.JSONDecodeError, TypeError):
            proj_raw = []

    if isinstance(proj_raw, list) and len(proj_raw) >= 2:
        rev_0 = proj_raw[0].get("revenue", 0)
        rev_1 = proj_raw[1].get("revenue", 0)
        if rev_0 > 0 and rev_1 > 0:
            return (rev_1 / rev_0) - 1.0

    return DEFAULT_GROWTH


def _infer_blended_growth(
    platform: dict,
    addons: list[dict],
    total_revenue: float,
) -> float:
    """Infère un taux de croissance consolidé pondéré par les revenus.

    Utilise la croissance implicite Y0→Y1 des projections LBO réelles de
    chaque cible quand elles sont disponibles (`lbo_projections`), sinon
    DEFAULT_GROWTH (croissance du profil sectoriel TIC, 4 %).
    """
    weighted_sum = 0.0
    weight_total = 0.0

    for target in [platform] + addons:
        rev = _safe_float(target, "estimated_revenue")
        if rev <= 0:
            continue
        growth = _extract_growth_from_projections(target)
        weighted_sum += growth * rev
        weight_total += rev

    if weight_total > 0:
        return max(0.0, min(0.50, weighted_sum / weight_total))
    return DEFAULT_GROWTH


def _empty_buildup() -> dict:
    """Retourne un résultat vide (edge case / erreur)."""
    return {
        "consolidated_revenue": 0.0,
        "consolidated_ebitda_pre_syn": 0.0,
        "synergies": 0.0,
        "synergy_pct": 0.0,
        "consolidated_ebitda_post_syn": 0.0,
        "consolidated_margin": 0.0,
        "growth_rate": 0.0,
        "platform_ev": 0.0,
        "platform_multiple": 0.0,
        "platform_url": "N/A",
        "platform_estimated": False,
        "addons_ev": 0.0,
        "addons_count": 0,
        "addon_details": [],
        "excluded_addons": [],
        "total_acquisition_cost": 0.0,
        "blended_entry_multiple": 0.0,
        "entry_debt": 0.0,
        "entry_equity": 0.0,
        "exit_ebitda": 0.0,
        "exit_ev": 0.0,
        "exit_debt": 0.0,
        "exit_equity": 0.0,
        "exit_multiple_applied": 0.0,
        "moic_buildup": 0.0,
        "irr_buildup": 0.0,
        "moic_standalone": 0.0,
        "irr_standalone": 0.0,
        "delta_irr": 0.0,
        "projections": [],
        "assumptions_used": {},
    }


# ============================================================
# Fonction principale — Build-up Engine
# ============================================================

def calculate_buildup(
    platform_target: dict,
    addon_targets: list[dict],
    synergy_pct: float = 0.05,
    capex_pct: float | None = None,
    wcr_pct: float | None = None,
    leverage_turns: float | None = None,
    growth_override: float | None = None,
) -> dict:
    """Simule une stratégie Buy & Build avec consolidation et multiple arbitrage.

    Args:
        platform_target:  Dict de la cible plateforme.
                          Clés attendues : url, estimated_revenue, ebitda, ev,
                          entry_multiple (ou multiple), irr, moic,
                          lbo_projections.
        addon_targets:    Liste de dicts des cibles add-on (même format).
        synergy_pct:      % de synergies sur le CA consolidé (ex : 0.05 = 5 %).
        capex_pct:        Capex en % du CA. Défaut : profil sectoriel TIC (2 %).
        wcr_pct:          BFR en % de la variation annuelle du CA. Défaut :
                          profil sectoriel TIC (15 %).
        leverage_turns:   Levier d'entrée en × EBITDA consolidé post-synergies.
                          Défaut : `SENIOR_DEBT_TURN` du LBO standalone (4.0x).
        growth_override:  Force la croissance annuelle du CA consolidé au lieu
                          de l'inférer des projections réelles des cibles
                          (voir `_infer_blended_growth`).

    Toutes les hypothèses ci-dessus sont des PARAMÈTRES NOMMÉS avec une
    valeur par défaut sourcée (profil sectoriel TIC `professional_svc`,
    seul profil calibré sur un CompSet réel — voir docstring module) —
    jamais une constante muette. L'API et l'UI les exposent, éditables.

    Returns:
        Dict JSON-sérialisable : consolidation, financement, exit,
        rendements, projections, comparaison standalone, ainsi que le bloc
        `assumptions_used` documentant chaque hypothèse effectivement
        appliquée (valeur, origine, modifiable).
    """
    if not platform_target:
        return _empty_buildup()

    platform_rev = _safe_float(platform_target, "estimated_revenue")
    platform_ebitda, platform_ev, platform_mult, platform_estimated = (
        _resolve_target_financials(platform_target)
    )
    platform_irr = _safe_float(platform_target, "irr")
    platform_moic = _safe_float(platform_target, "moic")

    if platform_rev <= 0 or platform_ebitda <= 0 or platform_ev <= 0:
        return _empty_buildup()

    # ── 1. Consolidation Year 0 ─────────────────────────────
    total_addon_rev = 0.0
    total_addon_ebitda = 0.0
    total_addon_ev = 0.0
    addon_details: list[dict] = []
    excluded_addons: list[str] = []

    for addon in addon_targets:
        a_rev = _safe_float(addon, "estimated_revenue")
        a_ebitda, a_ev, a_mult, a_estimated = _resolve_target_financials(addon)
        if a_ev <= 0 or a_ebitda <= 0:
            # Aucune donnée exploitable même après estimation sectorielle
            # (ex. CA lui-même manquant) — exclue et SIGNALÉE, jamais
            # silencieusement disparue du résultat.
            excluded_addons.append(addon.get("url", "N/A"))
            continue

        total_addon_rev += a_rev
        total_addon_ebitda += a_ebitda
        total_addon_ev += a_ev
        addon_details.append({
            "url": addon.get("url", "N/A"),
            "revenue": round2(a_rev),
            "ebitda": round2(a_ebitda),
            "ev": round2(a_ev),
            "entry_multiple": round2(a_mult),
            "estimated": a_estimated,
        })

    consolidated_revenue = platform_rev + total_addon_rev
    consolidated_ebitda_pre = platform_ebitda + total_addon_ebitda
    synergies = consolidated_revenue * synergy_pct
    consolidated_ebitda_post = consolidated_ebitda_pre + synergies

    # ── 2. Total Acquisition Cost & Blended Multiple ────────
    total_acquisition_cost = platform_ev + total_addon_ev
    blended_entry_multiple = (
        total_acquisition_cost / consolidated_ebitda_pre
        if consolidated_ebitda_pre > 0 else 0.0
    )

    # ── 3. Financement consolidé ────────────────────────────
    leverage_used = leverage_turns if leverage_turns is not None else DEFAULT_LEVERAGE_TURNS
    raw_debt = consolidated_ebitda_post * leverage_used
    entry_debt = min(raw_debt, total_acquisition_cost * MAX_LEVERAGE_PCT)
    entry_equity = total_acquisition_cost - entry_debt

    if entry_equity <= 0:
        return _empty_buildup()

    # ── 4. Hypothèses opérationnelles consolidées ───────────
    growth = (
        growth_override if growth_override is not None
        else _infer_blended_growth(platform_target, addon_targets, consolidated_revenue)
    )
    capex_used = capex_pct if capex_pct is not None else DEFAULT_CAPEX_PCT
    wcr_used = wcr_pct if wcr_pct is not None else DEFAULT_WCR_PCT
    consolidated_margin = (
        consolidated_ebitda_post / consolidated_revenue
        if consolidated_revenue > 0 else DEFAULT_MARGIN
    )

    # ── 5. Projections 5 ans ────────────────────────────────
    projections: list[dict] = []

    projections.append({
        "year": 0,
        "revenue": round2(consolidated_revenue),
        "ebitda": round2(consolidated_ebitda_post),
        "interest": 0.0,
        "fcf": 0.0,
        "debt_paydown": 0.0,
        "debt_eoy": round2(entry_debt),
    })

    prev_rev = consolidated_revenue
    debt_outstanding = entry_debt

    for year in range(1, HOLDING_PERIOD + 1):
        rev_t = prev_rev * (1.0 + growth)
        ebitda_t = rev_t * consolidated_margin
        interest_t = debt_outstanding * INTEREST_RATE

        taxable = ebitda_t - interest_t
        tax_t = max(0.0, taxable * TAX_RATE)

        capex_t = rev_t * capex_used
        delta_wcr = max(0.0, (rev_t - prev_rev) * wcr_used)

        fcf_t = ebitda_t - interest_t - tax_t - capex_t - delta_wcr

        paydown = 0.0
        if fcf_t > 0 and debt_outstanding > 0:
            paydown = min(fcf_t, debt_outstanding)
        debt_outstanding -= paydown

        projections.append({
            "year": year,
            "revenue": round2(rev_t),
            "ebitda": round2(ebitda_t),
            "interest": round2(interest_t),
            "fcf": round2(fcf_t),
            "debt_paydown": round2(paydown),
            "debt_eoy": round2(debt_outstanding),
        })
        prev_rev = rev_t

    # ── 6. Exit & Returns (Multiple Arbitrage) ──────────────
    exit_ebitda = projections[-1]["ebitda"]
    exit_debt = projections[-1]["debt_eoy"]
    exit_ev = exit_ebitda * platform_mult  # ← MULTIPLE ARBITRAGE
    exit_equity = max(0.0, exit_ev - exit_debt)

    moic_buildup = exit_equity / entry_equity if entry_equity > 0 else 0.0
    cash_flows = [-entry_equity] + [0.0] * (HOLDING_PERIOD - 1) + [exit_equity]
    irr_buildup = compute_irr(cash_flows)

    delta_irr = irr_buildup - platform_irr

    # ── 7. Assemblage ───────────────────────────────────────
    return {
        # Consolidation Year 0
        "consolidated_revenue": round2(consolidated_revenue),
        "consolidated_ebitda_pre_syn": round2(consolidated_ebitda_pre),
        "synergies": round2(synergies),
        "synergy_pct": round4(synergy_pct),
        "consolidated_ebitda_post_syn": round2(consolidated_ebitda_post),
        "consolidated_margin": round4(consolidated_margin),
        "growth_rate": round4(growth),
        # Acquisition
        "platform_ev": round2(platform_ev),
        "platform_multiple": round2(platform_mult),
        "platform_url": platform_target.get("url", "N/A"),
        "platform_estimated": platform_estimated,
        "addons_ev": round2(total_addon_ev),
        "addons_count": len(addon_details),
        "addon_details": addon_details,
        "excluded_addons": excluded_addons,
        "total_acquisition_cost": round2(total_acquisition_cost),
        "blended_entry_multiple": round2(blended_entry_multiple),
        # Financement
        "entry_debt": round2(entry_debt),
        "entry_equity": round2(entry_equity),
        # Exit (Multiple Arbitrage)
        "exit_ebitda": round2(exit_ebitda),
        "exit_ev": round2(exit_ev),
        "exit_debt": round2(exit_debt),
        "exit_equity": round2(exit_equity),
        "exit_multiple_applied": round2(platform_mult),
        # Rendements
        "moic_buildup": round2(moic_buildup),
        "irr_buildup": round4(irr_buildup),
        # Comparaison Standalone
        "moic_standalone": round2(platform_moic),
        "irr_standalone": round4(platform_irr),
        "delta_irr": round4(delta_irr),
        # Projections consolidées
        "projections": projections,
        # Hypothèses effectivement utilisées (D37 — transparence totale)
        "assumptions_used": {
            "growth_rate": round4(growth),
            "growth_source": "override" if growth_override is not None else "inferred_or_sector_default",
            "capex_pct": round4(capex_used),
            "capex_source": "override" if capex_pct is not None else "sector_default_professional_svc",
            "wcr_pct": round4(wcr_used),
            "wcr_source": "override" if wcr_pct is not None else "sector_default_professional_svc",
            "leverage_turns": round2(leverage_used),
            "leverage_source": "override" if leverage_turns is not None else "shared_lbo_standalone_default",
            "interest_rate": round4(INTEREST_RATE),
            "tax_rate": round4(TAX_RATE),
            "synergy_pct": round4(synergy_pct),
            "sector_profile_reference": _SECTOR_DEFAULT.name,
        },
    }


# ============================================================
# Async wrapper
# ============================================================

async def async_calculate_buildup(
    platform_target: dict,
    addon_targets: list[dict],
    synergy_pct: float = 0.05,
    **kwargs,
) -> dict:
    """Async wrapper autour de calculate_buildup (CPU sub-ms)."""
    return calculate_buildup(platform_target, addon_targets, synergy_pct, **kwargs)
