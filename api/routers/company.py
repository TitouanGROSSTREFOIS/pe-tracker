"""
Company Router — /company endpoints

Endpoints:
  GET  /company/{ticker}            Profile complet
  GET  /company/{ticker}/financials États financiers
  GET  /company/{ticker}/ratios     Ratios calculés
  GET  /companies                   Liste paginée
  GET  /companies/sectors           Secteurs disponibles
  GET  /companies/countries         Pays disponibles
  POST /company/ingest              Ingérer un ticker depuis Yahoo Finance
  POST /company/ingest-batch        Ingérer plusieurs tickers
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services import company_service
from api.services.data_ingestion import ingest_company, ingest_batch
from api.schemas.company import (
    CompanyProfile,
    CompanySummary,
    FinancialOut,
    FinancialRatioOut,
)

router = APIRouter(tags=["Company Intelligence"])


# ── Company Profile ──────────────────────────
@router.get("/company/{ticker}", response_model=CompanyProfile)
async def get_company(ticker: str, db: AsyncSession = Depends(get_db)):
    """
    Profil complet d'une entreprise : info, financials, ratios.
    Si le ticker n'est pas en base, tente une ingestion depuis Yahoo Finance.
    """
    profile = await company_service.get_company_profile(ticker, db)
    if profile:
        return profile

    # Auto-ingest if not found
    try:
        await ingest_company(ticker, db)
        profile = await company_service.get_company_profile(ticker, db)
        if profile:
            return profile
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found: {str(e)}")

    raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")


# ── Financial Statements ─────────────────────
@router.get("/company/{ticker}/financials", response_model=list[FinancialOut])
async def get_financials(
    ticker: str,
    period: str = Query("annual", regex="^(annual|quarterly)$"),
    limit: int = Query(5, le=20),
    db: AsyncSession = Depends(get_db),
):
    """États financiers historiques (income statement, BS, CF)."""
    data = await company_service.get_financials(ticker, db, period_type=period, limit=limit)
    if not data:
        raise HTTPException(status_code=404, detail=f"No financial data for '{ticker}'")
    return data


# ── Financial Ratios ─────────────────────────
@router.get("/company/{ticker}/ratios", response_model=list[FinancialRatioOut])
async def get_ratios(
    ticker: str,
    limit: int = Query(5, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Ratios financiers calculés (growth, margins, leverage, multiples)."""
    data = await company_service.get_ratios(ticker, db, limit=limit)
    if not data:
        raise HTTPException(status_code=404, detail=f"No ratio data for '{ticker}'")
    return data


# ── List Companies ───────────────────────────
@router.get("/companies", response_model=dict)
async def list_companies(
    sector: str | None = None,
    country: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Liste paginée des entreprises en base."""
    items, total = await company_service.list_companies(db, sector, country, limit, offset)
    return {"total": total, "offset": offset, "limit": limit, "companies": items}


# ── Metadata ─────────────────────────────────
@router.get("/companies/sectors", response_model=list[str])
async def get_sectors(db: AsyncSession = Depends(get_db)):
    """Secteurs disponibles."""
    return await company_service.get_distinct_sectors(db)


@router.get("/companies/countries", response_model=list[str])
async def get_countries(db: AsyncSession = Depends(get_db)):
    """Pays disponibles."""
    return await company_service.get_distinct_countries(db)


# ── Data Ingestion ───────────────────────────
@router.post("/company/ingest")
async def ingest_single(
    ticker: str = Query(..., description="Ticker symbol (e.g., AAPL, MSFT)"),
    db: AsyncSession = Depends(get_db),
):
    """Ingérer les données d'une entreprise depuis Yahoo Finance."""
    try:
        company = await ingest_company(ticker, db)
        return {
            "status": "ok",
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector,
            "market_cap": company.market_cap,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/company/ingest-batch")
async def ingest_multiple(
    tickers: list[str],
    db: AsyncSession = Depends(get_db),
):
    """Ingérer plusieurs entreprises en batch."""
    results = await ingest_batch(tickers, db)
    return {"status": "completed", "results": results}
