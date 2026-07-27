"""
Comps Router — /comps endpoints

Endpoints:
  POST /comps                     Créer un comp set
  GET  /comps                     Lister les comp sets
  GET  /comps/{comp_set_id}       Table de comparables avec stats
  DELETE /comps/{comp_set_id}     Supprimer un comp set
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.comps_service import (
    create_comp_set,
    list_comp_sets,
    get_comp_table,
    delete_comp_set,
)
from api.schemas.comps import CompSetCreate, CompSetOut, CompsTableResponse

router = APIRouter(prefix="/comps", tags=["Trading Comps"])


@router.post("", response_model=CompSetOut)
async def create(body: CompSetCreate, db: AsyncSession = Depends(get_db)):
    """
    Créer un comp set.

    Body:
    ```json
    {
      "name": "US Tech Large Cap",
      "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
      "description": "FAANG+ companies",
      "base_year": 2024
    }
    ```
    """
    cs, member_count = await create_comp_set(body, db)
    return CompSetOut(
        id=cs.id,
        name=cs.name,
        description=cs.description,
        base_year=cs.base_year,
        ticker_count=member_count,
        created_at=cs.created_at,
    )


@router.get("")
async def list_sets(db: AsyncSession = Depends(get_db)):
    """Lister tous les comp sets."""
    sets = await list_comp_sets(db)
    return [
        CompSetOut(
            id=cs.id,
            name=cs.name,
            description=cs.description,
            base_year=cs.base_year,
            ticker_count=len(cs.members) if cs.members else 0,
            created_at=cs.created_at,
        )
        for cs in sets
    ]


@router.get("/{comp_set_id}", response_model=CompsTableResponse)
async def get_table(comp_set_id: int, db: AsyncSession = Depends(get_db)):
    """
    Table de comparables : toutes les métriques + stats (mean, median, P25, P75).
    """
    table = await get_comp_table(comp_set_id, db)
    if not table:
        raise HTTPException(status_code=404, detail="Comp set not found")
    return table


@router.delete("/{comp_set_id}")
async def delete(comp_set_id: int, db: AsyncSession = Depends(get_db)):
    """Supprimer un comp set."""
    ok = await delete_comp_set(comp_set_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Comp set not found")
    return {"status": "deleted", "id": comp_set_id}
