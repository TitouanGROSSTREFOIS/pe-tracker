"""
esef_connector.py — Connecteur ESEF/XBRL (filings.xbrl.org) pour le Comps
Engine, source réelle des états financiers des comparables cotés européens
(D20, Tâche B.7).

Aucune clé, aucun quota constaté. Deux appels par émetteur : l'index JSON:API
(`https://filings.xbrl.org/api/...`) pour localiser le dépôt le plus récent,
puis le rapport xBRL-JSON lui-même (`https://filings.xbrl.org/{chemin}.json`)
— gros fichiers (2-8 Mo par émetteur testé), aucune dépendance de parsing
XBRL ajoutée : le format xBRL-JSON se lit avec `json` (stdlib) seul.

⚠️ HÉTÉROGÉNÉITÉ DES TAXONOMIES (constatée empiriquement, Tâche B.7, Étape 4) :
les émetteurs IFRS n'ont PAS de concept "EBITDA" standard. Le concept
`ifrs-full:DepreciationAndAmortisationExpense` (D&A pur, propre à
reconstruire un EBITDA = résultat opérationnel + D&A) n'existe QUE chez
Bureau Veritas et Eurofins parmi les 6 émetteurs testés. Les 4 autres
(Alten, Assystem, SPIE, Intertek — partiellement) exposent une D&A mélangée
à des provisions dans une extension propriétaire (ex.
`spie:AdjustmentsForDepreciationAmortizationAndProvisions`), impossible à
isoler proprement — ce connecteur NE SUBSTITUE PAS une approximation dans ce
cas, il laisse le champ vide (voir `EMITTER_CONCEPT_MAPS` : `da_concepts`
absent ou vide → EBITDA non reconstruit pour cet émetteur, documenté dans
RAPPORT B.7).

Tâche B.8, Étape 1 : le tableau de flux de trésorerie a été inspecté pour
Alten et SPIE — leur poste de retraitement D&A y est TOUJOURS mélangé à des
provisions (`ALT:AdjustmentsForProvisionsAndAdjustments...`,
`spie:AdjustmentsForDepreciationAmortizationAndProvisions`), confirmant
l'ambiguïté déjà documentée en B.7 : `da_concepts` reste vide pour ces deux
émetteurs. En revanche, Assystem publie un indicateur alternatif de
performance balisé explicitement `assystem:EBITDA` — un EBITDA DÉCLARÉ par
l'émetteur (pas reconstruit), utilisé tel quel via `ebitda_direct_concepts`,
avec une note de provenance qui le distingue clairement d'un EBITDA
reconstruit par ce connecteur.

Chaque société a sa propre carte de concepts, vérifiée manuellement dans son
rapport xBRL-JSON — pas de détection générique automatique, qui risquerait
de sélectionner silencieusement un concept ambigu.
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger


XBRL_API_BASE = "https://filings.xbrl.org/api"
XBRL_FILES_BASE = "https://filings.xbrl.org"
REQUEST_TIMEOUT = 30.0


# ── Cartes de concepts par émetteur (vérifiées manuellement, Tâche B.7) ────
# `da_concepts` : liste de concepts à SOMMER pour reconstituer la D&A totale
# (plusieurs sous-composantes chez Intertek) — vide si aucun concept propre
# n'a été trouvé (voir avertissement de module).
EMITTER_CONCEPT_MAPS: dict[str, dict[str, Any]] = {
    "BVI.PA": {
        "lei": "969500TPU5T3HA5D1F11", "currency": "EUR",
        "revenue_concepts": ["ifrs-full:Revenue"],
        "operating_result_concepts": ["ifrs-full:ProfitLossFromOperatingActivities"],
        "da_concepts": ["ifrs-full:DepreciationAndAmortisationExpense"],
        "net_income_concepts": ["ifrs-full:ProfitLoss"],
        "current_borrowings_concepts": ["ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
        "noncurrent_borrowings_concepts": ["ifrs-full:LongtermBorrowings"],
        "cash_concepts": ["ifrs-full:CashAndCashEquivalents"],
    },
    "ERF.PA": {
        "lei": "529900JEHFM47DYY3S57", "currency": "EUR",
        "revenue_concepts": ["ifrs-full:Revenue"],
        "operating_result_concepts": ["ifrs-full:ProfitLossFromOperatingActivities"],
        "da_concepts": ["ifrs-full:DepreciationAndAmortisationExpense"],
        "net_income_concepts": ["ifrs-full:ProfitLoss"],
        "current_borrowings_concepts": ["ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
        "noncurrent_borrowings_concepts": ["ifrs-full:LongtermBorrowings"],
        "cash_concepts": ["ifrs-full:CashAndCashEquivalents"],
    },
    "ATE.PA": {  # Alten
        "lei": "969500Y7G9TY7Y24GN07", "currency": "EUR",
        "revenue_concepts": ["ifrs-full:RevenueFromContractsWithCustomers"],
        "operating_result_concepts": ["ifrs-full:ProfitLossFromOperatingActivities"],
        # Ambigu au compte de résultat ET au tableau de flux de trésorerie :
        # ALT:AdjustmentsForProvisionsAndAdjustmentsForDepreciationAndAmortisation...
        # (poste de retraitement du cash-flow) mélange toujours D&A et
        # provisions/pertes de valeur — non isolable. Reconfirmé Tâche B.8.
        # Pas d'EBITDA balisé en extension propriétaire chez Alten non plus.
        "da_concepts": [],
        "net_income_concepts": ["ifrs-full:ProfitLoss"],
        "current_borrowings_concepts": ["ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
        "noncurrent_borrowings_concepts": ["ifrs-full:LongtermBorrowings"],
        "cash_concepts": ["ifrs-full:CashAndCashEquivalents"],
    },
    "ASY.PA": {  # Assystem
        "lei": "9695008GTTDJGF00CT88", "currency": "EUR",
        "revenue_concepts": ["ifrs-full:RevenueFromContractsWithCustomers"],
        "operating_result_concepts": ["assystem:OperatingProfitBeforeNonrecurringItems"],
        "da_concepts": [],  # ambigu : "AdjustmentsForDepreciationAmortisationAndProvisionsForRecurringOperatingItemsNet" mélange D&A et provisions
        # Assystem est le seul des 6 émetteurs à publier un EBITDA balisé en
        # extension propriétaire (indicateur alternatif de performance déclaré,
        # pas reconstruit) — trouvé Tâche B.8, Étape 1.
        "ebitda_direct_concepts": ["assystem:EBITDA"],
        "net_income_concepts": ["ifrs-full:ProfitLoss"],
        "current_borrowings_concepts": ["ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
        "noncurrent_borrowings_concepts": ["ifrs-full:LongtermBorrowings"],
        "cash_concepts": ["ifrs-full:CashAndCashEquivalents"],
    },
    "SPIE.PA": {
        "lei": "969500TJNS5GSFWJ8X85", "currency": "EUR",
        "revenue_concepts": ["ifrs-full:RevenueFromContractsWithCustomers"],
        "operating_result_concepts": ["ifrs-full:ProfitLossFromOperatingActivities"],
        # Ambigu au compte de résultat ET au tableau de flux de trésorerie :
        # spie:AdjustmentsForDepreciationAmortizationAndProvisions mélange
        # toujours D&A et provisions — non isolable. Reconfirmé Tâche B.8.
        # Pas d'EBITDA balisé en extension propriétaire chez SPIE non plus
        # (seul spie:RecurringOperatingIncome existe, ce n'est pas un EBITDA).
        "da_concepts": [],
        "net_income_concepts": ["ifrs-full:ProfitLoss"],
        "current_borrowings_concepts": ["spie:CurrentInterestbearingLoansAndDebts"],
        "noncurrent_borrowings_concepts": ["spie:NoncurrentInterestbearingLoansAndDebts"],
        "cash_concepts": ["ifrs-full:CashAndCashEquivalents"],
    },
    "ITRK.L": {  # Intertek — régime britannique, confirmé couvert (Étape 4)
        "lei": "2138003GAT25WW1RN369", "currency": "GBP",
        "revenue_concepts": ["ifrs-full:Revenue"],
        "operating_result_concepts": ["ifrs-full:ProfitLossFromOperatingActivities"],
        # 3 sous-composantes distinctes chez Intertek, propres, à sommer :
        "da_concepts": [
            "ifrs-full:AdjustmentsForDepreciationExpense",
            "intertekgroupplc:AdjustmentsForAmortisationOfSoftware",
            "intertekgroupplc:AdjustmentsForAmortisationOfAcquisitionIntangibles",
        ],
        "net_income_concepts": ["ifrs-full:ProfitLoss"],
        "current_borrowings_concepts": ["ifrs-full:ShorttermBorrowings"],
        "noncurrent_borrowings_concepts": ["ifrs-full:LongtermBorrowings"],
        "cash_concepts": ["ifrs-full:CashAndCashEquivalents"],
    },
}


async def find_latest_filing(lei: str) -> dict[str, Any] | None:
    """Localise le dépôt ESEF le plus récent (par period_end) pour ce LEI."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{XBRL_API_BASE}/filings",
                params={
                    "filter": f'[{{"name":"entity.identifier","op":"eq","val":"{lei}"}}]',
                    "sort": "-period_end",
                    "page[size]": "1",
                },
                timeout=REQUEST_TIMEOUT,
            )
    except httpx.HTTPError as e:
        logger.warning("[ESEF] Erreur réseau find_latest_filing({}) : {}", lei, e)
        return None

    if resp.status_code != 200:
        logger.warning("[ESEF] find_latest_filing({}) : HTTP {}", lei, resp.status_code)
        return None

    data = resp.json().get("data", [])
    if not data:
        return None
    return data[0]["attributes"]


async def fetch_filing_facts(json_url: str) -> dict[str, Any] | None:
    """Télécharge le rapport xBRL-JSON complet (2-8 Mo typiquement)."""
    url = json_url if json_url.startswith("http") else f"{XBRL_FILES_BASE}{json_url}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
    except httpx.HTTPError as e:
        logger.warning("[ESEF] Erreur réseau fetch_filing_facts({}) : {}", url, e)
        return None

    if resp.status_code != 200:
        logger.warning("[ESEF] fetch_filing_facts({}) : HTTP {}", url, resp.status_code)
        return None

    return resp.json().get("facts", {})


def _latest_periods(facts: dict[str, Any]) -> tuple[str | None, str | None]:
    """Retourne (période de durée la plus récente, période instantanée la plus récente)."""
    durations, instants = set(), set()
    for v in facts.values():
        p = v.get("dimensions", {}).get("period", "")
        if "/" in p:
            durations.add(p)
        elif p:
            instants.add(p)
    return (sorted(durations)[-1] if durations else None, sorted(instants)[-1] if instants else None)


def _find_concept_value(
    facts: dict[str, Any], concepts: list[str], period: str | None
) -> tuple[float, str] | None:
    """Cherche le premier concept de la liste présent pour cette période, sur
    le fait de base (sans axe/membre dimensionnel — `len(dims) <= 4` exclut
    les ventilations par segment)."""
    for concept in concepts:
        for v in facts.values():
            dims = v.get("dimensions", {})
            if dims.get("concept") == concept and dims.get("period") == period and len(dims) <= 4:
                try:
                    return float(v["value"]), concept
                except (TypeError, ValueError):
                    continue
    return None


def extract_financials(facts: dict[str, Any], concept_map: dict[str, Any]) -> dict[str, Any]:
    """Extrait revenue / operating_result / da (reconstruit, somme si
    plusieurs concepts) / net_income / net_debt depuis les facts xBRL-JSON,
    en utilisant la carte de concepts vérifiée pour cet émetteur.

    Ne SUBSTITUE JAMAIS un concept manquant par une approximation — un champ
    absent de `concept_map` (liste vide) reste `None` dans le résultat, avec
    la raison documentée dans `notes`.
    """
    duration, instant = _latest_periods(facts)
    result: dict[str, Any] = {
        "period_duration": duration, "period_instant": instant,
        "concepts_used": {}, "notes": [],
    }

    def _get(field_key: str, target: str) -> float | None:
        concepts = concept_map.get(field_key) or []
        if not concepts:
            result["notes"].append(f"{target}: no unambiguous concept identified — left blank.")
            return None
        found = _find_concept_value(facts, concepts, duration)
        if not found:
            result["notes"].append(f"{target}: none of {concepts} found for period {duration}.")
            return None
        value, concept = found
        result["concepts_used"][target] = concept
        return value

    def _get_instant(field_key: str, target: str) -> float | None:
        concepts = concept_map.get(field_key) or []
        if not concepts:
            return None
        found = _find_concept_value(facts, concepts, instant)
        if not found:
            result["notes"].append(f"{target}: none of {concepts} found for period {instant}.")
            return None
        value, concept = found
        result["concepts_used"][target] = concept
        return value

    revenue = _get("revenue_concepts", "revenue")
    operating_result = _get("operating_result_concepts", "operating_result")

    da_concepts = concept_map.get("da_concepts") or []
    da_total = None
    if da_concepts:
        parts: list[float] = []
        used: list[str] = []
        for c in da_concepts:
            found = _find_concept_value(facts, [c], duration)
            if found:
                parts.append(found[0])
                used.append(found[1])
        if parts:
            da_total = sum(parts)
            result["concepts_used"]["da"] = used
        else:
            result["notes"].append(f"da: none of {da_concepts} found for period {duration}.")
    else:
        result["notes"].append("da: no unambiguous concept identified (mixed with provisions in this filing) — left blank.")

    net_income = _get("net_income_concepts", "net_income")
    current_borrow = _get_instant("current_borrowings_concepts", "current_borrowings")
    noncurrent_borrow = _get_instant("noncurrent_borrowings_concepts", "noncurrent_borrowings")
    cash = _get_instant("cash_concepts", "cash")

    gross_debt = None
    if current_borrow is not None or noncurrent_borrow is not None:
        gross_debt = (current_borrow or 0) + (noncurrent_borrow or 0)

    net_debt = None
    if gross_debt is not None:
        if cash is not None:
            net_debt = gross_debt - cash
        else:
            result["notes"].append("net_debt: borrowings found but no cash figure — left blank.")

    # EBITDA : priorité à un indicateur DÉCLARÉ par l'émetteur (extension
    # propriétaire explicitement nommée "EBITDA") sur une reconstruction —
    # c'est un fait rapporté, pas une hypothèse de calcul.
    ebitda_direct_concepts = concept_map.get("ebitda_direct_concepts") or []
    ebitda_direct = None
    if ebitda_direct_concepts:
        found = _find_concept_value(facts, ebitda_direct_concepts, duration)
        if found:
            ebitda_direct = found[0]
            result["concepts_used"]["ebitda_direct"] = found[1]

    ebitda_reconstructed = None
    if operating_result is not None and da_total is not None:
        ebitda_reconstructed = operating_result + da_total

    if ebitda_direct is not None:
        ebitda_final, ebitda_source = ebitda_direct, "reported"
    elif ebitda_reconstructed is not None:
        ebitda_final, ebitda_source = ebitda_reconstructed, "reconstructed"
    else:
        ebitda_final, ebitda_source = None, None

    result.update(
        revenue=revenue,
        operating_result=operating_result,
        da=da_total,
        ebitda=ebitda_final,
        ebitda_source=ebitda_source,  # "reported" | "reconstructed" | None
        net_income=net_income,
        gross_debt=gross_debt,
        cash=cash,
        net_debt=net_debt,
    )
    return result
