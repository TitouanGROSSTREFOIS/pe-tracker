"""
Screener Router — /screener endpoints

Endpoints:
  POST   /screener              Exécuter un screening multi-critères
  GET    /screener/fields       Champs disponibles pour le screening
  POST   /screener/save         Sauvegarder un écran
  GET    /screener/saved        Lister les écrans sauvegardés
  DELETE /screener/saved/{id}   Supprimer un écran sauvegardé
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.screener_service import (
    run_screen,
    save_screen,
    list_saved_screens,
    delete_saved_screen,
    FIELD_MAP,
    OPERATORS,
)
from api.schemas.screener import (
    ScreenerRequest,
    ScreenerResult,
    SavedScreenCreate,
    SavedScreenOut,
)

router = APIRouter(prefix="/screener", tags=["Screening Engine"])


# ── Run Screen ───────────────────────────────
@router.post("", response_model=ScreenerResult)
async def run_screening(req: ScreenerRequest, db: AsyncSession = Depends(get_db)):
    """
    Exécuter un screening multi-critères.

    Exemple de body :
    ```json
    {
      "filters": [
        {"field": "market_cap", "operator": "gte", "value": 1e10},
        {"field": "sector", "operator": "eq", "value": "Technology"},
        {"field": "ebitda_margin", "operator": "gte", "value": 0.20}
      ],
      "sort_by": "market_cap",
      "sort_desc": true,
      "limit": 25,
      "offset": 0
    }
    ```
    """
    result = await run_screen(req, db)
    return result


# ── Available Fields ─────────────────────────
@router.get("/fields")
async def screener_fields():
    """
    Retourne la liste des champs disponibles pour le screening,
    avec leurs opérateurs supportés.
    """
    fields = []
    for field_name, col_ref in FIELD_MAP.items():
        col = col_ref
        python_type = "string"
        if hasattr(col, "type"):
            type_name = type(col.type).__name__
            if type_name in ("Float", "Numeric", "BigInteger", "Integer"):
                python_type = "number"
            elif type_name in ("Date", "DateTime"):
                python_type = "date"
            elif type_name == "Boolean":
                python_type = "boolean"

        fields.append({
            "field": field_name,
            "type": python_type,
            "operators": list(OPERATORS.keys()),
        })
    return {"fields": fields, "total": len(fields)}


# ── Saved Screens CRUD ───────────────────────
@router.post("/save", response_model=SavedScreenOut)
async def save(body: SavedScreenCreate, db: AsyncSession = Depends(get_db)):
    """Sauvegarder un écran de recherche."""
    screen = await save_screen(body, db)
    return screen


@router.get("/saved", response_model=list[SavedScreenOut])
async def list_saved(db: AsyncSession = Depends(get_db)):
    """Lister les écrans sauvegardés."""
    return await list_saved_screens(db)


@router.delete("/saved/{screen_id}")
async def delete_screen(screen_id: int, db: AsyncSession = Depends(get_db)):
    """Supprimer un écran sauvegardé."""
    ok = await delete_saved_screen(screen_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return {"status": "deleted", "id": screen_id}
