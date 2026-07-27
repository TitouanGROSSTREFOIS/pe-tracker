"""
Financial statements & computed ratios models
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Any
from sqlalchemy import String, Float, Integer, Date, DateTime, ForeignKey, UniqueConstraint, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.database import Base


class Financial(Base):
    """Normalized financial statement — one row per company per period."""
    __tablename__ = "financials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    period_type: Mapped[str] = mapped_column(String(10), default="annual")  # annual | quarterly
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)  # NULL for annual

    # --- Income Statement ---
    revenue: Mapped[float | None] = mapped_column(Float)
    cost_of_revenue: Mapped[float | None] = mapped_column(Float)
    gross_profit: Mapped[float | None] = mapped_column(Float)
    operating_expenses: Mapped[float | None] = mapped_column(Float)
    sga: Mapped[float | None] = mapped_column(Float)           # Selling, General & Admin
    rd_expense: Mapped[float | None] = mapped_column(Float)    # Research & Development
    depreciation_amortization: Mapped[float | None] = mapped_column(Float)
    ebitda: Mapped[float | None] = mapped_column(Float)
    ebit: Mapped[float | None] = mapped_column(Float)
    interest_expense: Mapped[float | None] = mapped_column(Float)
    pretax_income: Mapped[float | None] = mapped_column(Float)
    income_tax: Mapped[float | None] = mapped_column(Float)
    net_income: Mapped[float | None] = mapped_column(Float)

    # --- Balance Sheet ---
    total_assets: Mapped[float | None] = mapped_column(Float)
    current_assets: Mapped[float | None] = mapped_column(Float)
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float)
    total_liabilities: Mapped[float | None] = mapped_column(Float)
    current_liabilities: Mapped[float | None] = mapped_column(Float)
    total_debt: Mapped[float | None] = mapped_column(Float)
    long_term_debt: Mapped[float | None] = mapped_column(Float)
    total_equity: Mapped[float | None] = mapped_column(Float)
    goodwill: Mapped[float | None] = mapped_column(Float)
    intangible_assets: Mapped[float | None] = mapped_column(Float)

    # --- Cash Flow Statement ---
    operating_cash_flow: Mapped[float | None] = mapped_column(Float)
    capex: Mapped[float | None] = mapped_column(Float)
    free_cash_flow: Mapped[float | None] = mapped_column(Float)
    dividends_paid: Mapped[float | None] = mapped_column(Float)
    share_buybacks: Mapped[float | None] = mapped_column(Float)

    # --- Per-share ---
    shares_outstanding: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    dps: Mapped[float | None] = mapped_column(Float)  # dividends per share

    # --- Provenance (D19, Tâche B.7) — même format que Deal.financial_provenance ---
    # Un champ par poste du compte de résultat effectivement renseigné (ex.
    # "revenue", "ebitda", "net_income", "total_debt") — pas systématique sur
    # les ~25 colonnes ci-dessus, seulement celles réellement peuplées par une
    # source identifiable (FMP/Finnhub/Alpha Vantage/yfinance/ESEF).
    financial_provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship
    company: Mapped["Company"] = relationship("Company", back_populates="financials")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("company_id", "period_type", "period_end", name="uq_financial_period"),
        Index("ix_financials_year", "fiscal_year"),
    )


class FinancialRatio(Base):
    """Computed financial ratios — one row per company per fiscal year."""
    __tablename__ = "financial_ratios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Growth ---
    revenue_growth: Mapped[float | None] = mapped_column(Float)     # YoY %
    ebitda_growth: Mapped[float | None] = mapped_column(Float)
    net_income_growth: Mapped[float | None] = mapped_column(Float)
    eps_growth: Mapped[float | None] = mapped_column(Float)

    # --- Profitability ---
    gross_margin: Mapped[float | None] = mapped_column(Float)       # %
    ebitda_margin: Mapped[float | None] = mapped_column(Float)
    ebit_margin: Mapped[float | None] = mapped_column(Float)
    net_margin: Mapped[float | None] = mapped_column(Float)
    fcf_margin: Mapped[float | None] = mapped_column(Float)

    # --- Returns ---
    roe: Mapped[float | None] = mapped_column(Float)                # Return on Equity %
    roa: Mapped[float | None] = mapped_column(Float)                # Return on Assets %
    roic: Mapped[float | None] = mapped_column(Float)               # Return on Invested Capital %

    # --- Leverage ---
    debt_to_equity: Mapped[float | None] = mapped_column(Float)
    net_debt_to_ebitda: Mapped[float | None] = mapped_column(Float)
    interest_coverage: Mapped[float | None] = mapped_column(Float)
    current_ratio: Mapped[float | None] = mapped_column(Float)

    # --- Valuation Multiples (require market data) ---
    ev_revenue: Mapped[float | None] = mapped_column(Float)
    ev_ebitda: Mapped[float | None] = mapped_column(Float)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    price_to_book: Mapped[float | None] = mapped_column(Float)
    price_to_sales: Mapped[float | None] = mapped_column(Float)
    fcf_yield: Mapped[float | None] = mapped_column(Float)          # %
    dividend_yield: Mapped[float | None] = mapped_column(Float)     # %

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship
    company: Mapped["Company"] = relationship("Company", back_populates="ratios")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year", name="uq_ratio_year"),
    )
