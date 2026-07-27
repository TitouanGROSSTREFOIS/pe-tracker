"""
Company Pydantic schemas — request/response models
"""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, Field


# ── Response ──────────────────────────────────────────
class CompanyBase(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    exchange: str | None = None
    currency: str | None = "USD"


class CompanyCreate(CompanyBase):
    """Used when manually adding a company."""
    market_cap: float | None = None
    description: str | None = None
    employees: int | None = None
    website: str | None = None


class CompanySummary(CompanyBase):
    """Lightweight — used in lists and screener results."""
    id: int
    market_cap: float | None = None
    enterprise_value: float | None = None
    last_price: float | None = None
    is_active: bool = True
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompanyProfile(CompanySummary):
    """Full profile — includes description, employees, financials summary."""
    description: str | None = None
    employees: int | None = None
    website: str | None = None
    ipo_date: date | None = None
    shares_outstanding: float | None = None
    # Embedded latest ratios
    latest_ratios: FinancialRatioOut | None = None
    # Recent financials (last N years)
    financials: list[FinancialOut] = []

    model_config = {"from_attributes": True}


# ── Financial schemas ─────────────────────────────────
class FinancialOut(BaseModel):
    fiscal_year: int
    fiscal_quarter: int | None = None
    period_type: str = "annual"
    period_end: date | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    ebitda: float | None = None
    ebit: float | None = None
    net_income: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    shares_outstanding: float | None = None
    eps: float | None = None

    model_config = {"from_attributes": True}


class FinancialRatioOut(BaseModel):
    fiscal_year: int
    revenue_growth: float | None = None
    ebitda_growth: float | None = None
    gross_margin: float | None = None
    ebitda_margin: float | None = None
    net_margin: float | None = None
    fcf_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    ev_revenue: float | None = None
    ev_ebitda: float | None = None
    pe_ratio: float | None = None
    price_to_book: float | None = None
    fcf_yield: float | None = None
    dividend_yield: float | None = None

    model_config = {"from_attributes": True}


# Rebuild forward refs
CompanyProfile.model_rebuild()
