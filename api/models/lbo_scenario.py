"""
LBO Scenario model — persistance des scénarios LBO (D23, Tâche B.8).

Un scénario = un run figé du Paper LBO Engine, rattaché à un deal, sauvegardé
par une action EXPLICITE de l'utilisateur (jamais automatique — voir
`api/routers/lbo_scenarios.py`). Plusieurs scénarios possibles par deal (base
case, upside, downside…), distingués par `label`.

`assumptions_json` conserve le payload de requête complet (hypothèses :
revenue, sector_or_naf, multiples, levier, structure de dette…) et
`result_json` le résultat complet du moteur (Sources & Uses, projections,
Exit, Returns) — y compris, le cas échéant, le bloc `calibration` (D22) qui
documente la chaîne de calcul du multiple d'entrée. Aucun recalcul à la
lecture : ce qui est affiché lors du rechargement d'un scénario est
exactement ce qui a été sauvegardé.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.database import Base


class LBOScenario(Base):
    __tablename__ = "lbo_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    assumptions_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    deal: Mapped["Deal"] = relationship("Deal")  # noqa: F821

    def __repr__(self) -> str:
        return f"<LBOScenario '{self.label}' (deal_id={self.deal_id})>"
