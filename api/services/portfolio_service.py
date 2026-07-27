"""
Portfolio service — post-acquisition monitoring
"""
from __future__ import annotations

import random
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.portfolio import PortfolioCompany, MonthlyKPI
from api.models.sourcing import SourcedTarget


def _add_months(month_start: date, delta_months: int) -> date:
    month_index = (month_start.year * 12 + month_start.month - 1) + delta_months
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


async def list_portfolio_companies(db: AsyncSession) -> list[PortfolioCompany]:
    result = await db.execute(
        select(PortfolioCompany).order_by(PortfolioCompany.entry_date.desc(), PortfolioCompany.id.desc())
    )
    return list(result.scalars().all())


async def get_portfolio_company(db: AsyncSession, portfolio_company_id: int) -> PortfolioCompany | None:
    return await db.get(PortfolioCompany, portfolio_company_id)


async def get_portfolio_company_by_target_id(
    db: AsyncSession,
    sourced_target_id: int,
) -> PortfolioCompany | None:
    result = await db.execute(
        select(PortfolioCompany).where(PortfolioCompany.sourced_target_id == sourced_target_id)
    )
    return result.scalar_one_or_none()


async def list_monthly_kpis(db: AsyncSession, portfolio_company_id: int) -> list[MonthlyKPI]:
    result = await db.execute(
        select(MonthlyKPI)
        .where(MonthlyKPI.portfolio_company_id == portfolio_company_id)
        .order_by(MonthlyKPI.month_date.asc())
    )
    return list(result.scalars().all())


async def ensure_portfolio_company_with_mock_kpis(
    db: AsyncSession,
    sourced_target: SourcedTarget,
) -> PortfolioCompany:
    existing = await get_portfolio_company_by_target_id(db, sourced_target.id)
    if existing:
        return existing

    company = PortfolioCompany(
        sourced_target_id=sourced_target.id,
        company_name=sourced_target.company_name,
        entry_date=date.today(),
    )
    db.add(company)
    await db.flush()

    rng = random.Random(hash(f"portfolio::{sourced_target.company_name}"))

    annual_revenue = sourced_target.revenue_estimate or rng.uniform(8_000_000, 35_000_000)
    monthly_budget_revenue = annual_revenue / 12

    if sourced_target.revenue_estimate and sourced_target.ebitda_estimate:
        base_margin = max(0.05, min(0.40, sourced_target.ebitda_estimate / sourced_target.revenue_estimate))
    else:
        base_margin = rng.uniform(0.10, 0.24)

    cash_balance = monthly_budget_revenue * rng.uniform(1.3, 2.8)

    current_month = date.today().replace(day=1)
    start_month = _add_months(current_month, -11)

    for i in range(12):
        month_date = _add_months(start_month, i)

        growth_factor = 1 + (i * rng.uniform(0.003, 0.015))
        budget_revenue = monthly_budget_revenue * growth_factor
        actual_revenue = budget_revenue * rng.uniform(0.92, 1.08)

        budget_ebitda = budget_revenue * base_margin
        actual_margin = max(0.02, base_margin + rng.uniform(-0.03, 0.03))
        actual_ebitda = actual_revenue * actual_margin

        cash_balance = max(
            monthly_budget_revenue * 0.25,
            cash_balance + actual_ebitda * rng.uniform(0.20, 0.45) + rng.uniform(-200_000, 180_000),
        )

        kpi = MonthlyKPI(
            portfolio_company_id=company.id,
            month_date=month_date,
            actual_revenue=round(actual_revenue, 2),
            budget_revenue=round(budget_revenue, 2),
            actual_ebitda=round(actual_ebitda, 2),
            budget_ebitda=round(budget_ebitda, 2),
            cash_balance=round(cash_balance, 2),
        )
        db.add(kpi)

    await db.flush()
    await db.refresh(company)
    return company
