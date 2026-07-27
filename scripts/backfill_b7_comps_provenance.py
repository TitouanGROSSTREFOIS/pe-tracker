"""
Tâche B.7, Étape 3 — Reprise rétrospective de la provenance des 14
comparables du CompSet TIC (D19).

MG, CLB et J ont été ré-ingérés en direct (chemin réel `ingest_company`,
Finnhub + Alpha Vantage confirmés) — ce script ne les touche pas. Les 11
comparables restants n'ont que `market_cap` renseigné, et exclusivement par
FMP (`/stable/profile`, seul endpoint fonctionnel sur ce plan pour des
tickers non-démo — voir RAPPORT B.3/B.4) : aucun appel réseau n'est
nécessaire ici, le fait est déjà établi et documenté.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from api.database import AsyncSessionLocal, init_db
from api.models.company import Company
from api.schemas.provenance import DataProvenance, FieldProvenance

FMP_ONLY_TICKERS = [
    "BVI.PA", "SGSN.SW", "ERF.PA", "ITRK.L", "ALQ.AX",
    "ATE.PA", "ASY.PA", "SPIE.PA", "WSP.TO", "STN.TO", "ATRL.TO",
]


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Company).where(Company.ticker.in_(FMP_ONLY_TICKERS)))
        companies = list(result.scalars().all())
        print(f"{len(companies)} companies matched.")

        for c in companies:
            if c.financial_provenance:
                print(f"{c.ticker}: already has provenance — skipped.")
                continue
            if c.market_cap is None:
                print(f"{c.ticker}: no market_cap — nothing to qualify.")
                continue
            c.financial_provenance = {
                "market_cap": FieldProvenance(
                    provenance=DataProvenance.MARKET, reference="FMP",
                ).model_dump(mode="json"),
            }
            print(f"{c.ticker}: market_cap tagged MARKET/FMP.")

        await db.commit()


asyncio.run(main())
