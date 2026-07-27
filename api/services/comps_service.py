"""
Comps Service — Trading Comps analysis (comparable company tables).

D49 (Tâche Finalisation) : la couche "Comparable Intelligence" par cible
sourcée (public peers via LLM en texte libre, private peers via Pappers —
abandonné, retombant systématiquement sur des sociétés PLACEHOLDER
fabriquées) a été retirée. La vue détail d'une cible valorise désormais via
le CompSet TIC réel + le calibrage sectoriel existants (GET /lbo/calibration
et GET /comps/{comp_set_id}, appelés directement par le frontend — voir
DealSourcing.tsx) : un seul système de valorisation dans tout l'outil,
au lieu de deux (un réel, un fabriqué).
"""
from __future__ import annotations
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.company import Company
from api.models.financial import Financial, FinancialRatio
from api.models.comps import CompSet, CompSetMember
from api.schemas.comps import (
    CompSetCreate,
    CompSetOut,
    CompsTableRow,
    CompsStats,
    CompsTableResponse,
)
from api.schemas.provenance import (
    FieldProvenance,
    field_provenance_from_json,
    weakest_provenance,
)
from api.services.data_ingestion import ingest_company


# ── Create a comp set ────────────────────────
async def create_comp_set(body: CompSetCreate, db: AsyncSession) -> tuple[CompSet, int]:
    """Create a new comparable company set.  Auto-ingest missing tickers."""
    comp_set = CompSet(name=body.name, description=body.description, base_year=body.base_year)
    db.add(comp_set)
    await db.flush()

    member_count = 0
    for ticker in body.tickers:
        tkr = ticker.upper().strip()
        # Check if company exists, ingest if not
        result = await db.execute(select(Company).where(Company.ticker == tkr))
        company = result.scalar_one_or_none()
        if not company:
            try:
                company = await ingest_company(tkr, db)
            except Exception:
                continue  # skip tickers we can't find

        member = CompSetMember(comp_set_id=comp_set.id, company_id=company.id)
        db.add(member)
        member_count += 1

    await db.commit()
    await db.refresh(comp_set)
    return comp_set, member_count


# ── List comp sets ───────────────────────────
async def list_comp_sets(db: AsyncSession) -> list[CompSet]:
    result = await db.execute(
        select(CompSet)
        .options(selectinload(CompSet.members))
        .order_by(CompSet.created_at.desc())
    )
    return list(result.scalars().all())


# ── Provenance par ligne (D18/D19, branché Tâche B.11) ───────
def _build_comp_row_provenance(company: Company, fin: Financial | None) -> dict[str, Any]:
    """Fusionne la provenance de `Company` (market_cap, enterprise_value) et
    de `Financial` (revenue, ebitda, net_income) en un seul dict par ligne,
    même format structuré que `Deal.financial_provenance`. Les multiples
    dérivés (ev_revenue, ev_ebitda) héritent de la provenance la plus faible
    de leurs deux composantes — même règle que `compute_deal_multiples`
    (deals_service.py), pas une nouvelle convention."""
    company_prov = company.financial_provenance if isinstance(company.financial_provenance, dict) else {}
    fin_prov = (fin.financial_provenance if fin and isinstance(fin.financial_provenance, dict) else {})

    merged: dict[str, Any] = {}
    for field in ("market_cap", "enterprise_value"):
        p = field_provenance_from_json(company_prov, field)
        if p:
            merged[field] = p.model_dump(mode="json")
    for field in ("revenue", "ebitda", "net_income"):
        p = field_provenance_from_json(fin_prov, field)
        if p:
            merged[field] = p.model_dump(mode="json")

    ev_prov = field_provenance_from_json(company_prov, "enterprise_value")
    revenue_prov = field_provenance_from_json(fin_prov, "revenue")
    ebitda_prov = field_provenance_from_json(fin_prov, "ebitda")

    if ev_prov and revenue_prov:
        merged["ev_revenue"] = FieldProvenance(
            provenance=weakest_provenance(ev_prov.provenance, revenue_prov.provenance),
            reference="Calculated: enterprise_value / revenue (inherits the weakest provenance of its components)",
        ).model_dump(mode="json")
    if ev_prov and ebitda_prov:
        merged["ev_ebitda"] = FieldProvenance(
            provenance=weakest_provenance(ev_prov.provenance, ebitda_prov.provenance),
            reference="Calculated: enterprise_value / ebitda (inherits the weakest provenance of its components)",
        ).model_dump(mode="json")

    net_income_prov = field_provenance_from_json(fin_prov, "net_income")
    if ebitda_prov and revenue_prov:
        merged["ebitda_margin"] = FieldProvenance(
            provenance=weakest_provenance(ebitda_prov.provenance, revenue_prov.provenance),
            reference="Calculated: ebitda / revenue (inherits the weakest provenance of its components)",
        ).model_dump(mode="json")
    if net_income_prov and revenue_prov:
        merged["net_margin"] = FieldProvenance(
            provenance=weakest_provenance(net_income_prov.provenance, revenue_prov.provenance),
            reference="Calculated: net_income / revenue (inherits the weakest provenance of its components)",
        ).model_dump(mode="json")

    return merged


# ── Get comp table (the main analysis) ───────
async def get_comp_table(comp_set_id: int, db: AsyncSession) -> CompsTableResponse | None:
    # Fetch comp set with members
    result = await db.execute(
        select(CompSet)
        .options(selectinload(CompSet.members).selectinload(CompSetMember.company))
        .where(CompSet.id == comp_set_id)
    )
    comp_set = result.scalar_one_or_none()
    if not comp_set:
        return None

    rows: list[CompsTableRow] = []

    for member in comp_set.members:
        company = member.company
        if not company:
            continue

        # Latest financial ratios
        ratio_q = await db.execute(
            select(FinancialRatio)
            .where(FinancialRatio.company_id == company.id)
            .order_by(FinancialRatio.fiscal_year.desc())
            .limit(1)
        )
        ratio = ratio_q.scalar_one_or_none()

        # Latest annual financials
        fin_q = await db.execute(
            select(Financial)
            .where(Financial.company_id == company.id, Financial.period_type == "annual")
            .order_by(Financial.period_end.desc())
            .limit(1)
        )
        fin = fin_q.scalar_one_or_none()

        row = CompsTableRow(
            ticker=company.ticker,
            name=company.name or company.ticker,
            sector=company.sector,
            country=company.country,
            market_cap=company.market_cap,
            enterprise_value=company.enterprise_value,
            revenue=fin.revenue if fin else None,
            ebitda=fin.ebitda if fin else None,
            net_income=fin.net_income if fin else None,
            ev_revenue=ratio.ev_revenue if ratio else None,
            ev_ebitda=ratio.ev_ebitda if ratio else None,
            pe_ratio=ratio.pe_ratio if ratio else None,
            price_to_book=ratio.price_to_book if ratio else None,
            gross_margin=ratio.gross_margin if ratio else None,
            ebitda_margin=ratio.ebitda_margin if ratio else None,
            net_margin=ratio.net_margin if ratio else None,
            roe=ratio.roe if ratio else None,
            revenue_growth=ratio.revenue_growth if ratio else None,
            debt_to_equity=ratio.debt_to_equity if ratio else None,
            current_ratio=ratio.current_ratio if ratio else None,
            fiscal_year=fin.fiscal_year if fin else None,
            financial_provenance=_build_comp_row_provenance(company, fin),
        )
        rows.append(row)

    # Compute stats
    stats = _compute_stats(rows)

    return CompsTableResponse(
        comp_set_id=comp_set.id,
        comp_set_name=comp_set.name,
        base_year=comp_set.base_year,
        rows=rows,
        stats=stats,
    )


# ── Delete comp set ──────────────────────────
async def delete_comp_set(comp_set_id: int, db: AsyncSession) -> bool:
    result = await db.execute(select(CompSet).where(CompSet.id == comp_set_id))
    cs = result.scalar_one_or_none()
    if not cs:
        return False
    await db.delete(cs)
    await db.commit()
    return True


# ── Stats computation ────────────────────────
def _compute_stats(rows: list[CompsTableRow]) -> CompsStats:
    """Compute mean, median, 25th/75th percentile for numeric fields."""
    metric_fields = [
        "ev_revenue", "ev_ebitda", "pe_ratio", "price_to_book",
        "gross_margin", "ebitda_margin", "net_margin", "roe",
        "revenue_growth", "debt_to_equity", "current_ratio",
    ]

    mean_d: dict = {}
    median_d: dict = {}
    p25_d: dict = {}
    p75_d: dict = {}

    for field in metric_fields:
        values = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        if not values:
            mean_d[field] = None
            median_d[field] = None
            p25_d[field] = None
            p75_d[field] = None
        else:
            arr = np.array(values, dtype=float)
            mean_d[field] = round(float(np.mean(arr)), 4)
            median_d[field] = round(float(np.median(arr)), 4)
            p25_d[field] = round(float(np.percentile(arr, 25)), 4)
            p75_d[field] = round(float(np.percentile(arr, 75)), 4)

    return CompsStats(mean=mean_d, median=median_d, p25=p25_d, p75=p75_d)
