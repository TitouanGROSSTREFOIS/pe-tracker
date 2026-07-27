# PE Tracker

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Node 18+](https://img.shields.io/badge/node-18%2B-green.svg)
![React 19](https://img.shields.io/badge/react-19-61dafb.svg)

**An operational terminal for M&A / Private Equity deal analysis, from first
target sourcing to the investment committee memo — built entirely on free,
public data sources.**

## The gap it fills

A small investment team (PE fund, corporate development) prospecting the
French sub-€10M mid-market rarely has a Bloomberg or Capital IQ subscription,
or a pre-built database of private comparables. PE Tracker reconstructs that
workflow from public and free sources, on a deliberately narrow sector thesis:
**TIC (Testing, Inspection, Certification) and technical engineering**.

The differentiator isn't the LBO math (standard) — it's that **every figure on
screen carries its provenance**. Nothing is presented as a fact without being
able to say where it came from (official registry, uploaded document, market
data provider, model estimate, manual entry), and no simulated/mock value is
ever shown without an explicit label. See [Provenance tracking](#provenance-tracking) below.

## What it does, end to end

1. **Sourcing** — identifies real targets by industry code (NAF) and size in
   France's official company registry, not keyword search as an entry point.
2. **Qualification** — filters and scores targets by sector fit and revenue
   size.
3. **AI-assisted spreading** — extracts financial data from a teaser or PDF
   report automatically, with mandatory human review before anything is
   saved.
4. **Calibrated valuation** — builds a universe of listed comparables
   (Europe/US) from real market data and derives a sector entry multiple from
   it, rather than a hardcoded number.
5. **LBO modeling** — multi-tranche engine (senior/mezzanine debt, cash
   sweep, exit waterfall), saveable scenarios, Excel export with live
   formulas.
6. **IC memo** — generates a written investment committee memo from the deal,
   the reference LBO scenario and the comparables, citing every figure's
   origin.

The full pipeline (deals, portfolio, comparables, LBO, memos) is driven from a
single dashboard.

## Status: personal project, proof of concept

This is a solo side project, not a commercial product and not affiliated with
Anthropic or any investment fund. It was built to explore how far an
AI-assisted workflow can go using only free data sources, and the limitations
below are deliberate, not hidden:

- No real structured EBITDA for non-listed French targets exists on any free
  source checked so far (see [Assumed limitations](#assumed-limitations)) —
  those figures are clearly labeled `ESTIMATE`, never presented as real.
- The sector thesis (TIC / technical engineering) is intentionally narrow; it
  is not a general-purpose multi-sector tool.
- Portfolio monitoring is read-only illustration, not a production tracking
  flow.

## Architecture

The repository contains **two backends with strictly separated scopes**, and
one frontend.

| Service | Stack | Port | Role |
|---|---|---|---|
| `api/` | FastAPI (Python) | 8000 | **Single source of truth for the entire M&A domain**: deals, sourcing, portfolio, comparables, LBO, IC memos, activity log. |
| `backend/` | Express (Node/TypeScript) | 3001 | **Market / Macro / News layer only**: market quotes (direct Yahoo Finance Chart API scrape), central bank rates / yield curve / credit spreads / Euribor (FRED), news feed (NewsAPI). |
| `pe-market-intelligence-terminal/` | React 19 + Vite + TypeScript | 3000 | Frontend. Consumes both backends via [services/apiService.ts](pe-market-intelligence-terminal/services/apiService.ts). |

This separation is strict and intentional: `backend/` never serves M&A
routes. Everything related to deals, sourcing, portfolio or LBO lives in
`api/`. Without the Express service, the Market Intelligence banner, Credit &
Macro and Money Market screens stay incomplete; the rest of the app (deals,
sourcing, portfolio, comps, LBO) only depends on FastAPI.

## Functional modules

**Sourcing** — The target universe comes primarily from the official French
company registry (Sirene / Recherche d'Entreprises API), filtered by industry
code and size — not keyword discovery. Each target is scored two ways:
deterministic sector fit (NAF code) + real revenue-based sizing from the
registry + an LLM strategic-fit note. An optional free-search mode ("Radar",
TF-IDF + LLM) exists but isn't the default. A Kanban pipeline tracks
qualification through promotion to an active deal.

**Spreading (document ingestion)** — Upload a teaser or PDF report; an LLM
extracts financial data with one hard rule: **never infer an EBITDA that
isn't in the document**. A server-side plausibility check (margin bounds,
scale-factor detection) flags suspicious extractions without ever silently
correcting them; human review in a dedicated modal is mandatory before saving.

**Comparables (Comps Engine)** — Builds a universe of listed comparables from
real market data (profile, price, market cap, financial statements). Each row
shows its per-field provenance and fiscal year. Read-only dedicated page.

**Sector calibration** — The TIC sector's LBO entry multiple isn't a hardcoded
constant: it's derived dynamically from the real comp set's median
EV/EBITDA (minus a named, adjustable size/illiquidity discount), with an
explicit fallback flagged when the sample of comparables with real EBITDA is
insufficient.

**LBO** — Multi-tranche engine (senior/mezzanine debt, seniority-ordered cash
sweep, exit waterfall), optional sector calibration, saveable/reloadable
scenarios, Excel export with live formulas (the workbook recalculates in
Excel if an assumption changes).

**IC Memo** — Generates a Markdown investment committee memo from the deal,
the reference LBO scenario and the comparables — every cited figure carries
its provenance; the prompt explicitly forbids inventing a scenario or a
missing figure.

**Portfolio** — Post-acquisition monitoring by monthly KPIs. Read-only on the
API side today (no creation route exists yet): the data shown illustrates the
monitoring screen, not a real production data-entry flow.

## Data sources

All sources listed are free (free tier or no account required). Connectors
live in [api/services/ma_engine/](api/services/ma_engine/) on the FastAPI
side and [backend/routes/](backend/routes/) on the Express side.

| Source | Role | Key required |
|---|---|---|
| Recherche d'Entreprises (Sirene/INSEE) | Sourcing universe (NAF, real revenue) | No |
| ESEF/XBRL (`filings.xbrl.org`) | Real financial statements for listed European issuers (Comps Engine) | No |
| Financial Modeling Prep (FMP) | `Company` profile (price, market cap, sector) for the Comps Engine | Optional (falls back to yfinance) |
| Finnhub | Enterprise value + EBITDA for the Comps Engine — **US-listed tickers only** on the free plan | Optional |
| Alpha Vantage | Revenue for the Comps Engine — **US only**, 25 requests/day quota | Optional |
| OpenAI | Document extraction, IC memo generation, sourcing scoring | **Required** |
| FRED | Central bank rates, yield curve, credit spreads, Euribor (Express) | Optional (falls back to static data) |
| NewsAPI | PE news feed (Express) | Optional (empty list if absent) |
| Serper.dev | Google search (sourcing Radar, financial-estimate fallback) | Optional |
| Adzuna | HR/hiring signals for a sourced target | Optional (mock if absent) |
| BuiltWith | Tech stack (Digital DD) for a sourced target | Optional (mock if absent) |

The exact list of environment variables (names, required/optional, where to
get each key) is in [RUNBOOK.md](RUNBOOK.md), and template files are provided
at [api/.env.example](api/.env.example) and
[backend/.env.example](backend/.env.example).

## Provenance tracking

Every stored financial figure (revenue, EBITDA, enterprise value, derived
multiples) carries a provenance tag out of six
([api/schemas/provenance.py](api/schemas/provenance.py)):

| Provenance | Meaning |
|---|---|
| `REGISTRY` | Official filed accounts (company registry, INPI) |
| `DOCUMENT` | Extracted from an uploaded document (teaser, annual report) |
| `MARKET` | From a market data provider (FMP, Finnhub, ESEF) |
| `ESTIMATE` | Derived from an assumption or a calculation rule |
| `MANUAL` | Entered or corrected by the user |
| `UNKNOWN` | Origin cannot be determined — never guessed |

A calculated multiple inherits the weakest provenance of its components (an
EV/EBITDA computed on an `ESTIMATE` EBITDA is itself `ESTIMATE`, even if the
EV was `REGISTRY`). Provenance is shown on screen (`ProvenanceBadge`) and
carried into the IC memo prompt. More broadly, **no simulated data is ever
shown without a label**: modules that fall back to mock data (Digital DD,
Legal Watch, Talent Signals, fallback comparables) say so explicitly on
screen ("MOCK DATA" / "FALLBACK DATA" badge).

## Assumed limitations

- **No real structured EBITDA for non-listed French targets**: checked
  against several free sources (official registry, business directories) —
  none expose the operating result or depreciation add-backs needed to
  reconstruct it. Only the INPI filed-accounts API would allow it; documented
  but not yet implemented (approval-gated account, application pending).
- **Partial European comparables**: some listed comparables in the TIC comp
  set still have no real EV/EBITDA (outside ESEF/EU-UK coverage, or D&A not
  isolable in a proprietary IFRS taxonomy) — no substitute estimate is
  generated for those rows; they stay explicitly empty rather than guessed.
- **Illustrative portfolio module**: Portfolio Monitoring is read-only on the
  API side (no company or KPI creation route) — visible data illustrates the
  screen, not a real production tracking flow.
- **Known non-batched network call**: the Deal Pipeline screen fires one
  Adzuna call per displayed target on every page load (no server-side
  cache), which can slow the screen down on a large pipeline.
- **Optional keyword-based sourcing (Radar)** exists but isn't the default
  mode: the TF-IDF it relies on proved unsuited to the registry path
  (scraped-page comparison, not structured summaries).

## Installation

See [RUNBOOK.md](RUNBOOK.md) for full setup instructions (prerequisites,
environment variables, first run, common errors). Quick start once
prerequisites are installed:

```bash
./start.sh
```

This starts all three services (FastAPI :8000, Express :3001, Vite :3000)
with prefixed logs and clean shutdown on Ctrl+C.

## License

[MIT](LICENSE) — © 2026 Titouan.

## More documentation

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — one-page pitch (French).
- [RUNBOOK.md](RUNBOOK.md) — installation, startup, environment variables,
  common errors.
- [pitch/PE_Tracker_Script_Demo.md](pitch/PE_Tracker_Script_Demo.md) — a
  narrated demo walkthrough script.
