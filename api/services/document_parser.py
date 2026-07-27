"""
Document Parser Service — Extract deal information from PDF teasers/CIMs.
"""
from __future__ import annotations

import io
import json
from typing import Optional

import pdfplumber
from loguru import logger
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from api.config import get_settings


MAX_PDF_PAGES = 5
MAX_PROMPT_CHARS = 12_000

# Tâche B.11, Étape 3.3 : retry uniquement sur les erreurs TRANSITOIRES
# (réseau, timeout, rate limit, 5xx côté OpenAI) — jamais sur une clé API
# invalide (AuthenticationError) ou une requête malformée (BadRequestError),
# où réessayer ne changerait rien et ne ferait que retarder un message
# d'erreur qui serait de toute façon actionnable immédiatement. Constat
# motivant cet ajout : aucune logique de retry n'existait sur ce chemin
# avant cette tâche (contrairement à comps_service.py, yfinance/Pappers).
_OPENAI_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


async def extract_document_metadata(file_bytes: bytes) -> dict[str, Optional[str | float]]:
    """Strict PDF ingest path used by the Sprint 8 document route."""
    text = await _extract_text_from_pdf(file_bytes, max_pages=MAX_PDF_PAGES)
    if not text.strip():
        raise ValueError("No extractable text found in the first pages of the PDF")

    return await _extract_deal_info_with_llm(text)


async def parse_cim_pdf(file_bytes: bytes) -> dict[str, Optional[str | float]]:
    """Backward-compatible wrapper kept for the existing sourcing upload route."""
    try:
        return await extract_document_metadata(file_bytes)
    except Exception as exc:
        logger.warning("Falling back to placeholder PDF extraction: {}", exc)
        return {
            "company_name": "Company from PDF",
            "business_summary": "Could not extract structured data from PDF",
            "estimated_revenue": None,
            "estimated_ebitda": None,
            "fiscal_year": None,
        }


async def _extract_text_from_pdf(file_bytes: bytes, *, max_pages: int = MAX_PDF_PAGES) -> str:
    """Extract text from the first pages of a PDF file."""
    try:
        text_chunks: list[str] = []
        page_count = 0
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text()
                if page_text:
                    text_chunks.append(page_text)

        full_text = "\n\n".join(text_chunks)
        logger.info(
            "Extracted {} characters from PDF across {} page(s)",
            len(full_text),
            min(page_count, max_pages),
        )
        return full_text
    except Exception as exc:
        logger.error("PDF text extraction failed: {}", exc)
        raise ValueError(f"Could not extract PDF text: {exc}") from exc


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_OPENAI_RETRYABLE),
)
async def _call_openai_extraction(client: AsyncOpenAI, settings, prompt: str):
    """Isolated OpenAI call so tenacity can retry ONLY the network round-trip
    (not the JSON parsing that follows) — 3 attempts, backoff 1-10s."""
    return await client.chat.completions.create(
        model=settings.openai_model or "gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise financial extraction assistant for PE document ingestion. "
                    "Always return valid JSON and never include markdown or extra commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=settings.openai_temperature,
        max_tokens=settings.openai_max_tokens,
    )


async def _extract_deal_info_with_llm(text: str) -> dict[str, Optional[str | float]]:
    """Use GPT-4o-mini to extract structured deal information from raw text."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API key not configured")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    # D25 (Tâche B.10) : l'audit B.4 a montré deux passages sur le MÊME PDF
    # donnant une marge d'EBITDA de 15 % puis de 0,015 % (facteur ~1000) — le
    # prompt précédent ("Convert all monetary values to millions") ne donnait
    # ni exemple chiffré ni consigne explicite sur l'ABSENCE d'EBITDA dans le
    # document. Ce renforcement (Étape 1.1) ajoute les deux, en gardant les
    # mêmes 4 clés de sortie (aucun changement de structure).
    prompt = (
        "Extract structured financial information from a private equity teaser or CIM. "
        "Return ONLY a JSON object with these exact keys: company_name, business_summary, "
        "estimated_revenue, estimated_ebitda, fiscal_year. company_name and business_summary must be "
        "strings. estimated_revenue and estimated_ebitda must be numbers or null. fiscal_year must be "
        "an integer (4-digit year, e.g. 2022) or null.\n\n"
        "UNITS — read carefully, this has caused real extraction errors before: "
        "estimated_revenue and estimated_ebitda MUST be expressed in MILLIONS OF EUROS, as plain "
        "decimal numbers. Convert whatever unit the document uses (K€, raw €, M€) to millions before "
        "returning it. Never return a raw euro amount without converting it.\n\n"
        "MISSING EBITDA — do not estimate or infer it: if the document does not state an EBITDA figure "
        "explicitly (a margin percentage alone, an industry benchmark, or your own assumption about "
        "typical margins for this sector do NOT count as a stated figure), return null for "
        "estimated_ebitda. Guessing a plausible-looking number is worse than returning null.\n\n"
        "FISCAL YEAR — the year that estimated_revenue/estimated_ebitda relate to (e.g. \"Chiffre "
        "d'affaires 2022\" → 2022, \"FY2023 results\" → 2023). If revenue and EBITDA are stated for "
        "DIFFERENT years, use the year that revenue relates to. If no year is clearly associated with "
        "these figures anywhere in the document, return null — never guess a year (e.g. never assume "
        "\"the current year\" or the document's publication date if it isn't explicitly the figures' "
        "fiscal year).\n\n"
        "EXAMPLES (illustrate the required FORMAT only — never reuse these numbers):\n"
        "- Document states \"Chiffre d'affaires 2022 : 61,1 M€\" and no EBITDA figure anywhere "
        "→ estimated_revenue: 61.1, estimated_ebitda: null, fiscal_year: 2022\n"
        "- Document states \"Revenue: €45,200,000\" and \"EBITDA: €6,800,000\" with no year mentioned "
        "anywhere → estimated_revenue: 45.2, estimated_ebitda: 6.8, fiscal_year: null\n"
        "- Document states \"CA : 12 800 K€\" and \"EBITDA margin: 15%\" (percentage only, no absolute "
        "EBITDA figure), dated FY2021 → estimated_revenue: 12.8, estimated_ebitda: null, fiscal_year: 2021\n\n"
        "If the company name is confidential, infer the project name when possible.\n\n"
        f"DOCUMENT TEXT:\n{text[:MAX_PROMPT_CHARS]}"
    )

    response = await _call_openai_extraction(client, settings, prompt)

    message = response.choices[0].message.content or "{}"
    raw_content = message.strip()
    logger.debug("LLM response: {}", raw_content[:200])

    if raw_content.startswith("```"):
        raw_content = raw_content.split("```", 2)[1]
        if raw_content.startswith("json"):
            raw_content = raw_content[4:]
        raw_content = raw_content.strip()

    extracted_data = json.loads(raw_content)
    result = {
        "company_name": str(extracted_data.get("company_name", "Unknown Company")).strip() or "Unknown Company",
        "business_summary": str(extracted_data.get("business_summary", "No description available")).strip() or "No description available",
        "estimated_revenue": _parse_float(extracted_data.get("estimated_revenue")),
        "estimated_ebitda": _parse_float(extracted_data.get("estimated_ebitda")),
        # D44 (Tâche Finalisation) : exercice de référence des montants
        # ci-dessus, pour renseigner `as_of` sur la provenance DOCUMENT côté
        # modale (au lieu de le laisser toujours nul) — jamais deviné si
        # absent du document (voir consigne FISCAL YEAR du prompt).
        "fiscal_year": _parse_fiscal_year(extracted_data.get("fiscal_year")),
    }
    logger.info("Successfully extracted document metadata for {}", result["company_name"])
    return result


def _parse_float(value: object) -> Optional[float]:
    """Safely parse a value to float, returning None if invalid."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_fiscal_year(value: object) -> Optional[int]:
    """Safely parse a fiscal year to a plausible 4-digit int, else None —
    never a guessed/default year (D44)."""
    if value is None:
        return None
    try:
        year = int(value)
    except (ValueError, TypeError):
        return None
    # Borne large mais pas infinie : un teaser PE ne cite pas de figures
    # antérieures à 1990, ni "au-delà" de l'année prochaine — un nombre hors
    # de cette plage est presque certainement une erreur d'extraction (ex.
    # le LLM renvoie une valeur monétaire dans le mauvais champ) plutôt
    # qu'un vrai exercice fiscal.
    from datetime import datetime
    if 1990 <= year <= datetime.now().year + 1:
        return year
    return None


# ============================================================
# D25 (Tâche B.10), Étape 1.2 — Validation serveur de cohérence
#
# Ne corrige JAMAIS silencieusement : lève un drapeau transmis à la modale
# de review, qui l'affiche à l'utilisateur. La correction reste humaine
# (Étape 1.3). Placé après l'extraction LLM, avant la réponse HTTP — le
# prompt renforcé (Étape 1.1) réduit la fréquence des aberrations, ce
# contrôle est le filet de sécurité qui les empêche d'atteindre la modale
# sans signalement si elles se produisent malgré tout.
# ============================================================

PLAUSIBLE_MARGIN_MIN = -0.20
PLAUSIBLE_MARGIN_MAX = 0.60
# Plancher "typique" — sert UNIQUEMENT à la détection de facteur d'échelle
# ci-dessous côté BAS, pas de seuil de rejet. Volontairement asymétrique :
# une marge élevée mais réelle (SaaS, licences à 50-55 %) est fréquente et
# ne doit pas être signalée comme du bruit ; en revanche une marge
# anormalement PROCHE DE ZÉRO malgré des bornes techniquement respectées
# (ex. 0,015 %, le cas réel observé en audit B.4) est exactement le
# symptôme d'une unité non convertie (trop de zéros après la virgule).
TYPICAL_MARGIN_MIN = 0.02
# Facteurs d'échelle usuels d'une erreur de conversion d'unité (K€↔€↔M€,
# ou une confusion pourcentage/décimal).
_UNIT_ERROR_FACTORS = (10, 100, 1_000, 10_000, 100_000, 1_000_000)


def _unit_scale_factor_low(margin: float) -> float | None:
    """Retourne le facteur qui ramènerait une marge anormalement basse dans
    la bande typique, s'il en existe un."""
    return next(
        (f for f in _UNIT_ERROR_FACTORS if margin * f >= TYPICAL_MARGIN_MIN
         and margin * f <= PLAUSIBLE_MARGIN_MAX),
        None,
    )


def _unit_scale_factor_high(margin: float) -> float | None:
    """Retourne le facteur qui ramènerait une marge hors bornes dures dans
    une plage plausible, s'il en existe un (ex. 150 % → 15 %)."""
    return next(
        (f for f in _UNIT_ERROR_FACTORS if PLAUSIBLE_MARGIN_MIN <= margin / f <= PLAUSIBLE_MARGIN_MAX),
        None,
    )


def validate_extraction_plausibility(
    revenue: Optional[float], ebitda: Optional[float]
) -> list[dict[str, str]]:
    """Contrôles de vraisemblance sur les valeurs extraites. Retourne une
    liste de drapeaux `{"field", "reason", "severity"}` — vide si rien à
    signaler. N'écrit rien, ne modifie aucune valeur."""
    flags: list[dict[str, str]] = []

    if revenue is not None and revenue <= 0:
        flags.append({
            "field": "estimated_revenue",
            "reason": "Revenue is zero or negative — likely an extraction error.",
            "severity": "warning",
        })

    if ebitda is not None and revenue is not None and revenue > 0:
        margin = ebitda / revenue
        hard_implausible = margin < PLAUSIBLE_MARGIN_MIN or margin > PLAUSIBLE_MARGIN_MAX
        suspiciously_low = 0 <= margin < TYPICAL_MARGIN_MIN

        unit_factor = None
        if hard_implausible:
            unit_factor = _unit_scale_factor_high(margin)
        elif suspiciously_low:
            unit_factor = _unit_scale_factor_low(margin)

        if unit_factor is not None:
            reason = (
                f"EBITDA margin ({margin * 100:.4f}%) is far from a typical range and matches "
                f"a ~{unit_factor}x scale error — the unit was probably not converted to "
                f"millions correctly for revenue or EBITDA."
            )
            flags.append({"field": "estimated_ebitda", "reason": reason, "severity": "warning"})
        elif hard_implausible:
            reason = (
                f"EBITDA margin ({margin * 100:.1f}%) is outside the plausible range "
                f"({PLAUSIBLE_MARGIN_MIN * 100:.0f}% to {PLAUSIBLE_MARGIN_MAX * 100:.0f}%) "
                f"for a corporate teaser."
            )
            flags.append({"field": "estimated_ebitda", "reason": reason, "severity": "warning"})
        # else: within hard bounds, not suspiciously close to zero, or no clean scale
        # factor explains it (e.g. a genuine 1.5% or 55% margin) — not flagged, a real
        # business can legitimately sit there; flagging it would be noise, not signal.

    return flags
