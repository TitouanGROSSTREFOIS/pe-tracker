"""
SourcedTarget model — M&A Deal Sourcing & LBO Engine

Stores companies identified through web scraping / OSINT analysis
as potential acquisition targets for buy-and-build strategies.
Each record holds: company info, estimated financials, OSINT signals,
LBO quick-screening metrics, and full 5-year projection data.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.database import Base


class SourcedTarget(Base):
    __tablename__ = "sourced_targets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Link to official company (optional) ──
    company_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    # ── Identification ───────────────────────
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    siren: Mapped[str | None] = mapped_column(String(9), unique=True, nullable=True)
    # D47 (Tâche Finalisation, Partie C) : "registry" (sirene_sourcing_pipeline.py),
    # "google_radar" (sourcing_pipeline.py — manquait jusqu'ici), "document_upload"
    # (upload_teaser dans routers/sourcing.py — idem). "manual" reste réservé,
    # aucune voie ne le pose actuellement. NULL = indéterminé (créé avant D47,
    # jamais deviné rétroactivement si aucun signal fiable ne permet de trancher).
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "target" | "platform" (D11)
    business_summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list | dict | None] = mapped_column(JSON)  # ["SaaS", "B2B", "recurring revenue"]
    score: Mapped[float | None] = mapped_column(Float)          # attractiveness score (0-100)

    # ── Financials Estimés ───────────────────
    revenue_estimate: Mapped[float | None] = mapped_column(Float)   # $ estimated revenue
    ebitda_estimate: Mapped[float | None] = mapped_column(Float)    # $ estimated EBITDA
    enterprise_value: Mapped[float | None] = mapped_column(Float)   # $ estimated EV

    # ── OSINT Signals ────────────────────────
    growth_signals: Mapped[list | dict | None] = mapped_column(JSON)   # ["hiring +30%", "new product launch", ...]
    red_flags: Mapped[list | dict | None] = mapped_column(JSON)        # ["lawsuit pending", "key man risk", ...]
    competitors: Mapped[list | dict | None] = mapped_column(JSON)      # ["CompetitorA", "CompetitorB", ...]

    # ── LBO Quick-Screen Metrics ─────────────
    lbo_irr: Mapped[float | None] = mapped_column(Float)          # % projected IRR
    lbo_moic: Mapped[float | None] = mapped_column(Float)         # x projected MOIC
    entry_multiple: Mapped[float | None] = mapped_column(Float)   # x EV/EBITDA entry
    lbo_projections: Mapped[dict | None] = mapped_column(JSON)    # full 5-year cash flow sweep

    # ── Pipeline Status ──────────────────────
    status: Mapped[str] = mapped_column(
        String(30), default="Watchlist", nullable=False
    )  # Watchlist | Deep Dive | Passed | Active | Contacted

    pipeline_stage: Mapped[str] = mapped_column(
        String(40), default="Screening", nullable=False
    )  # Screening | NDA Signed | Management Meeting | Due Diligence | IC Memo | Closed | Passed

    # ── Timestamps ───────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # ── Relationship ────────────────────────
    company: Mapped["Company"] = relationship("Company", lazy="selectin")  # noqa: F821
    portfolio_company: Mapped["PortfolioCompany | None"] = relationship(  # noqa: F821
        "PortfolioCompany",
        back_populates="sourced_target",
        lazy="selectin",
        uselist=False,
    )

    # NOTE : SIREN unicité — `unique=True` sur la colonne suffit sous SQLite,
    # qui traite chaque NULL comme distinct des autres (contrairement à
    # Postgres où un index UNIQUE partiel serait nécessaire pour le même effet).
    __table_args__ = (
        Index("ix_sourced_targets_score", "score"),
        Index("ix_sourced_targets_status", "status"),
        Index("ix_sourced_targets_pipeline_stage", "pipeline_stage"),
    )

    def __repr__(self) -> str:
        return f"<SourcedTarget '{self.company_name}' score={self.score} status={self.status} stage={self.pipeline_stage}>"
