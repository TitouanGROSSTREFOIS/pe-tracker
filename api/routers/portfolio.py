"""
Portfolio Router — /portfolio endpoints
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.portfolio import (
    PortfolioCompanyListResponse,
    MonthlyKPIListResponse,
)
from api.services.portfolio_service import (
    list_portfolio_companies,
    get_portfolio_company,
    list_monthly_kpis,
)

router = APIRouter(prefix="/portfolio", tags=["Portfolio Monitoring"])


@router.get("", response_model=PortfolioCompanyListResponse)
async def list_companies(db: AsyncSession = Depends(get_db)):
    companies = await list_portfolio_companies(db)
    return PortfolioCompanyListResponse(total=len(companies), companies=companies)


@router.get("/{portfolio_company_id}/kpis", response_model=MonthlyKPIListResponse)
async def get_company_kpis(portfolio_company_id: int, db: AsyncSession = Depends(get_db)):
    company = await get_portfolio_company(db, portfolio_company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Portfolio company not found")

    kpis = await list_monthly_kpis(db, portfolio_company_id)
    return MonthlyKPIListResponse(
        portfolio_company_id=portfolio_company_id,
        company_name=company.company_name,
        total=len(kpis),
        kpis=kpis,
    )
