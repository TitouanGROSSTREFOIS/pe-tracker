"""
Legal & Corporate Watch Service — "Le Greffier Automatique"

Capte les signaux faibles de M&A avant le marché en intégrant
l'historique légal des entreprises via l'API Pappers.

Architecture identique au Sprint 2 (alt_data_service.py) :
  - Mode LIVE si PAPPERS_API_KEY configurée et entreprise trouvée.
  - Mode MOCK avec fallback réaliste sinon.
  - Chaque événement est annoté d'un **Signal M&A** :
      • Bullish  → changement structurel (statuts, capital, dirigeants)
      • Neutral  → événement administratif courant
      • Red Flag → procédure collective, radiation, alerte

Conçu pour ne *jamais crasher* : chaque appel externe est wrappé
en try/except avec fallback immédiat.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger

from api.config import get_settings


# ============================================================
#  Signal M&A tagging rules
# ============================================================

_SIGNAL_RULES: dict[str, dict[str, str]] = {
    # -- Bullish signals (potential M&A moves) --
    "Modification des statuts": {
        "signal": "Bullish",
        "reason": "Restructuration potentielle pré-cession",
    },
    "Augmentation de capital": {
        "signal": "Bullish",
        "reason": "Injection de capital — refinancement ou entrée investisseur",
    },
    "Changement de Président": {
        "signal": "Bullish",
        "reason": "Transition de gouvernance — signal de transmission",
    },
    "Changement de Directeur Général": {
        "signal": "Bullish",
        "reason": "Transition de management — possible carve-out",
    },
    "Nomination de commissaire aux apports": {
        "signal": "Bullish",
        "reason": "Opération d'apport en nature — rapprochement probable",
    },
    "Transfert de siège social": {
        "signal": "Bullish",
        "reason": "Réorganisation géographique — consolidation potentielle",
    },
    "Transformation de société": {
        "signal": "Bullish",
        "reason": "Changement de forme juridique — structuration pré-deal",
    },
    "Cession de parts sociales": {
        "signal": "Bullish",
        "reason": "Mouvement d'actionnariat — signal fort de M&A",
    },
    # -- Neutral signals --
    "Dépôt des comptes annuels": {
        "signal": "Neutral",
        "reason": "Obligation légale annuelle",
    },
    "Renouvellement de mandat": {
        "signal": "Neutral",
        "reason": "Continuité de gouvernance",
    },
    "Modification de l'objet social": {
        "signal": "Neutral",
        "reason": "Ajustement de l'activité déclarée",
    },
    "Approbation des comptes": {
        "signal": "Neutral",
        "reason": "Obligation légale annuelle",
    },
    # -- Red flags --
    "Procédure de sauvegarde": {
        "signal": "Red Flag",
        "reason": "Difficultés financières avérées",
    },
    "Redressement judiciaire": {
        "signal": "Red Flag",
        "reason": "Cessation de paiements — opportunité distressed",
    },
    "Liquidation judiciaire": {
        "signal": "Red Flag",
        "reason": "Fin d'activité — acquisition d'actifs possible",
    },
    "Radiation du RCS": {
        "signal": "Red Flag",
        "reason": "Société radiée — vigilance maximale",
    },
    "Inscription de privilège": {
        "signal": "Red Flag",
        "reason": "Créance fiscale ou sociale impayée",
    },
}


def _tag_event(event_label: str) -> dict[str, str]:
    """Return the M&A signal tag for a given event label.

    Falls back to Neutral if the label isn't in our rules.
    """
    for keyword, info in _SIGNAL_RULES.items():
        if keyword.lower() in event_label.lower():
            return info
    return {"signal": "Neutral", "reason": "Événement non classifié"}


# ============================================================
#  1.  Pappers API — Live corporate events
# ============================================================

async def _fetch_pappers(company_name: str) -> dict[str, Any]:
    """Call Pappers API to search the company and retrieve recent events.

    Pappers API docs: https://www.pappers.fr/api/documentation
    Endpoints used:
      - GET /recherche-entreprises?q={company_name}  → find SIREN
      - GET /entreprise?siren={siren}&extrait_rcs=true  → get legal publications
    """
    settings = get_settings()
    key = settings.pappers_api_key

    if not key:
        logger.info("[LEGAL-WATCH] No PAPPERS_API_KEY — using mock events for '{}'", company_name)
        return _mock_corporate_events(company_name)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            # Step 1 — Search company by name
            search_url = "https://api.pappers.fr/v2/recherche"
            search_resp = await client.get(
                search_url,
                params={"api_token": key, "q": company_name, "par_page": 1},
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()

            resultats = search_data.get("resultats", [])
            if not resultats:
                logger.info("[LEGAL-WATCH] Pappers found no match for '{}' — using mock", company_name)
                return _mock_corporate_events(company_name)

            entreprise = resultats[0]
            siren = entreprise.get("siren", "")
            denomination = entreprise.get("nom_entreprise", company_name)

            if not siren:
                logger.warning("[LEGAL-WATCH] No SIREN returned for '{}' — using mock", company_name)
                return _mock_corporate_events(company_name)

            # Step 2 — Get company details with RCS publications
            detail_url = "https://api.pappers.fr/v2/entreprise"
            detail_resp = await client.get(
                detail_url,
                params={"api_token": key, "siren": siren},
            )
            detail_resp.raise_for_status()
            detail_data = detail_resp.json()

            # Extract legal publications (BODACC / RCS)
            publications = detail_data.get("publications_bodacc", [])
            depot_actes = detail_data.get("depot_actes", [])

            events: list[dict[str, Any]] = []

            # Parse BODACC publications
            for pub in publications[:10]:
                label = pub.get("type", "Publication BODACC")
                date_str = pub.get("date", "")
                description = pub.get("contenu", pub.get("description", ""))
                tag = _tag_event(label)
                events.append({
                    "date": date_str,
                    "label": label,
                    "description": str(description)[:300] if description else "",
                    "source": "BODACC",
                    "signal": tag["signal"],
                    "signal_reason": tag["reason"],
                })

            # Parse depot d'actes (filed documents)
            for acte in depot_actes[:10]:
                label = acte.get("type", "Dépôt d'acte")
                date_str = acte.get("date_depot", acte.get("date", ""))
                decision = acte.get("decision", "")
                tag = _tag_event(label + " " + decision)
                events.append({
                    "date": date_str,
                    "label": label,
                    "description": decision[:300] if decision else "",
                    "source": "Greffe",
                    "signal": tag["signal"],
                    "signal_reason": tag["reason"],
                })

            # Sort by date descending, cap at 15 most recent
            events.sort(key=lambda e: e.get("date", ""), reverse=True)
            events = events[:15]

            if not events:
                logger.info("[LEGAL-WATCH] Pappers returned no events for '{}' — using mock", company_name)
                return _mock_corporate_events(company_name)

            logger.info(
                "[LEGAL-WATCH] Pappers returned {} events for '{}' (SIREN: {})",
                len(events), denomination, siren,
            )
            return {
                "company_name": denomination,
                "siren": siren,
                "events": events,
                "source": "pappers",
                "generated_at": datetime.now().isoformat(),
            }

    except Exception as exc:
        logger.warning("[LEGAL-WATCH] Pappers API error for '{}': {} — using mock", company_name, exc)
        return _mock_corporate_events(company_name)


# ============================================================
#  2.  Mock Corporate Events — realistic fallback
# ============================================================

# Pool of realistic events with built-in signal tags
_MOCK_EVENT_POOL: list[dict[str, str]] = [
    {
        "label": "Dépôt des comptes annuels",
        "description": "Dépôt au greffe des comptes annuels de l'exercice clos le 31/12/2025. Chiffre d'affaires supérieur aux seuils de publication simplifiée.",
        "source": "Greffe",
    },
    {
        "label": "Modification des statuts",
        "description": "Modification de l'article 7 des statuts relatif au capital social. Augmentation de la clause d'agrément pour les cessions de parts.",
        "source": "Greffe",
    },
    {
        "label": "Changement de Président",
        "description": "Nomination d'un nouveau Président en remplacement du fondateur. Prise d'effet immédiate par décision de l'assemblée générale extraordinaire.",
        "source": "BODACC",
    },
    {
        "label": "Approbation des comptes",
        "description": "Assemblée générale ordinaire approuvant les comptes de l'exercice 2025. Affectation du résultat en report à nouveau.",
        "source": "Greffe",
    },
    {
        "label": "Augmentation de capital",
        "description": "Augmentation de capital social de 500 000 € à 2 000 000 € par émission de parts nouvelles. Souscription réservée à un investisseur qualifié.",
        "source": "BODACC",
    },
    {
        "label": "Transfert de siège social",
        "description": "Transfert du siège social du 15 rue de la Paix, 75002 Paris au 42 avenue des Champs-Élysées, 75008 Paris.",
        "source": "BODACC",
    },
    {
        "label": "Cession de parts sociales",
        "description": "Cession de 35% des parts sociales par le fondateur. Agrément donné par l'assemblée des associés à l'unanimité.",
        "source": "Greffe",
    },
    {
        "label": "Renouvellement de mandat",
        "description": "Renouvellement du mandat du commissaire aux comptes titulaire pour une durée de 6 exercices.",
        "source": "Greffe",
    },
    {
        "label": "Nomination de commissaire aux apports",
        "description": "Nomination d'un commissaire aux apports dans le cadre d'un apport partiel d'actif.",
        "source": "Greffe",
    },
    {
        "label": "Transformation de société",
        "description": "Transformation de SARL en SAS par décision unanime des associés. Nouveau capital de 1 500 000 € divisé en 150 000 actions.",
        "source": "BODACC",
    },
    {
        "label": "Procédure de sauvegarde",
        "description": "Ouverture d'une procédure de sauvegarde par le Tribunal de Commerce de Paris. Période d'observation de 6 mois.",
        "source": "BODACC",
    },
    {
        "label": "Inscription de privilège",
        "description": "Inscription d'un privilège de l'URSSAF pour un montant de 45 000 €. Échéance de régularisation à 3 mois.",
        "source": "Greffe",
    },
]


def _mock_corporate_events(company_name: str) -> dict[str, Any]:
    """Generate 4-6 realistic mock corporate events for fallback."""
    rng = random.Random(hash(company_name))
    today = datetime.now()

    # Pick 4-6 random events from the pool
    n_events = rng.randint(4, 6)
    chosen = rng.sample(_MOCK_EVENT_POOL, min(n_events, len(_MOCK_EVENT_POOL)))

    events: list[dict[str, Any]] = []
    for i, evt in enumerate(chosen):
        # Generate dates spread over the last 24 months
        days_ago = rng.randint(15 + i * 60, 90 + i * 120)
        event_date = today - timedelta(days=days_ago)
        tag = _tag_event(evt["label"])

        events.append({
            "date": event_date.strftime("%Y-%m-%d"),
            "label": evt["label"],
            "description": evt["description"],
            "source": evt["source"],
            "signal": tag["signal"],
            "signal_reason": tag["reason"],
        })

    # Sort by date descending
    events.sort(key=lambda e: e["date"], reverse=True)

    # Generate a realistic fake SIREN
    siren = "".join(str(rng.randint(0, 9)) for _ in range(9))

    logger.info("[LEGAL-WATCH] Generated {} mock events for '{}'", len(events), company_name)
    return {
        "company_name": company_name,
        "siren": siren,
        "events": events,
        "source": "mock",
        "generated_at": datetime.now().isoformat(),
    }


# ============================================================
#  3.  Public Orchestrator
# ============================================================

async def get_corporate_events(company_name: str) -> dict[str, Any]:
    """Fetch corporate events for a company.

    Returns:
        {
            "company_name": "...",
            "siren": "...",
            "events": [
                {
                    "date": "YYYY-MM-DD",
                    "label": "...",
                    "description": "...",
                    "source": "BODACC" | "Greffe",
                    "signal": "Bullish" | "Neutral" | "Red Flag",
                    "signal_reason": "..."
                },
                ...
            ],
            "source": "pappers" | "mock",
            "generated_at": "ISO-8601"
        }
    """
    return await _fetch_pappers(company_name)
