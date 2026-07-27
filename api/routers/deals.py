"""
Deals Router — /deals endpoints

Endpoints:
  POST   /deals            Créer un deal
  GET    /deals            Lister / filtrer les deals
  GET    /deals/stats      Statistiques agrégées
  GET    /deals/{id}       Détail d'un deal
  PATCH  /deals/{id}       Mettre à jour un deal
  DELETE /deals/{id}       Supprimer un deal
"""
from __future__ import annotations
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from api.config import get_settings
from api.database import get_db
from api.services.deals_service import (
    create_deal,
    get_deal,
    list_deals,
    update_deal,
    delete_deal,
    deal_stats,
    SourcedTargetAlreadyLinkedError,
)
from api.services.deal_activity_service import create_activity, list_activities
from api.services import lbo_scenario_service
from api.services.ma_engine.docx_generator import generate_memo_docx
from api.services.ma_engine.ic_deck_generator import generate_ic_deck
from api.services.ma_engine.excel_generator import generate_lbo_model_excel
from api.services.ma_engine.ic_context import build_ic_context, MEMO_SECTIONS
from api.services.comps_service import get_comp_table
from api.services.ma_engine.sector_calibration import TIC_COMP_SET_ID
from api.schemas.deals import DealCreate, DealOut, DealFilter, DealListResponse, DealMemoResponse
from api.schemas.deal_activity import DealActivityOut, DealNoteCreate, DealActivityListResponse

router = APIRouter(prefix="/deals", tags=["M&A / Deal Database"])

# Tâche B.11, Étape 3.3 : retry uniquement sur les erreurs transitoires
# (réseau, timeout, rate limit, 5xx) — jamais sur une clé invalide ou une
# requête malformée. Aucune logique de retry n'existait sur ce chemin avant
# cette tâche — voir document_parser.py pour le même constat côté spreading.
_OPENAI_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_OPENAI_RETRYABLE),
)
async def _call_openai_memo(client: AsyncOpenAI, settings, prompt: str):
    """Isolated OpenAI call so tenacity can retry ONLY the network round-trip."""
    return await client.chat.completions.create(
        model=settings.openai_model or "gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a private equity investment committee memo writer. "
                    "Write the ENTIRE memo in English, regardless of the language of the input "
                    "data (deal descriptions may be in French or another language — always "
                    "respond in English). Return only polished Markdown. Use clear section "
                    "headings and no preamble."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=_MEMO_MAX_TOKENS,
    )


# Le mémo 9 sections (structure IC professionnelle) est nettement plus long
# que les 4 sections précédentes — un budget dédié, indépendant de
# `settings.openai_max_tokens` (partagé avec l'extraction de documents,
# hors périmètre de cette tâche : on ne veut pas changer son comportement
# en élevant un réglage global).
_MEMO_MAX_TOKENS = 3200


@router.post("", response_model=DealOut)
async def create(body: DealCreate, db: AsyncSession = Depends(get_db)):
    """Créer un deal M&A."""
    try:
        deal = await create_deal(body, db)
    except SourcedTargetAlreadyLinkedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This sourced target is already linked to deal #{exc.deal_id}. "
                   f"Use that existing deal instead of creating a duplicate.",
        )
    return deal


@router.get("", response_model=DealListResponse)
async def list_all(
    sector: str | None = None,
    deal_type: str | None = None,
    status: str | None = None,
    country: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: str = "announced_date",
    sort_desc: bool = True,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Lister / filtrer les deals M&A."""
    f = DealFilter(
        sector=sector,
        deal_type=deal_type,
        status=status,
        country=country,
        min_value=min_value,
        max_value=max_value,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_desc=sort_desc,
        limit=limit,
        offset=offset,
    )
    deals, total = await list_deals(f, db)
    return DealListResponse(total=total, offset=offset, limit=limit, deals=deals)


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    """Statistiques agrégées du deal database."""
    return await deal_stats(db)


@router.get("/{deal_id}", response_model=DealOut)
async def get_one(deal_id: int, db: AsyncSession = Depends(get_db)):
    """Détail d'un deal."""
    deal = await get_deal(deal_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.get("/{deal_id}/activities", response_model=DealActivityListResponse)
async def get_deal_activities(deal_id: int, db: AsyncSession = Depends(get_db)):
    """Return the chronological activity trail for a deal (newest first)."""
    deal = await get_deal(deal_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    activities = await list_activities(db, deal_id)
    return DealActivityListResponse(
        deal_id=deal_id,
        total=len(activities),
        activities=activities,
    )


@router.post("/{deal_id}/notes", response_model=DealActivityOut, status_code=201)
async def add_note(deal_id: int, body: DealNoteCreate, db: AsyncSession = Depends(get_db)):
    """Add a manual note to the deal activity log."""
    deal = await get_deal(deal_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    activity = await create_activity(
        db,
        deal_id=deal_id,
        action_type="user_note",
        content=body.content.strip(),
    )
    return activity


@router.patch("/{deal_id}", response_model=DealOut)
async def update(deal_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    """Mettre à jour un deal (partial update)."""
    current = await get_deal(deal_id, db)
    if not current:
        raise HTTPException(status_code=404, detail="Deal not found")

    previous_status = current.status
    deal = await update_deal(deal_id, body, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    new_status = body.get("status")
    if new_status and new_status != previous_status:
        await create_activity(
            db,
            deal_id=deal_id,
            action_type="system_event",
            content=f"Deal status changed from {previous_status} to {new_status}",
        )
    return deal


@router.delete("/{deal_id}")
async def delete(deal_id: int, db: AsyncSession = Depends(get_db)):
    """Supprimer un deal."""
    ok = await delete_deal(deal_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"status": "deleted", "id": deal_id}


@router.post("/{deal_id}/generate-memo", response_model=DealMemoResponse)
async def generate_memo(deal_id: int, db: AsyncSession = Depends(get_db)):
    """Generate an IC Memo in Markdown and persist it on the deal."""
    deal = await get_deal(deal_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    reference_scenario = await lbo_scenario_service.get_reference_scenario(db, deal_id)
    downside_scenario = await lbo_scenario_service.get_downside_scenario(db, deal_id)
    comps_table = await get_comp_table(TIC_COMP_SET_ID, db)
    context = build_ic_context(deal, reference_scenario, comps_table, downside_scenario)

    headings_block = "\n".join(f"## {h}" for h in MEMO_SECTIONS)

    # D17 (Tâche B.5) : mémo systématiquement en anglais — conservé tel
    # quel (rédiger le prompt utilisateur lui-même en anglais, en plus de la
    # directive système, supprime l'ambiguïté au lieu de se reposer sur une
    # seule instruction).
    #
    # Format 9 sections (Tâche IC professionnel) : le LLM ne calcule et
    # n'invente RIEN — chaque chiffre du contexte est déjà qualifié de sa
    # provenance (D18) ou calculé par le moteur LBO réel (self_check,
    # sensitivity) ; le modèle ne fait que le CITER tel quel et l'entourer
    # d'analyse (thèse, risques, recommandation).
    prompt = (
        "Write a professional Investment Committee Memo in Markdown from the DEAL_DATA below. "
        "The document must contain EXACTLY these 9 sections, as H2 headings, in this exact order "
        "and with this exact wording:\n"
        f"{headings_block}\n\n"
        "Ground rules — read carefully, these are hard constraints, not style preferences:\n\n"
        "1. NEVER invent, estimate, or calculate a number yourself. Every figure you may cite is "
        "already present in DEAL_DATA, most of it already qualified with its provenance in "
        "parentheses (e.g. 'estimated — sector EBITDA margin assumption', 'derived: 8.2x listed "
        "comparables median ...'). When you cite such a figure anywhere in the memo, you MUST "
        "reproduce its qualification alongside the number — never state it as a bare fact. If you "
        "need a number that is not in DEAL_DATA, do not estimate it — say it is not available.\n\n"
        "2. Wherever a field's value is exactly the string "
        f"\"{context['dd_marker']}\" (the standard due-diligence marker), reproduce that exact "
        "marker verbatim at that point in the memo instead of writing around it or guessing. Do "
        "not paraphrase it.\n\n"
        "2b. Never contradict yourself within a section: if 'reference_lbo_scenario' or "
        "'sensitivity' is NOT null, you have already been given real figures for it — do not "
        "ALSO write a sentence claiming no scenario was modelled, no data is available, or "
        "something is 'marked for due diligence' for that same section. The 'if null, say X' "
        "instructions below apply ONLY when the field is actually null — check the value before "
        "writing the fallback sentence, never write both the real figures and the fallback "
        "sentence together.\n\n"
        "3. Section I (Executive Summary): 3-5 sentences — what the target does, the strategic "
        "rationale for the acquirer, the headline terms (entry multiple, leverage) and projected "
        "returns (IRR/MOIC) FROM 'reference_lbo_scenario' if present, the top 3 risks in one line "
        "each, and a one-line recommendation using the EXACT SAME label as Section IX (see rule "
        "11 below — never a different or softer phrase here than what Section IX ends up using). "
        "If 'reference_lbo_scenario' is null, do not mention IRR, MOIC or an entry multiple "
        "anywhere in the memo — no scenario has been saved for this deal.\n\n"
        "4. Section II (Company Overview): use 'company_overview' — description, sector, industry, "
        "country, and OSINT signals (growth_signals/red_flags/competitors) if present. "
        "'management_team' and 'headcount' must show the due-diligence marker as given — the tool "
        "has no such data.\n\n"
        "5. Section III (Industry & Market): write qualitative narrative about the sector and the "
        "consolidation/buy-and-build thesis, grounded in 'comps_summary' (real listed comparables) "
        "if present. Do NOT invent market-size figures (TAM/SAM/CAGR) — if you have no sourced "
        "market-size data, say so explicitly and keep the discussion qualitative. IMPORTANT — if "
        "'comps_summary.size_gap_note' is present, you MUST include it (verbatim or close "
        "paraphrase): the comparables are listed mega/mid-caps several orders of magnitude larger "
        "than this target, and the median EV/EBITDA is a market anchor, NEVER a multiple directly "
        "applicable to this target as-is. If 'comps_summary.smallest_subset_median_ev_ebitda' is "
        "present, mention it alongside the full-sample median as a second, smaller-sample reference "
        "point (labelled as such, not a better estimate). If 'comps_summary.adjacent_sector_flags' "
        "is present, name those specific comparables and state plainly that they are adjacent to, "
        "not squarely within, the target's core sector (e.g. oilfield services vs testing/"
        "inspection/certification) — do not present the CompSet as if every member is a pure-play "
        "peer.\n\n"
        "6. Section IV (Financial Analysis): present 'financials' (revenue, EBITDA, EV, margin, "
        "multiples) with their qualifications. 'quality_of_earnings', 'working_capital' and "
        "'capex_detail' must show the due-diligence marker. If "
        "'reference_lbo_scenario.valuation_reconciliation_note' is present, this section's "
        "Enterprise Value is NOT the only one in this memo — Section VI cites a different, "
        "equally real Enterprise Value from the LBO scenario's own retained multiple. Do not "
        "present the two as if they were the same number with no explanation; a single bridging "
        "sentence here (or in Section VI, but at least once) using that note's content is "
        "required — never two orphaned EV figures with nothing connecting them.\n\n"
        "7. Section V (Investment Thesis): your own analytical reasoning — investment pillars, "
        "value-creation levers (organic growth, margin improvement, M&A build-up, multiple "
        "expansion), and 100-day priorities. This is legitimate analysis you may write, not a "
        "data point — but do not attach any number to it that isn't already in DEAL_DATA.\n\n"
        "8. Section VI (Deal Terms & Structure): use 'reference_lbo_scenario' and "
        "'sources_and_uses' — entry EV, entry multiple (qualified), debt/equity split, leverage, "
        "tranches if any. 'sources_and_uses.tranches' being null just means a simple single-tranche "
        "debt structure (one senior debt block, still shown as 'entry_debt') — it does NOT mean no "
        "scenario exists; never write 'no LBO scenario has been modelled' when 'reference_lbo_scenario' "
        "is actually populated (as it is whenever you can see an entry multiple/IRR/MOIC above). "
        "'sources_and_uses.entry_equity' is the sponsor's total cash-in, sized to cover the Enterprise "
        "Value AND real transaction costs — 'entry_transaction_fees', 'entry_financing_fees' and "
        "'entry_min_cash' are genuine, separate Uses (advisory/legal/DD fees, debt arrangement fees, "
        "and a minimum operating cash balance funded at closing), not rounding noise; never describe "
        "the equity check as if it only funded the Enterprise Value. If "
        "'reference_lbo_scenario.ebitda_reconciliation_note' is present, include it — it explains a "
        "real, legitimate difference between the EBITDA figure used here and the one in Section IV; "
        "do not omit it and do not try to make the two numbers agree. Likewise, if "
        "'reference_lbo_scenario.valuation_reconciliation_note' is present, include it too — it "
        "bridges this section's entry Enterprise Value with the different one cited in Section IV "
        "(see rule 6 above); never show both EV figures across the memo without this bridge. Only "
        "if 'reference_lbo_scenario' is ACTUALLY null, state clearly that no LBO scenario has been "
        "modelled and mark this section "
        "for due diligence. "
        "IMPORTANT — check the boolean 'reference_lbo_scenario.sizing_guidance.is_indicative' for THIS "
        "deal before writing anything about sizing: "
        "if it is literally true, open this section with the exact caveat given in "
        "'reference_lbo_scenario.sizing_guidance.note' (reproduce it verbatim or paraphrase closely — "
        "never soften or omit it) and explicitly point the reader to the Buy & Build module as the "
        "realistic structure at this size — a standalone mezzanine LBO at THIS deal's revenue size is "
        "not financeable, and the memo must say so in plain language, not bury it in a footnote. "
        "If 'is_indicative' is literally false, this deal is ABOVE the standalone-financeability "
        "threshold — do NOT mention indicative sizing, bolt-on structuring, or non-financeability "
        "anywhere in this section; treat the LBO structure as a normal standalone deal with no size "
        "caveat at all. Never guess this from the revenue number yourself — read the boolean.\n\n"
        "9. Section VII (Returns Analysis): cite IRR/MOIC/holding period from "
        "'reference_lbo_scenario' as the BASE CASE. If 'downside_scenario' is present, you MUST also "
        "present it side by side — its own IRR/MOIC, the entry revenue haircut and exit multiple "
        "degradation vs the base case (both given directly in 'downside_scenario') — an IC memo with "
        "a single scenario is not acceptable; never present the base case alone when a downside exists. "
        "If 'downside_scenario' is null, state that only a base case has been modelled. If "
        "'sensitivity' is present, describe it in prose: the exit multiple × leverage grid it covers "
        "(ranges only — the full grid is rendered as a table elsewhere, do not reproduce every cell) "
        "and how returns move across the range — this sensitivity table is a complement to the "
        "base/downside comparison, not a replacement for it. State its 'method' line so the reader "
        "knows it was recalculated by the same LBO engine, not a new formula. If 'sensitivity' is "
        "null, say a sensitivity analysis could not be produced (no saved scenario) and mark it for "
        "due diligence.\n\n"
        "10. Section VIII (Risk Factors): select and prioritize (roughly by severity × probability) "
        "FROM 'risk_candidates' — a curated list of real, sector-relevant risks for this target's "
        "actual business (key-person dependency, regulatory/accreditation dependency, decennial "
        "liability, customer concentration, order-book visibility, etc., each with severity/"
        "probability/mitigants already given). 'risk_candidates' is ordered SECTOR-SPECIFIC risks "
        "first, generic small-cap risks after — you MUST include at least one or two of the "
        "sector-specific risks near the top of the list (the ones tied to this target's actual "
        "activity, e.g. decennial liability for a structural/construction target, accreditation "
        "dependency for a testing/inspection target), not just the generic ones; a memo that only "
        "cites generic risks when sector-specific ones were available is not acceptable. Do NOT "
        "invent risks outside this list, and do NOT pad the section with a generic 'model risk' or "
        "'financial model integrity' item — that is not a commercial/investment risk and has no "
        "place in Section VIII; model correctness is not this memo's subject. Pick the ones genuinely "
        "relevant to THIS target (not every candidate — judge by the deal's actual description/"
        "sector), state the given mitigants, and separately "
        "you MUST also include, honestly and without minimizing: any 'self_check' item with "
        "passed=false (explain it in plain English) and the EBITDA-margin caveat already embedded in "
        "the comparables' provenance text when 'comps_summary' informed the calibration. Do not "
        "downplay these — an IC memo that hides a known model limitation is worse than one that "
        "states it.\n\n"
        "11. Section IX (Recommendation): a clear call, consistent with the returns cited in "
        "Section VII and the risks in Section VIII. Your options are Pass, or a positive "
        "recommendation. If positive, you MUST use the exact label given in "
        "'recommendation_guidance.required_positive_label' — reproduce it verbatim as the "
        "opening of this section, do not paraphrase or soften it, and do not write 'Proceed "
        "with the acquisition' unless that is literally the label given (see "
        "'recommendation_guidance.rule' for why). This is not a style choice: it reflects "
        "whether the EBITDA driving this entire analysis is confirmed by real financial "
        "statements or still an estimate — never let a positive tone override this. Add "
        "conditions or next steps after the label if relevant (e.g. do not recommend "
        "proceeding unconditionally if a self_check item failed or a top risk is "
        "unmitigated).\n\n"
        "Be concise, analytical, and written for an investment committee audience. Present both "
        "the bull case and the bear case where relevant (Sections I, V, VIII, IX) — never a "
        "one-sided pitch.\n\n"
        f"DEAL_DATA:\n{json.dumps(context, default=str, ensure_ascii=False, indent=2)}"
    )

    try:
        response = await _call_openai_memo(client, settings, prompt)
        memo = (response.choices[0].message.content or "").strip()
        if not memo:
            raise HTTPException(status_code=502, detail="Empty memo generated by OpenAI")

        deal.ic_memo = memo
        await create_activity(
            db,
            deal_id=deal.id,
            action_type="system_event",
            content="IC Memo generated by GPT-4o-mini",
        )
        # D31 (Tâche Review Produit — Partie A) : un mémo généré fait
        # avancer le deal en revue de comité — bascule automatique une seule
        # fois (ne réécrase jamais un statut avancé manuellement au-delà de
        # Screening, ex. si l'utilisateur a déjà classé le deal "Approved").
        if deal.status == "Screening":
            deal.status = "IC Review"
            await create_activity(
                db, deal_id=deal.id, action_type="system_event",
                content="Deal status changed from Screening to IC Review",
            )
        await db.commit()
        await db.refresh(deal)
        return DealMemoResponse(deal_id=deal.id, ic_memo=memo)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate IC memo for deal {}", deal_id)
        raise HTTPException(status_code=500, detail=f"IC Memo generation failed: {exc}") from exc


@router.get(
    "/{deal_id}/export-memo-docx",
    summary="Exporter le mémo IC en Word (.docx)",
    response_class=StreamingResponse,
)
async def export_memo_docx(deal_id: int, db: AsyncSession = Depends(get_db)):
    """Génère un .docx propre et mis en forme à partir du mémo IC déjà
    généré (D28) : titre, en-tête, tableau des chiffres clés avec
    provenance, puis les sections du mémo. Le mémo doit avoir été généré
    au préalable (`POST /{deal_id}/generate-memo`) — ne régénère rien."""
    deal = await get_deal(deal_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if not deal.ic_memo:
        raise HTTPException(
            status_code=409,
            detail="No IC memo generated yet for this deal — generate it first.",
        )

    reference_scenario = await lbo_scenario_service.get_reference_scenario(db, deal_id)
    downside_scenario = await lbo_scenario_service.get_downside_scenario(db, deal_id)
    comps_table = await get_comp_table(TIC_COMP_SET_ID, db)
    ic_context = build_ic_context(deal, reference_scenario, comps_table, downside_scenario)
    buf = generate_memo_docx(deal, reference_scenario, ic_context)

    safe_name = re.sub(r"[^A-Za-z0-9-_]+", "_", deal.target_name or "Deal").strip("_") or "Deal"
    filename = f"Memo_IC_{safe_name}.docx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{deal_id}/export-deck-pptx",
    summary="Exporter le deck de comité d'investissement (.pptx)",
    response_class=StreamingResponse,
)
async def export_deck_pptx(deal_id: int, db: AsyncSession = Depends(get_db)):
    """Génère le deck IC complet (D30) : couverture, profil société,
    chiffres clés, thèse, comparables cotés, chaîne de calibrage, structure
    LBO par tranche, synthèse + risques (extraits du mémo déjà généré).

    Les comparables et le scénario LBO sont optionnels — le deck s'adapte
    (sections signalées comme non disponibles) plutôt que d'échouer si l'un
    des deux manque."""
    deal = await get_deal(deal_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    reference_scenario = await lbo_scenario_service.get_reference_scenario(db, deal_id)
    downside_scenario = await lbo_scenario_service.get_downside_scenario(db, deal_id)
    comps_table = await get_comp_table(TIC_COMP_SET_ID, db)
    ic_context = build_ic_context(deal, reference_scenario, comps_table, downside_scenario)

    buf = generate_ic_deck(deal, comps_table, reference_scenario, ic_context)

    safe_name = re.sub(r"[^A-Za-z0-9-_]+", "_", deal.target_name or "Deal").strip("_") or "Deal"
    filename = f"Deck_IC_{safe_name}.pptx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{deal_id}/export-lbo-excel",
    summary="Exporter le modèle LBO du deal en Excel (.xlsx, standard professionnel 8 onglets)",
    response_class=StreamingResponse,
)
async def export_lbo_excel(deal_id: int, db: AsyncSession = Depends(get_db)):
    """Génère le classeur Excel du scénario LBO de référence du deal (D23) —
    même générateur formulaïque que le calculateur manuel
    (`POST /lbo/export-excel`), enrichi d'un en-tête Cover (cible/secteur/
    provenance réel vs estimé) puisqu'ici, contrairement au calculateur, un
    deal réel existe. Ne recalcule rien : lit le `result_json` déjà figé du
    scénario sauvegardé, tel que l'affichent le mémo et le deck IC."""
    deal = await get_deal(deal_id, db)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    reference_scenario = await lbo_scenario_service.get_reference_scenario(db, deal_id)
    if reference_scenario is None:
        raise HTTPException(
            status_code=409,
            detail="No LBO scenario saved for this deal — generate/save one first.",
        )
    downside_scenario = await lbo_scenario_service.get_downside_scenario(db, deal_id)

    buf = generate_lbo_model_excel(
        reference_scenario.result_json, deal=deal, scenario_label=reference_scenario.label,
        sizing_note=(reference_scenario.assumptions_json or {}).get("sizing_note"),
        downside_result=downside_scenario.result_json if downside_scenario else None,
        downside_label=downside_scenario.label if downside_scenario else None,
    )

    safe_name = re.sub(r"[^A-Za-z0-9-_]+", "_", deal.target_name or "Deal").strip("_") or "Deal"
    filename = f"LBO_Model_{safe_name}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
