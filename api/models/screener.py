"""
Saved screens model — persist screener filter sets
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from api.database import Base


class SavedScreen(Base):
    __tablename__ = "saved_screens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    filters: Mapped[dict] = mapped_column(JSON, nullable=False)   # Dynamic filter config
    result_count: Mapped[int | None] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SavedScreen '{self.name}'>"
