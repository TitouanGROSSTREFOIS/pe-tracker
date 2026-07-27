"""
Portfolio schemas — post-acquisition monitoring
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel


class PortfolioCompanyOut(BaseModel):
    id: int
    sourced_target_id: int
    company_name: str
    entry_date: date
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PortfolioCompanyListResponse(BaseModel):
    total: int
    companies: list[PortfolioCompanyOut]


class MonthlyKPIOut(BaseModel):
    id: int
    portfolio_company_id: int
    month_date: date
    actual_revenue: float
    budget_revenue: float
    actual_ebitda: float
    budget_ebitda: float
    cash_balance: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MonthlyKPIListResponse(BaseModel):
    portfolio_company_id: int
    company_name: str
    total: int
    kpis: list[MonthlyKPIOut]
