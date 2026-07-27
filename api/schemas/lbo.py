"""
Pydantic v2 schemas for the M&A Engine (LBO Standalone & Build-up).

Provides typed, validated I/O contracts for:
  - Paper LBO (valuation_engine)  — V3 with multi-tranche debt & management package
  - Build-up / Multiple Arbitrage (buildup_engine)
  - Sensitivity matrix
  - Excel export
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# V3 — Debt Structure & Management Package Sub-Schemas
# ============================================================

class AmortizationType(str, Enum):
    """Debt amortization profile."""
    BULLET = "bullet"          # In fine — interest only, principal at maturity
    AMORTIZING = "amortizing"  # Linear amortization over the holding period


class DebtTranche(BaseModel):
    """One tranche in a multi-layer debt structure.

    Examples:
      - Senior A: 2.5× EBITDA, 5.0%, amortizing
      - Senior B: 1.0× EBITDA, 6.5%, bullet
      - Mezzanine: 1.0× EBITDA, 10.0%, bullet (PIK-like)
    """
    name: str = Field(..., min_length=1, description="Tranche label (e.g. 'Senior A', 'Mezzanine')")
    amount_turns: float = Field(
        ..., ge=0, description="Tranche size expressed as x EBITDA turns"
    )
    interest_rate: float = Field(
        ..., ge=0, le=1, description="Annual interest rate (decimal, e.g. 0.05 = 5%)"
    )
    amortization: AmortizationType = Field(
        default=AmortizationType.BULLET,
        description="Repayment profile: 'bullet' (in fine) or 'amortizing' (linear)"
    )


class ManagementPackage(BaseModel):
    """Sweet Equity / Ratchet structure for the management team.

    The management package dilutes the fund's equity stake at exit.
    Sweet equity % = share of exit equity allocated to management.
    Ratchet_irr_threshold: if fund IRR exceeds this, management gets
    an extra ratchet_bonus_pct on top of sweet equity.
    """
    sweet_equity_pct: float = Field(
        default=0.0, ge=0, le=0.50,
        description="Management sweet equity share (e.g. 0.15 = 15%)"
    )
    ratchet_irr_threshold: float = Field(
        default=0.25, ge=0, le=1.0,
        description="Fund IRR threshold that triggers the ratchet bonus"
    )
    ratchet_bonus_pct: float = Field(
        default=0.0, ge=0, le=0.20,
        description="Extra equity share if ratchet is triggered (e.g. 0.05 = +5%)"
    )


# ============================================================
# LBO Standalone — V3 Input
# ============================================================

class LBOInput(BaseModel):
    """Input payload for a Paper LBO simulation (V3).

    Backward-compatible: if debt_structure is empty, the engine falls
    back to the V2 single-tranche model (4× EBITDA senior @ 7%).
    """

    revenue: float = Field(..., gt=0, description="Estimated Year-0 revenue (€)")
    sector_or_naf: str = Field(
        default="",
        description="Free-text sector description or NAF code (e.g. '62.01Z', 'B2B SaaS')",
    )
    holding_period: int = Field(default=5, ge=1, le=15, description="Investment horizon (years)")
    override_entry_mult: float | None = Field(
        default=None, gt=0, description="Override entry EV/EBITDA multiple"
    )
    override_exit_mult: float | None = Field(
        default=None, gt=0, description="Override exit EV/EBITDA multiple"
    )
    override_leverage: float | None = Field(
        default=None, ge=0, description="Override senior debt turns (x EBITDA) — ignored if debt_structure provided"
    )

    # ── V3: Multi-tranche debt ───────────────────────────────
    debt_structure: list[DebtTranche] = Field(
        default_factory=list,
        description="Optional multi-tranche debt structure. If empty, uses default single-tranche.",
    )

    # ── V3: Management Package ───────────────────────────────
    management_package: ManagementPackage | None = Field(
        default=None,
        description="Optional management sweet equity / ratchet structure",
    )


# ============================================================
# LBO Projection — V3 (per-tranche detail)
# ============================================================

class DebtTrancheYear(BaseModel):
    """One tranche's state for a given year."""
    name: str
    interest: float
    amortization: float
    balance_eoy: float


class LBOProjectionYear(BaseModel):
    """One year of the LBO cash-flow projection (V3)."""

    year: int
    revenue: float
    ebitda: float
    interest: float          # Total interest (sum of all tranches)
    capex: float
    delta_wcr: float
    taxable_income: float
    tax: float
    fcf: float
    debt_paydown: float      # Total principal repayment
    debt_eoy: float          # Total debt end of year

    # V3: per-tranche breakdown (empty for legacy calls)
    tranches: list[DebtTrancheYear] = []


# ============================================================
# V3 — Waterfall (Fund vs Management)
# ============================================================

class WaterfallOutput(BaseModel):
    """Exit equity distribution between Fund and Management."""
    total_exit_equity: float = 0.0
    management_sweet_pct: float = 0.0
    ratchet_triggered: bool = False
    management_total_pct: float = 0.0
    management_proceeds: float = 0.0
    fund_proceeds: float = 0.0
    fund_moic: float = 0.0
    fund_irr: float = 0.0
    management_moic: float = 0.0


# ============================================================
# LBO Result — V3
# ============================================================

class LBOResult(BaseModel):
    """Full output of a Paper LBO simulation (V3)."""

    # --- Retro-compatible keys (consumed by scoring / persistence) ---
    ebitda: float = 0.0
    ev: float = 0.0
    debt_capacity: float = 0.0
    required_equity: float = 0.0
    ebitda_margin: float = 0.0
    multiple: float = 0.0
    entry_multiple: float = 0.0
    exit_multiple: float = 0.0

    # --- Model parameters ---
    sector_profile: str = "N/A"
    revenue_growth: float = 0.0
    capex_pct: float = 0.0
    wcr_pct: float = 0.0
    interest_rate: float = 0.0  # Weighted average (V3) or flat (V2)
    tax_rate: float = 0.0
    holding_period: int = 5

    # --- Sources & Uses (Entry) ---
    entry_revenue: float = 0.0
    entry_ebitda: float = 0.0
    entry_ev: float = 0.0
    entry_debt: float = 0.0
    entry_equity: float = 0.0
    leverage_entry: float = 0.0

    # --- V3: Per-tranche Sources ---
    debt_tranches_detail: list[dict[str, Any]] = []

    # --- Exit (Year N) ---
    exit_revenue: float = 0.0
    exit_ebitda: float = 0.0
    exit_ev: float = 0.0
    exit_debt: float = 0.0
    exit_equity: float = 0.0
    leverage_exit: float = 0.0

    # --- Returns (gross, pre-waterfall) ---
    moic: float = 0.0
    irr: float = 0.0

    # --- V3: Waterfall (Fund vs Management) ---
    waterfall: WaterfallOutput | None = None

    # --- Annual projections ---
    projections: list[LBOProjectionYear] = []


# ============================================================
# Sensitivity Matrix
# ============================================================

class SensitivityInput(BaseModel):
    """Input for the IRR sensitivity matrix (Entry × Exit multiples)."""

    revenue: float = Field(..., gt=0, description="Year-0 revenue (€)")
    sector_or_naf: str = ""
    base_entry: float = Field(..., gt=0, description="Base entry multiple")
    base_exit: float = Field(..., gt=0, description="Base exit multiple")
    base_leverage: float = Field(default=4.0, ge=0, description="Base leverage turns")
    entry_range: float = Field(default=1.0, gt=0, description="±range on entry multiple")
    exit_range: float = Field(default=1.0, gt=0, description="±range on exit multiple")
    step: float = Field(default=0.5, gt=0, description="Grid step (x)")


class SensitivityCell(BaseModel):
    """One cell in the sensitivity grid."""

    entry_multiple: str
    exit_multiple: str
    irr: float


class SensitivityResult(BaseModel):
    """IRR sensitivity matrix output."""

    entry_multiples: list[str]
    exit_multiples: list[str]
    matrix: dict[str, dict[str, float]]
    """Nested dict: matrix[entry_label][exit_label] = IRR"""


# ============================================================
# Sector Calibration (D22, Tâche B.8)
# ============================================================

class SectorCalibrationOut(BaseModel):
    """Chaîne de calibrage du multiple d'entrée dérivé du CompSet réel."""
    sufficient: bool
    fallback_reason: str | None = None
    applicable: bool = True  # False si le secteur résolu n'est pas celui du CompSet calibré
    sample_size: int = 0
    comp_set_id: int | None = None
    comp_set_name: str | None = None
    tickers: list[str] = []
    fiscal_years: list[int] = []
    median_ebitda_margin: float | None = None
    ebitda_margin_min: float | None = None
    ebitda_margin_max: float | None = None
    median_ev_ebitda: float | None = None
    ev_ebitda_min: float | None = None
    ev_ebitda_max: float | None = None
    size_illiquidity_discount: float = 0.35
    discount_label: str = "size & illiquidity discount, French mid-market"
    derived_entry_multiple: float | None = None
    entry_multiple_provenance: dict[str, Any] | None = None
    ebitda_margin_provenance: dict[str, Any] | None = None


# ============================================================
# LBO Scenarios (D23, Tâche B.8)
# ============================================================

class LBOScenarioCreate(BaseModel):
    """Payload de sauvegarde d'un scénario LBO — action explicite utilisateur."""
    deal_id: int = Field(..., description="Deal auquel rattacher ce scénario")
    label: str = Field(..., min_length=1, max_length=120, description="Libellé saisi par l'utilisateur (ex. 'Base case')")
    assumptions: dict[str, Any] = Field(..., description="Payload complet de la requête LBO")
    result: dict[str, Any] = Field(..., description="Résultat complet du moteur LBO")


class LBOScenarioOut(BaseModel):
    id: int
    deal_id: int
    label: str
    assumptions_json: dict[str, Any]
    result_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class LBOScenarioListItem(BaseModel):
    """Version allégée pour les listes (sans le détail complet)."""
    id: int
    deal_id: int
    label: str
    created_at: datetime
    entry_multiple: float | None = None
    exit_multiple: float | None = None
    irr: float | None = None
    moic: float | None = None

    model_config = {"from_attributes": True}


# ============================================================
# Build-up (Buy & Build)
# ============================================================

class BuildupTargetInput(BaseModel):
    """Minimal target representation for build-up simulation."""

    url: str = "N/A"
    estimated_revenue: float = Field(default=0.0, ge=0)
    ebitda: float = Field(default=0.0, ge=0)
    ev: float = Field(default=0.0, ge=0)
    entry_multiple: float | None = Field(default=None, ge=0)
    multiple: float | None = Field(default=None, ge=0)
    irr: float = 0.0
    moic: float = 0.0
    lbo_projections: list[dict[str, Any]] | str | None = None
    projections: list[dict[str, Any]] | None = None


class BuildupInput(BaseModel):
    """Input payload for a Build-up simulation."""

    platform: BuildupTargetInput = Field(
        ..., description="Platform (main acquisition target)"
    )
    addons: list[BuildupTargetInput] = Field(
        default_factory=list, description="List of add-on targets"
    )
    synergy_pct: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="Synergy % applied to consolidated revenue (e.g. 0.05 = 5%)",
    )


class BuildupAddonDetail(BaseModel):
    """Detail of one add-on in the build-up result."""

    url: str = "N/A"
    revenue: float = 0.0
    ebitda: float = 0.0
    ev: float = 0.0
    entry_multiple: float = 0.0
    estimated: bool = False


class BuildupAssumptions(BaseModel):
    """Hypothèses effectivement appliquées par la simulation (D37 — transparence)."""

    growth_rate: float = 0.0
    growth_source: str = ""
    capex_pct: float = 0.0
    capex_source: str = ""
    wcr_pct: float = 0.0
    wcr_source: str = ""
    leverage_turns: float = 0.0
    leverage_source: str = ""
    interest_rate: float = 0.0
    tax_rate: float = 0.0
    synergy_pct: float = 0.0
    sector_profile_reference: str = ""


class BuildupProjectionYear(BaseModel):
    """One year of consolidated build-up projection."""

    year: int
    revenue: float
    ebitda: float
    interest: float
    fcf: float
    debt_paydown: float
    debt_eoy: float


class BuildupResult(BaseModel):
    """Full output of a Build-up / Multiple Arbitrage simulation."""

    # --- Consolidation Year 0 ---
    consolidated_revenue: float = 0.0
    consolidated_ebitda_pre_syn: float = 0.0
    synergies: float = 0.0
    synergy_pct: float = 0.0
    consolidated_ebitda_post_syn: float = 0.0
    consolidated_margin: float = 0.0
    growth_rate: float = 0.0

    # --- Acquisition ---
    platform_ev: float = 0.0
    platform_multiple: float = 0.0
    platform_url: str = "N/A"
    platform_estimated: bool = False
    addons_ev: float = 0.0
    addons_count: int = 0
    addon_details: list[BuildupAddonDetail] = []
    excluded_addons: list[str] = []
    total_acquisition_cost: float = 0.0
    blended_entry_multiple: float = 0.0

    # --- Financing ---
    entry_debt: float = 0.0
    entry_equity: float = 0.0

    # --- Exit (Multiple Arbitrage) ---
    exit_ebitda: float = 0.0
    exit_ev: float = 0.0
    exit_debt: float = 0.0
    exit_equity: float = 0.0
    exit_multiple_applied: float = 0.0

    # --- Returns ---
    moic_buildup: float = 0.0
    irr_buildup: float = 0.0
    moic_standalone: float = 0.0
    irr_standalone: float = 0.0
    delta_irr: float = 0.0

    # --- Consolidated projections ---
    projections: list[BuildupProjectionYear] = []

    # --- Assumptions actually applied (D37) ---
    assumptions_used: BuildupAssumptions = Field(default_factory=BuildupAssumptions)
