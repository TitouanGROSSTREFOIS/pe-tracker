"""Tâche B.4 — Banc d'essai Finnhub / Alpha Vantage / FMP sur les 14 tickers TIC validés (Tâche B.1).

Objectif : mesurer empiriquement, sur le plan GRATUIT de chaque fournisseur, ce qui est
réellement accessible (reconnaissance du ticker, capitalisation, valeur d'entreprise,
CA, EBITDA, dette nette, résultat net, actions en circulation, profondeur historique)
avant toute décision d'intégration (A.3). Aucune estimation de substitution : chaque
case du tableau final reflète un appel HTTP réel, pas une supposition.

Usage :
    ./.venv/bin/python3 scripts/benchmark_market_data.py

Le budget Alpha Vantage gratuit est de 25 requêtes/jour (mesuré empiriquement dans ce
script — voir message d'erreur "Information" renvoyé par l'API en cas de dépassement).
Ce script est donc volontairement économe : un seul appel OVERVIEW par ticker, sur la
convention de symbole la plus probable, sans recherche exploratoire de variantes.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.config import get_settings  # noqa: E402

settings = get_settings()
FINNHUB_KEY = settings.finnhub_api_key
AV_KEY = settings.alphavantage_api_key
FMP_KEY = settings.fmp_api_key

TICKERS = [
    "BVI.PA", "SGSN.SW", "ERF.PA", "ITRK.L", "ALQ.AX", "MG", "CLB",
    "ATE.PA", "ASY.PA", "SPIE.PA", "WSP.TO", "STN.TO", "ATRL.TO", "J",
]

# Convention de symbole la plus probable pour Alpha Vantage (suffixes documentés AV).
# Les tickers US (MG, CLB, J) sont utilisés tels quels.
AV_SYMBOL_GUESS = {
    "BVI.PA": "BVI.PAR", "SGSN.SW": "SGSN.SWI", "ERF.PA": "ERF.PAR",
    "ITRK.L": "ITRK.LON", "ALQ.AX": "ALQ.AUS", "MG": "MG", "CLB": "CLB",
    "ATE.PA": "ATE.PAR", "ASY.PA": "ASY.PAR", "SPIE.PA": "SPIE.PAR",
    "WSP.TO": "WSP.TRT", "STN.TO": "STN.TRT", "ATRL.TO": "ATRL.TRT", "J": "J",
}

client = httpx.Client(timeout=20)
results: dict[str, dict] = {t: {"finnhub": {}, "alphavantage": {}, "fmp": {}} for t in TICKERS}


def finnhub_get(path: str, **params):
    params["token"] = FINNHUB_KEY
    r = client.get(f"https://finnhub.io/api/v1/{path}", params=params)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def av_get(**params):
    params["apikey"] = AV_KEY
    r = client.get("https://www.alphavantage.co/query", params=params)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def fmp_get(path: str, **params):
    params["apikey"] = FMP_KEY
    r = client.get(f"https://financialmodelingprep.com/stable/{path}", params=params)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


print("=" * 100)
print("FINNHUB — profile2 (identité/capi) + metric?metric=all (fondamentaux) pour les 14 tickers")
print("=" * 100)
for t in TICKERS:
    sc1, profile = finnhub_get("stock/profile2", symbol=t)
    sc2, metric = finnhub_get("stock/metric", symbol=t, metric="all")
    recognized = bool(profile) and isinstance(profile, dict) and "name" in profile
    m = metric.get("metric", {}) if isinstance(metric, dict) else {}
    results[t]["finnhub"] = {
        "profile_status": sc1, "recognized": recognized,
        "marketCapitalization": profile.get("marketCapitalization") if recognized else None,
        "shareOutstanding": profile.get("shareOutstanding") if recognized else None,
        "currency": profile.get("currency") if recognized else None,
        "metric_status": sc2,
        "metric_keys_sample": sorted(m.keys())[:8] if m else [],
        "ebitda_ttm_in_metric": any("ebitda" in k.lower() for k in m.keys()),
        "revenue_in_metric": any("revenue" in k.lower() for k in m.keys()),
        "netMargin": m.get("netProfitMarginTTM"),
    }
    print(f"{t:10s} profile2={sc1} recognized={recognized} marketCap={profile.get('marketCapitalization') if recognized else '-'} metric={sc2} keys~{len(m)}")
    time.sleep(0.15)

print()
print("=" * 100)
print("FINNHUB — tentative d'accès aux états financiers (souvent premium) : /stock/financials-reported")
print("=" * 100)
for t in TICKERS[:3] + ["MG"]:  # échantillon, pour ne pas multiplier les appels inutilement
    sc, data = finnhub_get("stock/financials-reported", symbol=t, freq="annual")
    n_reports = len(data.get("data", [])) if isinstance(data, dict) else 0
    print(f"{t:10s} status={sc} n_reports={n_reports} sample_error={data if sc != 200 else ''}")

print()
print("=" * 100)
print(f"ALPHA VANTAGE — OVERVIEW (1 appel/ticker, budget 25/jour, symboles devinés) pour les 14 tickers")
print("=" * 100)
av_calls_used = 0
for t in TICKERS:
    symbol = AV_SYMBOL_GUESS[t]
    sc, data = av_get(function="OVERVIEW", symbol=symbol)
    av_calls_used += 1
    is_dict = isinstance(data, dict)
    quota_hit = is_dict and ("Information" in data or "Note" in data)
    recognized = is_dict and bool(data.get("Symbol"))
    results[t]["alphavantage"] = {
        "symbol_tried": symbol, "status": sc, "recognized": recognized,
        "quota_or_note_message": data.get("Information") or data.get("Note") if quota_hit else None,
        "MarketCapitalization": data.get("MarketCapitalization") if recognized else None,
        "EBITDA": data.get("EBITDA") if recognized else None,
        "RevenueTTM": data.get("RevenueTTM") if recognized else None,
        "SharesOutstanding": data.get("SharesOutstanding") if recognized else None,
        "raw_keys_count": len(data) if is_dict else 0,
    }
    flag = "QUOTA/NOTE" if quota_hit else ("OK" if recognized else "NON-RECONNU")
    print(f"{t:10s} -> {symbol:12s} status={sc} [{flag}] MarketCap={data.get('MarketCapitalization') if recognized else '-'} EBITDA={data.get('EBITDA') if recognized else '-'}")
    if quota_hit:
        print(f"  -> message brut: {results[t]['alphavantage']['quota_or_note_message']}")
    time.sleep(1)

print(f"\nAppels Alpha Vantage consommés dans ce banc d'essai : {av_calls_used}")

print()
print("=" * 100)
print("FMP — rappel des résultats déjà mesurés en Tâche B.3 (/stable/profile OK, états financiers 402)")
print("=" * 100)
for t in TICKERS:
    sc, data = fmp_get("profile", symbol=t)
    is_list = isinstance(data, list) and len(data) > 0
    d = data[0] if is_list else {}
    results[t]["fmp"] = {
        "profile_status": sc, "recognized": is_list,
        "marketCap": d.get("marketCap") if is_list else None,
        "currency": d.get("currency") if is_list else None,
    }
    print(f"{t:10s} profile status={sc} recognized={is_list} marketCap={d.get('marketCap') if is_list else '-'}")
    time.sleep(0.15)

out_path = Path(__file__).resolve().parent.parent / "scripts" / "benchmark_market_data_results.json"
out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
print(f"\nRésultats bruts écrits dans {out_path}")
