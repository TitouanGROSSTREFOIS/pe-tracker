"""
check_provenance_coverage.py — Contrôle de traçabilité (Tâche : Provenance
DOCUMENT/MANUAL sur le flux réel + audit, Partie F).

Détecte tout `Deal` en base dont un champ financier renseigné (target_revenue,
target_ebitda, enterprise_value) n'a PAS d'entrée correspondante dans
`financial_provenance`. Vérifie la même chose côté comparables cotés
(`Company`/`Financial`, champs market_cap/enterprise_value/revenue/ebitda) —
même argument différenciant du projet ("chaque chiffre sait d'où il vient"),
même risque de régression silencieuse.

Ne corrige rien : signale uniquement (même philosophie que
`validate_extraction_plausibility` en B.10). Aucune nouvelle dépendance —
uniquement SQLAlchemy, déjà utilisé partout dans `api/`.

Usage :
    python scripts/check_provenance_coverage.py
Sortie : 0 si aucune anomalie, 1 si au moins un champ sans provenance trouvé
(exploitable en CI ou pre-commit plus tard si souhaité — pas branché
automatiquement dans cette tâche, script autonome à lancer manuellement).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.models.company import Company
from api.models.deal import Deal
from api.models.financial import Financial

# Champs financiers de Deal qui DOIVENT porter une provenance dès qu'ils sont
# renseignés (les multiples dérivés ev_revenue_multiple/ev_ebitda_multiple ne
# sont volontairement pas vérifiés ici : ils ne sont écrits qu'AVEC leur
# provenance par compute_deal_multiples, jamais indépendamment — vérifier les
# trois champs sources suffit à couvrir la chaîne).
DEAL_FIELDS = ["target_revenue", "target_ebitda", "enterprise_value"]

# Champs de Company/Financial couverts par _build_comp_row_provenance
# (comps_service.py) — même exigence pour les comparables cotés.
COMPANY_FIELDS = ["market_cap", "enterprise_value"]
FINANCIAL_FIELDS = ["revenue", "ebitda", "net_income"]


async def check_deals() -> list[str]:
    issues: list[str] = []
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Deal))
        deals = result.scalars().all()
        for deal in deals:
            prov = deal.financial_provenance if isinstance(deal.financial_provenance, dict) else {}
            for field in DEAL_FIELDS:
                value = getattr(deal, field, None)
                if value is not None and field not in prov:
                    issues.append(
                        f"Deal #{deal.id} ({deal.target_name!r}): {field}={value} "
                        f"n'a AUCUNE entrée de provenance dans financial_provenance."
                    )
    return issues


async def check_comps() -> list[str]:
    issues: list[str] = []
    async with AsyncSessionLocal() as db:
        companies = (await db.execute(select(Company))).scalars().all()
        for company in companies:
            prov = company.financial_provenance if isinstance(company.financial_provenance, dict) else {}
            for field in COMPANY_FIELDS:
                value = getattr(company, field, None)
                if value is not None and field not in prov:
                    issues.append(
                        f"Company #{company.id} ({company.ticker}): {field}={value} "
                        f"n'a AUCUNE entrée de provenance."
                    )

        financials = (await db.execute(select(Financial))).scalars().all()
        for fin in financials:
            prov = fin.financial_provenance if isinstance(fin.financial_provenance, dict) else {}
            for field in FINANCIAL_FIELDS:
                value = getattr(fin, field, None)
                if value is not None and field not in prov:
                    issues.append(
                        f"Financial #{fin.id} (company_id={fin.company_id}, FY{fin.fiscal_year}): "
                        f"{field}={value} n'a AUCUNE entrée de provenance."
                    )
    return issues


async def main() -> int:
    deal_issues = await check_deals()
    comp_issues = await check_comps()
    all_issues = deal_issues + comp_issues

    print(f"Deals vérifiés — anomalies : {len(deal_issues)}")
    print(f"Comparables (Company/Financial) vérifiés — anomalies : {len(comp_issues)}")
    print()

    if not all_issues:
        print("✅ Aucun champ financier sans provenance associée.")
        return 0

    print(f"❌ {len(all_issues)} champ(s) financier(s) sans provenance :\n")
    for issue in all_issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
