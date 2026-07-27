"""
Sourcing Service — CRUD for M&A sourced targets.
"""
from __future__ import annotations
import re
import unicodedata
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from api.models.sourcing import SourcedTarget
from api.models.deal import Deal
from api.schemas.sourcing import SourcedTargetCreate, SourcedTargetUpdate
from api.schemas.provenance import DataProvenance, FieldProvenance, provenance_dict_to_json
from api.services.deals_service import compute_deal_multiples


STATUS_TO_STAGE = {
    "Watchlist": "Screening",
    "Contacted": "NDA Signed",
    "Deep Dive": "Due Diligence",
    "Active": "IC Memo",
    "Passed": "Passed",
}

STAGE_TO_STATUS = {
    "Screening": "Watchlist",
    "NDA Signed": "Contacted",
    "Management Meeting": "Deep Dive",
    "Due Diligence": "Deep Dive",
    "IC Memo": "Active",
    "Closed": "Active",
    "Passed": "Passed",
}


async def _attach_promoted_deal_ids(db: AsyncSession, targets: list[SourcedTarget]) -> None:
    """Set a transient `.promoted_deal_id` attribute on each target (Tâche B.5).

    Pas une colonne mappée : un attribut Python simple, peuplé par une seule
    requête jointe plutôt qu'un N+1, et lu par `SourcedTargetOut` (Pydantic
    `from_attributes=True` lit n'importe quel attribut d'instance, mappé ou
    non). Permet au frontend d'afficher "déjà promue" sans appel séparé par
    ligne et évite une double promotion accidentelle.
    """
    ids = [t.id for t in targets]
    if not ids:
        return
    rows = await db.execute(
        select(Deal.sourced_target_id, Deal.id).where(Deal.sourced_target_id.in_(ids))
    )
    deal_by_target = {row[0]: row[1] for row in rows.all()}
    for t in targets:
        t.promoted_deal_id = deal_by_target.get(t.id)


_LEGAL_FORM_SUFFIXES_RE = re.compile(
    r"\b(sas|sasu|sarl|eurl|sci|snc|sa|scop|scic)\b", re.IGNORECASE
)


def _normalize_company_name(name: str) -> str:
    """Normalise un nom de société pour comparaison approximative (Tâche
    B.5, Étape 3) : minuscules, accents retirés, formes juridiques
    courantes retirées, ponctuation/espaces multiples aplatis. Ne modifie
    rien en base — sert uniquement à comparer, jamais à afficher."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    n = n.lower()
    n = _LEGAL_FORM_SUFFIXES_RE.sub(" ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


async def find_matching_sourced_targets(
    db: AsyncSession, company_name: str, *, siren: str | None = None, limit: int = 3
) -> list[tuple[SourcedTarget, float]]:
    """Rapprochement d'un nom extrait de teaser avec les cibles déjà
    sourcées (Tâche B.5, Étape 3) — SIREN si fourni (jamais le cas
    aujourd'hui : l'extraction LLM ne le récupère pas, voir document_parser.py,
    non modifié dans cette tâche), sinon nom normalisé (`difflib`, pas de
    dépendance de fuzzy-matching ajoutée).

    Ne décide JAMAIS de rattacher automatiquement — retourne des couples
    (cible, score de similarité 0-1) triés décroissant, à exposer à
    l'utilisateur. Un score de 1.0 (SIREN identique ou nom normalisé
    strictement égal) reste une PROPOSITION, pas une résolution automatique.
    """
    result = await db.execute(select(SourcedTarget))
    all_targets = list(result.scalars().all())

    if siren:
        siren_matches = [t for t in all_targets if t.siren == siren]
        if siren_matches:
            return [(t, 1.0) for t in siren_matches[:limit]]

    normalized_query = _normalize_company_name(company_name)
    if not normalized_query:
        return []

    scored: list[tuple[float, SourcedTarget]] = []
    for t in all_targets:
        normalized_candidate = _normalize_company_name(t.company_name)
        if not normalized_candidate:
            continue
        similarity = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
        if similarity >= 0.6:
            scored.append((similarity, t))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [(t, round(sim, 2)) for sim, t in scored[:limit]]


async def get_target(db: AsyncSession, target_id: int) -> SourcedTarget | None:
    """Fetch a single sourced target by ID."""
    target = await db.get(SourcedTarget, target_id)
    if target:
        await _attach_promoted_deal_ids(db, [target])
    return target


async def get_target_by_url(db: AsyncSession, url: str) -> SourcedTarget | None:
    """Fetch by URL — used to deduplicate before inserting."""
    result = await db.execute(
        select(SourcedTarget).where(SourcedTarget.url == url)
    )
    return result.scalar_one_or_none()


async def list_targets(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> tuple[list[SourcedTarget], int]:
    """Return (targets, total_count) with optional status filter."""
    conditions = []
    if status:
        conditions.append(SourcedTarget.status == status)

    where = conditions[0] if len(conditions) == 1 else True if not conditions else None

    # Count
    count_q = select(func.count(SourcedTarget.id))
    if conditions:
        count_q = count_q.where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    # Data
    query = select(SourcedTarget)
    if conditions:
        query = query.where(*conditions)
    query = query.order_by(SourcedTarget.score.desc().nullslast()).limit(limit).offset(offset)

    result = await db.execute(query)
    targets = list(result.scalars().all())
    await _attach_promoted_deal_ids(db, targets)

    return targets, total


async def create_target(
    db: AsyncSession,
    target_in: SourcedTargetCreate,
) -> SourcedTarget:
    """Insert a new sourced target."""
    payload = target_in.model_dump(exclude_none=False)

    if not payload.get("pipeline_stage") and payload.get("status"):
        payload["pipeline_stage"] = STATUS_TO_STAGE.get(payload["status"], "Screening")
    if not payload.get("status") and payload.get("pipeline_stage"):
        payload["status"] = STAGE_TO_STATUS.get(payload["pipeline_stage"], "Watchlist")

    target = SourcedTarget(**payload)
    db.add(target)
    await db.flush()
    await db.refresh(target)
    return target


async def update_target(
    db: AsyncSession,
    target_id: int,
    target_update: SourcedTargetUpdate,
) -> SourcedTarget | None:
    """Partial update — only set fields that are provided (not None)."""
    target = await db.get(SourcedTarget, target_id)
    if not target:
        return None

    update_data = target_update.model_dump(exclude_unset=True)

    if "status" in update_data and "pipeline_stage" not in update_data:
        update_data["pipeline_stage"] = STATUS_TO_STAGE.get(update_data["status"], "Screening")
    if "pipeline_stage" in update_data and "status" not in update_data:
        update_data["status"] = STAGE_TO_STATUS.get(update_data["pipeline_stage"], "Watchlist")

    for key, value in update_data.items():
        setattr(target, key, value)

    await db.flush()
    await db.refresh(target)
    return target


async def delete_target(db: AsyncSession, target_id: int) -> bool:
    """Delete a sourced target. Returns True if found and deleted."""
    target = await db.get(SourcedTarget, target_id)
    if not target:
        return False
    await db.delete(target)
    return True


class TargetNotFoundError(Exception):
    pass


class TargetAlreadyPromotedError(Exception):
    def __init__(self, deal_id: int):
        self.deal_id = deal_id
        super().__init__(f"Target already promoted to deal {deal_id}")


async def _fetch_registry_exercise_year(siren: str) -> str | None:
    """Récupère l'exercice (année) du dernier CA connu au registre public pour
    ce SIREN (Tâche B.6, D18) — même source déjà utilisée par le pipeline
    registre (`recherche-entreprises.api.gouv.fr`), gratuite, sans clé.
    Retourne None si indisponible plutôt que de deviner une année."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://recherche-entreprises.api.gouv.fr/search",
                params={"q": siren},
                timeout=10.0,
            )
        if resp.status_code != 200:
            return None
        results = resp.json().get("results", [])
        if not results:
            return None
        finances = results[0].get("finances") or {}
        if not isinstance(finances, dict) or not finances:
            return None
        return sorted(finances.keys(), reverse=True)[0]
    except Exception as e:
        logger.warning("[Promote] Impossible de récupérer l'exercice registre pour SIREN {} : {}", siren, e)
        return None


# D18 (Tâche B.6) — l'EBITDA et l'EV présents sur SourcedTarget (quand ils le
# sont : legacy uniquement, voir RAPPORT B.6 §Étape 5) proviennent TOUJOURS
# d'une hypothèse sectorielle du moteur de valorisation LBO (marge EBITDA %
# et multiple d'entrée résolus par code NAF/mots-clés) — aucun pipeline de ce
# projet n'expose un EBITDA réel pour une société française non cotée (voir
# RAPPORT B.6 §Étape 6). Jamais REGISTRY ni MARKET pour ces deux champs.
#
# Tâche "P0 : un seul deal dans les 3 documents" (Partie D) : ce texte est
# cité VERBATIM dans le mémo/deck client (qualify_amount affiche `reference`
# telle quelle) — la version précédente contenait un chemin de fichier
# (`api/services/ma_engine/valuation_engine.py::LBO_PROFILES`) et un renvoi à
# un rapport interne (`RAPPORT B.6 §Étape 6`), tous deux visibles par un
# lecteur externe du mémo. Reformulé en langage naturel, sans référence
# interne — le contenu factuel (méthode d'estimation, limite de la donnée)
# est conservé à l'identique.
_ESTIMATE_METHOD_REF = (
    "Estimated using a sector-based valuation methodology (EBITDA margin and "
    "entry multiple derived from the target's business sector). No real "
    "EBITDA is available from free public sources for a non-listed French "
    "company."
)


async def promote_target_to_deal(db: AsyncSession, target_id: int) -> Deal:
    """Promote a qualified SourcedTarget into a Deal (D14, Tâche B.5 ; D18, Tâche B.6).

    Les deux entités restent distinctes — ceci crée un NOUVEAU `Deal` relié
    par `sourced_target_id`, ça ne transforme/fusionne rien. Pré-remplit à
    partir des seules données réellement connues de la cible :
      - `country="France"` uniquement si `source="registry"` (le registre
        Sirene ne couvre que des entités françaises — ce n'est pas une
        supposition mais une propriété de la source) ; sinon laissé nul.
      - `sector` = premier mot-clé du pipeline de qualification, s'il existe
        (donnée réelle réutilisée telle quelle, pas une catégorisation
        inventée) ; sinon laissé nul.
      - SIREN n'est PAS dupliqué sur `Deal` : il reste accessible via la
        relation `deal.sourced_target.siren`, pour éviter la désynchronisation
        de deux copies de la même donnée d'identité (cohérent avec D14 :
        deux entités distinctes reliées par FK, pas fusionnées).

    Provenance (D18) :
      - target_revenue : REGISTRY (avec l'exercice réel, récupéré en direct)
        si `source="registry"` ; ESTIMATE si `source="google_radar"` (cascade
        OSINT, voir financial_estimator.py) ; UNKNOWN sinon — jamais deviné.
      - target_ebitda / enterprise_value : ESTIMATE dès qu'ils sont présents
        (voir `_ESTIMATE_METHOD_REF`) — absents de la provenance s'ils sont
        eux-mêmes absents (rien à qualifier).
    """
    target = await db.get(SourcedTarget, target_id)
    if not target:
        raise TargetNotFoundError(f"Sourced target {target_id} not found")

    existing = await db.execute(select(Deal.id).where(Deal.sourced_target_id == target_id))
    existing_deal_id = existing.scalar_one_or_none()
    if existing_deal_id is not None:
        raise TargetAlreadyPromotedError(existing_deal_id)

    keywords = target.keywords if isinstance(target.keywords, list) else None
    sector = keywords[0] if keywords else None
    country = "France" if target.source == "registry" else None

    provenance: dict[str, dict] = {}
    if target.revenue_estimate is not None:
        if target.source == "registry":
            as_of = await _fetch_registry_exercise_year(target.siren) if target.siren else None
            provenance["target_revenue"] = FieldProvenance(
                provenance=DataProvenance.REGISTRY,
                as_of=as_of,
                reference="Sirene / recherche-entreprises.api.gouv.fr"
                          + (f", SIREN {target.siren}" if target.siren else ""),
            ).model_dump(mode="json")
        elif target.source == "google_radar":
            # Tâche "P0 : un seul deal dans les 3 documents" (Partie D) : ce
            # texte est cité VERBATIM dans le mémo/deck client (qualify_amount
            # affiche `reference` telle quelle) — la version précédente
            # contenait un chemin de fichier ("financial_estimator.py") et du
            # jargon technique ("OSINT waterfall") visibles par un lecteur
            # externe (cas Ingebime). Reformulé en langage naturel.
            provenance["target_revenue"] = FieldProvenance(
                provenance=DataProvenance.ESTIMATE,
                reference="Estimated from public headcount data (official registry, sector "
                          "revenue-per-employee ratio) or public professional listings — exact "
                          "method not tracked at source.",
            ).model_dump(mode="json")
        else:
            provenance["target_revenue"] = FieldProvenance(
                provenance=DataProvenance.UNKNOWN,
                reference=f"SourcedTarget.source='{target.source}' not recognized to qualify origin.",
            ).model_dump(mode="json")

    if target.ebitda_estimate is not None:
        provenance["target_ebitda"] = FieldProvenance(
            provenance=DataProvenance.ESTIMATE, reference=_ESTIMATE_METHOD_REF,
        ).model_dump(mode="json")
    if target.enterprise_value is not None:
        provenance["enterprise_value"] = FieldProvenance(
            provenance=DataProvenance.ESTIMATE, reference=_ESTIMATE_METHOD_REF,
        ).model_dump(mode="json")

    deal = Deal(
        acquirer_name="TBD",
        target_name=target.company_name,
        sourced_target_id=target.id,
        deal_type="M&A",
        status="Screening",
        target_revenue=target.revenue_estimate,
        target_ebitda=target.ebitda_estimate,
        enterprise_value=target.enterprise_value,
        sector=sector,
        country=country,
        description=target.business_summary,
        source="Sourcing Promotion",
        source_url=target.url,
        financial_provenance=provenance,
    )
    compute_deal_multiples(deal)
    db.add(deal)
    await db.flush()
    await db.refresh(deal)
    return deal
