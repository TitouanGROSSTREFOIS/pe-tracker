"""
Deal activity service — history log and manual notes.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.deal_activity import DealActivity


async def create_activity(
    db: AsyncSession,
    *,
    deal_id: int,
    action_type: str,
    content: str,
) -> DealActivity:
    activity = DealActivity(
        deal_id=deal_id,
        action_type=action_type,
        content=content,
    )
    db.add(activity)
    await db.flush()
    await db.refresh(activity)
    return activity


async def list_activities(db: AsyncSession, deal_id: int) -> list[DealActivity]:
    result = await db.execute(
        select(DealActivity)
        .where(DealActivity.deal_id == deal_id)
        .order_by(DealActivity.created_at.desc(), DealActivity.id.desc())
    )
    return list(result.scalars().all())
