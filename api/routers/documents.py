"""
Document extraction router — PDF teaser/CIM to structured JSON.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.documents import DocumentExtractionOut, ExtractionFlag, SourcedTargetMatch
from api.services.document_parser import extract_document_metadata, validate_extraction_plausibility
from api.services.sourcing_service import find_matching_sourced_targets


router = APIRouter(prefix="/documents", tags=["Document Ingestion"])


@router.post("/extract", response_model=DocumentExtractionOut, status_code=status.HTTP_200_OK)
@router.post("/ingest", response_model=DocumentExtractionOut, status_code=status.HTTP_200_OK)
async def ingest_document(
    file: UploadFile = File(..., description="PDF teaser or CIM document"),
    db: AsyncSession = Depends(get_db),
):
    """Extract structured data from a PDF teaser/CIM without persisting it.

    Propose aussi un rapprochement avec des cibles déjà sourcées (Tâche B.5,
    Étape 3) — par nom normalisé (aucun SIREN extrait par le prompt actuel,
    non modifié dans cette tâche). Ces candidats sont exposés à l'utilisateur
    dans la modale de review, jamais rattachés automatiquement.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Uploaded file is empty")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc

    try:
        extracted = await extract_document_metadata(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected ingestion failure")
        raise HTTPException(status_code=500, detail=f"Document ingestion failed: {exc}") from exc

    matches = await find_matching_sourced_targets(db, extracted["company_name"])

    # D25 (Tâche B.10), Étape 1.2 : contrôle de vraisemblance AVANT que la
    # valeur n'atteigne la modale — ne corrige rien, signale seulement.
    flags = validate_extraction_plausibility(
        extracted.get("estimated_revenue"), extracted.get("estimated_ebitda")
    )
    if flags:
        logger.warning("Extraction plausibility flags for '{}': {}", extracted["company_name"], flags)

    return DocumentExtractionOut(
        **extracted,
        sourced_target_matches=[
            SourcedTargetMatch(id=t.id, company_name=t.company_name, siren=t.siren, similarity=sim)
            for t, sim in matches
        ],
        flags=[ExtractionFlag(**f) for f in flags],
    )