"""
Tâche B.7, Étape 4 — Ingestion ESEF/XBRL des états financiers réels des
comparables européens (D20).

Persiste, pour chaque émetteur de `EMITTER_CONCEPT_MAPS` :
  - `Financial` : revenue, depreciation_amortization, ebitda (soit DÉCLARÉ par
    l'émetteur via une extension propriétaire explicite type "EBITDA", soit
    reconstruit = operating_result + D&A quand IFRS n'a pas de concept
    standard — voir `esef_connector.py::extract_financials.ebitda_source`),
    ebit (= operating_result), net_income, total_debt (= dette brute avant
    cash) — avec provenance MARKET, référence = URL du dépôt.
  - `Company.enterprise_value` = market_cap (déjà connu, FMP) + net_debt
    (ESEF) — SEULEMENT quand net_debt a pu être calculé sans ambiguïté.

N'écrase JAMAIS un champ avec une approximation : un poste absent de la
carte de concepts (ambiguïté documentée dans esef_connector.py) reste NULL.
"""
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from api.database import AsyncSessionLocal, init_db
from api.models.company import Company
from api.models.financial import Financial
from api.schemas.provenance import DataProvenance, FieldProvenance
from api.services.data_ingestion import _compute_ratios
from api.services.ma_engine.esef_connector import (
    EMITTER_CONCEPT_MAPS,
    find_latest_filing,
    fetch_filing_facts,
    extract_financials,
)


async def main():
    await init_db()
    report: dict[str, dict] = {}

    async with AsyncSessionLocal() as db:
        for ticker, concept_map in EMITTER_CONCEPT_MAPS.items():
            print(f"\n=== {ticker} (LEI {concept_map['lei']}) ===")
            filing = await find_latest_filing(concept_map["lei"])
            if not filing:
                report[ticker] = {"status": "no filing found"}
                print("  No filing found.")
                continue

            period_end = filing["period_end"]
            json_url = filing["json_url"]
            filing_url = f"https://filings.xbrl.org{json_url}"
            print(f"  Filing: period_end={period_end}, url={filing_url}")

            facts = await fetch_filing_facts(json_url)
            if not facts:
                report[ticker] = {"status": "could not fetch facts", "filing_url": filing_url}
                continue

            extracted = extract_financials(facts, concept_map)
            fiscal_year = int(period_end[:4])
            currency = concept_map["currency"]

            print(f"  revenue={extracted['revenue']}, operating_result={extracted['operating_result']}, "
                  f"da={extracted['da']}, ebitda={extracted['ebitda']} (source={extracted['ebitda_source']}), "
                  f"net_income={extracted['net_income']}, net_debt={extracted['net_debt']}")
            if extracted["notes"]:
                print("  NOTES:", extracted["notes"])

            # ── Persist Financial ──
            result = await db.execute(select(Company).where(Company.ticker == ticker))
            company = result.scalar_one_or_none()
            if not company:
                report[ticker] = {"status": "company not found in DB"}
                print(f"  ⚠️ Company '{ticker}' not found in DB — skipped.")
                continue

            fin_result = await db.execute(
                select(Financial).where(
                    Financial.company_id == company.id,
                    Financial.period_type == "annual",
                    Financial.fiscal_year == fiscal_year,
                )
            )
            fin = fin_result.scalar_one_or_none()

            provenance: dict[str, dict] = {}
            ref = f"ESEF filing (filings.xbrl.org): {filing_url}"

            def _prov(field, value):
                if value is not None:
                    provenance[field] = FieldProvenance(
                        provenance=DataProvenance.MARKET, as_of=str(fiscal_year), reference=ref,
                    ).model_dump(mode="json")

            _prov("revenue", extracted["revenue"])
            _prov("ebit", extracted["operating_result"])
            _prov("depreciation_amortization", extracted["da"])
            _prov("ebitda", extracted["ebitda"])
            _prov("net_income", extracted["net_income"])
            _prov("total_debt", extracted["gross_debt"])
            _prov("cash_and_equivalents", extracted["cash"])
            if extracted["ebitda"] is not None:
                if extracted["ebitda_source"] == "reported":
                    provenance["ebitda"]["reference"] = (
                        f"{ref} — AS REPORTED by issuer (proprietary alternative "
                        f"performance indicator, concept: {extracted['concepts_used'].get('ebitda_direct')})"
                    )
                else:
                    provenance["ebitda"]["reference"] = (
                        f"{ref} — RECONSTRUCTED: operating_result + D&A "
                        f"(concepts: {extracted['concepts_used']})"
                    )

            fin_data = dict(
                company_id=company.id,
                period_type="annual",
                period_end=date(fiscal_year, 12, 31),
                fiscal_year=fiscal_year,
                revenue=extracted["revenue"],
                ebit=extracted["operating_result"],
                depreciation_amortization=extracted["da"],
                ebitda=extracted["ebitda"],
                net_income=extracted["net_income"],
                # Dette BRUTE (courante + non courante) et trésorerie séparées
                # (pas le net_debt déjà agrégé) — _compute_ratios() recalcule
                # net_debt = total_debt - cash_and_equivalents lui-même,
                # inchangé (Tâche B.3/B.4).
                total_debt=extracted["gross_debt"],
                cash_and_equivalents=extracted["cash"],
                financial_provenance=provenance,
            )

            if fin:
                for k, v in fin_data.items():
                    if v is not None and k != "company_id":
                        setattr(fin, k, v)
                fin.financial_provenance = provenance
            else:
                fin = Financial(**fin_data)
                db.add(fin)

            # ── Persist Company.enterprise_value = market_cap + net_debt ──
            if extracted["net_debt"] is not None and company.market_cap is not None:
                new_ev = company.market_cap + extracted["net_debt"]
                company.enterprise_value = new_ev
                company_prov = dict(company.financial_provenance or {})
                company_prov["enterprise_value"] = FieldProvenance(
                    provenance=DataProvenance.MARKET, as_of=str(fiscal_year),
                    reference=f"Computed: market_cap (FMP) + net_debt ({ref})",
                ).model_dump(mode="json")
                company.financial_provenance = company_prov
                print(f"  ✅ enterprise_value = {new_ev:,.0f} {currency} (market_cap + net_debt)")

            report[ticker] = {
                "status": "ok", "filing_url": filing_url, "fiscal_year": fiscal_year,
                "concepts_used": extracted["concepts_used"], "notes": extracted["notes"],
                "ebitda": extracted["ebitda"], "ebitda_source": extracted["ebitda_source"],
            }

            # B.8 fix : sans ce recalcul, `FinancialRatio.ev_ebitda` (lu par
            # /comps/{id}, la table CompSet réellement affichée en UI) reste
            # figé sur l'ancienne valeur — Financial/Company seuls ne suffisent
            # pas, /comps ne les lit pas directement.
            await db.flush()
            await _compute_ratios(company.id, db)

        await db.commit()

    print("\n\n=== SUMMARY ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))


asyncio.run(main())
