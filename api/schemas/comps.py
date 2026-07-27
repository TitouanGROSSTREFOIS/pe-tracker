"""
Comps Pydantic schemas — trading comparables
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class CompSetCreate(BaseModel):
    name: str
    description: str | None = None
    tickers: list[str]       # list of tickers to include
    base_year: int | None = None


class CompSetOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    base_year: int | None = None
    ticker_count: int = 0
    created_at: datetime


class CompMemberOut(BaseModel):
    company_id: int
    ticker: str
    name: str

    model_config = {"from_attributes": True}


class CompsTableRow(BaseModel):
    """One row in the comps output table."""
    ticker: str
    name: str
    sector: str | None = None
    country: str | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    revenue: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    revenue_growth: float | None = None
    gross_margin: float | None = None
    ebitda_margin: float | None = None
    net_margin: float | None = None
    ev_revenue: float | None = None
    ev_ebitda: float | None = None
    pe_ratio: float | None = None
    price_to_book: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    fcf_yield: float | None = None
    current_ratio: float | None = None
    # D18/D19 (Tâche B.6/B.7), branché Tâche B.11 : exercice fiscal de la
    # ligne (`base_year` au niveau du comp set est global — ERF.PA porte un
    # exercice différent des autres membres, constaté manquant en B.10) et
    # provenance par champ chiffré, même format structuré que
    # `Deal.financial_provenance` (api/schemas/provenance.py::FieldProvenance).
    fiscal_year: int | None = None
    financial_provenance: dict[str, Any] = {}


class CompsStats(BaseModel):
    """Aggregated statistics for a comps set."""
    mean: dict = {}
    median: dict = {}
    p25: dict = {}
    p75: dict = {}


class CompsTableResponse(BaseModel):
    """Full comps table response."""
    comp_set_id: int
    comp_set_name: str
    base_year: int
    rows: list[CompsTableRow]
    stats: CompsStats
