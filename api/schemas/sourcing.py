"""
Sourcing Pydantic schemas — M&A Deal Sourcing & LBO Engine
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl

PipelineStage = Literal[
    "Screening",
    "NDA Signed",
    "Management Meeting",
    "Due Diligence",
    "IC Memo",
    "Closed",
    "Passed",
    "Archived",
]

# D11 — typologie par taille (Tâche B.3)
TargetType = Literal["target", "platform"]


# ── Base (shared fields) ─────────────────────

class SourcedTargetBase(BaseModel):
    company_name: str
    url: str
    company_id: int | None = None
    siren: str | None = None
    source: str | None = None
    target_type: TargetType | None = None
    business_summary: str | None = None
    keywords: list[str] | None = None                   # ["SaaS", "B2B", "recurring revenue"]
    score: float | None = Field(None, ge=0, le=100)     # attractiveness 0-100

    # Financials estimés
    revenue_estimate: float | None = None
    ebitda_estimate: float | None = None
    enterprise_value: float | None = None

    # OSINT signals
    growth_signals: list[str] | None = None             # ["hiring +30%", "new product launch"]
    red_flags: list[str] | None = None                  # ["lawsuit pending", "key man risk"]
    competitors: list[str] | None = None                # ["CompetitorA", "CompetitorB"]

    # LBO quick-screen
    lbo_irr: float | None = None                        # % projected IRR
    lbo_moic: float | None = None                       # x projected MOIC
    entry_multiple: float | None = None                 # x EV/EBITDA entry
    lbo_projections: dict[str, Any] | None = None       # full 5-year cash-flow sweep

    # Pipeline
    status: str = "Watchlist"
    pipeline_stage: PipelineStage = "Screening"


# ── Create (POST body after scraping) ────────

class SourcedTargetCreate(SourcedTargetBase):
    """Used when inserting a new sourced target from the scraping pipeline."""
    pass


# ── Update (PATCH — all optional) ────────────

class SourcedTargetUpdate(BaseModel):
    """Partial update: change status, tweak LBO assumptions, link to company, etc."""
    company_name: str | None = None
    url: str | None = None
    company_id: int | None = None
    siren: str | None = None
    source: str | None = None
    target_type: TargetType | None = None
    business_summary: str | None = None
    keywords: list[str] | None = None
    score: float | None = Field(None, ge=0, le=100)

    revenue_estimate: float | None = None
    ebitda_estimate: float | None = None
    enterprise_value: float | None = None

    growth_signals: list[str] | None = None
    red_flags: list[str] | None = None
    competitors: list[str] | None = None

    lbo_irr: float | None = None
    lbo_moic: float | None = None
    entry_multiple: float | None = None
    lbo_projections: dict[str, Any] | None = None

    status: str | None = None
    pipeline_stage: PipelineStage | None = None


class SourcedTargetStageUpdate(BaseModel):
    """Payload for PATCH /sourcing/{id}/stage."""
    stage: PipelineStage


# ── Out (GET response) ───────────────────────

class SourcedTargetOut(SourcedTargetBase):
    """Full representation returned by the API."""
    id: int
    created_at: datetime
    updated_at: datetime
    # Rempli en mémoire par sourcing_service (jointure, pas une colonne) —
    # None si la cible n'a jamais été promue en Deal (Tâche B.5, D14).
    promoted_deal_id: int | None = None

    model_config = {"from_attributes": True}


class TargetPromoteResponse(BaseModel):
    """Réponse de POST /sourcing/{target_id}/promote."""
    deal_id: int
    sourced_target_id: int
    message: str


# ── List response (paginated) ────────────────

class SourcedTargetListResponse(BaseModel):
    total: int
    offset: int = 0
    limit: int = 50
    targets: list[SourcedTargetOut]


# ── Scan request / response ──────────────────

class SourcingScanRequest(BaseModel):
    """Body for POST /sourcing/scan — triggers full OSINT pipeline."""
    platform_url: HttpUrl


class SourcingScanResponse(BaseModel):
    """202 Accepted — scan is running in background."""
    message: str
    platform_url: str


# D40 (Tâche Finalisation, Partie A) : le scan tourne en tâche de fond
# (202 Accepted immédiat) — sans ceci, un scan qui ne trouve/ne garde
# aucune cible (hors périmètre TIC/France, contenu insuffisant, etc.)
# échouait silencieusement du point de vue utilisateur : aucun moyen de
# savoir que le scan est fini, ni pourquoi 0 résultat. État en mémoire
# (process unique, un seul scan actif à la fois — suffisant pour un usage
# mono-analyste local, pas une file d'attente multi-utilisateurs).
class ScanSavedTarget(BaseModel):
    """Résumé minimal d'une cible sauvegardée par CE scan — D46 (Tâche
    Finalisation, Partie B) : le pipeline calculait déjà cette liste
    (`saved_results` dans sourcing_pipeline.py) mais elle était jetée avant
    d'atteindre ScanStatus, laissant l'utilisateur deviner lesquelles des
    cibles de la base venaient de son scan."""
    id: int
    company_name: str
    url: str
    score: float | None = None


class ScanStatus(BaseModel):
    platform_url: str
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    # D46 (Tâche Finalisation, Partie B) : nom de la société identifiée comme
    # point de départ (extrait par le LLM depuis platform_url) — jamais
    # ajoutée elle-même comme cible, voir sourcing_pipeline.py.
    seed_company_name: str | None = None
    targets_found: int | None = None
    targets_scored: int | None = None
    targets_saved: int | None = None
    targets_skipped: int | None = None
    saved_targets: list[ScanSavedTarget] | None = None
    error: str | None = None


# ── Batch scan request / response ─────────────

class BatchScanResponse(BaseModel):
    """202 Accepted — batch is running in background."""
    message: str
    total_urls: int
    urls: list[str]
