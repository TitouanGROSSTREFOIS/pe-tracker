"""
Screener Pydantic schemas — dynamic filter DSL
"""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any


class ScreenerFilter(BaseModel):
    """A single filter condition."""
    field: str           # e.g. "sector", "market_cap", "ebitda_margin", "country"
    operator: str        # eq, neq, gt, gte, lt, lte, in, like
    value: Any           # scalar or list


class ScreenerRequest(BaseModel):
    """Screener query payload."""
    filters: list[ScreenerFilter] = []
    sort_by: str = "market_cap"
    sort_dir: str = "desc"      # asc | desc
    limit: int = Field(default=50, le=500)
    offset: int = 0


class SavedScreenCreate(BaseModel):
    name: str
    description: str | None = None
    filters: list[ScreenerFilter]


class SavedScreenOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    filters: list[dict]     # stored as JSON
    result_count: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScreenerResult(BaseModel):
    """Paginated screener response."""
    total: int
    offset: int
    limit: int
    results: list[ScreenerRow]
    sql_preview: str | None = None  # debug: show generated WHERE clause


class ScreenerRow(BaseModel):
    """One row in screener results — company + key metrics."""
    id: int
    ticker: str
    name: str
    sector: str | None = None
    country: str | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    last_price: float | None = None
    revenue: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    revenue_growth: float | None = None
    ebitda_margin: float | None = None
    net_margin: float | None = None
    ev_ebitda: float | None = None
    ev_revenue: float | None = None
    pe_ratio: float | None = None
    roe: float | None = None
    net_debt_to_ebitda: float | None = None

    model_config = {"from_attributes": True}


# Forward ref rebuild
ScreenerResult.model_rebuild()
