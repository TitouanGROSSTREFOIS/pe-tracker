"""
Comparable set models — peer group for trading comps
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.database import Base


class CompSet(Base):
    __tablename__ = "comp_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    base_year: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[list["CompSetMember"]] = relationship(
        "CompSetMember", back_populates="comp_set", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CompSet '{self.name}' ({len(self.members)} peers)>"


class CompSetMember(Base):
    __tablename__ = "comp_set_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    comp_set_id: Mapped[int] = mapped_column(ForeignKey("comp_sets.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)

    comp_set: Mapped["CompSet"] = relationship("CompSet", back_populates="members")
    company: Mapped["Company"] = relationship("Company")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("comp_set_id", "company_id", name="uq_comp_member"),
    )
