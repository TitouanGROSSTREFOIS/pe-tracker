"""
ic_context.py — Structured 9-section IC data context (Tâche "Mémo IC et
deck au format IC professionnel").

Single source of truth consumed identically by:
  - the memo LLM prompt (api/routers/deals.py::generate_memo) — the model
    receives this context and WRITES NARRATIVE ONLY; it invents no number.
  - the Word memo generator (docx_generator.py)
  - the PowerPoint deck generator (ic_deck_generator.py)

Building the same dict once and handing it to all three renderers is what
guarantees the memo and the deck can never show different figures for the
same deal — there is exactly one place where a number is qualified with its
provenance or a table is assembled.

Nothing here is a new valuation formula: `build_returns_sensitivity` only
CALLS the existing `run_lbo_model` (varying exit multiple / leverage) with
the saved scenario's own frozen sector profile, reconstructed from its
`result_json` — never a re-derivation of the LBO/calibration math itself.

Any datum the tool genuinely does not have is flagged with `DD_MARKER`
rather than invented (the zero-fabrication principle applies to narrative
inputs exactly as it already applies to every figure in the product).
"""
from __future__ import annotations

import re
from typing import Any

from api.services.ma_engine.valuation_engine import MAX_LEVERAGE_PCT, SectorProfile, run_lbo_model
from api.services.ma_engine.sector_risks import get_sector_risk_candidates
from api.schemas.provenance import DataProvenance, field_provenance_from_json

DD_MARKER = "[To be completed in due diligence — data not available from automated analysis]"

# Tâche "P0 : un seul deal dans les 3 documents" (Partie E) — la
# recommandation positive autorisée dépend de la provenance de l'EBITDA du
# deal, PAS du jugement libre du LLM : jamais un "Proceed with the
# acquisition" complet tant que l'EBITDA qui pilote toute l'analyse reste une
# ESTIMATE non confirmée par des comptes réels.
_RECOMMENDATION_LABEL_ESTIMATED = "Proceed to LOI / obtain audited financials"
_RECOMMENDATION_LABEL_REAL = "Proceed with the acquisition"

# The 9 section headings, in order — the LLM prompt requires these EXACT H2
# headings; both renderers (docx/pptx) extract sections by this same list so
# a heading typo can never silently drop a section from one output only.
MEMO_SECTIONS: tuple[str, ...] = (
    "I. Executive Summary", "II. Company Overview", "III. Industry & Market",
    "IV. Financial Analysis", "V. Investment Thesis", "VI. Deal Terms & Structure",
    "VII. Returns Analysis", "VIII. Risk Factors", "IX. Recommendation",
)

# Grid points around the saved scenario's own exit multiple / leverage —
# mirrors the step/range convention already used by
# `valuation_engine.generate_sensitivity_matrix` (±1.0, step 0.5).
_SENSITIVITY_OFFSETS: tuple[float, ...] = (-1.0, -0.5, 0.0, 0.5, 1.0)


def _build_feasible_leverage_axis(
    base_leverage: float, entry_ebitda: float, entry_ev: float,
    count: int = 5, step: float = 0.5,
) -> list[float]:
    """Tâche "P1 : physique financière du modèle LBO" (Partie G) — builds a
    leverage (× EBITDA) axis around the scenario's own base leverage, but
    never yields two turns the engine's own MAX_LEVERAGE_PCT debt cap would
    realize as the IDENTICAL debt quantum. Before this fix, whenever a
    scenario's base case already sat at (or above) that cap — Ingebime's
    3.6x base leverage IS exactly its cap — every leverage ≥ base clipped
    to the same capped debt amount, so the sensitivity grid shipped 3
    byte-identical rows (same IRR/MOIC to the last cent). Walks outward in
    `step` increments, clips each candidate to the actually-feasible
    ceiling, and keeps walking on the DOWNSIDE until `count` distinct
    values are found — the base case (or its capped equivalent) is always
    included; a duplicate clipped value is simply skipped in favour of the
    next feasible one further down."""
    if entry_ebitda <= 0:
        return sorted({round(base_leverage + d, 2) for d in _SENSITIVITY_OFFSETS if base_leverage + d >= 0})
    max_feasible = (entry_ev * MAX_LEVERAGE_PCT) / entry_ebitda

    values: set[float] = set()
    k = 0
    while len(values) < count and k < 200:
        signs = (0,) if k == 0 else (-1, 1)
        for sign in signs:
            candidate = base_leverage + sign * k * step
            if candidate < 0:
                continue
            values.add(round(min(candidate, max_feasible), 2))
        k += 1

    result = sorted(values)
    if len(result) > count:
        result = sorted(sorted(result, key=lambda v: abs(v - base_leverage))[:count])
    return result


def extract_markdown_section(markdown_text: str | None, heading: str) -> list[str]:
    """Extracts the raw lines (bold markers left intact) under a given H2
    heading, up to the next H2 or the end of the document. Returns [] if the
    section is absent — never invented. Shared by the docx and pptx
    renderers so both cut the same memo the same way."""
    if not markdown_text:
        return []
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    collecting = False
    out: list[str] = []
    for line in lines:
        if line.strip().startswith("## "):
            collecting = line.strip()[3:].strip().lower() == heading.lower()
            continue
        if collecting and line.strip():
            out.append(line.strip())
    return out


def strip_markdown_bold(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text)


# ============================================================
# Provenance qualification (moved from api/routers/deals.py — same rules,
# single copy now shared by the prompt AND the docx/pptx renderers).
# ============================================================

def qualify_amount(value: float | None, field: str, provenance: dict | None) -> str:
    """Formats an amount WITH its provenance qualification — never a bare
    figure. Same rules the memo prompt has enforced since D18."""
    if value is None:
        return "Not disclosed"
    money = f"€{value:,.0f}"
    field_prov = (provenance or {}).get(field)
    if not field_prov:
        return f"{money} (origin unknown — not tracked)"

    label = field_prov.get("provenance", "UNKNOWN")
    ref = field_prov.get("reference")
    as_of = field_prov.get("as_of")

    if label == "REGISTRY":
        return f"{money} (official registry filing{f', FY{as_of}' if as_of else ''})"
    if label == "DOCUMENT":
        return f"{money} (extracted from uploaded document{f', FY{as_of}' if as_of else ''}: {ref or 'unspecified file'})"
    if label == "MARKET":
        return f"{money} (market data provider: {ref or 'unspecified'})"
    if label == "ESTIMATE":
        return f"{money} (estimated — {ref or 'method not specified'})"
    if label == "MANUAL":
        return f"{money} (manually entered by the analyst{f', FY{as_of}' if as_of else ''})"
    return f"{money} (origin unknown — not tracked)"


def qualify_entry_multiple(result: dict) -> str:
    """Qualifies an LBO scenario's entry multiple with its calibration chain
    (D22) if applicable, else as a generic sector profile assumption."""
    mult = result.get("entry_multiple")
    if mult is None:
        return "Not disclosed"
    calibration = result.get("calibration") or {}
    if calibration.get("sufficient") and calibration.get("applicable"):
        median = calibration.get("median_ev_ebitda")
        median_txt = f"{median:.1f}x" if median is not None else "N/A"
        return (
            f"{mult:.2f}x (derived: {median_txt} listed comparables "
            f"median, CompSet '{calibration.get('comp_set_name')}', n={calibration.get('sample_size')} "
            f"− {calibration.get('size_illiquidity_discount', 0) * 100:.0f}% "
            f"{calibration.get('discount_label', 'size & illiquidity discount')})"
        )
    return f"{mult:.2f}x (sector profile assumption: {result.get('sector_profile', 'N/A')})"


def _margin_provenance_label(financial_provenance: dict, field: str) -> str:
    entry = (financial_provenance or {}).get(field) or {}
    label = entry.get("provenance")
    return {
        "MARKET": "market data (listed comparables)",
        "DOCUMENT": "listed comparables (document)",
        "ESTIMATE": "estimated — sector profile assumption",
        "REGISTRY": "official registry filing",
        "MANUAL": "manually entered by the analyst",
    }.get(label, "origin unknown — not tracked")


# ============================================================
# Returns sensitivity — orchestration only, no new formula (Étape 4).
# ============================================================

def reconstruct_scenario_profile(result_json: dict) -> SectorProfile | None:
    """Rebuilds the EXACT frozen SectorProfile a saved scenario was computed
    with, from its own `result_json` — avoids any risk of the sensitivity
    grid silently drifting onto a re-resolved generic profile (which is
    exactly what calling `generate_sensitivity_matrix` directly would do:
    it re-resolves `resolve_profile(sector_or_naf)` internally and does not
    accept a `calibrated_profile` override)."""
    required = ("sector_profile", "ebitda_margin", "entry_multiple", "revenue_growth", "capex_pct", "wcr_pct")
    if any(result_json.get(k) is None for k in required):
        return None
    # Recompute the margin from the two stored EURO amounts (entry_ebitda /
    # entry_revenue) at full precision rather than trusting the stored
    # `ebitda_margin` field, which is rounded to 4dp — a real, non-"round"
    # entry EBITDA (Tâche "Le moteur LBO accepte un EBITDA réel en entrée")
    # would otherwise reintroduce a tiny drift when reconstructing the
    # profile, and the sensitivity grid's center cell would no longer
    # reproduce the saved scenario exactly. Falls back to the stored field
    # if the two amounts aren't both available.
    entry_revenue = result_json.get("entry_revenue")
    entry_ebitda = result_json.get("entry_ebitda")
    margin = (
        entry_ebitda / entry_revenue
        if entry_revenue and entry_ebitda and entry_revenue > 0
        else result_json["ebitda_margin"]
    )
    return SectorProfile(
        name=result_json["sector_profile"],
        ebitda_margin=margin,
        entry_multiple=result_json["entry_multiple"],
        revenue_growth=result_json["revenue_growth"],
        capex_pct=result_json["capex_pct"],
        wcr_pct=result_json["wcr_pct"],
    )


# Tâche "P2 : crédibilité de la thèse" (Partie D) — le CompSet TIC calibré
# (D22) inclut deux membres dont l'activité principale n'est PAS du TIC pur :
# Core Laboratories (services pétroliers — analyse de réservoir/laboratoire
# pour l'industrie pétrolière, coté CLB) et Mistras Group (inspection
# industrielle/contrôle non destructif — adjacent, souvent classé aux côtés
# des services pétroliers, coté MG). Fait public, pas une donnée financière
# recalculée — signalé honnêtement partout où la liste des comparables est
# montrée, jamais retiré silencieusement du CompSet (hors périmètre : le
# calibrage/CompSet lui-même n'est pas modifié).
_ADJACENT_SECTOR_TICKERS: dict[str, str] = {
    "CLB": "Core Laboratories — oilfield services (reservoir/laboratory analysis for the oil & gas industry), not pure TIC.",
    "MG": "Mistras Group — industrial inspection / non-destructive testing, adjacent to pure TIC (often oilfield-services-adjacent clientele).",
}


_SENSITIVITY_METHOD_NOTE = (
    "Recalculated with the same valuation model used throughout this "
    "document, reusing the base-case scenario's own frozen sector profile "
    "(EBITDA margin, entry multiple, revenue growth, capex, WCR) exactly as "
    "saved — only the two named axes are varied across the grid. No new "
    "formula."
)


def compute_exit_leverage_sensitivity(revenue: float, sector_or_naf: str, result: dict) -> dict | None:
    """Exit multiple × leverage sensitivity grid (IRR + MOIC per cell),
    computed by repeatedly CALLING `run_lbo_model` — never a new formula —
    with the scenario's own frozen sector profile reconstructed from `result`.
    The center cell (base exit multiple, base leverage) reproduces the saved
    scenario's own IRR/MOIC exactly — the sanity check that this grid is
    faithful to the real base case rather than a re-derivation. Takes plain
    primitives so it is reusable by the memo/deck context AND the Excel
    export, which have no ORM `deal`/`reference_scenario` objects to hand."""
    profile = reconstruct_scenario_profile(result)
    base_exit = result.get("exit_multiple")
    base_leverage = result.get("leverage_entry")
    holding_period = result.get("holding_period")
    if profile is None or base_exit is None or base_leverage is None or not holding_period:
        return None
    if not revenue or revenue <= 0:
        return None

    # Round to 2dp rather than 1dp: preserves the exact base-case value at
    # offset 0 (e.g. 8.16x, not rounded to a "clean" 8.2x) so the grid's own
    # center cell reproduces the saved scenario's IRR/MOIC exactly instead of
    # drifting by rounding to a nearby display-friendly multiple.
    exit_axis = sorted({round(base_exit + d, 2) for d in _SENSITIVITY_OFFSETS if base_exit + d > 0})
    entry_ebitda = result.get("entry_ebitda") or 0.0
    entry_ev = result.get("entry_ev") or 0.0
    leverage_axis = _build_feasible_leverage_axis(base_leverage, entry_ebitda, entry_ev)
    if not exit_axis or not leverage_axis:
        return None

    grid = []
    for lev in leverage_axis:
        cells = []
        for ex in exit_axis:
            res = run_lbo_model(
                revenue=revenue,
                sector_or_naf=sector_or_naf,
                holding_period=int(holding_period),
                calibrated_profile=profile,
                override_exit_mult=ex,
                override_leverage=lev,
            )
            cells.append({"exit_multiple": ex, "irr": res.get("irr"), "moic": res.get("moic")})
        grid.append({"leverage": lev, "cells": cells})

    return {
        "exit_axis": exit_axis,
        "leverage_axis": leverage_axis,
        "grid": grid,
        "base_exit_multiple": base_exit,
        "base_leverage": base_leverage,
        "method": _SENSITIVITY_METHOD_NOTE,
    }


def compute_entry_exit_sensitivity(revenue: float, sector_or_naf: str, result: dict) -> dict | None:
    """Entry multiple × exit multiple sensitivity grid (IRR + MOIC per cell),
    leverage held at the scenario's own base value — same reconstruction
    approach and same exactness guarantee as `compute_exit_leverage_sensitivity`."""
    profile = reconstruct_scenario_profile(result)
    base_entry = result.get("entry_multiple")
    base_exit = result.get("exit_multiple")
    base_leverage = result.get("leverage_entry")
    holding_period = result.get("holding_period")
    if profile is None or base_entry is None or base_exit is None or base_leverage is None or not holding_period:
        return None
    if not revenue or revenue <= 0:
        return None

    entry_axis = sorted({round(base_entry + d, 2) for d in _SENSITIVITY_OFFSETS if base_entry + d > 0})
    exit_axis = sorted({round(base_exit + d, 2) for d in _SENSITIVITY_OFFSETS if base_exit + d > 0})
    if not entry_axis or not exit_axis:
        return None

    grid = []
    for en in entry_axis:
        cells = []
        for ex in exit_axis:
            res = run_lbo_model(
                revenue=revenue,
                sector_or_naf=sector_or_naf,
                holding_period=int(holding_period),
                calibrated_profile=profile,
                override_entry_mult=en,
                override_exit_mult=ex,
                override_leverage=base_leverage,
            )
            cells.append({"exit_multiple": ex, "irr": res.get("irr"), "moic": res.get("moic")})
        grid.append({"entry_multiple": en, "cells": cells})

    return {
        "entry_axis": entry_axis,
        "exit_axis": exit_axis,
        "grid": grid,
        "base_entry_multiple": base_entry,
        "base_exit_multiple": base_exit,
        "method": _SENSITIVITY_METHOD_NOTE,
    }


def build_returns_sensitivity(deal, reference_scenario) -> dict | None:
    """Exit multiple × leverage sensitivity grid for the memo/deck (D23 ORM
    objects) — thin wrapper around `compute_exit_leverage_sensitivity`."""
    if reference_scenario is None or not deal.target_revenue or deal.target_revenue <= 0:
        return None
    assumptions = reference_scenario.assumptions_json or {}
    return compute_exit_leverage_sensitivity(
        deal.target_revenue, assumptions.get("sector_or_naf", ""), reference_scenario.result_json or {},
    )


# ============================================================
# Self-check (Étape 4) — Sources=Uses, returns coherence, EBITDA alignment.
# Reports discrepancies; never silently forces two legitimately different
# figures to match (same convention as the earlier "two multiples" issue).
# ============================================================

def build_self_check(deal, reference_scenario) -> dict:
    checks: list[dict[str, Any]] = []

    if reference_scenario is None:
        checks.append({
            "name": "LBO scenario availability",
            "passed": False,
            "detail": (
                "No saved LBO scenario for this deal — Deal Terms & Structure, "
                "Returns Analysis and the sensitivity table are marked as "
                "'To be completed in DD'."
            ),
        })
        return {"checks": checks, "all_passed": False}

    r = reference_scenario.result_json or {}

    entry_debt = r.get("entry_debt")
    entry_equity = r.get("entry_equity")
    # Tâche "P1 : physique financière du modèle LBO" (Partie E) — Uses n'est
    # plus l'Enterprise Value seule (frais de transaction/financement + cash
    # minimum s'y ajoutent désormais) : ce check doit comparer Sources au
    # total RÉEL des emplois, sinon il signalerait à tort un écart dès que
    # ces frais sont non nuls (un faux FAIL introduit par notre propre fix,
    # pas une vraie incohérence).
    entry_uses_total = r.get("entry_uses_total")
    if None not in (entry_debt, entry_equity, entry_uses_total):
        total_sources = entry_debt + entry_equity
        diff = abs(total_sources - entry_uses_total)
        checks.append({
            "name": "Sources & Uses balance",
            "passed": diff < 1.0,
            "detail": (
                f"Sources (debt €{entry_debt:,.0f} + equity €{entry_equity:,.0f} = "
                f"€{total_sources:,.0f}) vs Uses (EV + transaction/financing fees + minimum "
                f"cash = €{entry_uses_total:,.0f}) — difference €{diff:,.2f}."
            ),
        })

    exit_equity = r.get("exit_equity")
    moic = r.get("moic")
    if None not in (exit_equity, entry_equity, moic) and entry_equity:
        implied_moic = exit_equity / entry_equity
        diff = abs(implied_moic - moic)
        checks.append({
            "name": "Returns consistency (MOIC)",
            "passed": diff < 0.01,
            "detail": (
                f"Exit equity / entry equity = {implied_moic:.4f}x vs stored MOIC "
                f"{moic:.2f}x — difference {diff:.4f} (within rounding)."
            ),
        })

    scenario_ebitda = r.get("entry_ebitda")
    if scenario_ebitda is not None and deal.target_ebitda:
        diff = abs(scenario_ebitda - deal.target_ebitda)
        rel = diff / deal.target_ebitda
        passed = rel < 0.01
        detail = (
            f"Deal-level EBITDA €{deal.target_ebitda:,.0f} vs LBO scenario entry EBITDA "
            f"€{scenario_ebitda:,.0f} — {rel * 100:.1f}% difference."
        )
        if not passed:
            detail += (
                " Explained divergence, not a data error: the deal-level figure uses the "
                "generic sector profile's default EBITDA margin, while the LBO scenario "
                "was built using the calibrated median margin from listed comparables — two "
                "distinct, legitimate estimation methods computed at different points in the "
                "deal lifecycle. Both figures are cited with their own provenance wherever "
                "EBITDA appears in this memo/deck; neither is silently forced to match "
                "the other."
            )
        checks.append({"name": "EBITDA consistency across tables", "passed": passed, "detail": detail})

    return {"checks": checks, "all_passed": all(c["passed"] for c in checks)}


def _build_recommendation_guidance(prov: dict) -> dict[str, Any]:
    """Deterministic (not LLM-judged) gate on Section IX's recommendation:
    the EBITDA driving the entire analysis must be confirmed by real
    financial statements (DOCUMENT/REGISTRY — or MANUAL, a human-entered
    real figure) before a full "Proceed with the acquisition" is allowed.
    On an ESTIMATE (or untracked) EBITDA, only "Proceed to LOI / obtain
    audited financials" is permitted as the positive recommendation label —
    the LLM is instructed to reproduce this exact label verbatim, the same
    verbatim-reproduction pattern already used for DD_MARKER."""
    ebitda_prov = field_provenance_from_json(prov, "target_ebitda")
    ebitda_is_real = bool(
        ebitda_prov is not None
        and ebitda_prov.provenance in (DataProvenance.DOCUMENT, DataProvenance.REGISTRY, DataProvenance.MANUAL)
    )
    required_label = _RECOMMENDATION_LABEL_REAL if ebitda_is_real else _RECOMMENDATION_LABEL_ESTIMATED
    return {
        "ebitda_is_real": ebitda_is_real,
        "ebitda_provenance": ebitda_prov.provenance.value if ebitda_prov else "UNKNOWN",
        "required_positive_label": required_label,
        "rule": (
            f"If the recommendation is positive (not a Pass), the label MUST be exactly "
            f"'{required_label}' — reproduce it verbatim, do not paraphrase it. "
            + (
                "The target's EBITDA is confirmed by real financial statements, so a full "
                "proceed recommendation is permitted."
                if ebitda_is_real else
                "The target's EBITDA is an ESTIMATE, not yet confirmed by audited or "
                "otherwise real financial statements — a full 'Proceed with the "
                "acquisition' is NOT permitted; the recommendation must instead be "
                "conditioned on confirming the financials first."
            )
        ),
    }


# ============================================================
# Master context — one dict, three consumers (prompt, docx, pptx).
# ============================================================

def build_ic_context(deal, reference_scenario=None, comps_table=None, downside_scenario=None) -> dict[str, Any]:
    prov = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
    sourced = getattr(deal, "sourced_target", None)

    # --- II. Company Overview ---
    company_overview = {
        "description": deal.description or (sourced.business_summary if sourced else None) or DD_MARKER,
        "sector": deal.sector or "Not disclosed",
        "industry": deal.industry or "Not disclosed",
        "country": deal.country or "Not disclosed",
        "growth_signals": (sourced.growth_signals if sourced and sourced.growth_signals else None),
        "red_flags": (sourced.red_flags if sourced and sourced.red_flags else None),
        "competitors": (sourced.competitors if sourced and sourced.competitors else None),
        "management_team": DD_MARKER,
        "headcount": DD_MARKER,
    }

    # --- IV. Financial Analysis ---
    margin = None
    if deal.target_revenue and deal.target_ebitda and deal.target_revenue > 0:
        margin = deal.target_ebitda / deal.target_revenue
    financials = {
        "revenue_qualified": qualify_amount(deal.target_revenue, "target_revenue", prov),
        "ebitda_qualified": qualify_amount(deal.target_ebitda, "target_ebitda", prov),
        "enterprise_value_qualified": qualify_amount(deal.enterprise_value, "enterprise_value", prov),
        "ebitda_margin_pct": round(margin * 100, 1) if margin is not None else None,
        "ev_revenue_multiple": deal.ev_revenue_multiple,
        "ev_ebitda_multiple": deal.ev_ebitda_multiple,
        "quality_of_earnings": DD_MARKER,
        "working_capital": DD_MARKER,
        "capex_detail": DD_MARKER,
    }

    # --- VI/VII. LBO scenario, Sources & Uses, Returns ---
    scenario_context = None
    sources_and_uses = None
    if reference_scenario is not None:
        r = reference_scenario.result_json or {}
        fin_prov = r.get("financial_provenance") or {}
        tranches = r.get("debt_tranches_detail") or []

        scenario_ebitda = r.get("entry_ebitda")
        ebitda_reconciliation_note = None
        if scenario_ebitda is not None and deal.target_ebitda and abs(scenario_ebitda - deal.target_ebitda) > max(1.0, 0.01 * deal.target_ebitda):
            ebitda_reconciliation_note = (
                f"This LBO scenario's entry EBITDA (€{scenario_ebitda:,.0f}, "
                f"{_margin_provenance_label(fin_prov, 'ebitda_margin')}) differs from the "
                f"deal-level EBITDA cited in Financial Analysis (€{deal.target_ebitda:,.0f}, "
                f"{_margin_provenance_label(prov, 'target_ebitda') if prov.get('target_ebitda') else 'estimated — generic sector profile'}) "
                f"— two distinct, legitimate EBITDA-margin estimation methods (generic sector "
                f"profile vs CompSet-calibrated median), not a data error. See self-check."
            )

        # Tâche "P0 : un seul deal dans les 3 documents" (Partie F) — le
        # deal-level EV (Section IV, Financial Analysis) et l'entry EV de ce
        # scénario (Section VI, Deal Terms) sont deux chiffres RÉELS mais
        # distincts dès que l'EBITDA est unifié : ce qui reste à concilier,
        # c'est le MULTIPLE (celui posé sur le deal au sourcing vs celui
        # réellement retenu par ce scénario LBO). Sans ce pont explicite, un
        # lecteur externe voit deux EV à quelques pages d'écart sans
        # explication — constat d'une revue IC externe sur Ingebime (secteur
        # non calibré, où l'écart est le plus visible).
        scenario_entry_ev = r.get("entry_ev")
        scenario_entry_multiple = r.get("entry_multiple")
        valuation_reconciliation_note = None
        if (
            scenario_entry_ev is not None and deal.enterprise_value
            and abs(scenario_entry_ev - deal.enterprise_value) > max(1.0, 0.01 * deal.enterprise_value)
        ):
            deal_mult_txt = (
                f"{deal.ev_ebitda_multiple:.2f}x" if deal.ev_ebitda_multiple is not None else "an unrecorded multiple"
            )
            scenario_mult_txt = f"{scenario_entry_multiple:.2f}x" if scenario_entry_multiple is not None else "N/A"
            valuation_reconciliation_note = (
                f"Two Enterprise Value figures appear in this memo, from two distinct multiples "
                f"on the same (unified) EBITDA: the deal-level Enterprise Value (€{deal.enterprise_value:,.0f}, "
                f"at {deal_mult_txt} EV/EBITDA recorded at sourcing) and this LBO scenario's own "
                f"entry Enterprise Value (€{scenario_entry_ev:,.0f}, at the {scenario_mult_txt} "
                f"multiple actually retained for this valuation). The scenario's figures are the "
                f"ones driving the returns analysis in Section VII; the deal-level figure is the "
                f"target's originally recorded valuation. Neither is invented; both are cited "
                f"with their own basis — never presented as if they were the same number."
            )

        # Tâche "P2 : crédibilité de la thèse" (Partie A) — hypothèses
        # figées dans assumptions_json par build_base_case_scenario, jamais
        # recalculées ici : "indicative_bolt_on" en dessous du seuil de CA,
        # sinon "standalone" (comportement inchangé).
        assumptions = reference_scenario.assumptions_json or {}
        sizing_guidance = {
            "tier": assumptions.get("sizing_tier", "standalone"),
            "is_indicative": assumptions.get("sizing_tier") == "indicative_bolt_on",
            "note": assumptions.get("sizing_note"),
        }

        scenario_context = {
            "label": reference_scenario.label,
            "entry_multiple_qualified": qualify_entry_multiple(r),
            "exit_multiple": r.get("exit_multiple"),
            "leverage_entry_x_ebitda": r.get("leverage_entry"),
            "irr": r.get("irr"),
            "moic": r.get("moic"),
            "holding_period_years": r.get("holding_period"),
            "entry_ebitda": scenario_ebitda,
            "entry_ebitda_margin_pct": round(r.get("ebitda_margin", 0) * 100, 1) if r.get("ebitda_margin") is not None else None,
            "revenue_growth_pct": round(r.get("revenue_growth", 0) * 100, 1) if r.get("revenue_growth") is not None else None,
            "interest_rate_pct": round(r.get("interest_rate", 0) * 100, 1) if r.get("interest_rate") is not None else None,
            "ebitda_reconciliation_note": ebitda_reconciliation_note,
            "valuation_reconciliation_note": valuation_reconciliation_note,
            "sizing_guidance": sizing_guidance,
        }

        sources_and_uses = {
            "entry_ev": r.get("entry_ev"),
            # Tâche "P1 : physique financière du modèle LBO" (Partie E) — Uses
            # réels : l'EV seul n'est plus la totalité des emplois.
            "entry_transaction_fees": r.get("entry_transaction_fees"),
            "entry_financing_fees": r.get("entry_financing_fees"),
            "entry_min_cash": r.get("entry_min_cash"),
            "entry_uses_total": r.get("entry_uses_total"),
            "entry_debt": r.get("entry_debt"),
            "entry_equity": r.get("entry_equity"),
            "leverage_entry": r.get("leverage_entry"),
            "tranches": [
                {"name": t.get("name"), "amount": t.get("amount"), "interest_rate": t.get("interest_rate"),
                 "amortization": t.get("amortization")}
                for t in tranches
            ] if tranches else None,
        }

    # Tâche "P2 : crédibilité de la thèse" (Partie B) — cas baissier, en plus
    # du base case : "un mémo d'IC mono-scénario n'existe pas" était le
    # constat de la revue IC externe. Même forme minimale que scenario_context
    # (label/hypothèses clés/IRR/MOIC) — le mémo/deck affichent les deux côte
    # à côte en Section VII, jamais le downside seul ni fusionné avec le base.
    downside_context = None
    if downside_scenario is not None:
        dr = downside_scenario.result_json or {}
        d_assumptions = downside_scenario.assumptions_json or {}
        downside_context = {
            "label": downside_scenario.label,
            "entry_revenue": dr.get("entry_revenue"),
            "revenue_haircut_pct": d_assumptions.get("downside_revenue_haircut_pct"),
            "exit_multiple": dr.get("exit_multiple"),
            "exit_multiple_delta": d_assumptions.get("downside_exit_multiple_delta"),
            "entry_multiple_qualified": qualify_entry_multiple(dr),
            "leverage_entry_x_ebitda": dr.get("leverage_entry"),
            "irr": dr.get("irr"),
            "moic": dr.get("moic"),
            "holding_period_years": dr.get("holding_period"),
        }

    # --- Comparables summary (grounds Section III narrative in real data) ---
    comps_summary = None
    if comps_table and comps_table.rows:
        raw_median_ev_ebitda = comps_table.stats.median.get("ev_ebitda") if comps_table.stats else None
        raw_median_ev_revenue = comps_table.stats.median.get("ev_revenue") if comps_table.stats else None
        # Rounded to 1dp here, at the source dict handed to the memo prompt —
        # the raw stats median carries 4dp (comps_service.py's np.median
        # round(...,4)) and the LLM is instructed to reproduce given numbers
        # verbatim, so an unrounded value here used to render literally as
        # e.g. "12.5551x" in the memo prose (found during Part H review).
        median_ev_ebitda = round(raw_median_ev_ebitda, 1) if raw_median_ev_ebitda is not None else None
        median_ev_revenue = round(raw_median_ev_revenue, 1) if raw_median_ev_revenue is not None else None
        # `sample_size` counts rows with a usable EV/EBITDA — the same
        # population the median above is actually computed from, and the
        # same count `sector_calibration` reports for its own median. The
        # CompSet may hold more members overall (`total_members`) than have
        # a real EBITDA to compute a multiple from; conflating the two would
        # make this note look inconsistent with the calibration chain cited
        # elsewhere for the same CompSet.
        usable_rows = [row for row in comps_table.rows if row.ev_ebitda is not None]

        # Tâche "P2" (Partie D) — honnêteté de taille : la médiane du CompSet
        # est un ANCRAGE DE MARCHÉ, jamais un multiple directement applicable
        # à une cible de quelques M€ face à des comparables cotés de
        # plusieurs Md€. Calcule l'écart de taille réel (market cap min/max
        # du CompSet vs le CA de la cible) plutôt que de l'affirmer sans
        # preuve chiffrée.
        market_caps = [row.market_cap for row in comps_table.rows if row.market_cap]
        size_gap_note = None
        smallest_subset_median_ev_ebitda = None
        if market_caps and deal.target_revenue:
            mcap_lo, mcap_hi = min(market_caps), max(market_caps)
            size_gap_note = (
                f"Comparables are listed companies with market capitalisation from "
                f"€{mcap_lo / 1e9:.1f}bn to €{mcap_hi / 1e9:.1f}bn — several orders of "
                f"magnitude above this target's revenue (€{deal.target_revenue:,.0f}). The "
                f"median EV/EBITDA above is a MARKET ANCHOR, indicative of how the broader "
                f"sector is priced by public markets — it is NOT a multiple directly "
                f"applicable to this target before a substantial size and illiquidity "
                f"discount (see the calibration chain in Section VI, which applies exactly "
                f"such a discount rather than using the raw median)."
            )
            # Médiane du sous-ensemble le plus petit (les 2 comparables les
            # moins capitalisés) — montré À CÔTÉ de la médiane pleine
            # population, jamais à sa place : un sous-échantillon de 2 n'est
            # pas une meilleure estimation statistique, seulement un point de
            # comparaison supplémentaire, plus honnête sur l'écart de taille
            # résiduel même parmi les comparables les plus proches en taille.
            smallest_rows = sorted(
                (row for row in usable_rows if row.market_cap), key=lambda row: row.market_cap,
            )[:2]
            if smallest_rows:
                smallest_vals = [row.ev_ebitda for row in smallest_rows]
                smallest_subset_median_ev_ebitda = round(sum(smallest_vals) / len(smallest_vals), 1)

        adjacent_sector_flags = [
            {"ticker": row.ticker, "name": row.name, "note": _ADJACENT_SECTOR_TICKERS[row.ticker]}
            for row in comps_table.rows if row.ticker in _ADJACENT_SECTOR_TICKERS
        ]

        comps_summary = {
            "comp_set_name": comps_table.comp_set_name,
            "sample_size": len(usable_rows),
            "total_members": len(comps_table.rows),
            "median_ev_ebitda": median_ev_ebitda,
            "median_ev_revenue": median_ev_revenue,
            "tickers": [row.ticker for row in usable_rows],
            "size_gap_note": size_gap_note,
            "smallest_subset_median_ev_ebitda": smallest_subset_median_ev_ebitda,
            "smallest_subset_tickers": [row.ticker for row in smallest_rows] if market_caps and deal.target_revenue else [],
            "adjacent_sector_flags": adjacent_sector_flags or None,
        }

    return {
        "id": deal.id,
        "acquirer_name": deal.acquirer_name,
        "target_name": deal.target_name,
        "deal_type": deal.deal_type,
        "status": deal.status,
        "source": deal.source,
        "source_url": deal.source_url,
        "company_overview": company_overview,
        "financials": financials,
        "reference_lbo_scenario": scenario_context,
        "sources_and_uses": sources_and_uses,
        "downside_scenario": downside_context,
        "comps_summary": comps_summary,
        # Tâche "P2 : crédibilité de la thèse" (Partie C) — candidats de
        # risques sectoriels réels (voir sector_risks.py), jamais des risques
        # génériques ou un "risque" sur l'intégrité du modèle financier — le
        # LLM sélectionne/priorise parmi cette liste, il ne l'invente pas.
        "risk_candidates": get_sector_risk_candidates(deal.sector or ""),
        "sensitivity": build_returns_sensitivity(deal, reference_scenario),
        "self_check": build_self_check(deal, reference_scenario),
        "recommendation_guidance": _build_recommendation_guidance(prov),
        "dd_marker": DD_MARKER,
    }
