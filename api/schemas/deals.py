"""
Deal Pydantic schemas
"""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Any

from api.schemas.provenance import FieldProvenance


class DealCreate(BaseModel):
    # `extra="forbid"` (Tâche B.5) : un champ inconnu dans le payload lève
    # désormais une 422 explicite au lieu d'être absorbé sans bruit — c'est
    # ce comportement par défaut de Pydantic (extra="ignore") qui faisait
    # disparaître silencieusement l'EBITDA saisi en human-in-the-loop
    # (le frontend envoyait `estimated_ebitda`, un nom absent de ce schéma,
    # voir RAPPORT B.4). Portée volontairement limitée à CE schéma : c'est
    # le point d'entrée directement impliqué dans l'incident. Les autres
    # schémas d'entrée de l'app n'ont pas été audités un par un pour ce
    # changement — le généraliser sans les revérifier pourrait casser des
    # flux qui dépendent aujourd'hui du comportement permissif.
    model_config = {"extra": "forbid"}

    acquirer_name: str
    target_name: str | None = None
    acquirer_id: int | None = None
    target_id: int | None = None
    sourced_target_id: int | None = None
    announcement_date: date | None = None
    close_date: date | None = None
    deal_type: str | None = None
    status: str = "Completed"
    deal_value: float | None = None
    equity_value: float | None = None
    enterprise_value_deal: float | None = None
    target_revenue: float | None = None
    target_ebitda: float | None = None
    enterprise_value: float | None = None
    ev_revenue_multiple: float | None = None
    ev_ebitda_multiple: float | None = None
    pe_multiple: float | None = None
    premium_paid: float | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    description: str | None = None
    source: str | None = None
    source_url: str | None = None
    ic_memo: str | None = None
    # D18 (Tâche B.6) — provenance par champ financier. Voir api/schemas/provenance.py.
    financial_provenance: dict[str, FieldProvenance] | None = None


class DealOut(BaseModel):
    id: int
    acquirer_name: str
    target_name: str | None = None
    sourced_target_id: int | None = None
    target_type: str | None = None  # 'target' / 'platform' (D11), lu depuis la cible sourcing liée
    announcement_date: date | None = None
    close_date: date | None = None
    deal_type: str | None = None
    status: str
    deal_value: float | None = None
    target_revenue: float | None = None
    target_ebitda: float | None = None
    enterprise_value: float | None = None
    ev_revenue_multiple: float | None = None
    ev_ebitda_multiple: float | None = None
    premium_paid: float | None = None
    sector: str | None = None
    country: str | None = None
    description: str | None = None
    ic_memo: str | None = None
    updated_at: datetime | None = None
    financial_provenance: dict[str, FieldProvenance] | None = None

    model_config = {"from_attributes": True}


class DealMemoResponse(BaseModel):
    deal_id: int
    ic_memo: str
    model_config = {"from_attributes": True}


class DealFilter(BaseModel):
    sector: str | None = None
    deal_type: str | None = None
    status: str | None = None
    country: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort_by: str = "announcement_date"
    sort_desc: bool = True
    limit: int = Field(default=50, le=500)
    offset: int = 0


class DealListResponse(BaseModel):
    total: int
    offset: int = 0
    limit: int = 50
    deals: list[DealOut]
