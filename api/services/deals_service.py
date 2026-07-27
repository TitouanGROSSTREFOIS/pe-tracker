"""
Deals Service — M&A / Deal Database CRUD + filters.
"""
from __future__ import annotations
from datetime import date
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.deal import Deal
from api.models.deal_activity import DealActivity
from api.models.lbo_scenario import LBOScenario
from api.schemas.deals import DealCreate, DealFilter
from api.schemas.provenance import (
    DataProvenance,
    FieldProvenance,
    field_provenance_from_json,
    weakest_provenance,
)


class SourcedTargetAlreadyLinkedError(Exception):
    """La cible visée par `sourced_target_id` est déjà reliée à un autre
    deal — la contrainte UNIQUE sur `deals.sourced_target_id` (D14, Tâche
    B.5) l'empêche en base ; on le détecte AVANT l'insert pour renvoyer une
    erreur claire au lieu de laisser remonter un 500 IntegrityError brut
    (constaté lors du test de parcours complet, Étape 6)."""

    def __init__(self, deal_id: int):
        self.deal_id = deal_id
        super().__init__(f"sourced_target_id already linked to deal {deal_id}")


def compute_deal_multiples(deal: Deal) -> None:
    """Recalcule ev_revenue_multiple / ev_ebitda_multiple à partir de
    `enterprise_value` — JAMAIS de `deal_value` (D15, Tâche B.5).

    N'écrase un multiple existant que si `enterprise_value` est connue : les
    deals historiques seedés (api/seed.py) portent des multiples annoncés
    publiquement sans que l'EV brute soit renseignée ici — on ne les efface
    pas faute de donnée.

    D18 (Tâche B.6) : un multiple calculé hérite de la provenance la plus
    faible de ses deux composantes — un EV/EBITDA calculé sur un EBITDA
    ESTIMATE est lui-même ESTIMATE, même si l'EV était REGISTRY.
    """
    if deal.enterprise_value is None:
        return

    raw_prov = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
    ev_prov = field_provenance_from_json(raw_prov, "enterprise_value")
    updated_prov = dict(raw_prov)

    if deal.target_revenue:
        deal.ev_revenue_multiple = deal.enterprise_value / deal.target_revenue
        rev_prov = field_provenance_from_json(raw_prov, "target_revenue")
        if ev_prov or rev_prov:
            multiple_provenance = weakest_provenance(
                ev_prov.provenance if ev_prov else None,
                rev_prov.provenance if rev_prov else None,
            )
            updated_prov["ev_revenue_multiple"] = FieldProvenance(
                provenance=multiple_provenance,
                reference="Calculated: enterprise_value / target_revenue (inherits the weakest provenance of its components)",
            ).model_dump(mode="json")

    if deal.target_ebitda:
        deal.ev_ebitda_multiple = deal.enterprise_value / deal.target_ebitda
        ebitda_prov = field_provenance_from_json(raw_prov, "target_ebitda")
        if ev_prov or ebitda_prov:
            multiple_provenance = weakest_provenance(
                ev_prov.provenance if ev_prov else None,
                ebitda_prov.provenance if ebitda_prov else None,
            )
            updated_prov["ev_ebitda_multiple"] = FieldProvenance(
                provenance=multiple_provenance,
                reference="Calculated: enterprise_value / target_ebitda (inherits the weakest provenance of its components)",
            ).model_dump(mode="json")

    if updated_prov != raw_prov:
        deal.financial_provenance = updated_prov


# ── Create deal ──────────────────────────────
async def create_deal(body: DealCreate, db: AsyncSession) -> Deal:
    if body.sourced_target_id is not None:
        existing = await db.execute(
            select(Deal.id).where(Deal.sourced_target_id == body.sourced_target_id)
        )
        existing_deal_id = existing.scalar_one_or_none()
        if existing_deal_id is not None:
            raise SourcedTargetAlreadyLinkedError(existing_deal_id)

    deal = Deal(**body.model_dump(exclude_none=True))
    compute_deal_multiples(deal)
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return deal


# ── Get single deal ──────────────────────────
async def get_deal(deal_id: int, db: AsyncSession) -> Deal | None:
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    return result.scalar_one_or_none()


# ── List / filter deals ─────────────────────
async def list_deals(
    filters: DealFilter,
    db: AsyncSession,
) -> tuple[list[Deal], int]:
    """Return (deals, total_count) with optional filters."""
    conditions = []

    if filters.sector:
        conditions.append(Deal.sector == filters.sector)
    if filters.deal_type:
        conditions.append(Deal.deal_type == filters.deal_type)
    if filters.status:
        conditions.append(Deal.status == filters.status)
    if filters.min_value is not None:
        conditions.append(Deal.deal_value >= filters.min_value)
    if filters.max_value is not None:
        conditions.append(Deal.deal_value <= filters.max_value)
    if filters.date_from:
        conditions.append(Deal.announcement_date >= filters.date_from)
    if filters.date_to:
        conditions.append(Deal.announcement_date <= filters.date_to)
    if filters.country:
        conditions.append(Deal.country == filters.country)

    where_clause = and_(*conditions) if conditions else True

    # Count
    count_q = select(func.count(Deal.id)).where(where_clause)
    total = (await db.execute(count_q)).scalar() or 0

    # Data
    query = select(Deal).where(where_clause)

    # Sort
    sort_col = getattr(Deal, filters.sort_by, Deal.announcement_date)
    query = query.order_by(sort_col.desc() if filters.sort_desc else sort_col.asc())

    query = query.limit(filters.limit).offset(filters.offset)
    result = await db.execute(query)
    deals = list(result.scalars().all())

    return deals, total


# ── Update deal ──────────────────────────────
async def update_deal(deal_id: int, updates: dict, db: AsyncSession) -> Deal | None:
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        return None
    for key, val in updates.items():
        if val is None or not hasattr(deal, key):
            continue
        if key == "financial_provenance" and isinstance(val, dict):
            # Traçabilité (cette tâche) : un PATCH partiel de financial_provenance
            # ne doit JAMAIS effacer silencieusement la provenance déjà posée
            # sur d'autres champs (ex. un PATCH qui ne touche que
            # enterprise_value écrasait auparavant target_revenue/target_ebitda,
            # un `setattr` remplaçant tout le dict au lieu de le fusionner —
            # aucun appelant actuel ne déclenche cette perte, mais c'était une
            # mine dormante pour toute future fonctionnalité d'édition).
            existing = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
            setattr(deal, key, {**existing, **val})
        else:
            setattr(deal, key, val)
    compute_deal_multiples(deal)
    await db.commit()
    await db.refresh(deal)
    return deal


# ── Delete deal ──────────────────────────────
async def delete_deal(deal_id: int, db: AsyncSession) -> bool:
    """Supprime un deal ET ses lignes dépendantes explicitement.

    Constat (trouvé pendant l'audit de traçabilité, Partie F) : `deal_activities`
    et `lbo_scenarios` déclarent `ForeignKey("deals.id", ondelete="CASCADE")`,
    mais SQLite n'applique un `ON DELETE CASCADE` déclaratif que si
    `PRAGMA foreign_keys=ON` est actif sur la connexion — ce qui n'est pas le
    cas ici (non configuré dans `api/database.py`). Un `db.delete(deal)` seul
    laissait donc des lignes orphelines (`PRAGMA foreign_key_check` les
    détecte). Suppression explicite ici plutôt qu'activer le PRAGMA
    globalement, dont l'effet sur le reste de l'app n'a pas été audité dans
    cette tâche."""
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        return False
    await db.execute(DealActivity.__table__.delete().where(DealActivity.deal_id == deal_id))
    await db.execute(LBOScenario.__table__.delete().where(LBOScenario.deal_id == deal_id))
    await db.delete(deal)
    await db.commit()
    return True


# ── Aggregations ─────────────────────────────
async def deal_stats(db: AsyncSession) -> dict:
    """Quick deal-database statistics."""
    total = (await db.execute(select(func.count(Deal.id)))).scalar() or 0
    total_value = (await db.execute(select(func.sum(Deal.deal_value)))).scalar() or 0

    # By type
    type_q = await db.execute(
        select(Deal.deal_type, func.count(Deal.id), func.sum(Deal.deal_value))
        .group_by(Deal.deal_type)
    )
    by_type = [
        {"type": row[0] or "Unknown", "count": row[1], "total_value": float(row[2] or 0)}
        for row in type_q.all()
    ]

    # By sector
    sector_q = await db.execute(
        select(Deal.sector, func.count(Deal.id))
        .group_by(Deal.sector)
        .order_by(func.count(Deal.id).desc())
        .limit(10)
    )
    by_sector = [{"sector": row[0] or "Unknown", "count": row[1]} for row in sector_q.all()]

    return {
        "total_deals": total,
        "total_value": float(total_value),
        "by_type": by_type,
        "by_sector": by_sector,
    }
