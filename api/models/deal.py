"""
M&A Deal model
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Any
from sqlalchemy import String, Float, Integer, Date, DateTime, ForeignKey, Text, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.database import Base


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # --- Parties ---
    acquirer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    acquirer_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    target_name: Mapped[str | None] = mapped_column(String(255))
    target_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))

    # --- Sourcing lineage (D14, Tâche B.5) ---
    # Une cible qualifiée est PROMUE en deal — les deux entités restent
    # distinctes, reliées par cette FK. `unique=True` empêche une double
    # promotion accidentelle de la même cible (contrainte DB, pas seulement
    # une vérification applicative). Nullable : un deal peut naître d'un
    # upload de teaser sans cible SourcedTarget préexistante.
    sourced_target_id: Mapped[int | None] = mapped_column(
        ForeignKey("sourced_targets.id", ondelete="SET NULL"), unique=True, nullable=True, index=True
    )

    # --- Deal Info ---
    announcement_date: Mapped[date | None] = mapped_column(Date)
    close_date: Mapped[date | None] = mapped_column(Date)
    deal_type: Mapped[str | None] = mapped_column(String(50))   # LBO, M&A, Growth, Carve-out, Recap, Secondary
    # Cycle de vie réel d'un deal PROMU (Tâche Review Produit — Partie A, D31) :
    # Screening (défaut à la promotion) -> IC Review (bascule automatique dès
    # qu'un mémo est généré, voir routers/deals.py::generate_memo) -> Approved
    # -> Closed, avec Passed comme branche de sortie négative à tout moment.
    # Ce champ alimente désormais le tableau de suivi Deal Pipeline (colonnes
    # = ces 5 valeurs) — distinct du `pipeline_stage` de SourcedTarget, qui
    # suit la qualification PRÉ-promotion.
    status: Mapped[str] = mapped_column(String(30), default="Screening")
    deal_value: Mapped[float | None] = mapped_column(Float)      # $B
    equity_value: Mapped[float | None] = mapped_column(Float)
    enterprise_value_deal: Mapped[float | None] = mapped_column(Float)  # historique — voir `enterprise_value` (D15)

    # --- Données financières de la cible (D15, Tâche B.5) ---
    # Distinctes de `deal_value` (taille de transaction). `enterprise_value`
    # est la valeur d'entreprise propre à la cible — saisie explicitement ou
    # laissée nulle, JAMAIS dérivée mécaniquement de `target_revenue`. C'est
    # la colonne manquante qui faisait disparaître silencieusement l'EBITDA
    # validé en human-in-the-loop (voir RAPPORT B.4, DocumentReviewModal).
    target_revenue: Mapped[float | None] = mapped_column(Float)
    target_ebitda: Mapped[float | None] = mapped_column(Float)
    enterprise_value: Mapped[float | None] = mapped_column(Float)

    # --- Provenance (D18, Tâche B.6) ---
    # {"target_revenue": {"provenance": "REGISTRY", "as_of": "2022", "reference": "..."},
    #  "target_ebitda": {...}, "enterprise_value": {...}, "deal_value": {...},
    #  "ev_revenue_multiple": {...}, "ev_ebitda_multiple": {...}}
    # Colonne JSON plutôt qu'une table de jointure : besoin d'affichage, pas de
    # requête sur la provenance elle-même (voir RAPPORT B.6 pour la justification
    # complète). Voir api/schemas/provenance.py pour le schéma de chaque entrée.
    financial_provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # --- Multiples ---
    ev_revenue_multiple: Mapped[float | None] = mapped_column(Float)
    ev_ebitda_multiple: Mapped[float | None] = mapped_column(Float)
    pe_multiple: Mapped[float | None] = mapped_column(Float)
    premium_paid: Mapped[float | None] = mapped_column(Float)   # % premium to undisturbed price

    # --- Classification ---
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    # --- Source ---
    source: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(500))

    # --- IC Memo ---
    ic_memo: Mapped[str | None] = mapped_column(Text)

    activities: Mapped[list["DealActivity"]] = relationship(
        "DealActivity",
        back_populates="deal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="desc(DealActivity.created_at)",
    )

    sourced_target: Mapped["SourcedTarget | None"] = relationship(  # noqa: F821
        "SourcedTarget", lazy="selectin",
    )

    @property
    def target_type(self) -> str | None:
        """'target' / 'platform' (D11) — lu depuis la cible sourcing d'origine
        si le deal en a une. Enrichissement en lecture seule pour l'affichage
        (Deal Pipeline, Tâche Review Produit — Partie A) ; `sourced_target`
        est chargé en `lazy="selectin"`, donc toujours disponible sans
        requête supplémentaire ni risque de lazy-load hors contexte async."""
        return self.sourced_target.target_type if self.sourced_target else None

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_deals_sector", "sector"),
        Index("ix_deals_date", "announcement_date"),
        Index("ix_deals_type", "deal_type"),
    )

    def __repr__(self) -> str:
        return f"<Deal {self.acquirer_name} → {self.target_name} ({self.deal_value}B)>"
