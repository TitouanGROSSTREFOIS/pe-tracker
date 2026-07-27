"""
Company model — core entity
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Any
from sqlalchemy import String, Float, Integer, Boolean, Date, DateTime, Text, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(100))
    exchange: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str | None] = mapped_column(String(10), default="USD")
    market_cap: Mapped[float | None] = mapped_column(Float)
    enterprise_value: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    employees: Mapped[int | None] = mapped_column(Integer)
    website: Mapped[str | None] = mapped_column(String(500))
    ipo_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_price: Mapped[float | None] = mapped_column(Float)
    shares_outstanding: Mapped[float | None] = mapped_column(Float)

    # --- Provenance (D19, Tâche B.7) — même format que Deal.financial_provenance ---
    # {"market_cap": {"provenance": "MARKET", "as_of": "...", "reference": "..."}, ...}
    financial_provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    financials: Mapped[list["Financial"]] = relationship(  # noqa: F821
        "Financial", back_populates="company", cascade="all, delete-orphan"
    )
    ratios: Mapped[list["FinancialRatio"]] = relationship(  # noqa: F821
        "FinancialRatio", back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_companies_sector", "sector"),
        Index("ix_companies_country", "country"),
        Index("ix_companies_market_cap", "market_cap"),
    )

    def __repr__(self) -> str:
        return f"<Company {self.ticker} — {self.name}>"
