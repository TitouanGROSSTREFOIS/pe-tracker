"""
Tâche B.8, Étape 2 — SGS S.A. (émetteur suisse, hors régime ESEF) : transcription
sourcée depuis le rapport annuel public (audité), PAS une fabrication.

Chaque valeur ci-dessous a été relevée manuellement dans :
  SGS 2025 Integrated Report — Financial statements
  https://www.sgs.com/-/media/sgscorp/documents/corporate/reports-and-presentations/2020s/2026/sgs-financial-statements-en.cdn.en.pdf
  (PDF téléchargé et vérifié le 2026-07-21)

- Revenue, operating income, net income, D&A+impairment combiné (485) :
  Consolidated income statement, PDF p.7 (rapport p.96).
- Loans and other financial liabilities, cash and cash equivalents :
  Consolidated statement of financial position, PDF p.8 (rapport p.97).
- D&A pur (hors dépréciation), décomposé par poste :
    Note 11 Property, plant and equipment (PDF p.24, rapport p.113) :
      depreciation = 227, impairment = 13
    Note 12 Right-of-use assets and lease liabilities (PDF p.25, rapport p.114) :
      "Depreciation/impairment expense" = 181 (poste combiné dans le
      libellé 2025 ; le libellé 2024 équivalent était "Depreciation
      expense" pour un montant quasi identique — l'impairment inclus y est
      documenté comme négligeable, mais reste un poste combiné : signalé).
    Note 14 Other intangible assets (PDF p.26, rapport p.116) :
      amortization = 58, impairment = 6
  Total D&A pur = 227 + 181 + 58 = 466 (CHF million).
  Vérification de cohérence : 466 (D&A pur) + 13 + 6 (impairment PP&E +
  intangibles) = 485 = exactement le poste combiné du compte de résultat.
  → EBITDA reconstruit = operating income (1 014) + D&A pur (466) = 1 480,
  EXCLUANT l'impairment (19), conformément à la formule demandée par la
  tâche (résultat opérationnel + dotations aux amortissements).

Net financial debt = Loans and other financial liabilities (3 505 non
courant + 832 courant = 4 337) − Cash and cash equivalents (2 330) = 2 007.
Les lease liabilities IFRS 16 (560) sont EXCLUES de ce calcul, par
cohérence avec les autres comparables du CompSet (concepts ESEF
"Borrowings", qui n'incluent pas les dettes locatives).

Toute valeur non trouvée avec certitude reste absente de ce script — aucune
déduction.
"""
import asyncio
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

TICKER = "SGSN.SW"
FISCAL_YEAR = 2025
SOURCE_URL = (
    "https://www.sgs.com/-/media/sgscorp/documents/corporate/reports-and-presentations/"
    "2020s/2026/sgs-financial-statements-en.cdn.en.pdf"
)

REVENUE = 6_945_000_000.0
OPERATING_INCOME = 1_014_000_000.0
NET_INCOME = 717_000_000.0  # "Profit for the period" total (equity holders + NCI), cohérent avec ifrs-full:ProfitLoss utilisé pour les comps ESEF
DA_PURE = 466_000_000.0  # 227 (PP&E, note 11) + 181 (ROU, note 12) + 58 (intangibles, note 14)
EBITDA = OPERATING_INCOME + DA_PURE  # 1 480
GROSS_DEBT = 4_337_000_000.0  # 3 505 (non-current) + 832 (current) loans and other financial liabilities, note 22 / balance sheet
CASH = 2_330_000_000.0
NET_DEBT = GROSS_DEBT - CASH  # 2 007


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        company = (
            await db.execute(select(Company).where(Company.ticker == TICKER))
        ).scalar_one_or_none()
        if not company:
            print(f"Company '{TICKER}' not found in DB — aborting.")
            return

        fin = (
            await db.execute(
                select(Financial).where(
                    Financial.company_id == company.id,
                    Financial.period_type == "annual",
                    Financial.fiscal_year == FISCAL_YEAR,
                )
            )
        ).scalar_one_or_none()

        ref = lambda note: f"SGS 2025 Integrated Report, Financial statements ({SOURCE_URL}) — {note}"
        provenance = {
            "revenue": FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref("Consolidated income statement, PDF p.7 (report p.96): Sales"),
            ).model_dump(mode="json"),
            "ebit": FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref("Consolidated income statement, PDF p.7 (report p.96): Operating income"),
            ).model_dump(mode="json"),
            "depreciation_amortization": FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref(
                    "Sum of pure depreciation/amortization only (impairment excluded): "
                    "Note 11 PP&E depreciation=227 (PDF p.24) + Note 12 right-of-use "
                    "depreciation/impairment=181 (PDF p.25, combined label in filing) + "
                    "Note 14 intangibles amortization=58 (PDF p.26) = 466. Cross-check: "
                    "466 + impairment (13+6=19) = 485 = the income statement's combined "
                    "'Depreciation, amortization and impairment' line."
                ),
            ).model_dump(mode="json"),
            "ebitda": FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref(
                    "RECONSTRUCTED: operating income (1 014) + pure D&A (466, see "
                    "depreciation_amortization provenance) = 1 480. Impairment (19) excluded."
                ),
            ).model_dump(mode="json"),
            "net_income": FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref("Consolidated income statement, PDF p.7 (report p.96): Profit for the period (total, incl. non-controlling interests)"),
            ).model_dump(mode="json"),
            "total_debt": FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref(
                    "Consolidated statement of financial position, PDF p.8 (report p.97): "
                    "Loans and other financial liabilities, non-current (3 505) + current (832) = 4 337. "
                    "IFRS 16 lease liabilities (560) excluded for consistency with ESEF comps."
                ),
            ).model_dump(mode="json"),
            "cash_and_equivalents": FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref("Consolidated statement of financial position, PDF p.8 (report p.97): Cash and cash equivalents"),
            ).model_dump(mode="json"),
        }

        fin_data = dict(
            company_id=company.id,
            period_type="annual",
            period_end=date(FISCAL_YEAR, 12, 31),
            fiscal_year=FISCAL_YEAR,
            revenue=REVENUE,
            ebit=OPERATING_INCOME,
            depreciation_amortization=DA_PURE,
            ebitda=EBITDA,
            net_income=NET_INCOME,
            total_debt=GROSS_DEBT,
            cash_and_equivalents=CASH,
            financial_provenance=provenance,
        )

        if fin:
            for k, v in fin_data.items():
                if k != "company_id":
                    setattr(fin, k, v)
        else:
            fin = Financial(**fin_data)
            db.add(fin)

        if company.market_cap is not None:
            new_ev = company.market_cap + NET_DEBT
            company.enterprise_value = new_ev
            company_prov = dict(company.financial_provenance or {})
            company_prov["enterprise_value"] = FieldProvenance(
                provenance=DataProvenance.DOCUMENT, as_of=str(FISCAL_YEAR),
                reference=ref(f"Computed: market_cap (FMP) + net_debt (4 337 − 2 330 = 2 007)"),
            ).model_dump(mode="json")
            company.financial_provenance = company_prov
            print(f"enterprise_value = {new_ev:,.0f} CHF (market_cap {company.market_cap:,.0f} + net_debt {NET_DEBT:,.0f})")

        # B.8 fix : sans ce recalcul, FinancialRatio.ev_ebitda (lu par
        # /comps/{id}) reste figé — voir ingest_esef_comps.py pour le même correctif.
        await db.flush()
        await _compute_ratios(company.id, db)

        await db.commit()
        print(f"SGS ({TICKER}) FY{FISCAL_YEAR} persisted: revenue={REVENUE:,.0f}, ebit={OPERATING_INCOME:,.0f}, "
              f"da={DA_PURE:,.0f}, ebitda={EBITDA:,.0f}, net_income={NET_INCOME:,.0f}, "
              f"total_debt={GROSS_DEBT:,.0f}, cash={CASH:,.0f}, net_debt={NET_DEBT:,.0f}")


asyncio.run(main())
