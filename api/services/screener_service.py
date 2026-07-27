"""
Screener Service — dynamic SQL filter builder
"""
from __future__ import annotations
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, and_, or_, desc, asc, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.company import Company
from api.models.financial import Financial, FinancialRatio
from api.models.screener import SavedScreen
from api.schemas.screener import (
    ScreenerRequest,
    ScreenerFilter,
    ScreenerResult,
    ScreenerRow,
    SavedScreenCreate,
    SavedScreenOut,
)

# ─────────────────────────────────────────────
# Filter → SQL clause mapping
# ─────────────────────────────────────────────

# Map filter field names to actual SQLAlchemy columns
FIELD_MAP = {
    # Company fields
    "ticker": Company.ticker,
    "name": Company.name,
    "sector": Company.sector,
    "industry": Company.industry,
    "country": Company.country,
    "exchange": Company.exchange,
    "market_cap": Company.market_cap,
    "enterprise_value": Company.enterprise_value,
    "last_price": Company.last_price,
    "employees": Company.employees,
    # Ratio fields (joined)
    "revenue_growth": FinancialRatio.revenue_growth,
    "ebitda_growth": FinancialRatio.ebitda_growth,
    "gross_margin": FinancialRatio.gross_margin,
    "ebitda_margin": FinancialRatio.ebitda_margin,
    "net_margin": FinancialRatio.net_margin,
    "roe": FinancialRatio.roe,
    "roa": FinancialRatio.roa,
    "roic": FinancialRatio.roic,
    "debt_to_equity": FinancialRatio.debt_to_equity,
    "net_debt_to_ebitda": FinancialRatio.net_debt_to_ebitda,
    "current_ratio": FinancialRatio.current_ratio,
    "ev_revenue": FinancialRatio.ev_revenue,
    "ev_ebitda": FinancialRatio.ev_ebitda,
    "pe_ratio": FinancialRatio.pe_ratio,
    "price_to_book": FinancialRatio.price_to_book,
    "fcf_yield": FinancialRatio.fcf_yield,
    "dividend_yield": FinancialRatio.dividend_yield,
    # Financial fields (latest year)
    "revenue": Financial.revenue,
    "ebitda": Financial.ebitda,
    "net_income": Financial.net_income,
    "total_debt": Financial.total_debt,
    "free_cash_flow": Financial.free_cash_flow,
}

# Sortable fields
SORT_MAP = {
    "ticker": Company.ticker,
    "name": Company.name,
    "market_cap": Company.market_cap,
    "enterprise_value": Company.enterprise_value,
    "revenue_growth": FinancialRatio.revenue_growth,
    "ebitda_margin": FinancialRatio.ebitda_margin,
    "ev_ebitda": FinancialRatio.ev_ebitda,
    "pe_ratio": FinancialRatio.pe_ratio,
    "roe": FinancialRatio.roe,
    "revenue": Financial.revenue,
}

OPERATORS = {
    "eq": lambda col, val: col == val,
    "neq": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "in": lambda col, val: col.in_(val if isinstance(val, list) else [val]),
    "like": lambda col, val: col.ilike(f"%{val}%"),
}


def _build_where_clauses(filters: list[ScreenerFilter]) -> list:
    """Convert ScreenerFilter list into SQLAlchemy WHERE clauses."""
    clauses = []
    for f in filters:
        col = FIELD_MAP.get(f.field)
        if col is None:
            continue
        op_fn = OPERATORS.get(f.operator)
        if op_fn is None:
            continue
        clauses.append(op_fn(col, f.value))
    return clauses


def _needs_ratio_join(filters: list[ScreenerFilter], sort_by: str) -> bool:
    ratio_fields = {k for k, v in FIELD_MAP.items() if hasattr(v, "property") and v.class_.__tablename__ == "financial_ratios"}
    # Simpler check: see if any filter or sort touches ratio table
    for f in filters:
        if f.field in ("revenue_growth", "ebitda_growth", "gross_margin", "ebitda_margin",
                        "net_margin", "roe", "roa", "roic", "debt_to_equity",
                        "net_debt_to_ebitda", "current_ratio", "ev_revenue", "ev_ebitda",
                        "pe_ratio", "price_to_book", "fcf_yield", "dividend_yield"):
            return True
    return sort_by in ("revenue_growth", "ebitda_margin", "ev_ebitda", "pe_ratio", "roe")


def _needs_financial_join(filters: list[ScreenerFilter], sort_by: str) -> bool:
    for f in filters:
        if f.field in ("revenue", "ebitda", "net_income", "total_debt", "free_cash_flow"):
            return True
    return sort_by in ("revenue",)


# ─────────────────────────────────────────────
# Main screener query
# ─────────────────────────────────────────────

async def run_screen(req: ScreenerRequest, db: AsyncSession) -> ScreenerResult:
    """Execute a screener query with dynamic filters."""

    # Base query — company + optional joins
    query = select(
        Company.id,
        Company.ticker,
        Company.name,
        Company.sector,
        Company.country,
        Company.market_cap,
        Company.enterprise_value,
        Company.last_price,
    ).where(Company.is_active == True)  # noqa: E712

    count_base = select(func.count(Company.id.distinct())).where(Company.is_active == True)  # noqa: E712

    # Determine if we need joins
    need_ratios = _needs_ratio_join(req.filters, req.sort_by)
    need_financials = _needs_financial_join(req.filters, req.sort_by)

    # Add ratio columns
    ratio_cols = []
    if need_ratios:
        ratio_cols = [
            FinancialRatio.revenue_growth,
            FinancialRatio.ebitda_margin,
            FinancialRatio.net_margin,
            FinancialRatio.ev_ebitda,
            FinancialRatio.ev_revenue,
            FinancialRatio.pe_ratio,
            FinancialRatio.roe,
            FinancialRatio.net_debt_to_ebitda,
        ]

    financial_cols = []
    if need_financials:
        financial_cols = [
            Financial.revenue,
            Financial.ebitda,
            Financial.net_income,
        ]

    # Build full query with joins using subqueries for latest year
    if need_ratios:
        # Subquery: latest ratio per company
        latest_ratio = (
            select(
                FinancialRatio.company_id,
                func.max(FinancialRatio.fiscal_year).label("max_fy"),
            )
            .group_by(FinancialRatio.company_id)
            .subquery()
        )
        query = query.outerjoin(
            FinancialRatio,
            and_(
                FinancialRatio.company_id == Company.id,
                FinancialRatio.fiscal_year == (
                    select(func.max(FinancialRatio.fiscal_year))
                    .where(FinancialRatio.company_id == Company.id)
                    .correlate(Company)
                    .scalar_subquery()
                ),
            ),
        )
        count_base = count_base.outerjoin(
            FinancialRatio,
            and_(
                FinancialRatio.company_id == Company.id,
                FinancialRatio.fiscal_year == (
                    select(func.max(FinancialRatio.fiscal_year))
                    .where(FinancialRatio.company_id == Company.id)
                    .correlate(Company)
                    .scalar_subquery()
                ),
            ),
        )
        query = query.add_columns(*ratio_cols)

    if need_financials:
        query = query.outerjoin(
            Financial,
            and_(
                Financial.company_id == Company.id,
                Financial.period_type == "annual",
                Financial.fiscal_year == (
                    select(func.max(Financial.fiscal_year))
                    .where(Financial.company_id == Company.id, Financial.period_type == "annual")
                    .correlate(Company)
                    .scalar_subquery()
                ),
            ),
        )
        count_base = count_base.outerjoin(
            Financial,
            and_(
                Financial.company_id == Company.id,
                Financial.period_type == "annual",
                Financial.fiscal_year == (
                    select(func.max(Financial.fiscal_year))
                    .where(Financial.company_id == Company.id, Financial.period_type == "annual")
                    .correlate(Company)
                    .scalar_subquery()
                ),
            ),
        )
        query = query.add_columns(*financial_cols)

    # Apply WHERE clauses
    where_clauses = _build_where_clauses(req.filters)
    if where_clauses:
        query = query.where(and_(*where_clauses))
        count_base = count_base.where(and_(*where_clauses))

    # Count total
    count_result = await db.execute(count_base)
    total = count_result.scalar() or 0

    # Sort
    sort_col = SORT_MAP.get(req.sort_by, Company.market_cap)
    if req.sort_dir == "asc":
        query = query.order_by(asc(sort_col).nullslast())
    else:
        query = query.order_by(desc(sort_col).nullslast())

    # Paginate
    query = query.limit(req.limit).offset(req.offset)

    # Execute
    result = await db.execute(query)
    rows = result.all()

    # Map to ScreenerRow
    screener_rows = []
    for row in rows:
        r = row._mapping
        screener_rows.append(ScreenerRow(
            id=r.get("id"),
            ticker=r.get("ticker"),
            name=r.get("name"),
            sector=r.get("sector"),
            country=r.get("country"),
            market_cap=r.get("market_cap"),
            enterprise_value=r.get("enterprise_value"),
            last_price=r.get("last_price"),
            revenue=r.get("revenue"),
            ebitda=r.get("ebitda"),
            net_income=r.get("net_income"),
            revenue_growth=r.get("revenue_growth"),
            ebitda_margin=r.get("ebitda_margin"),
            net_margin=r.get("net_margin"),
            ev_ebitda=r.get("ev_ebitda"),
            ev_revenue=r.get("ev_revenue"),
            pe_ratio=r.get("pe_ratio"),
            roe=r.get("roe"),
            net_debt_to_ebitda=r.get("net_debt_to_ebitda"),
        ))

    # Generate SQL preview for debugging
    where_desc = " AND ".join(f"{f.field} {f.operator} {f.value}" for f in req.filters) if req.filters else "no filters"

    return ScreenerResult(
        total=total,
        offset=req.offset,
        limit=req.limit,
        results=screener_rows,
        sql_preview=f"WHERE {where_desc} ORDER BY {req.sort_by} {req.sort_dir}",
    )


# ─────────────────────────────────────────────
# Saved screens CRUD
# ─────────────────────────────────────────────

async def save_screen(data: SavedScreenCreate, db: AsyncSession) -> SavedScreen:
    """Persist a screener configuration."""
    screen = SavedScreen(
        name=data.name,
        description=data.description,
        filters=[f.model_dump() for f in data.filters],
    )
    db.add(screen)
    await db.flush()
    return screen


async def list_saved_screens(db: AsyncSession) -> list[SavedScreenOut]:
    result = await db.execute(
        select(SavedScreen).order_by(SavedScreen.updated_at.desc())
    )
    return [SavedScreenOut.model_validate(s) for s in result.scalars().all()]


async def delete_saved_screen(screen_id: int, db: AsyncSession) -> bool:
    screen = await db.get(SavedScreen, screen_id)
    if not screen:
        return False
    await db.delete(screen)
    return True
