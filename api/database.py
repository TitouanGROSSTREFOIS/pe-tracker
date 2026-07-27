"""
PE Intelligence Platform — Database engine & session management
"""
import re
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from api.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables (dev only — use Alembic in prod)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_schema)


def _migrate_schema(sync_conn) -> None:
    """Lightweight dev migration for backward compatibility."""
    inspector = inspect(sync_conn)
    table_names = inspector.get_table_names()
    if "sourced_targets" not in table_names:
        return

    columns = {col["name"] for col in inspector.get_columns("sourced_targets")}
    pipeline_stage_freshly_added = "pipeline_stage" not in columns
    if pipeline_stage_freshly_added:
        sync_conn.execute(
            text(
                "ALTER TABLE sourced_targets "
                "ADD COLUMN pipeline_stage VARCHAR(40) NOT NULL DEFAULT 'Screening'"
            )
        )

    if "deals" in table_names:
        deal_columns = {col["name"] for col in inspector.get_columns("deals")}
        if "ic_memo" not in deal_columns:
            sync_conn.execute(
                text(
                    "ALTER TABLE deals "
                    "ADD COLUMN ic_memo TEXT"
                )
            )

        # BUG corrigé (Tâche B.3) : ce backfill par CASE(status) ne doit
        # s'exécuter QU'UNE FOIS, juste après l'ajout de la colonne
        # pipeline_stage — pas à chaque démarrage. Avant ce correctif, il
        # tournait inconditionnellement à chaque `init_db()` (donc à chaque
        # démarrage de l'API) et écrasait silencieusement tout changement
        # d'étape fait à la main sur le Kanban (drag & drop) qui n'a pas
        # d'équivalent exact dans `status` — et cassait spécifiquement la
        # migration "Archived" ci-dessous (status='Archived' retombait dans
        # le ELSE 'Screening', qui s'exécutait APRÈS que status soit passé à
        # 'Archived' en Tâche B.2).
        if pipeline_stage_freshly_added:
            sync_conn.execute(
                text(
                    "UPDATE sourced_targets "
                    "SET pipeline_stage = CASE "
                    "WHEN status = 'Passed' THEN 'Passed' "
                    "WHEN status = 'Archived' THEN 'Archived' "
                    "WHEN status = 'Deep Dive' THEN 'Due Diligence' "
                    "WHEN status = 'Contacted' THEN 'NDA Signed' "
                    "WHEN status = 'Active' THEN 'IC Memo' "
                    "ELSE 'Screening' END"
                )
            )

    # ── Tâche B.3 — siren / source / target_type ─────────────────────
    if "siren" not in columns:
        sync_conn.execute(text("ALTER TABLE sourced_targets ADD COLUMN siren VARCHAR(9)"))
        sync_conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_sourced_targets_siren ON sourced_targets(siren)")
        )
    if "source" not in columns:
        sync_conn.execute(text("ALTER TABLE sourced_targets ADD COLUMN source VARCHAR(30)"))
    if "target_type" not in columns:
        sync_conn.execute(text("ALTER TABLE sourced_targets ADD COLUMN target_type VARCHAR(20)"))

    # Ne backfill qu'une fois (colonnes fraîchement ajoutées lors de CETTE
    # invocation) — évite d'écraser des valeurs déjà correctement peuplées
    # par le pipeline registre (Tâche B.3) lors des démarrages suivants.
    if "siren" not in columns and "source" not in columns and "target_type" not in columns:
        _backfill_b3_columns(sync_conn)

    # ── Tâche B.5 — sourced_target_id / target_revenue / target_ebitda /
    #    enterprise_value sur `deals` (D14/D15) ───────────────────────────
    if "deals" in table_names:
        deal_columns = {col["name"] for col in inspector.get_columns("deals")}
        if "sourced_target_id" not in deal_columns:
            sync_conn.execute(
                text(
                    "ALTER TABLE deals ADD COLUMN sourced_target_id INTEGER "
                    "REFERENCES sourced_targets(id)"
                )
            )
            sync_conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_deals_sourced_target_id "
                    "ON deals(sourced_target_id)"
                )
            )
        if "target_revenue" not in deal_columns:
            sync_conn.execute(text("ALTER TABLE deals ADD COLUMN target_revenue FLOAT"))
        if "target_ebitda" not in deal_columns:
            sync_conn.execute(text("ALTER TABLE deals ADD COLUMN target_ebitda FLOAT"))
        if "enterprise_value" not in deal_columns:
            sync_conn.execute(text("ALTER TABLE deals ADD COLUMN enterprise_value FLOAT"))

        # ── Tâche B.6 — financial_provenance (D18) ──────────────────────
        if "financial_provenance" not in deal_columns:
            sync_conn.execute(text("ALTER TABLE deals ADD COLUMN financial_provenance JSON"))

    # ── Tâche B.7 — financial_provenance sur companies / financials (D19) ──
    if "companies" in table_names:
        company_columns = {col["name"] for col in inspector.get_columns("companies")}
        if "financial_provenance" not in company_columns:
            sync_conn.execute(text("ALTER TABLE companies ADD COLUMN financial_provenance JSON"))

    if "financials" in table_names:
        financial_columns = {col["name"] for col in inspector.get_columns("financials")}
        if "financial_provenance" not in financial_columns:
            sync_conn.execute(text("ALTER TABLE financials ADD COLUMN financial_provenance JSON"))


# IDs connus et documentés dans les rapports de tâches précédentes (Tâche
# B.2) — pas une déduction heuristique, une correspondance directe avec ce
# qui a réellement été inséré par chaque pipeline à l'époque.
_KNOWN_REGISTRY_IDS = (30, 31, 32, 33, 34)   # sirene_sourcing_pipeline (B.2)
_KNOWN_RADAR_IDS = tuple(range(18, 30))       # run_full_sourcing_scan (B.1)

_SIREN_PREFIX_RE = re.compile(r"^\[SIREN:\s*(\d{9})\s*\|")


def _backfill_b3_columns(sync_conn) -> None:
    """Peuple siren/source/target_type sur les lignes existantes, du mieux
    possible, en signalant explicitement ce qui reste indéterminé (voir
    RAPPORT B.3).
    """
    rows = sync_conn.execute(
        text("SELECT id, business_summary, revenue_estimate FROM sourced_targets")
    ).fetchall()

    for row_id, business_summary, revenue_estimate in rows:
        # ── SIREN : extrait du préfixe texte posé par le pipeline B.2 ──
        siren = None
        if business_summary:
            m = _SIREN_PREFIX_RE.match(business_summary)
            if m:
                siren = m.group(1)
                # Nettoie tout le préfixe texte "[SIREN: ... | Source: ... | NAF: ...]"
                # devenu redondant (siren a désormais sa propre colonne).
                closing = business_summary.find("]\n\n")
                cleaned_summary = (
                    business_summary[closing + 3:].lstrip() if closing != -1
                    else business_summary[m.end():].lstrip()
                )
                sync_conn.execute(
                    text("UPDATE sourced_targets SET business_summary = :s, siren = :siren WHERE id = :id"),
                    {"s": cleaned_summary, "siren": siren, "id": row_id},
                )

        # ── source : provenance connue (B.1/B.2) ou indéterminée ──
        if row_id in _KNOWN_REGISTRY_IDS:
            source = "registry"
        elif row_id in _KNOWN_RADAR_IDS:
            source = "google_radar"
        else:
            source = None  # indéterminable — antérieur au suivi de tâches
        sync_conn.execute(
            text("UPDATE sourced_targets SET source = :source WHERE id = :id"),
            {"source": source, "id": row_id},
        )

        # ── target_type (D11) : uniquement si CA connu ──
        target_type = None
        if revenue_estimate is not None:
            if revenue_estimate > 100_000_000:
                target_type = "platform"
            elif revenue_estimate >= 10_000_000:
                target_type = "target"
            # < 10M€ ou non classifiable → laissé NULL, volontairement
        sync_conn.execute(
            text("UPDATE sourced_targets SET target_type = :tt WHERE id = :id"),
            {"tt": target_type, "id": row_id},
        )

    # ── Migration des 14 cibles "Archived/Passed" (contournement B.2) ──
    sync_conn.execute(
        text(
            "UPDATE sourced_targets SET pipeline_stage = 'Archived' "
            "WHERE status = 'Archived' AND pipeline_stage = 'Passed'"
        )
    )


async def drop_db():
    """Drop all tables (dev/testing only)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
