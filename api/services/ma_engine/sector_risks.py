"""
sector_risks.py — Sector risk library (Tâche "P2 : crédibilité de la
thèse", Partie C).

Constat de la revue IC externe : les risques cités dans le mémo étaient
génériques (parfois même un "risque" sur l'intégrité du modèle financier —
hors sujet pour un comité d'investissement) au lieu de risques sectoriels
réels et actionnables (homme-clé, garantie décennale, concentration client,
cycle des permis, dépendance réglementaire…).

Ce module ne fait QUE fournir des CANDIDATS de risques, classés par clé de
profil sectoriel (les mêmes clés que `valuation_engine.LBO_PROFILES` —
`resolve_profile_key` fait déjà tout le travail de résolution NAF/mots-clés,
réutilisé tel quel, jamais redéfini ici). Le LLM du mémo SÉLECTIONNE et
PRIORISE parmi cette bibliothèque selon la cible réelle — il ne les invente
pas librement (voir la règle du prompt qui la consomme).

Chaque risque est un dict {risk, detail, severity, probability, mitigants} —
severity/probability ∈ {"high","medium","low"}, jamais un score numérique
inventé (pas de fausse précision).
"""
from __future__ import annotations

from api.services.ma_engine.valuation_engine import resolve_profile_key

# Risques transverses aux PME françaises de petite taille (< quelques
# dizaines de M€ de CA) — s'ajoutent aux risques sectoriels ci-dessous,
# jamais à leur place : une petite société d'ingénierie a À LA FOIS un
# risque homme-clé générique-PME ET un risque sectoriel spécifique
# (garantie décennale, accréditation…).
_UNIVERSAL_SMALL_CAP_RISKS: list[dict] = [
    {
        "risk": "Key-person dependency",
        "detail": (
            "At this size, revenue generation, client relationships and technical "
            "delivery are typically concentrated in the founder or a small handful of "
            "senior staff — the business may not survive their departure intact."
        ),
        "severity": "high", "probability": "high",
        "mitigants": "Management retention package / earn-out, key-person insurance, documented client relationships, planned transition period.",
    },
    {
        "risk": "Customer concentration",
        "detail": (
            "Revenue often relies on a small number of clients or framework contracts; "
            "loss of a top client can disproportionately impact the business."
        ),
        "severity": "high", "probability": "medium",
        "mitigants": "Review client contract terms/renewal dates, diversification plan, revenue-per-client concentration analysis in DD.",
    },
    {
        "risk": "Order book / revenue visibility",
        "detail": (
            "Limited forward order book or backlog visibility beyond a few months — "
            "revenue growth assumptions may not be contractually secured."
        ),
        "severity": "medium", "probability": "medium",
        "mitigants": "Backlog/pipeline review in DD, conversion-rate analysis on the commercial pipeline.",
    },
]

SECTOR_RISK_LIBRARY: dict[str, list[dict]] = {
    "construction": [
        {
            "risk": "Ten-year decennial liability (garantie décennale)",
            "detail": (
                "French construction law (art. 1792 Code civil) imposes a mandatory "
                "10-year liability on structural works — a latent defect discovered "
                "years after delivery can trigger a claim against the company."
            ),
            "severity": "high", "probability": "medium",
            "mitigants": "Verify décennale insurance coverage and claims history, review past project defect records in DD.",
        },
        {
            "risk": "Building permit cycle dependency",
            "detail": (
                "Revenue pipeline is tied to the timing of building-permit issuance "
                "(permis de construire) by local authorities — sensitive to municipal "
                "election cycles and administrative delays, not just end-market demand."
            ),
            "severity": "medium", "probability": "high",
            "mitigants": "Diversify geographic footprint across municipalities, track permit-pipeline lead indicators.",
        },
        {
            "risk": "Subcontractor / skilled-labor availability",
            "detail": "Delivery capacity depends on subcontractor and skilled-labor availability, a persistent constraint in French construction/BTP.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Map subcontractor dependency, assess labor-cost inflation exposure.",
        },
    ],
    "professional_svc": [
        {
            "risk": "Regulatory accreditation dependency",
            "detail": (
                "For TIC (testing/inspection/certification) or regulated advisory "
                "activities, revenue depends on maintained accreditation (e.g. COFRAC) "
                "or professional licensing — loss or suspension would be existential."
            ),
            "severity": "high", "probability": "low",
            "mitigants": "Confirm accreditation status and renewal history, review any past compliance findings.",
        },
        {
            "risk": "Fee-rate / utilization pressure",
            "detail": "Margins depend on billable utilization and fee rates, exposed to client price pressure and staff attrition.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review utilization rates and rate-card trends in DD.",
        },
    ],
    "business_svc": [
        {
            "risk": "Contract renewal / re-tender risk",
            "detail": "B2B service contracts (outsourcing, facility management, staffing) are often re-tendered periodically — a lost tender can remove revenue with little warning.",
            "severity": "high", "probability": "medium",
            "mitigants": "Review contract maturities and renewal history, client tenure analysis.",
        },
        {
            "risk": "Labor cost / minimum wage exposure",
            "detail": "Labor-intensive service models are directly exposed to minimum-wage and social-charge increases in France.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review pass-through clauses in client contracts.",
        },
    ],
    "heavy_industry": [
        {
            "risk": "Raw material / input cost volatility",
            "detail": "Manufacturing margins are exposed to metal/chemical/energy input price swings.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review hedging policy and pass-through clauses.",
        },
        {
            "risk": "Environmental / ICPE regulatory compliance",
            "detail": "French industrial sites are often subject to ICPE (installations classées) permitting — non-compliance or permit renewal risk can halt operations.",
            "severity": "high", "probability": "low",
            "mitigants": "Environmental compliance audit in DD, review permit renewal timelines.",
        },
        {
            "risk": "Customer concentration (OEM/automotive supply chain)",
            "detail": "Industrial subcontractors are often concentrated on a small number of OEM clients with strong negotiating power.",
            "severity": "high", "probability": "medium",
            "mitigants": "Review client contract terms and diversification plan.",
        },
    ],
    "transport": [
        {
            "risk": "Fuel price / energy cost exposure",
            "detail": "Transport & logistics margins are directly exposed to fuel price volatility.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review fuel surcharge pass-through clauses in client contracts.",
        },
        {
            "risk": "Driver / labor shortage",
            "detail": "Persistent driver shortages in French road transport constrain capacity and push up wage costs.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review workforce retention metrics.",
        },
        {
            "risk": "Client concentration (contract logistics)",
            "detail": "Contract logistics revenue is often concentrated on a handful of shipper relationships.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review client contract terms and renewal dates.",
        },
    ],
    "wholesale_retail": [
        {
            "risk": "Supplier concentration / sourcing dependency",
            "detail": "Distribution margins depend on maintained supplier terms — loss of a key supplier or distribution agreement is a material risk.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review supplier contract terms and alternative sourcing options.",
        },
        {
            "risk": "E-commerce / channel disruption",
            "detail": "Traditional distribution/retail models remain exposed to online-channel disintermediation.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Assess digital channel strategy and investment.",
        },
    ],
    "hospitality": [
        {
            "risk": "Seasonality / occupancy volatility",
            "detail": "Revenue is exposed to seasonal demand swings and discretionary consumer spending.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review historical occupancy/seasonality patterns.",
        },
        {
            "risk": "Location / lease dependency",
            "detail": "Value is often tied to a small number of leased or owned locations — lease renewal terms are a material risk.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review lease terms/renewal options in DD.",
        },
    ],
    "media_telecom": [
        {
            "risk": "Content/audience concentration and platform dependency",
            "detail": "Revenue may depend on a small number of distribution platforms or advertisers, exposed to algorithm/policy changes outside the company's control.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review platform/distribution diversification.",
        },
        {
            "risk": "Regulatory dependency (telecom licensing/media regulation)",
            "detail": "Telecom and broadcast activities are subject to ARCEP/CSA-type regulatory licensing in France.",
            "severity": "medium", "probability": "low",
            "mitigants": "Confirm licensing status and compliance history.",
        },
    ],
    "software_it": [
        {
            "risk": "Key-developer / technical-debt dependency",
            "detail": "Small software businesses often concentrate core product knowledge in a few developers; undocumented technical debt is a common DD finding.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Code/architecture review in technical DD, documentation assessment.",
        },
        {
            "risk": "Customer churn / contract renewal (SaaS)",
            "detail": "Recurring-revenue models are exposed to churn — reported ARR may not reflect true retained revenue without a cohort analysis.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Cohort/churn analysis in DD, net revenue retention review.",
        },
    ],
    "finance": [
        {
            "risk": "Regulatory capital / licensing dependency",
            "detail": "Financial services activities are subject to ACPR/AMF-type licensing and capital requirements — a compliance breach can restrict operations.",
            "severity": "high", "probability": "low",
            "mitigants": "Regulatory compliance review in DD.",
        },
        {
            "risk": "Credit / counterparty risk",
            "detail": "Lending or credit-adjacent activities carry direct exposure to counterparty default.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review loan book quality and provisioning policy.",
        },
    ],
    "real_estate": [
        {
            "risk": "Interest rate sensitivity",
            "detail": "Real estate values and financing costs are directly exposed to interest-rate movements.",
            "severity": "high", "probability": "medium",
            "mitigants": "Review debt maturity profile and rate hedges.",
        },
        {
            "risk": "Tenant concentration / vacancy risk",
            "detail": "Rental income may be concentrated on a small number of tenants or assets.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review tenant diversification and lease maturities.",
        },
    ],
    "education": [
        {
            "risk": "Regulatory accreditation dependency",
            "detail": "Training/education providers depend on state or professional accreditation (e.g. Qualiopi) for funding eligibility — loss of accreditation would cut off a funding channel.",
            "severity": "high", "probability": "low",
            "mitigants": "Confirm accreditation status and renewal history.",
        },
        {
            "risk": "Public funding dependency",
            "detail": "Revenue may depend on public training-funding mechanisms (CPF, OPCO) subject to policy change.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review funding-source diversification.",
        },
    ],
    "healthcare": [
        {
            "risk": "Regulatory / licensing dependency",
            "detail": "Healthcare and social-care activities are subject to ARS (Agence Régionale de Santé) authorization in France — a material regulatory dependency.",
            "severity": "high", "probability": "low",
            "mitigants": "Confirm authorization status and renewal history.",
        },
        {
            "risk": "Reimbursement / tariff dependency",
            "detail": "Revenue may depend on public health reimbursement tariffs, subject to periodic government revision.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review tariff exposure and historical revision impact.",
        },
    ],
    "leisure": [
        {
            "risk": "Discretionary spending / seasonality",
            "detail": "Leisure/culture/sport revenue is exposed to discretionary consumer spending and seasonal demand.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review historical seasonality and demand resilience.",
        },
    ],
    "energy": [
        {
            "risk": "Regulatory / permitting dependency",
            "detail": "Energy and environmental activities (production, waste, renewables) are subject to ICPE-type permitting and evolving regulation.",
            "severity": "high", "probability": "medium",
            "mitigants": "Environmental/permitting compliance review in DD.",
        },
        {
            "risk": "Commodity / tariff price exposure",
            "detail": "Margins may be exposed to energy commodity prices or regulated tariff changes.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review hedging policy and contract indexation.",
        },
    ],
    "food_bev": [
        {
            "risk": "Food-safety / regulatory compliance",
            "detail": "Agri-food activities are subject to strict food-safety regulation (HACCP, DGCCRF controls) — a compliance failure can trigger recalls or shutdowns.",
            "severity": "high", "probability": "low",
            "mitigants": "Food-safety audit and compliance history review in DD.",
        },
        {
            "risk": "Input commodity price volatility",
            "detail": "Margins are exposed to agricultural commodity price swings.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review hedging/pass-through arrangements.",
        },
    ],
    "textile": [
        {
            "risk": "Fashion-cycle / demand volatility",
            "detail": "Textile/apparel revenue is exposed to fashion trends and discretionary consumer spending.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review order-book visibility and inventory turnover.",
        },
        {
            "risk": "Supply-chain concentration",
            "detail": "Sourcing is often concentrated in a small number of manufacturing partners, frequently overseas.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review supplier diversification and lead times.",
        },
    ],
    "agriculture": [
        {
            "risk": "Weather / climate exposure",
            "detail": "Agricultural output is directly exposed to weather variability and climate events.",
            "severity": "high", "probability": "medium",
            "mitigants": "Review crop/weather insurance coverage.",
        },
        {
            "risk": "Commodity price volatility",
            "detail": "Revenue is exposed to agricultural commodity price cycles, often outside the company's control.",
            "severity": "medium", "probability": "high",
            "mitigants": "Review hedging and forward-contract practices.",
        },
    ],
    "hightech_mfg": [
        {
            "risk": "Component / semiconductor supply dependency",
            "detail": "Electronics manufacturing is exposed to global component and semiconductor supply-chain disruption.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review supplier diversification and inventory buffers.",
        },
        {
            "risk": "Customer concentration (OEM)",
            "detail": "Revenue may be concentrated on a small number of OEM clients.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review client contract terms and diversification.",
        },
    ],
    "pharma": [
        {
            "risk": "Regulatory / marketing-authorization dependency",
            "detail": "Pharma/biotech revenue depends on regulatory approval (ANSM/EMA) — a delayed or denied authorization is an existential risk.",
            "severity": "high", "probability": "medium",
            "mitigants": "Review regulatory pipeline status and approval history.",
        },
        {
            "risk": "Patent / IP cliff exposure",
            "detail": "Revenue may be exposed to patent expiry or generic competition.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review IP portfolio and patent expiry schedule.",
        },
    ],
    "other_services": [
        {
            "risk": "Customer concentration",
            "detail": "Small services businesses often depend on a limited client base.",
            "severity": "medium", "probability": "medium",
            "mitigants": "Review client contract terms and renewal dates.",
        },
    ],
    "default": [
        {
            "risk": "Sector not precisely identified — generic assumptions applied",
            "detail": (
                "This target's sector could not be matched to a specific risk profile "
                "in the library — the LBO assumptions used a generic sector profile, "
                "and the risk list below is necessarily generic. Sector-specific risks "
                "(regulatory, customer concentration, key-person, seasonality) should "
                "be confirmed in due diligence rather than assumed absent."
            ),
            "severity": "medium", "probability": "medium",
            "mitigants": "Confirm actual sector/NAF classification and revisit risk factors accordingly during DD.",
        },
    ],
}


# Le mapping financier (`resolve_profile_key`, NAF/mots-clés → marge/
# multiple LBO) reste la SEULE autorité pour les hypothèses financières —
# jamais touché ici. Mais un texte sectoriel libre peut décrire une activité
# de façon assez précise pour trigger un risque réel (ex. "études de
# structure béton armé" = ingénierie structure/BTP) SANS matcher les
# mots-clés, volontairement étroits, que `resolve_profile_key` utilise pour
# le calibrage financier (ex. "béton"/"structure" ne sont pas des mots-clés
# financiers de "construction" — à raison, un profil générique reste le bon
# choix financier par défaut). Cette couche de risque est INDÉPENDANTE et
# plus permissive : elle ne change AUCUNE hypothèse financière, seulement la
# sélection de risques candidats.
_RISK_TEXT_OVERRIDES: list[tuple[list[str], str]] = [
    (["béton", "structure", "génie civil", "gros œuvre", "charpente", "maçonnerie"], "construction"),
    (["décennale", "contrôle technique", "inspection", "certification", "essai technique"], "professional_svc"),
]


def get_sector_risk_candidates(sector_or_naf: str) -> list[dict]:
    """Resolves a deal's sector/NAF text to its risk-library entry and
    returns SECTOR-SPECIFIC risks FIRST, universal small-cap risks after —
    candidates for the memo LLM to select/prioritize from, never a risk list
    it invents freely. Sector-specific risks lead the list deliberately: an
    LLM asked to "select and prioritize" tends to favour earlier items, and
    a genuinely sector-relevant risk (e.g. decennial liability for a
    structural-engineering target) is more useful in an IC memo than a
    restated universal one — found during verification, where an early
    ordering with universal risks first caused the model to pick 3 generic
    risks and never reach the sector-specific ones at all. Tries a broader,
    risk-only keyword match first (real activity descriptions like "études
    de structure béton armé" won't always match `resolve_profile_key`'s
    narrower financial-calibration keywords), then falls back to the same
    sector-profile resolution the LBO engine uses."""
    text_lower = str(sector_or_naf).lower()
    for keywords, risk_key in _RISK_TEXT_OVERRIDES:
        if any(kw in text_lower for kw in keywords):
            return SECTOR_RISK_LIBRARY[risk_key] + _UNIVERSAL_SMALL_CAP_RISKS

    key = resolve_profile_key(sector_or_naf)
    sector_specific = SECTOR_RISK_LIBRARY.get(key, SECTOR_RISK_LIBRARY["default"])
    return sector_specific + _UNIVERSAL_SMALL_CAP_RISKS
