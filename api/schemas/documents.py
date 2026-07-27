"""
Document extraction schemas for PDF teaser / CIM ingestion.
"""
from __future__ import annotations

from pydantic import BaseModel


class SourcedTargetMatch(BaseModel):
    """Candidat de rapprochement SourcedTarget proposé pour un teaser
    uploadé (Tâche B.5, Étape 3) — jamais appliqué automatiquement, toujours
    exposé à l'utilisateur pour décision dans la modale de review."""
    id: int
    company_name: str
    siren: str | None = None
    similarity: float


class ExtractionFlag(BaseModel):
    """Drapeau de vraisemblance serveur (D25, Tâche B.10) — ne corrige rien,
    signale une valeur suspecte pour attirer l'attention de l'utilisateur
    dans la modale de review (human-in-the-loop, Étape 1.3)."""
    field: str
    reason: str
    severity: str = "warning"


class DocumentExtractionOut(BaseModel):
    company_name: str
    business_summary: str
    estimated_revenue: float | None = None
    estimated_ebitda: float | None = None
    # D44 (Tâche Finalisation) : exercice de référence des montants
    # ci-dessus, jamais deviné — null si non déterminable depuis le document.
    fiscal_year: int | None = None
    sourced_target_matches: list[SourcedTargetMatch] = []
    flags: list[ExtractionFlag] = []
