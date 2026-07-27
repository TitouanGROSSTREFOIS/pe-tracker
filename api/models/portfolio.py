"""
Portfolio models — post-acquisition monitoring
"""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import String, Float, Integer, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class PortfolioCompany(Base):
    __tablename__ = "portfolio_companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sourced_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sourced_targets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    sourced_target: Mapped["SourcedTarget"] = relationship(
        "SourcedTarget",
        back_populates="portfolio_company",
        lazy="selectin",
    )
    monthly_kpis: Mapped[list["MonthlyKPI"]] = relationship(
        "MonthlyKPI",
        back_populates="portfolio_company",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_portfolio_companies_entry_date", "entry_date"),
    )


class MonthlyKPI(Base):
    __tablename__ = "monthly_kpis"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    portfolio_company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("portfolio_companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    month_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    actual_revenue: Mapped[float] = mapped_column(Float, nullable=False)
    budget_revenue: Mapped[float] = mapped_column(Float, nullable=False)
    actual_ebitda: Mapped[float] = mapped_column(Float, nullable=False)
    budget_ebitda: Mapped[float] = mapped_column(Float, nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    portfolio_company: Mapped["PortfolioCompany"] = relationship(
        "PortfolioCompany",
        back_populates="monthly_kpis",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("portfolio_company_id", "month_date", name="uq_monthly_kpis_company_month"),
        Index("ix_monthly_kpis_company_month", "portfolio_company_id", "month_date"),
    )
