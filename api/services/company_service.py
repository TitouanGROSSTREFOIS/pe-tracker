"""
Company Service — CRUD + profile assembly
"""
from __future__ import annotations
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.company import Company
from api.models.financial import Financial, FinancialRatio
from api.schemas.company import CompanyProfile, CompanySummary, FinancialOut, FinancialRatioOut


async def get_company_by_ticker(ticker: str, db: AsyncSession) -> Company | None:
    """Fetch a company by ticker symbol."""
    result = await db.execute(
        select(Company).where(Company.ticker == ticker.upper())
    )
    return result.scalar_one_or_none()


async def get_company_profile(ticker: str, db: AsyncSession) -> CompanyProfile | None:
    """Full company profile with financials and latest ratios."""
    result = await db.execute(
        select(Company)
        .where(Company.ticker == ticker.upper())
        .options(
            selectinload(Company.financials),
            selectinload(Company.ratios),
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        return None

    # Sort financials by year descending
    financials_sorted = sorted(
        [f for f in company.financials if f.period_type == "annual"],
        key=lambda f: f.fiscal_year,
        reverse=True,
    )

    # Latest ratio
    ratios_sorted = sorted(company.ratios, key=lambda r: r.fiscal_year, reverse=True)
    latest_ratio = ratios_sorted[0] if ratios_sorted else None

    return CompanyProfile(
        id=company.id,
        ticker=company.ticker,
        name=company.name,
        sector=company.sector,
        industry=company.industry,
        country=company.country,
        exchange=company.exchange,
        currency=company.currency,
        market_cap=company.market_cap,
        enterprise_value=company.enterprise_value,
        last_price=company.last_price,
        is_active=company.is_active,
        updated_at=company.updated_at,
        description=company.description,
        employees=company.employees,
        website=company.website,
        ipo_date=company.ipo_date,
        shares_outstanding=company.shares_outstanding,
        latest_ratios=FinancialRatioOut.model_validate(latest_ratio) if latest_ratio else None,
        financials=[FinancialOut.model_validate(f) for f in financials_sorted[:5]],
    )


async def list_companies(
    db: AsyncSession,
    sector: str | None = None,
    country: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CompanySummary], int]:
    """List companies with optional filters. Returns (items, total_count)."""
    query = select(Company).where(Company.is_active == True)  # noqa: E712
    count_query = select(func.count(Company.id)).where(Company.is_active == True)  # noqa: E712

    if sector:
        query = query.where(Company.sector == sector)
        count_query = count_query.where(Company.sector == sector)
    if country:
        query = query.where(Company.country == country)
        count_query = count_query.where(Company.country == country)

    query = query.order_by(Company.market_cap.desc().nullslast()).limit(limit).offset(offset)

    result = await db.execute(query)
    companies = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return [CompanySummary.model_validate(c) for c in companies], total


async def get_financials(
    ticker: str,
    db: AsyncSession,
    period_type: str = "annual",
    limit: int = 5,
) -> list[FinancialOut]:
    """Get financial statements for a company."""
    company = await get_company_by_ticker(ticker, db)
    if not company:
        return []

    result = await db.execute(
        select(Financial)
        .where(Financial.company_id == company.id, Financial.period_type == period_type)
        .order_by(Financial.fiscal_year.desc())
        .limit(limit)
    )
    return [FinancialOut.model_validate(f) for f in result.scalars().all()]


async def get_ratios(
    ticker: str,
    db: AsyncSession,
    limit: int = 5,
) -> list[FinancialRatioOut]:
    """Get computed ratios for a company."""
    company = await get_company_by_ticker(ticker, db)
    if not company:
        return []

    result = await db.execute(
        select(FinancialRatio)
        .where(FinancialRatio.company_id == company.id)
        .order_by(FinancialRatio.fiscal_year.desc())
        .limit(limit)
    )
    return [FinancialRatioOut.model_validate(r) for r in result.scalars().all()]


async def get_distinct_sectors(db: AsyncSession) -> list[str]:
    """Get all distinct sectors in the database."""
    result = await db.execute(
        select(Company.sector)
        .where(Company.sector.isnot(None), Company.is_active == True)  # noqa: E712
        .distinct()
        .order_by(Company.sector)
    )
    return [row[0] for row in result.all()]


async def get_distinct_countries(db: AsyncSession) -> list[str]:
    """Get all distinct countries in the database."""
    result = await db.execute(
        select(Company.country)
        .where(Company.country.isnot(None), Company.is_active == True)  # noqa: E712
        .distinct()
        .order_by(Company.country)
    )
    return [row[0] for row in result.all()]
