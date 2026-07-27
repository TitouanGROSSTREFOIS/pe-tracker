"""
Seed script — Insert realistic sample data into the database
for testing all API endpoints without depending on Yahoo Finance.

Run: python -m api.seed
"""
import asyncio
from datetime import date, datetime
from api.database import init_db, AsyncSessionLocal
from api.models.company import Company
from api.models.financial import Financial, FinancialRatio
from api.models.deal import Deal

COMPANIES = [
    dict(ticker="AAPL", name="Apple Inc.", sector="Technology", industry="Consumer Electronics",
         country="United States", exchange="NASDAQ", currency="USD", market_cap=3_450_000_000_000,
         enterprise_value=3_500_000_000_000, employees=164000, website="https://apple.com",
         last_price=228.50, shares_outstanding=15_100_000_000, is_active=True,
         description="Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide."),
    dict(ticker="MSFT", name="Microsoft Corporation", sector="Technology", industry="Software—Infrastructure",
         country="United States", exchange="NASDAQ", currency="USD", market_cap=3_200_000_000_000,
         enterprise_value=3_240_000_000_000, employees=228000, website="https://microsoft.com",
         last_price=430.20, shares_outstanding=7_430_000_000, is_active=True,
         description="Microsoft Corporation develops and supports software, services, devices, and solutions worldwide."),
    dict(ticker="GOOGL", name="Alphabet Inc.", sector="Technology", industry="Internet Content & Information",
         country="United States", exchange="NASDAQ", currency="USD", market_cap=2_100_000_000_000,
         enterprise_value=2_050_000_000_000, employees=182502, website="https://abc.xyz",
         last_price=172.50, shares_outstanding=12_190_000_000, is_active=True,
         description="Alphabet Inc. offers various products and platforms across the world through Google Services, Google Cloud, and Other Bets."),
    dict(ticker="AMZN", name="Amazon.com, Inc.", sector="Technology", industry="Internet Retail",
         country="United States", exchange="NASDAQ", currency="USD", market_cap=2_050_000_000_000,
         enterprise_value=2_120_000_000_000, employees=1540000, website="https://amazon.com",
         last_price=198.80, shares_outstanding=10_310_000_000, is_active=True,
         description="Amazon.com, Inc. engages in the retail sale of consumer products, advertising, and subscription services."),
    dict(ticker="META", name="Meta Platforms, Inc.", sector="Technology", industry="Internet Content & Information",
         country="United States", exchange="NASDAQ", currency="USD", market_cap=1_550_000_000_000,
         enterprise_value=1_500_000_000_000, employees=72404, website="https://meta.com",
         last_price=612.30, shares_outstanding=2_530_000_000, is_active=True,
         description="Meta Platforms, Inc. engages in the development of products that enable people to connect and share with friends and family."),
    dict(ticker="NVDA", name="NVIDIA Corporation", sector="Technology", industry="Semiconductors",
         country="United States", exchange="NASDAQ", currency="USD", market_cap=3_300_000_000_000,
         enterprise_value=3_280_000_000_000, employees=32600, website="https://nvidia.com",
         last_price=134.50, shares_outstanding=24_530_000_000, is_active=True,
         description="NVIDIA Corporation provides graphics and compute solutions in the United States, Taiwan, China, Hong Kong, and internationally."),
    dict(ticker="JPM", name="JPMorgan Chase & Co.", sector="Financial Services", industry="Banks—Diversified",
         country="United States", exchange="NYSE", currency="USD", market_cap=710_000_000_000,
         enterprise_value=None, employees=313206, website="https://jpmorganchase.com",
         last_price=248.50, shares_outstanding=2_860_000_000, is_active=True,
         description="JPMorgan Chase & Co. operates as a financial services company worldwide."),
    dict(ticker="GS", name="The Goldman Sachs Group, Inc.", sector="Financial Services", industry="Capital Markets",
         country="United States", exchange="NYSE", currency="USD", market_cap=190_000_000_000,
         enterprise_value=None, employees=46500, website="https://goldmansachs.com",
         last_price=590.20, shares_outstanding=322_000_000, is_active=True,
         description="The Goldman Sachs Group, Inc. is a global investment banking, securities and investment management firm."),
    dict(ticker="JNJ", name="Johnson & Johnson", sector="Healthcare", industry="Drug Manufacturers—General",
         country="United States", exchange="NYSE", currency="USD", market_cap=370_000_000_000,
         enterprise_value=385_000_000_000, employees=131900, website="https://jnj.com",
         last_price=153.50, shares_outstanding=2_410_000_000, is_active=True,
         description="Johnson & Johnson researches, develops, manufactures, and sells various products in the healthcare field worldwide."),
    dict(ticker="UNH", name="UnitedHealth Group Incorporated", sector="Healthcare", industry="Healthcare Plans",
         country="United States", exchange="NYSE", currency="USD", market_cap=455_000_000_000,
         enterprise_value=510_000_000_000, employees=440000, website="https://unitedhealthgroup.com",
         last_price=492.30, shares_outstanding=924_000_000, is_active=True,
         description="UnitedHealth Group Incorporated operates as a diversified healthcare company in the United States."),
    dict(ticker="TTE", name="TotalEnergies SE", sector="Energy", industry="Oil & Gas Integrated",
         country="France", exchange="EPA", currency="EUR", market_cap=145_000_000_000,
         enterprise_value=170_000_000_000, employees=105476, website="https://totalenergies.com",
         last_price=58.50, shares_outstanding=2_340_000_000, is_active=True,
         description="TotalEnergies SE is a multi-energy production and supply company operating globally."),
    dict(ticker="MC.PA", name="LVMH Moët Hennessy Louis Vuitton", sector="Consumer Cyclical", industry="Luxury Goods",
         country="France", exchange="EPA", currency="EUR", market_cap=320_000_000_000,
         enterprise_value=350_000_000_000, employees=213000, website="https://lvmh.com",
         last_price=640.00, shares_outstanding=500_000_000, is_active=True,
         description="LVMH Moët Hennessy Louis Vuitton SE engages in luxury products and operates through Fashion & Leather, Wines & Spirits, and more."),
    dict(ticker="BRK-B", name="Berkshire Hathaway Inc.", sector="Financial Services", industry="Insurance—Diversified",
         country="United States", exchange="NYSE", currency="USD", market_cap=1_100_000_000_000,
         enterprise_value=1_050_000_000_000, employees=396500, website="https://berkshirehathaway.com",
         last_price=508.00, shares_outstanding=2_165_000_000, is_active=True,
         description="Berkshire Hathaway Inc. engages in insurance, freight rail, and utility businesses, among other diversified holdings."),
]

# Financials (simplified annual data — last 3 years)
# Format: (ticker, year, revenue, cogs, gross_profit, ebitda, ebit, net_income, eps, total_assets, total_debt, total_equity, cash, capex, ocf, fcf, da, shares)
FINANCIALS = [
    ("AAPL", 2024, 391e9, 214e9, 177e9, 134e9, 123e9, 94e9, 6.22, 364e9, 109e9, 56e9, 30e9, -10e9, 118e9, 108e9, 11e9, 15.1e9),
    ("AAPL", 2023, 383e9, 214e9, 169e9, 130e9, 119e9, 97e9, 6.42, 352e9, 111e9, 62e9, 29e9, -11e9, 110e9, 99e9, 11e9, 15.1e9),
    ("AAPL", 2022, 394e9, 223e9, 171e9, 134e9, 122e9, 99e9, 6.15, 352e9, 120e9, 50e9, 24e9, -11e9, 122e9, 111e9, 12e9, 16.1e9),
    ("MSFT", 2024, 245e9, 74e9, 171e9, 125e9, 109e9, 88e9, 11.84, 512e9, 59e9, 268e9, 76e9, -28e9, 119e9, 91e9, 16e9, 7.43e9),
    ("MSFT", 2023, 212e9, 65e9, 147e9, 109e9, 94e9, 72e9, 9.72, 411e9, 59e9, 206e9, 34e9, -28e9, 87e9, 59e9, 15e9, 7.43e9),
    ("MSFT", 2022, 198e9, 62e9, 136e9, 100e9, 84e9, 73e9, 9.70, 365e9, 61e9, 166e9, 13e9, -24e9, 89e9, 65e9, 16e9, 7.50e9),
    ("GOOGL", 2024, 350e9, 155e9, 195e9, 120e9, 108e9, 86e9, 7.05, 432e9, 29e9, 315e9, 95e9, -33e9, 101e9, 68e9, 12e9, 12.2e9),
    ("GOOGL", 2023, 307e9, 134e9, 173e9, 100e9, 85e9, 74e9, 5.80, 402e9, 29e9, 283e9, 111e9, -32e9, 92e9, 60e9, 15e9, 12.8e9),
    ("GOOGL", 2022, 283e9, 127e9, 156e9, 82e9, 74e9, 60e9, 4.56, 365e9, 30e9, 256e9, 114e9, -31e9, 92e9, 61e9, 8e9, 13.2e9),
    ("AMZN", 2024, 638e9, 393e9, 245e9, 108e9, 69e9, 59e9, 5.73, 624e9, 162e9, 260e9, 78e9, -75e9, 116e9, 41e9, 39e9, 10.3e9),
    ("AMZN", 2023, 575e9, 358e9, 217e9, 85e9, 37e9, 30e9, 2.95, 528e9, 154e9, 201e9, 74e9, -54e9, 85e9, 31e9, 48e9, 10.3e9),
    ("AMZN", 2022, 514e9, 332e9, 182e9, 55e9, 12e9, -3e9, -0.27, 462e9, 164e9, 146e9, 54e9, -63e9, 46e9, -17e9, 43e9, 10.2e9),
    ("META", 2024, 164e9, 28e9, 136e9, 78e9, 64e9, 56e9, 22.13, 256e9, 37e9, 165e9, 58e9, -31e9, 74e9, 43e9, 14e9, 2.53e9),
    ("META", 2023, 135e9, 26e9, 109e9, 59e9, 47e9, 39e9, 14.87, 229e9, 37e9, 142e9, 42e9, -28e9, 72e9, 44e9, 12e9, 2.61e9),
    ("META", 2022, 117e9, 26e9, 91e9, 41e9, 29e9, 23e9, 8.59, 185e9, 27e9, 125e9, 40e9, -32e9, 50e9, 18e9, 12e9, 2.69e9),
    ("NVDA", 2024, 130e9, 29e9, 101e9, 83e9, 80e9, 73e9, 2.94, 112e9, 10e9, 65e9, 32e9, -3e9, 65e9, 62e9, 3e9, 24.5e9),
    ("NVDA", 2023, 61e9, 17e9, 44e9, 33e9, 30e9, 30e9, 1.21, 65e9, 11e9, 43e9, 26e9, -2e9, 29e9, 27e9, 3e9, 24.5e9),
    ("NVDA", 2022, 27e9, 12e9, 15e9, 11e9, 10e9, 10e9, 0.40, 41e9, 11e9, 26e9, 21e9, -2e9, 9e9, 7e9, 1e9, 24.9e9),
    ("JPM", 2024, 178e9, 0, 178e9, 72e9, 65e9, 54e9, 18.88, 4000e9, 420e9, 340e9, 700e9, -8e9, 42e9, 34e9, 7e9, 2.86e9),
    ("JPM", 2023, 162e9, 0, 162e9, 70e9, 64e9, 50e9, 17.30, 3875e9, 412e9, 328e9, 680e9, -7e9, 38e9, 31e9, 6e9, 2.89e9),
    ("GS", 2024, 52e9, 0, 52e9, 18e9, 15e9, 12e9, 37.27, 1762e9, 310e9, 128e9, 260e9, -2e9, 10e9, 8e9, 3e9, 0.322e9),
    ("GS", 2023, 46e9, 0, 46e9, 14e9, 12e9, 8.5e9, 25.93, 1640e9, 290e9, 120e9, 240e9, -2e9, 8e9, 6e9, 2e9, 0.328e9),
    ("JNJ", 2024, 89e9, 29e9, 60e9, 32e9, 24e9, 18e9, 7.47, 187e9, 35e9, 72e9, 20e9, -4e9, 24e9, 20e9, 8e9, 2.41e9),
    ("JNJ", 2023, 85e9, 28e9, 57e9, 30e9, 22e9, 16e9, 6.53, 190e9, 37e9, 68e9, 23e9, -5e9, 22e9, 17e9, 8e9, 2.42e9),
    ("UNH", 2024, 400e9, 330e9, 70e9, 38e9, 30e9, 22e9, 23.80, 285e9, 55e9, 67e9, 25e9, -4e9, 28e9, 24e9, 8e9, 0.924e9),
    ("UNH", 2023, 372e9, 309e9, 63e9, 34e9, 28e9, 22e9, 23.42, 273e9, 52e9, 65e9, 28e9, -4e9, 25e9, 21e9, 6e9, 0.933e9),
    ("TTE", 2024, 215e9, 175e9, 40e9, 42e9, 28e9, 16e9, 6.84, 290e9, 52e9, 120e9, 32e9, -16e9, 38e9, 22e9, 14e9, 2.34e9),
    ("TTE", 2023, 228e9, 185e9, 43e9, 48e9, 32e9, 21e9, 8.76, 296e9, 48e9, 125e9, 35e9, -17e9, 40e9, 23e9, 16e9, 2.39e9),
    ("MC.PA", 2024, 86e9, 33e9, 53e9, 26e9, 22e9, 14e9, 28.00, 130e9, 28e9, 48e9, 8e9, -5e9, 20e9, 15e9, 4e9, 0.50e9),
    ("MC.PA", 2023, 86e9, 32e9, 54e9, 28e9, 23e9, 15e9, 30.50, 128e9, 26e9, 50e9, 7e9, -6e9, 21e9, 15e9, 5e9, 0.50e9),
    ("BRK-B", 2024, 365e9, 300e9, 65e9, 54e9, 45e9, 97e9, 44.81, 1075e9, 120e9, 612e9, 334e9, -12e9, 47e9, 35e9, 9e9, 2.165e9),
    ("BRK-B", 2023, 364e9, 297e9, 67e9, 53e9, 44e9, 96e9, 42.51, 1002e9, 125e9, 558e9, 168e9, -10e9, 50e9, 40e9, 9e9, 2.26e9),
]

DEALS = [
    dict(acquirer_name="Broadcom Inc.", target_name="VMware, Inc.", announcement_date=date(2024, 11, 22),
         close_date=date(2024, 11, 22), deal_type="Acquisition", status="Completed",
         deal_value=69_000_000_000.0, ev_ebitda_multiple=24.5, ev_revenue_multiple=8.3,
         sector="Technology", country="United States", source="Public Filing",
         description="Broadcom completed its $69B acquisition of VMware, creating a major infrastructure software player."),
    dict(acquirer_name="Exxon Mobil Corporation", target_name="Pioneer Natural Resources", announcement_date=date(2024, 5, 3),
         close_date=date(2024, 5, 3), deal_type="Acquisition", status="Completed",
         deal_value=60_000_000_000.0, ev_ebitda_multiple=7.1, ev_revenue_multiple=3.8,
         sector="Energy", country="United States", source="Public Filing",
         description="ExxonMobil acquired Pioneer Natural Resources in an all-stock deal."),
    dict(acquirer_name="Capital One Financial", target_name="Discover Financial Services", announcement_date=date(2024, 2, 19),
         close_date=None, deal_type="Acquisition", status="Pending",
         deal_value=35_300_000_000.0, ev_revenue_multiple=2.2,
         sector="Financial Services", country="United States", source="Press Release",
         description="Capital One announced acquisition of Discover Financial in an all-stock deal."),
    dict(acquirer_name="Mars, Incorporated", target_name="Kellanova", announcement_date=date(2024, 8, 14),
         close_date=None, deal_type="Acquisition", status="Pending",
         deal_value=35_900_000_000.0, ev_ebitda_multiple=18.2, ev_revenue_multiple=2.4,
         sector="Consumer Staples", country="United States", source="Press Release",
         description="Mars announced $36B acquisition of Kellanova, the largest food deal ever."),
    dict(acquirer_name="Synopsys, Inc.", target_name="Ansys, Inc.", announcement_date=date(2024, 1, 16),
         close_date=None, deal_type="Acquisition", status="Pending",
         deal_value=35_000_000_000.0, ev_ebitda_multiple=43.7, ev_revenue_multiple=15.0,
         sector="Technology", country="United States", source="Public Filing",
         description="Synopsys agreed to acquire Ansys in a cash-and-stock deal."),
    dict(acquirer_name="Johnson & Johnson", target_name="Intra-Cellular Therapies", announcement_date=date(2025, 1, 13),
         close_date=None, deal_type="Acquisition", status="Pending",
         deal_value=14_600_000_000.0, ev_revenue_multiple=25.0,
         sector="Healthcare", country="United States", source="Press Release",
         description="J&J announced acquisition of Intra-Cellular Therapies to boost neuroscience portfolio."),
    dict(acquirer_name="Bain Capital", target_name="Envestnet, Inc.", announcement_date=date(2024, 7, 10),
         close_date=date(2024, 12, 15), deal_type="LBO", status="Completed",
         deal_value=4_500_000_000.0, ev_ebitda_multiple=18.0, ev_revenue_multiple=3.2,
         sector="Financial Services", country="United States", source="Press Release",
         description="Bain Capital completed take-private of Envestnet."),
    dict(acquirer_name="Thoma Bravo", target_name="Darktrace plc", announcement_date=date(2024, 4, 26),
         close_date=date(2024, 10, 1), deal_type="LBO", status="Completed",
         deal_value=5_320_000_000.0, ev_revenue_multiple=7.5,
         sector="Technology", country="United Kingdom", source="Press Release",
         description="Thoma Bravo acquired cybersecurity firm Darktrace in take-private deal."),
    dict(acquirer_name="Blackstone Inc.", target_name="Tropical Smoothie Cafe", announcement_date=date(2024, 8, 1),
         close_date=date(2024, 11, 15), deal_type="LBO", status="Completed",
         deal_value=2_000_000_000.0, ev_ebitda_multiple=22.0,
         sector="Consumer Cyclical", country="United States", source="Press Release",
         description="Blackstone acquired fast-growing franchise Tropical Smoothie Cafe."),
    dict(acquirer_name="Hellman & Friedman", target_name="Worldpay", announcement_date=date(2024, 2, 6),
         close_date=date(2024, 7, 31), deal_type="LBO", status="Completed",
         deal_value=12_500_000_000.0, ev_ebitda_multiple=14.5, ev_revenue_multiple=5.0,
         sector="Financial Services", country="United States", source="Press Release",
         description="GTCR and Hellman & Friedman agreed to acquire a majority stake in Worldpay from FIS."),
    dict(acquirer_name="Reddit, Inc.", target_name=None, announcement_date=date(2024, 3, 21),
         deal_type="IPO", status="Completed", deal_value=748_000_000.0,
         sector="Technology", country="United States", source="SEC Filing",
         description="Reddit completed IPO on NYSE, raising $748M at $34 per share."),
    dict(acquirer_name="Astera Labs", target_name=None, announcement_date=date(2024, 3, 20),
         deal_type="IPO", status="Completed", deal_value=713_000_000.0,
         sector="Technology", country="United States", source="SEC Filing",
         description="Astera Labs IPO priced at $36, shares surged 72% on first day."),
]


async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        # ── Companies ─────────────────────────
        ticker_to_id = {}
        for c in COMPANIES:
            company = Company(**c, updated_at=datetime.utcnow())
            db.add(company)
            await db.flush()
            ticker_to_id[c["ticker"]] = company.id
            print(f"  ✅ {c['ticker']:8s} — {c['name']}")

        # ── Financials ────────────────────────
        for row in FINANCIALS:
            tkr, year, rev, cogs, gp, ebitda, ebit, ni, eps, ta, td, te, cash, capex, ocf, fcf, da, shares = row
            cid = ticker_to_id.get(tkr)
            if not cid:
                continue
            fin = Financial(
                company_id=cid,
                period_type="annual",
                period_end=date(year, 12, 31),
                fiscal_year=year,
                revenue=rev,
                cost_of_revenue=cogs,
                gross_profit=gp,
                ebitda=ebitda,
                ebit=ebit,
                net_income=ni,
                eps=eps,
                total_assets=ta,
                total_debt=td,
                total_equity=te,
                cash_and_equivalents=cash,
                capex=capex,
                operating_cash_flow=ocf,
                free_cash_flow=fcf,
                depreciation_amortization=da,
                shares_outstanding=shares,
            )
            db.add(fin)
        print(f"  📊 {len(FINANCIALS)} financial records inserted")

        await db.flush()

        # ── Ratios (compute from financials) ──
        ratio_count = 0
        for row in FINANCIALS:
            tkr, year, rev, cogs, gp, ebitda, ebit, ni, eps, ta, td, te, cash, capex, ocf, fcf, da, shares = row
            cid = ticker_to_id.get(tkr)
            if not cid:
                continue
            company = [c for c in COMPANIES if c["ticker"] == tkr][0]
            mc = company["market_cap"]
            ev = company.get("enterprise_value") or mc

            # Find previous year revenue for growth
            prev = [r for r in FINANCIALS if r[0] == tkr and r[1] == year - 1]
            prev_rev = prev[0][2] if prev else None

            ratio = FinancialRatio(
                company_id=cid,
                fiscal_year=year,
                revenue_growth=((rev - prev_rev) / abs(prev_rev) * 100) if prev_rev and prev_rev != 0 else None,
                ebitda_growth=None,
                net_income_growth=None,
                gross_margin=(gp / rev * 100) if rev else None,
                ebitda_margin=(ebitda / rev * 100) if rev else None,
                net_margin=(ni / rev * 100) if rev else None,
                fcf_margin=(fcf / rev * 100) if rev else None,
                roe=(ni / te * 100) if te and te != 0 else None,
                roa=(ni / ta * 100) if ta and ta != 0 else None,
                roic=(ebit * 0.75 / (td + te) * 100) if (td + te) != 0 else None,
                debt_to_equity=(td / te) if te and te != 0 else None,
                net_debt_to_ebitda=((td - cash) / ebitda) if ebitda and ebitda != 0 else None,
                current_ratio=None,
                ev_revenue=(ev / rev) if rev and rev != 0 else None,
                ev_ebitda=(ev / ebitda) if ebitda and ebitda != 0 else None,
                pe_ratio=(mc / ni) if ni and ni > 0 else None,
                price_to_book=(mc / te) if te and te != 0 else None,
                fcf_yield=(fcf / mc * 100) if mc and mc != 0 else None,
                dividend_yield=None,
            )
            db.add(ratio)
            ratio_count += 1
        print(f"  📈 {ratio_count} ratio records inserted")

        # ── Deals ────────────────────────────
        for d in DEALS:
            deal = Deal(**d)
            db.add(deal)
        print(f"  🤝 {len(DEALS)} deal records inserted")

        await db.commit()
        print("\n🎉 Seed completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
