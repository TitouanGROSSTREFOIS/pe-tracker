"""
Analytics Service — Valuation (DCF), peer comparison, charts data.
"""
from __future__ import annotations
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.company import Company
from api.models.financial import Financial, FinancialRatio


# ── DCF Valuation ────────────────────────────
async def run_dcf(
    ticker: str,
    db: AsyncSession,
    *,
    wacc: float = 0.10,
    terminal_growth: float = 0.025,
    projection_years: int = 5,
    revenue_growth: float | None = None,
    ebitda_margin: float | None = None,
    capex_pct: float | None = None,
    tax_rate: float = 0.25,
    da_pct: float | None = None,
    nwc_pct: float | None = None,
) -> dict:
    """
    Simplified DCF valuation.
    Uses latest financials as base, projects FCF, discounts to present value.
    Returns intrinsic value per share + waterfall breakdown.
    """
    # Fetch company
    result = await db.execute(select(Company).where(Company.ticker == ticker.upper()))
    company = result.scalar_one_or_none()
    if not company:
        raise ValueError(f"Company '{ticker}' not found in database")

    # Latest financials
    fin_q = await db.execute(
        select(Financial)
        .where(Financial.company_id == company.id, Financial.period_type == "annual")
        .order_by(Financial.period_end.desc())
        .limit(2)
    )
    financials = list(fin_q.scalars().all())
    if not financials:
        raise ValueError(f"No financial data for '{ticker}'")

    latest = financials[0]

    # Base values
    base_revenue = latest.revenue or 0
    base_ebitda = latest.ebitda or 0
    base_capex = abs(latest.capex or 0)
    base_da = abs(latest.depreciation_amortization or 0)

    # Tâche B.7, Étape 1.2 : sans CA de base, toute la projection (revenue *=
    # (1+growth) démarrant à 0) est mathématiquement dégénérée — un DCF à
    # zéro silencieux, pas une estimation. L'ancien repli `ebitda_margin =
    # 0.15` masquait ce cas au lieu de le signaler ; on échoue proprement à
    # la place (D18 : pas de substitution silencieuse par approximation).
    if base_revenue <= 0:
        raise ValueError(
            f"Cannot run DCF for '{ticker}': latest financial statement has no revenue "
            f"(fiscal_year={latest.fiscal_year}). A DCF projection cannot be built from a zero base."
        )

    # Defaults from actuals if not overridden
    if revenue_growth is None:
        if len(financials) > 1 and financials[1].revenue and financials[1].revenue > 0:
            revenue_growth = (base_revenue - financials[1].revenue) / financials[1].revenue
        else:
            revenue_growth = 0.05  # default 5%

    if ebitda_margin is None:
        ebitda_margin = base_ebitda / base_revenue

    if capex_pct is None:
        capex_pct = (base_capex / base_revenue) if base_revenue else 0.05

    if da_pct is None:
        da_pct = (base_da / base_revenue) if base_revenue else 0.03

    if nwc_pct is None:
        nwc_pct = 0.02  # simple default

    # Project FCF
    projected_years = []
    revenue = base_revenue
    for year in range(1, projection_years + 1):
        revenue *= (1 + revenue_growth)
        ebitda = revenue * ebitda_margin
        da = revenue * da_pct
        ebit = ebitda - da
        nopat = ebit * (1 - tax_rate)
        capex = revenue * capex_pct
        delta_nwc = revenue * nwc_pct
        fcf = nopat + da - capex - delta_nwc

        discount_factor = 1 / (1 + wacc) ** year
        pv_fcf = fcf * discount_factor

        projected_years.append({
            "year": year,
            "revenue": round(revenue, 0),
            "ebitda": round(ebitda, 0),
            "ebit": round(ebit, 0),
            "nopat": round(nopat, 0),
            "fcf": round(fcf, 0),
            "discount_factor": round(discount_factor, 4),
            "pv_fcf": round(pv_fcf, 0),
        })

    # Terminal value (Gordon Growth)
    terminal_fcf = projected_years[-1]["fcf"] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1 + wacc) ** projection_years

    # Enterprise value
    sum_pv_fcf = sum(y["pv_fcf"] for y in projected_years)
    enterprise_value = sum_pv_fcf + pv_terminal

    # Equity value
    net_debt = (company.enterprise_value or 0) - (company.market_cap or 0)
    equity_value = enterprise_value - net_debt
    shares = company.shares_outstanding or 1
    intrinsic_per_share = equity_value / shares

    # Upside / downside
    current_price = company.last_price or 0
    upside = ((intrinsic_per_share - current_price) / current_price * 100) if current_price else 0

    return {
        "ticker": company.ticker,
        "company_name": company.name,
        "assumptions": {
            "wacc": wacc,
            "terminal_growth": terminal_growth,
            "projection_years": projection_years,
            "revenue_growth": round(revenue_growth, 4),
            "ebitda_margin": round(ebitda_margin, 4),
            "capex_pct": round(capex_pct, 4),
            "tax_rate": tax_rate,
            "da_pct": round(da_pct, 4),
            "nwc_pct": nwc_pct,
        },
        "projections": projected_years,
        "terminal_value": round(terminal_value, 0),
        "pv_terminal": round(pv_terminal, 0),
        "sum_pv_fcf": round(sum_pv_fcf, 0),
        "enterprise_value": round(enterprise_value, 0),
        "net_debt": round(net_debt, 0),
        "equity_value": round(equity_value, 0),
        "shares_outstanding": shares,
        "intrinsic_per_share": round(intrinsic_per_share, 2),
        "current_price": current_price,
        "upside_pct": round(upside, 2),
    }


# ── Sensitivity Table ────────────────────────
async def dcf_sensitivity(
    ticker: str,
    db: AsyncSession,
    wacc_range: list[float] | None = None,
    growth_range: list[float] | None = None,
    **dcf_kwargs,
) -> dict:
    """
    Sensitivity table: intrinsic value per share for combinations of WACC and terminal growth.
    """
    if wacc_range is None:
        wacc_range = [0.08, 0.09, 0.10, 0.11, 0.12]
    if growth_range is None:
        growth_range = [0.015, 0.02, 0.025, 0.03, 0.035]

    table = []
    for w in wacc_range:
        row_values = []
        for g in growth_range:
            try:
                res = await run_dcf(ticker, db, wacc=w, terminal_growth=g, **dcf_kwargs)
                row_values.append(res["intrinsic_per_share"])
            except Exception:
                row_values.append(None)
        table.append({"wacc": w, "values": row_values})

    return {
        "ticker": ticker,
        "wacc_range": wacc_range,
        "growth_range": growth_range,
        "table": table,
    }


# ── Peer Comparison (radar / spider data) ────
async def peer_comparison(
    tickers: list[str],
    db: AsyncSession,
) -> list[dict]:
    """
    Returns normalized metrics for multiple tickers — useful for radar charts.
    Metrics: revenue_growth, ebitda_margin, roe, debt_to_equity, pe_ratio, ev_ebitda.
    """
    metrics_keys = [
        "revenue_growth", "ebitda_margin", "roe",
        "debt_to_equity", "pe_ratio", "ev_ebitda",
    ]

    peers = []
    for ticker in tickers:
        tkr = ticker.upper().strip()
        result = await db.execute(select(Company).where(Company.ticker == tkr))
        company = result.scalar_one_or_none()
        if not company:
            continue

        ratio_q = await db.execute(
            select(FinancialRatio)
            .where(FinancialRatio.company_id == company.id)
            .order_by(FinancialRatio.fiscal_year.desc())
            .limit(1)
        )
        ratio = ratio_q.scalar_one_or_none()

        entry = {"ticker": tkr, "name": company.name}
        for key in metrics_keys:
            entry[key] = getattr(ratio, key, None) if ratio else None
        peers.append(entry)

    return peers


# ── Historical Financials Chart Data ─────────
async def financials_chart(
    ticker: str,
    db: AsyncSession,
    metrics: list[str] | None = None,
    limit: int = 5,
) -> dict:
    """
    Returns time-series data for charting financials.
    """
    if metrics is None:
        metrics = ["revenue", "ebitda", "net_income", "free_cash_flow"]

    result = await db.execute(select(Company).where(Company.ticker == ticker.upper()))
    company = result.scalar_one_or_none()
    if not company:
        raise ValueError(f"Company '{ticker}' not found")

    fin_q = await db.execute(
        select(Financial)
        .where(Financial.company_id == company.id, Financial.period_type == "annual")
        .order_by(Financial.period_end.asc())
        .limit(limit)
    )
    financials = list(fin_q.scalars().all())

    series = {m: [] for m in metrics}
    labels = []

    for fin in financials:
        labels.append(str(fin.period_end.year) if fin.period_end else "N/A")
        for m in metrics:
            series[m].append(getattr(fin, m, None))

    return {
        "ticker": ticker.upper(),
        "name": company.name,
        "labels": labels,
        "series": series,
    }
