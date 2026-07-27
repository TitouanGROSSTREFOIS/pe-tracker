"""
Analytics Router — /analytics endpoints

Endpoints:
  POST /analytics/dcf               DCF Valuation
  POST /analytics/dcf/sensitivity   Sensitivity table (WACC x terminal growth)
  POST /analytics/peers             Peer comparison (radar chart data)
  GET  /analytics/{ticker}/chart    Historical financials chart data
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.analytics_service import (
    run_dcf,
    dcf_sensitivity,
    peer_comparison,
    financials_chart,
)

router = APIRouter(prefix="/analytics", tags=["Analytics & Valuation"])


# ── Request models ───────────────────────────
class DCFRequest(BaseModel):
    ticker: str
    wacc: float = 0.10
    terminal_growth: float = 0.025
    projection_years: int = 5
    revenue_growth: float | None = None
    ebitda_margin: float | None = None
    capex_pct: float | None = None
    tax_rate: float = 0.25
    da_pct: float | None = None
    nwc_pct: float | None = None


class SensitivityRequest(BaseModel):
    ticker: str
    wacc_range: list[float] = Field(default=[0.08, 0.09, 0.10, 0.11, 0.12])
    growth_range: list[float] = Field(default=[0.015, 0.02, 0.025, 0.03, 0.035])
    ebitda_margin: float | None = None
    revenue_growth: float | None = None


class PeerRequest(BaseModel):
    tickers: list[str]


# ── DCF Valuation ────────────────────────────
@router.post("/dcf")
async def dcf(body: DCFRequest, db: AsyncSession = Depends(get_db)):
    """
    DCF valuation simplifié.

    Utilise les derniers états financiers comme base,
    projette les FCF sur N années, actualise au WACC,
    calcule la terminal value (Gordon Growth).

    Retourne : valeur intrinsèque par action + upside/downside.
    """
    try:
        result = await run_dcf(
            body.ticker,
            db,
            wacc=body.wacc,
            terminal_growth=body.terminal_growth,
            projection_years=body.projection_years,
            revenue_growth=body.revenue_growth,
            ebitda_margin=body.ebitda_margin,
            capex_pct=body.capex_pct,
            tax_rate=body.tax_rate,
            da_pct=body.da_pct,
            nwc_pct=body.nwc_pct,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Sensitivity Table ────────────────────────
@router.post("/dcf/sensitivity")
async def sensitivity(body: SensitivityRequest, db: AsyncSession = Depends(get_db)):
    """
    Table de sensibilité : valeur intrinsèque pour chaque combinaison WACC × terminal growth.
    """
    try:
        result = await dcf_sensitivity(
            body.ticker,
            db,
            wacc_range=body.wacc_range,
            growth_range=body.growth_range,
            ebitda_margin=body.ebitda_margin,
            revenue_growth=body.revenue_growth,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Peer Comparison ──────────────────────────
@router.post("/peers")
async def peers(body: PeerRequest, db: AsyncSession = Depends(get_db)):
    """
    Comparaison entre pairs : métriques normalisées pour spider/radar chart.
    """
    data = await peer_comparison(body.tickers, db)
    return {"peers": data}


# ── Historical Chart Data ────────────────────
@router.get("/{ticker}/chart")
async def chart(
    ticker: str,
    metrics: str = Query("revenue,ebitda,net_income,free_cash_flow"),
    limit: int = Query(5, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Données de chart historiques (revenue, EBITDA, NI, FCF, etc.).
    `metrics` = liste CSV des champs Financial.
    """
    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]
    try:
        return await financials_chart(ticker, db, metrics=metric_list, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
