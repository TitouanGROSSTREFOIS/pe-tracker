"""
Sourcing Router — /sourcing endpoints

Endpoints:
  POST   /sourcing/scan             Lancer un scan OSINT complet (background)
  GET    /sourcing/scan/status      Statut du dernier scan (D40)
  POST   /sourcing/batch            Batch scan depuis un CSV (background)
  GET    /sourcing/export            Export CSV de toutes les cibles
  GET    /sourcing                   Lister les cibles (paginé, filtre status)
  POST   /sourcing                   Créer une cible (après scraping)
  GET    /sourcing/{target_id}       Détail d'une cible
  PATCH  /sourcing/{target_id}       Mise à jour partielle (status, LBO, etc.)
  DELETE /sourcing/{target_id}       Supprimer une cible

Note (D42, Tâche Finalisation) : l'ancien export "teaser PPTX" pré-promotion
(GET /sourcing/{target_id}/teaser, pptx_generator.py) a été retiré — le deck
IC (ic_deck_generator.py, GET /deals/{deal_id}/export-deck-pptx) est
désormais le seul export PowerPoint du produit, disponible une fois la
cible promue en deal.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db, AsyncSessionLocal
from api.services.sourcing_service import (
    get_target,
    get_target_by_url,
    list_targets,
    create_target,
    update_target,
    delete_target,
    promote_target_to_deal,
    TargetNotFoundError,
    TargetAlreadyPromotedError,
)
from api.services.ma_engine.sourcing_pipeline import run_full_sourcing_scan
from api.services.ma_engine.batch_processor import process_url_batch
from api.services.ma_engine.exporter import export_targets_csv, export_targets_html
from api.services.alt_data_service import get_digital_dd
from api.services.legal_watch_service import get_corporate_events
from api.services.talent_signal_service import get_talent_signals
from api.services.portfolio_service import ensure_portfolio_company_with_mock_kpis
from api.services.lbo_scenario_service import build_base_case_scenario, build_downside_scenario
from api.services.document_parser import parse_cim_pdf
from api.schemas.sourcing import (
    SourcedTargetCreate,
    SourcedTargetUpdate,
    SourcedTargetStageUpdate,
    SourcedTargetOut,
    SourcedTargetListResponse,
    SourcingScanRequest,
    SourcingScanResponse,
    ScanStatus,
    ScanSavedTarget,
    BatchScanResponse,
    TargetPromoteResponse,
)

router = APIRouter(prefix="/sourcing", tags=["Sourcing M&A"])

# D40 — dernier statut de scan connu (process unique, voir docstring de
# ScanStatus). Remplacé à chaque nouveau scan lancé.
_LAST_SCAN: ScanStatus | None = None


# ============================================================
# Background task wrapper — self-managed DB session
# ============================================================

async def _run_scan_background(platform_url: str) -> None:
    """Wrapper exécuté dans BackgroundTasks.

    Crée sa propre session DB (AsyncSessionLocal) car la session
    injectée par Depends(get_db) est fermée dès que la réponse HTTP
    est envoyée — bien avant la fin d'un scan de 1-3 min.
    """
    global _LAST_SCAN
    from datetime import datetime, timezone

    logger.info("[BG-TASK] ▶ Démarrage background scan pour {}", platform_url)
    db = AsyncSessionLocal()
    try:
        result = await run_full_sourcing_scan(db, platform_url)
        # Commit final de sécurité (au cas où le pipeline n'a pas commit)
        await db.commit()
        logger.info(
            "[BG-TASK] ✅ SCAN TERMINÉ {} — {} cibles sauvegardées / {} trouvées",
            platform_url,
            result.get("targets_saved", 0),
            result.get("targets_found", 0),
        )
        _LAST_SCAN = ScanStatus(
            platform_url=platform_url,
            status="completed",
            started_at=_LAST_SCAN.started_at if _LAST_SCAN else datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            seed_company_name=(result.get("company_dna") or {}).get("company_name"),
            targets_found=result.get("targets_found", 0),
            targets_scored=result.get("targets_scored", 0),
            targets_saved=result.get("targets_saved", 0),
            targets_skipped=result.get("targets_skipped", 0),
            # D46 (Tâche Finalisation, Partie B) : `results` était déjà calculé
            # par le pipeline (sourcing_pipeline.py::saved_results) mais jeté
            # avant ScanStatus — l'utilisateur ne pouvait pas savoir QUELLES
            # cibles son scan avait ajoutées, seulement combien.
            saved_targets=[
                ScanSavedTarget(id=r["id"], company_name=r["company_name"], url=r["url"], score=r.get("score"))
                for r in (result.get("results") or [])
            ],
            error=result.get("error"),
        )
    except Exception as exc:
        logger.error(
            "[BG-TASK] ❌ ERREUR FATALE dans le background scan pour {} : {}",
            platform_url,
            str(exc),
        )
        # Affiche la stacktrace complète dans le terminal Uvicorn
        import traceback
        logger.error(traceback.format_exc())
        try:
            await db.rollback()
        except Exception:
            pass
        _LAST_SCAN = ScanStatus(
            platform_url=platform_url,
            status="failed",
            started_at=_LAST_SCAN.started_at if _LAST_SCAN else datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            error=str(exc),
        )
    finally:
        try:
            await db.close()
            logger.info("[BG-TASK] 🔒 Session DB fermée proprement.")
        except Exception:
            pass


# ── Scan endpoint (background) ───────────────
@router.post(
    "/scan",
    response_model=SourcingScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Lancer un scan OSINT complet",
)
async def launch_scan(
    body: SourcingScanRequest,
    background_tasks: BackgroundTasks,
):
    """
    Déclenche le pipeline M&A complet en arrière-plan :
    Scraping → NLP → Google Radar → Scoring → LBO → DB.

    Retourne immédiatement un 202 Accepted.
    Les résultats apparaîtront dans GET /sourcing au fur et à mesure ;
    GET /sourcing/scan/status (D40) permet de suivre l'issue réelle du scan
    (terminé, cibles trouvées/retenues/sauvegardées, ou raison d'un 0 résultat)
    plutôt que de laisser l'utilisateur deviner depuis ce seul message générique.
    """
    global _LAST_SCAN
    from datetime import datetime, timezone

    url = str(body.platform_url)
    _LAST_SCAN = ScanStatus(platform_url=url, status="running", started_at=datetime.now(timezone.utc))
    background_tasks.add_task(_run_scan_background, url)
    return SourcingScanResponse(
        message=f"Scan lancé en arrière-plan pour {url}.",
        platform_url=url,
    )


# ── Scan status (D40, Tâche Finalisation) ────
@router.get("/scan/status", response_model=ScanStatus | None, summary="Statut du dernier scan lancé")
async def scan_status():
    """Renvoie l'état du dernier scan (running/completed/failed) avec le
    détail réel (cibles trouvées/retenues/sauvegardées, ou raison d'un 0
    résultat) — évite qu'un scan qui ne ramène rien reste un échec
    silencieux côté interface. `null` si aucun scan n'a encore été lancé
    depuis le démarrage du serveur."""
    return _LAST_SCAN


# ── List targets ─────────────────────────────
@router.get("", response_model=SourcedTargetListResponse)
async def list_all(
    status_filter: str | None = Query(None, alias="status", description="Filter by pipeline status"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Liste paginée des cibles M&A sourcées.
    Triées par score décroissant. Filtrable par status.
    """
    targets, total = await list_targets(db, limit=limit, offset=offset, status=status_filter)
    return SourcedTargetListResponse(
        total=total,
        offset=offset,
        limit=limit,
        targets=targets,
    )


# ── Create target ────────────────────────────
@router.post("", response_model=SourcedTargetOut, status_code=status.HTTP_201_CREATED)
async def create(body: SourcedTargetCreate, db: AsyncSession = Depends(get_db)):
    """
    Insérer une nouvelle cible identifiée par le pipeline de scraping.
    Déduplique sur l'URL : renvoie 409 si la cible existe déjà.
    """
    existing = await get_target_by_url(db, body.url)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Target with URL '{body.url}' already exists (id={existing.id})",
        )
    target = await create_target(db, body)
    return target


# ============================================================
# Batch scan endpoint  (MUST be before /{target_id})
# ============================================================

@router.post(
    "/batch",
    response_model=BatchScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Lancer un batch scan depuis un fichier CSV",
)
async def launch_batch(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV avec une colonne 'url'"),
):
    """
    Accepte un fichier CSV contenant une colonne 'url' (ou première colonne).
    Lance un scan OSINT complet en arrière-plan pour chaque URL.

    Retourne immédiatement un 202 Accepted.
    Les résultats apparaîtront dans GET /sourcing au fur et à mesure.
    """
    try:
        content = await file.read()
        text = content.decode("utf-8-sig")
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de lire le fichier CSV : {exc}",
        )

    urls: list[str] = []
    reader = csv.DictReader(io.StringIO(text))

    url_column: str | None = None
    if reader.fieldnames:
        for col in reader.fieldnames:
            if col.strip().lower() == "url":
                url_column = col
                break

    if url_column:
        for row in reader:
            val = row.get(url_column, "").strip()
            if val and val.startswith("http"):
                urls.append(val)
    else:
        text_io = io.StringIO(text)
        simple_reader = csv.reader(text_io)
        next(simple_reader, None)
        for row in simple_reader:
            if row and row[0].strip().startswith("http"):
                urls.append(row[0].strip())

    if not urls:
        raise HTTPException(
            status_code=400,
            detail="Aucune URL valide trouvée dans le CSV. "
                   "Le fichier doit contenir une colonne 'url' avec des URLs http(s).",
        )

    logger.info("🔄 Batch scan lancé — {} URLs extraites du CSV", len(urls))
    background_tasks.add_task(process_url_batch, urls)

    return BatchScanResponse(
        message=f"Batch scan lancé pour {len(urls)} URLs. Résultats via GET /sourcing.",
        total_urls=len(urls),
        urls=urls,
    )


# ============================================================
# Upload Teaser/CIM endpoint  (MUST be before /{target_id})
# ============================================================

@router.post(
    "/upload-teaser",
    response_model=SourcedTargetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF teaser/CIM to create a new deal",
)
async def upload_teaser(
    file: UploadFile = File(..., description="PDF teaser or CIM document"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF teaser or CIM (Confidential Information Memorandum).
    
    The system will:
    1. Extract text from the PDF
    2. Use AI to identify company name, business summary, and financials
    3. Create a new SourcedTarget with status 'Screening'
    4. Return the created target
    
    This enables deal sourcing from documents sent by bankers, not just URLs.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )
    
    logger.info(f"📄 Receiving PDF upload: {file.filename} ({file.content_type})")
    
    # Read file bytes
    try:
        file_bytes = await file.read()
        file_size_mb = len(file_bytes) / (1024 * 1024)
        
        if file_size_mb > 50:  # 50 MB limit
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large: {file_size_mb:.1f} MB. Maximum 50 MB.",
            )
        
        logger.info(f"📊 PDF size: {file_size_mb:.2f} MB")
    
    except Exception as exc:
        logger.error(f"Failed to read uploaded file: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read file: {exc}",
        )
    
    # Parse PDF and extract deal info
    try:
        logger.info("🔍 Parsing PDF with document_parser...")
        extracted_data = await parse_cim_pdf(file_bytes)
        logger.info(f"✅ Extracted: {extracted_data['company_name']}")
    
    except Exception as exc:
        logger.error(f"PDF parsing failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse PDF: {exc}",
        )
    
    # Create SourcedTarget from extracted data
    # D47 (Tâche Finalisation, Partie C) : troisième voie de création de
    # SourcedTarget (avec registry et google_radar) qui ne renseignait pas
    # `source` non plus.
    target_data = SourcedTargetCreate(
        url=f"upload://{file.filename}",  # Synthetic URL for PDF uploads
        company_name=extracted_data["company_name"],
        business_summary=extracted_data["business_summary"],
        revenue_estimate=extracted_data.get("estimated_revenue"),
        ebitda_estimate=extracted_data.get("estimated_ebitda"),
        status="Screening",  # Default status for uploaded deals
        pipeline_stage="Screening",
        source="document_upload",
    )
    
    # Check for duplicates by company name
    existing_targets, _ = await list_targets(db, offset=0, limit=1000)
    for existing in existing_targets:
        if existing.company_name and existing.company_name.lower().strip() == target_data.company_name.lower().strip():
            logger.warning(f"⚠️  Duplicate company name detected: {target_data.company_name} (existing id={existing.id})")
            # Return existing instead of creating duplicate
            return existing
    
    # Create new target
    try:
        target = await create_target(db, target_data)
        logger.info(f"✅ Created target from PDF: id={target.id}, name={target.company_name}")
        return target
    
    except Exception as exc:
        logger.error(f"Failed to create target from PDF: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create target: {exc}",
        )


# ============================================================
# Export endpoint  (MUST be before /{target_id})
# ============================================================

@router.get(
    "/export",
    summary="Exporter toutes les cibles en CSV",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_csv(
    status_filter: str | None = Query(None, alias="status", description="Filtrer par statut"),
    format: str = Query("csv", description="Format d'export : csv ou html"),
    db: AsyncSession = Depends(get_db),
):
    """
    Exporte toutes les cibles (ou filtrées par statut) au format CSV ou HTML.
    Retourne un fichier téléchargeable via StreamingResponse.
    """
    targets, total = await list_targets(db, offset=0, limit=10000, status=status_filter)

    if not targets:
        raise HTTPException(status_code=404, detail="Aucune cible à exporter.")

    targets_dicts = []
    for t in targets:
        targets_dicts.append({
            "id": t.id,
            "company_name": t.company_name,
            "url": t.url,
            "status": t.status,
            "pipeline_stage": t.pipeline_stage,
            "score": t.score,
            "revenue_estimate": t.revenue_estimate,
            "ebitda_estimate": t.ebitda_estimate,
            "enterprise_value": t.enterprise_value,
            "lbo_irr": t.lbo_irr,
            "lbo_moic": t.lbo_moic,
            "entry_multiple": t.entry_multiple,
            "business_summary": t.business_summary,
            "keywords": t.keywords,
            "growth_signals": t.growth_signals,
            "red_flags": t.red_flags,
            "competitors": t.competitors,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })

    timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M")

    if format.lower() == "html":
        buf = export_targets_html(targets_dicts)
        return StreamingResponse(
            buf,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="pe_targets_{timestamp}.html"'},
        )

    buf = export_targets_csv(targets_dicts)
    return StreamingResponse(
        buf,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="pe_targets_{timestamp}.csv"'},
    )


# ============================================================
# Digital Due Diligence endpoint  (before /{target_id})
# ============================================================

@router.get(
    "/{target_id}/digital-dd",
    summary="Digital Due Diligence report (Tech Stack + Google Trends)",
)
async def digital_due_diligence(
    target_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Génère un rapport Digital DD pour la cible :
      - **Tech Stack** : Technologies détectées via BuiltWith (ou mock si pas de clé).
      - **Search Trends** : Intérêt de recherche Google (12 mois) via pytrends.

    Ne crashe jamais — renvoie des données factices en mode dégradé.
    """
    target = await get_target(db, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Sourced target not found")

    domain = target.url
    company_name = target.company_name

    report = await get_digital_dd(domain, company_name)
    return report


# ============================================================
# Legal & Corporate Watch endpoint  (before /{target_id})
# ============================================================

@router.get(
    "/{target_id}/legal-events",
    summary="Corporate & Legal events (Pappers / mock fallback)",
)
async def legal_events(
    target_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne l'historique des événements légaux et corporatifs
    pour la cible identifiée par target_id.

    Chaque événement est annoté d'un **Signal M&A** :
      - **Bullish** : changement structurel (statuts, capital, dirigeants)
      - **Neutral** : événement administratif courant
      - **Red Flag** : procédure collective, radiation, alerte

    Ne crashe jamais — renvoie des données mock en mode dégradé.
    """
    target = await get_target(db, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Sourced target not found")

    result = await get_corporate_events(target.company_name)
    return result


# ============================================================
# Talent & HR Intelligence endpoint  (before /{target_id})
# ============================================================

@router.get(
    "/{target_id}/talent-signals",
    summary="Talent & HR Intelligence (Adzuna / mock fallback)",
)
async def talent_signals(
    target_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne les signaux Talent & RH pour la cible :
      - **Hiring Velocity Score** (0-100)
      - **Headcount Trend** (ex: +15%)
      - **Department Breakdown** (Tech, Sales, Finance, etc.)
      - **Recent Job Openings** avec tags Executive Hire

    Ne crashe jamais — renvoie des données mock en mode dégradé.
    """
    target = await get_target(db, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Sourced target not found")

    result = await get_talent_signals(target.company_name)
    return result


# ============================================================
# D49 (Tâche Finalisation) : l'ancien endpoint "Comparable Intelligence"
# (GET /{target_id}/comps — public peers LLM en texte libre, private peers
# fabriqués via un repli Pappers systématique) a été retiré. La vue détail
# d'une cible valorise désormais directement via GET /lbo/calibration
# (sector_or_naf dérivé de target.keywords, même dérivation que
# sourcing_service.py::promote_target_to_deal pour rester cohérent avec le
# multiple utilisé plus tard par le LBO) et GET /comps/{comp_set_id} pour le
# CompSet TIC réel — appelés directement par le frontend (DealSourcing.tsx),
# aucun endpoint dédié nécessaire ici.
# ============================================================


# ── Get one target ───────────────────────────
@router.get("/{target_id}", response_model=SourcedTargetOut)
async def get_one(target_id: int, db: AsyncSession = Depends(get_db)):
    """Détail complet d'une cible M&A."""
    target = await get_target(db, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Sourced target not found")

    return target


# ── Promote to Deal (D14, Tâche B.5) ─────────
@router.post("/{target_id}/promote", response_model=TargetPromoteResponse, status_code=status.HTTP_201_CREATED)
async def promote(target_id: int, db: AsyncSession = Depends(get_db)):
    """
    Promeut une cible qualifiée du sourcing en Deal exécutable.

    Crée un nouveau `Deal` relié par `sourced_target_id`, pré-rempli avec les
    données réellement connues de la cible (CA/EBITDA/EV du registre, secteur,
    pays, description). Les deux entités restent distinctes (D14) — rejoue
    cette action une seconde fois sur la même cible renvoie 409, pas un
    doublon silencieux.
    """
    try:
        deal = await promote_target_to_deal(db, target_id)
    except TargetNotFoundError:
        raise HTTPException(status_code=404, detail="Sourced target not found")
    except TargetAlreadyPromotedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Target already promoted to deal {exc.deal_id}",
        )

    await db.commit()

    # D27 — LBO base-case calibré automatique à la promotion (Tâche Review
    # Produit, Partie B). Best-effort : ne doit jamais faire échouer la
    # promotion elle-même si le calcul/calibrage rencontre un problème.
    try:
        base_scenario = await build_base_case_scenario(db, deal)
        # Tâche "P2 : crédibilité de la thèse" (Partie B) — un mémo d'IC
        # mono-scénario n'existe pas : génère aussi un cas baissier attaché
        # au même deal, dès que le base case existe.
        if base_scenario is not None:
            await build_downside_scenario(db, deal, base_scenario.result_json)
    except Exception as exc:
        logger.warning(
            "[LBO base-case auto] Échec pour deal {} : {} — promotion non affectée.",
            deal.id, exc,
        )

    return TargetPromoteResponse(
        deal_id=deal.id,
        sourced_target_id=target_id,
        message=f"Target promoted to deal #{deal.id}",
    )


# ── Update only pipeline stage ───────────────
@router.patch("/{target_id}/stage", response_model=SourcedTargetOut)
async def update_stage(
    target_id: int,
    body: SourcedTargetStageUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour uniquement l'étape pipeline Kanban d'une cible.
    Endpoint dédié CRM pour les interactions rapides en UI.
    """
    stage = body.stage
    legacy_status_map = {
        "Screening": "Watchlist",
        "NDA Signed": "Contacted",
        "Management Meeting": "Deep Dive",
        "Due Diligence": "Deep Dive",
        "IC Memo": "Active",
        "Closed": "Active",
        "Passed": "Passed",
    }

    target = await update_target(
        db,
        target_id,
        SourcedTargetUpdate(
            pipeline_stage=stage,
            status=legacy_status_map.get(stage, "Watchlist"),
        ),
    )
    if not target:
        raise HTTPException(status_code=404, detail="Sourced target not found")

    if stage == "Closed":
        await ensure_portfolio_company_with_mock_kpis(db, target)

    return target


# ── Update target ────────────────────────────
@router.patch("/{target_id}", response_model=SourcedTargetOut)
async def update(
    target_id: int,
    body: SourcedTargetUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Mise à jour partielle d'une cible.
    Cas d'usage : changer le status, ajuster les hypothèses LBO,
    lier à une company_id officielle.
    """
    target = await update_target(db, target_id, body)
    if not target:
        raise HTTPException(status_code=404, detail="Sourced target not found")
    return target


# ── Delete target ────────────────────────────
@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(target_id: int, db: AsyncSession = Depends(get_db)):
    """Supprimer une cible du pipeline."""
    ok = await delete_target(db, target_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sourced target not found")
