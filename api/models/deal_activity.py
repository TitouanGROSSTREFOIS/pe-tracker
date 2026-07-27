"""
Deal activity log model.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class DealActivity(Base):
    __tablename__ = "deal_activities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    deal: Mapped["Deal"] = relationship("Deal", back_populates="activities", lazy="selectin")  # noqa: F821

    __table_args__ = (
        Index("ix_deal_activities_deal_created", "deal_id", "created_at"),
    )
