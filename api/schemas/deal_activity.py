"""
Deal activity Pydantic schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ActivityType = Literal["system_event", "user_note"]


class DealActivityBase(BaseModel):
    action_type: ActivityType
    content: str


class DealNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class DealActivityOut(DealActivityBase):
    id: int
    deal_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DealActivityListResponse(BaseModel):
    deal_id: int
    total: int
    activities: list[DealActivityOut]
