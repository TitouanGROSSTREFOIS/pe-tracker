"""
Data Ingestion Service — yfinance wrapper
Fetches company info, financials, and market data from Yahoo Finance.

Depuis la Tâche B.3 (D13) : Financial Modeling Prep (FMP) est la source
PRIMAIRE pour le profil `Company` (voir fmp_connector.py), yfinance passe en
repli — pour le profil ET pour la totalité des états financiers (`Financial`),
que FMP ne fournit pas sur le plan gratuit constaté (voir fmp_connector.py).

Depuis la Tâche B.4 (A.3) : lorsque yfinance échoue (blocage HTTP 429
confirmé, voir RAPPORT SPRINT B.4 §A.1) et ne peut donc fournir aucun état
financier, un repli supplémentaire tente Finnhub puis Alpha Vantage pour
reconstituer un unique exercice exploitable (`enterprise_value` + `ebitda`
via Finnhub, `revenue` via Alpha Vantage) — UNIQUEMENT pour les tickers
cotés aux États-Unis, seuls couverts par les plans gratuits de ces deux
fournisseurs (voir finnhub_connector.py / alphavantage_connector.py). Pour
tout autre ticker, aucun état financier n'est produit — pas d'estimation de
substitution. La logique de calcul des ratios (_compute_ratios) n'est PAS
modifiée.
"""
from __future__ import annotations
import asyncio
from datetime import date, datetime
from typing import Any

import pandas as pd
import yfinance as yf
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.company import Company
from api.models.financial import Financial, FinancialRatio
from api.services.ma_engine.fmp_connector import fetch_fmp_profile
from api.services.ma_engine.finnhub_connector import fetch_finnhub_financials
from api.services.ma_engine.alphavantage_connector import fetch_alphavantage_financials
from api.schemas.provenance import DataProvenance, FieldProvenance


# ─────────────────────────────────────────────
# Yahoo Finance data extraction helpers
# ─────────────────────────────────────────────

def _fetch_yf_data(ticker: str, max_retries: int = 3) -> dict[str, Any]:
    """Synchronous yfinance fetch (runs in executor) with retry on 429."""
    import time
    last_exc = None
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}

            # Financial statements — pandas DataFrames
            try:
                income_stmt = t.income_stmt  # annual
            except Exception:
                income_stmt = pd.DataFrame()

            try:
                balance_sheet = t.balance_sheet
            except Exception:
                balance_sheet = pd.DataFrame()

            try:
                cash_flow = t.cashflow
            except Exception:
                cash_flow = pd.DataFrame()

            return {
                "info": info,
                "income_stmt": income_stmt,
                "balance_sheet": balance_sheet,
                "cash_flow": cash_flow,
            }
        except Exception as e:
            last_exc = e
            wait = 2 ** attempt * 2  # 2s, 4s, 8s
            logger.warning(f"⏳ yfinance {ticker} attempt {attempt+1} failed: {e}. Retrying in {wait}s…")
            time.sleep(wait)

    raise last_exc or RuntimeError(f"Failed to fetch {ticker} after {max_retries} retries")


def _safe(d: dict, key: str, default=None):
    """Safely extract a value from yfinance info dict."""
    v = d.get(key, default)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    return v


def _safe_float(d: dict, key: str) -> float | None:
    v = _safe(d, key)
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _market_provenance(*fields_and_sources: tuple[str, str | None, object]) -> dict[str, dict]:
    """Construit un dict de provenance MARKET (D19, Tâche B.7) pour les
    champs `Financial` effectivement peuplés. `fields_and_sources` est une
    liste de (nom_du_champ, nom_de_la_source, valeur) — ignoré si valeur ou
    source est None (rien à qualifier)."""
    prov: dict[str, dict] = {}
    for field, src, val in fields_and_sources:
        if val is not None and src is not None:
            prov[field] = FieldProvenance(provenance=DataProvenance.MARKET, reference=src).model_dump(mode="json")
    return prov


def _df_val(df: pd.DataFrame, label: str, col_idx: int = 0) -> float | None:
    """Extract a value from a yfinance DataFrame by row label and column index."""
    if df is None or df.empty:
        return None
    # yfinance DataFrames have dates as columns, items as rows
    for row_label in df.index:
        if isinstance(row_label, str) and label.lower() in row_label.lower():
            try:
                val = df.iloc[df.index.get_loc(row_label), col_idx]
                if pd.notna(val):
                    return float(val)
            except (IndexError, KeyError):
                pass
    return None


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

async def ingest_company(ticker: str, db: AsyncSession) -> Company:
    """
    Fetch or update a company and its financials.

    Source des données (D13, Tâche B.3 ; étendu Tâche B.4, A.3) :
        - Profil (`Company`) : FMP en priorité, yfinance en repli. Si ni
          l'un ni l'autre ne fournit `enterprise_value`/`market_cap`
          (FMP ne les expose pas, yfinance est bloqué), Finnhub comble ces
          deux champs — mais UNIQUEMENT pour les tickers cotés aux
          États-Unis (seuls couverts par son plan gratuit).
        - États financiers (`Financial`) : yfinance en priorité (5 exercices
          si disponible). S'il échoue, repli sur Finnhub (`ebitda`) + Alpha
          Vantage (`revenue`) — un seul exercice, uniquement pour les
          tickers US (voir finnhub_connector.py / alphavantage_connector.py).
          Si aucune des trois sources ne couvre le ticker (cas de tous les
          comparables non-US du CompSet TIC), aucun `Financial` n'est créé —
          pas d'estimation de repli, l'absence est documentée dans les
          stats appelantes plutôt que masquée.

    Returns Company ORM object.
    """
    ticker = ticker.upper().strip()
    logger.info(f"📡 Ingesting data for {ticker}...")

    fmp_info = await fetch_fmp_profile(ticker)

    # Les états financiers (income/balance/cash-flow) viennent TOUJOURS de
    # yfinance (FMP ne les fournit pas sur ce plan) — sauf s'il est bloqué,
    # auquel cas on continue avec le seul profil FMP si disponible.
    loop = asyncio.get_event_loop()
    yf_raw: dict[str, Any] | None
    try:
        yf_raw = await loop.run_in_executor(None, _fetch_yf_data, ticker)
    except Exception as exc:
        logger.warning(f"  ⚠️ yfinance indisponible pour {ticker} ({exc}) — "
                        f"{'profil FMP conservé, ' if fmp_info else ''}aucun état financier ingéré.")
        yf_raw = None

    if fmp_info:
        info = fmp_info
        logger.info(f"  ✅ Profil source : FMP")
    elif yf_raw:
        info = yf_raw["info"]
        logger.info(f"  ✅ Profil source : yfinance (repli)")
    else:
        raise ValueError(f"Ticker '{ticker}' introuvable : FMP et yfinance indisponibles.")

    if not info.get("shortName") and not info.get("longName"):
        raise ValueError(f"Ticker '{ticker}' not found")

    raw = yf_raw or {"income_stmt": pd.DataFrame(), "balance_sheet": pd.DataFrame(), "cash_flow": pd.DataFrame()}

    # ── Repli Finnhub / Alpha Vantage (Tâche B.4, A.3) ──────────────────
    # Uniquement si yfinance n'a fourni aucun état financier — pour ne pas
    # consommer inutilement le quota Alpha Vantage (25 req/jour, très
    # restrictif, voir alphavantage_connector.py) quand yfinance suffit déjà.
    finnhub_fin: dict[str, Any] | None = None
    av_fin: dict[str, Any] | None = None
    if raw["income_stmt"].empty:
        finnhub_fin = await fetch_finnhub_financials(ticker)
        if finnhub_fin:
            logger.info(f"  ✅ Finnhub : enterprise_value + EBITDA {finnhub_fin['fiscal_year']} récupérés")
            av_fin = await fetch_alphavantage_financials(ticker)
            if av_fin:
                logger.info(f"  ✅ Alpha Vantage : revenue TTM récupéré")

    # ── Provenance (D19, Tâche B.7) : quelle source a réellement fourni
    #    chaque champ, dans le même ordre de priorité que la résolution
    #    ci-dessous — évite de dupliquer la logique de repli en la
    #    recalculant, on capture juste la source au moment du choix.
    profile_source = "FMP" if fmp_info else ("yfinance" if yf_raw else None)

    market_cap_val = _safe_float(info, "marketCap")
    market_cap_src = profile_source if market_cap_val is not None else None
    if market_cap_val is None and finnhub_fin:
        market_cap_val, market_cap_src = finnhub_fin["market_cap"], "Finnhub"

    ev_val = _safe_float(info, "enterpriseValue")
    ev_src = profile_source if ev_val is not None else None
    if ev_val is None and finnhub_fin:
        ev_val, ev_src = finnhub_fin["enterprise_value"], "Finnhub"

    shares_val = _safe_float(info, "sharesOutstanding")
    shares_src = profile_source if shares_val is not None else None
    if shares_val is None and av_fin:
        shares_val, shares_src = av_fin["shares_outstanding"], "Alpha Vantage"

    # ── Upsert Company ──────────────────────────
    result = await db.execute(select(Company).where(Company.ticker == ticker))
    company = result.scalar_one_or_none()

    company_data = dict(
        ticker=ticker,
        name=_safe(info, "longName") or _safe(info, "shortName", ticker),
        sector=_safe(info, "sector"),
        industry=_safe(info, "industry"),
        country=_safe(info, "country"),
        exchange=_safe(info, "exchange"),
        currency=_safe(info, "currency", "USD"),
        market_cap=market_cap_val,
        enterprise_value=ev_val,
        description=_safe(info, "longBusinessSummary"),
        employees=_safe(info, "fullTimeEmployees"),
        website=_safe(info, "website"),
        last_price=_safe_float(info, "currentPrice") or _safe_float(info, "regularMarketPrice"),
        shares_outstanding=shares_val,
        updated_at=datetime.utcnow(),
    )

    company_provenance = dict((company.financial_provenance or {}) if company else {})
    for field, val, src in (
        ("market_cap", market_cap_val, market_cap_src),
        ("enterprise_value", ev_val, ev_src),
        ("shares_outstanding", shares_val, shares_src),
    ):
        if val is not None and src is not None:
            company_provenance[field] = FieldProvenance(
                provenance=DataProvenance.MARKET, reference=src,
            ).model_dump(mode="json")

    if company:
        for k, v in company_data.items():
            if v is not None:
                setattr(company, k, v)
        company.financial_provenance = company_provenance
        logger.info(f"  ✅ Updated company: {company.name}")
    else:
        company = Company(**company_data, financial_provenance=company_provenance)
        db.add(company)
        logger.info(f"  ✅ Created company: {company_data['name']}")

    await db.flush()  # get company.id

    # ── Ingest Financial Statements ─────────────
    is_df = raw["income_stmt"]
    bs_df = raw["balance_sheet"]
    cf_df = raw["cash_flow"]

    if not is_df.empty:
        n_periods = min(len(is_df.columns), 5)  # up to 5 years
        for col_idx in range(n_periods):
            col_date = is_df.columns[col_idx]
            period_end = col_date.date() if hasattr(col_date, "date") else date(col_date.year, 12, 31)
            fiscal_year = period_end.year

            # Check if already exists
            existing = await db.execute(
                select(Financial).where(
                    Financial.company_id == company.id,
                    Financial.period_type == "annual",
                    Financial.fiscal_year == fiscal_year,
                )
            )
            fin = existing.scalar_one_or_none()

            _revenue = _df_val(is_df, "Total Revenue", col_idx)
            _ebitda = _df_val(is_df, "EBITDA", col_idx)
            _net_income = _df_val(is_df, "Net Income", col_idx)

            fin_data = dict(
                company_id=company.id,
                period_type="annual",
                period_end=period_end,
                fiscal_year=fiscal_year,
                financial_provenance=_market_provenance(
                    ("revenue", "yfinance", _revenue),
                    ("ebitda", "yfinance", _ebitda),
                    ("net_income", "yfinance", _net_income),
                ),
                # Income Statement
                revenue=_revenue,
                cost_of_revenue=_df_val(is_df, "Cost Of Revenue", col_idx),
                gross_profit=_df_val(is_df, "Gross Profit", col_idx),
                operating_expenses=_df_val(is_df, "Operating Expense", col_idx),
                sga=_df_val(is_df, "Selling General And Administration", col_idx),
                rd_expense=_df_val(is_df, "Research And Development", col_idx),
                depreciation_amortization=_df_val(is_df, "Reconciled Depreciation", col_idx),
                ebitda=_ebitda,
                ebit=_df_val(is_df, "EBIT", col_idx),
                interest_expense=_df_val(is_df, "Interest Expense", col_idx),
                pretax_income=_df_val(is_df, "Pretax Income", col_idx),
                income_tax=_df_val(is_df, "Tax Provision", col_idx),
                net_income=_net_income,
                # Balance Sheet
                total_assets=_df_val(bs_df, "Total Assets", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                current_assets=_df_val(bs_df, "Current Assets", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                cash_and_equivalents=_df_val(bs_df, "Cash And Cash Equivalents", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                total_liabilities=_df_val(bs_df, "Total Liabilities", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                current_liabilities=_df_val(bs_df, "Current Liabilities", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                total_debt=_df_val(bs_df, "Total Debt", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                long_term_debt=_df_val(bs_df, "Long Term Debt", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                total_equity=_df_val(bs_df, "Total Equity", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                goodwill=_df_val(bs_df, "Goodwill", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                intangible_assets=_df_val(bs_df, "Intangible Assets", col_idx) if not bs_df.empty and col_idx < len(bs_df.columns) else None,
                # Cash Flow
                operating_cash_flow=_df_val(cf_df, "Operating Cash Flow", col_idx) if not cf_df.empty and col_idx < len(cf_df.columns) else None,
                capex=_df_val(cf_df, "Capital Expenditure", col_idx) if not cf_df.empty and col_idx < len(cf_df.columns) else None,
                free_cash_flow=_df_val(cf_df, "Free Cash Flow", col_idx) if not cf_df.empty and col_idx < len(cf_df.columns) else None,
                dividends_paid=_df_val(cf_df, "Common Stock Dividend", col_idx) if not cf_df.empty and col_idx < len(cf_df.columns) else None,
                share_buybacks=_df_val(cf_df, "Repurchase Of Capital Stock", col_idx) if not cf_df.empty and col_idx < len(cf_df.columns) else None,
                # Per-share
                shares_outstanding=_safe_float(info, "sharesOutstanding"),
                eps=_df_val(is_df, "Basic EPS", col_idx),
                updated_at=datetime.utcnow(),
            )

            if fin:
                for k, v in fin_data.items():
                    if v is not None and k != "company_id":
                        setattr(fin, k, v)
            else:
                fin = Financial(**fin_data)
                db.add(fin)

        logger.info(f"  📊 Ingested {n_periods} annual periods")
    elif finnhub_fin:
        # Repli Finnhub/Alpha Vantage (Tâche B.4, A.3) : un seul exercice,
        # champs limités à ce que ces deux sources exposent réellement en
        # valeur absolue sur leur plan gratuit — le reste (dette, cash,
        # équité...) reste None, pas d'estimation de substitution.
        fiscal_year = finnhub_fin["fiscal_year"]
        existing = await db.execute(
            select(Financial).where(
                Financial.company_id == company.id,
                Financial.period_type == "annual",
                Financial.fiscal_year == fiscal_year,
            )
        )
        fin = existing.scalar_one_or_none()

        fin_data = dict(
            company_id=company.id,
            period_type="annual",
            period_end=date(fiscal_year, 12, 31),
            fiscal_year=fiscal_year,
            ebitda=finnhub_fin["ebitda"],
            revenue=av_fin["revenue"] if av_fin else None,
            shares_outstanding=(av_fin["shares_outstanding"] if av_fin else None) or _safe_float(info, "sharesOutstanding"),
            financial_provenance=_market_provenance(
                ("ebitda", "Finnhub", finnhub_fin["ebitda"]),
                ("revenue", "Alpha Vantage", av_fin["revenue"] if av_fin else None),
            ),
            updated_at=datetime.utcnow(),
        )
        if fin:
            for k, v in fin_data.items():
                if v is not None and k != "company_id":
                    setattr(fin, k, v)
        else:
            fin = Financial(**fin_data)
            db.add(fin)
        logger.info(
            f"  📊 Repli Finnhub/Alpha Vantage : exercice {fiscal_year} seul "
            f"(EBITDA={'oui' if finnhub_fin['ebitda'] else 'non'}, "
            f"CA={'oui' if av_fin and av_fin['revenue'] else 'non'})"
        )
    else:
        logger.warning(f"  ⚠️ No income statement data for {ticker}")

    await db.flush()

    # ── Compute Ratios ──────────────────────────
    await _compute_ratios(company.id, db)

    await db.commit()
    logger.info(f"  ✅ Ingestion complete for {ticker}")

    # Refresh to load relationships
    await db.refresh(company)
    return company


async def _compute_ratios(company_id: int, db: AsyncSession):
    """Compute financial ratios from stored financial statements."""
    result = await db.execute(
        select(Financial)
        .where(Financial.company_id == company_id, Financial.period_type == "annual")
        .order_by(Financial.fiscal_year.desc())
    )
    financials = list(result.scalars().all())
    if not financials:
        return

    # Get company for market data
    company = await db.get(Company, company_id)
    ev = company.enterprise_value if company else None
    mcap = company.market_cap if company else None

    for i, fin in enumerate(financials):
        fy = fin.fiscal_year

        # Previous year for growth calcs
        prev = financials[i + 1] if i + 1 < len(financials) else None

        # Growth
        rev_growth = _pct_change(fin.revenue, prev.revenue if prev else None)
        ebitda_growth = _pct_change(fin.ebitda, prev.ebitda if prev else None)
        ni_growth = _pct_change(fin.net_income, prev.net_income if prev else None)

        # Margins
        gross_m = _divide(fin.gross_profit, fin.revenue) * 100 if fin.gross_profit and fin.revenue else None
        ebitda_m = _divide(fin.ebitda, fin.revenue) * 100 if fin.ebitda and fin.revenue else None
        ebit_m = _divide(fin.ebit, fin.revenue) * 100 if fin.ebit and fin.revenue else None
        net_m = _divide(fin.net_income, fin.revenue) * 100 if fin.net_income and fin.revenue else None
        fcf_m = _divide(fin.free_cash_flow, fin.revenue) * 100 if fin.free_cash_flow and fin.revenue else None

        # Returns
        roe = _divide(fin.net_income, fin.total_equity) * 100 if fin.net_income and fin.total_equity else None
        roa = _divide(fin.net_income, fin.total_assets) * 100 if fin.net_income and fin.total_assets else None
        # ROIC = NOPAT / Invested Capital (simplified)
        invested_cap = (fin.total_equity or 0) + (fin.total_debt or 0) - (fin.cash_and_equivalents or 0)
        nopat = fin.ebit * 0.75 if fin.ebit else None  # assume ~25% tax rate
        roic = _divide(nopat, invested_cap) * 100 if nopat and invested_cap and invested_cap > 0 else None

        # Leverage
        d_to_e = _divide(fin.total_debt, fin.total_equity) if fin.total_debt and fin.total_equity else None
        net_debt = (fin.total_debt or 0) - (fin.cash_and_equivalents or 0)
        nd_ebitda = _divide(net_debt, fin.ebitda) if fin.ebitda and fin.ebitda > 0 else None
        int_cov = _divide(fin.ebit, abs(fin.interest_expense)) if fin.ebit and fin.interest_expense and fin.interest_expense != 0 else None
        cur_ratio = _divide(fin.current_assets, fin.current_liabilities) if fin.current_assets and fin.current_liabilities else None

        # Valuation (only for most recent year with EV data)
        ev_rev = _divide(ev, fin.revenue) if ev and fin.revenue and i == 0 else None
        ev_ebitda_r = _divide(ev, fin.ebitda) if ev and fin.ebitda and fin.ebitda > 0 and i == 0 else None
        pe = _divide(mcap, fin.net_income) if mcap and fin.net_income and fin.net_income > 0 and i == 0 else None
        p_to_b = _divide(mcap, fin.total_equity) if mcap and fin.total_equity and fin.total_equity > 0 and i == 0 else None
        p_to_s = _divide(mcap, fin.revenue) if mcap and fin.revenue and i == 0 else None
        fcf_yield = _divide(fin.free_cash_flow, mcap) * 100 if fin.free_cash_flow and mcap and mcap > 0 and i == 0 else None
        div_yield = _divide(abs(fin.dividends_paid or 0), mcap) * 100 if fin.dividends_paid and mcap and mcap > 0 and i == 0 else None

        # Upsert ratio
        existing = await db.execute(
            select(FinancialRatio).where(
                FinancialRatio.company_id == company_id,
                FinancialRatio.fiscal_year == fy,
            )
        )
        ratio = existing.scalar_one_or_none()

        ratio_data = dict(
            company_id=company_id,
            fiscal_year=fy,
            revenue_growth=rev_growth,
            ebitda_growth=ebitda_growth,
            net_income_growth=ni_growth,
            gross_margin=gross_m,
            ebitda_margin=ebitda_m,
            ebit_margin=ebit_m,
            net_margin=net_m,
            fcf_margin=fcf_m,
            roe=roe,
            roa=roa,
            roic=roic,
            debt_to_equity=d_to_e,
            net_debt_to_ebitda=nd_ebitda,
            interest_coverage=int_cov,
            current_ratio=cur_ratio,
            ev_revenue=ev_rev,
            ev_ebitda=ev_ebitda_r,
            pe_ratio=pe,
            price_to_book=p_to_b,
            price_to_sales=p_to_s,
            fcf_yield=fcf_yield,
            dividend_yield=div_yield,
            updated_at=datetime.utcnow(),
        )

        if ratio:
            for k, v in ratio_data.items():
                if k != "company_id":
                    setattr(ratio, k, v)
        else:
            ratio = FinancialRatio(**ratio_data)
            db.add(ratio)

    logger.info(f"  📐 Computed ratios for {len(financials)} years")


async def ingest_batch(tickers: list[str], db: AsyncSession) -> dict[str, str]:
    """Ingest multiple companies with delays to avoid Yahoo rate limits."""
    results = {}
    for i, ticker in enumerate(tickers):
        try:
            await ingest_company(ticker, db)
            results[ticker] = "ok"
        except Exception as e:
            logger.error(f"❌ Failed to ingest {ticker}: {e}")
            results[ticker] = f"error: {str(e)[:100]}"
        # Delay between tickers to avoid 429 rate limits
        if i < len(tickers) - 1:
            await asyncio.sleep(2)
    return results


# ─────────────────────────────────────────────
# Math helpers
# ─────────────────────────────────────────────

def _divide(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100
