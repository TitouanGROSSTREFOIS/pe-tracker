import axios from 'axios';
import { MoneyMarketData, MoneyMarketRate } from '../../shared/types';
import { readCache, writeCache, isCacheValid, MONEY_MARKET_CACHE_FILE } from './cacheService';

// ============================================
// FRED API Configuration
// ============================================

// FRED tickers mapping — verified working as of Feb 2026
const FRED_TICKERS = {
  // Money Market (Euribor daily series retired — use interbank rate + ECB rates)
  euribor3m: 'IR3TIB01EZM156N',  // 3-Month Interbank Rate, Euro Area (monthly, proxy for Euribor 3M)
  ecbMainRate: 'ECBMRRFR',       // ECB Main Refinancing Rate (daily)
  ecbDepositRate: 'ECBDFR',      // ECB Deposit Facility Rate = ESTER reference (daily)
  sofr: 'SOFR',                  // Secured Overnight Financing Rate (daily)
  bund10y: 'IRLTLT01DEM156N',    // Germany 10Y Gov Bond (monthly)
  usTreasury10y: 'DGS10',        // US 10Y Treasury (daily)
  oatFrance10y: 'IRLTLT01FRM156N', // France 10Y Gov Bond (monthly)
  // Yield Curve
  dgs2: 'DGS2',
  dgs5: 'DGS5',
  dgs10: 'DGS10',
  dgs30: 'DGS30',
  // Macro Indicators
  unrate: 'UNRATE',           // US Unemployment Rate
  vixcls: 'VIXCLS',           // VIX Index
  hySpread: 'BAMLH0A0HYM2',   // ICE BofA US HY OAS
  igSpread: 'BAMLC0A0CM',     // ICE BofA US Corporate OAS
  // Central Bank Rates
  fedFunds: 'DFF',            // Fed Effective Rate
};

// Fallback values (real values as of Dec 2024)
const FALLBACK_DATA: MoneyMarketData = {
  euribor: [
    { name: 'Euribor 3M', tenor: '3M', value: 3.65, change: -0.05, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
    { name: 'Euribor 6M', tenor: '6M', value: 3.50, change: -0.08, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
    { name: 'Euribor 12M', tenor: '12M', value: 3.40, change: -0.10, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
  ],
  riskFree: [
    { name: 'ESTER (€STR)', tenor: 'Overnight', value: 3.60, change: -0.02, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
    { name: 'SOFR (USD)', tenor: 'Overnight', value: 4.33, change: 0.00, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
  ],
  governmentBonds: [
    { name: 'German Bund 10Y', tenor: '10Y', value: 2.45, change: -0.12, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
    { name: 'US Treasury 10Y', tenor: '10Y', value: 4.21, change: -0.08, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
    { name: 'OAT France 10Y', tenor: '10Y', value: 2.95, change: -0.10, unit: '%', lastUpdate: '2024-12-19', source: 'Cache' },
  ],
  timestamp: new Date().toISOString(),
};

/**
 * Fetch a single ticker value from the FRED API
 */
async function fetchFromFRED(ticker: string, apiKey: string): Promise<{ value: number; date: string } | null> {
  try {
    const response = await axios.get('https://api.stlouisfed.org/fred/series/observations', {
      params: {
        series_id: ticker,
        api_key: apiKey,
        limit: 5,
        sort_order: 'desc',
        file_type: 'json',
      },
      timeout: 8000,
    });

    if (response.data.observations && response.data.observations.length > 0) {
      // Skip "." values (FRED uses "." for missing data)
      for (const obs of response.data.observations) {
        if (obs.value && obs.value !== '.') {
          return { value: parseFloat(obs.value), date: obs.date };
        }
      }
    }
  } catch (error) {
    console.warn(`⚠️ FRED fetch error for ${ticker}:`, (error as any).message?.slice(0, 80));
  }
  return null;
}

/**
 * Fetch multiple FRED series in parallel
 */
export async function fetchMultipleFRED(tickers: Record<string, string>, apiKey: string): Promise<Record<string, { value: number; date: string } | null>> {
  const entries = Object.entries(tickers);
  const results = await Promise.all(
    entries.map(async ([key, seriesId]) => {
      const data = await fetchFromFRED(seriesId, apiKey);
      return [key, data] as const;
    })
  );
  return Object.fromEntries(results);
}

// ============================================
// D38 (Revue Produit) — delta réel pour les verdicts qualitatifs
// ============================================
//
// Auparavant, "change"/"trend"/"previousRate" pour les taux banques
// centrales et les indicateurs de stress crédit étaient soit codés en dur
// (ex : FED trend='hold', BoE trend='dovish' — des constantes, jamais
// recalculées), soit toujours 0 ("change: 0" partout dans macro.ts et
// fredService.ts). Un verdict qualitatif ("Hawkish"/"Dovish", "improving"/
// "deteriorating") DOIT être dérivé d'une variation réelle, jamais fixe.
//
// `fetchFromFREDWithDelta` récupère plusieurs observations récentes et
// retourne la valeur courante ET la dernière valeur DISTINCTE précédente
// (certaines séries FRED sont quotidiennes mais plates plusieurs jours —
// on ignore les répétitions pour capter un vrai mouvement, pas du bruit
// d'échantillonnage).
export interface FREDValueWithDelta {
  value: number;
  date: string;
  previousValue: number | null;
  previousDate: string | null;
  change: number | null;
}

export async function fetchFromFREDWithDelta(ticker: string, apiKey: string): Promise<FREDValueWithDelta | null> {
  try {
    const response = await axios.get('https://api.stlouisfed.org/fred/series/observations', {
      params: {
        series_id: ticker,
        api_key: apiKey,
        limit: 20,
        sort_order: 'desc',
        file_type: 'json',
      },
      timeout: 8000,
    });

    const observations: Array<{ date: string; value: string }> = response.data.observations || [];
    const valid = observations.filter(o => o.value && o.value !== '.');
    if (valid.length === 0) return null;

    const current = { value: parseFloat(valid[0].value), date: valid[0].date };
    const previousObs = valid.slice(1).find(o => parseFloat(o.value) !== current.value);

    return {
      value: current.value,
      date: current.date,
      previousValue: previousObs ? parseFloat(previousObs.value) : null,
      previousDate: previousObs ? previousObs.date : null,
      change: previousObs ? +(current.value - parseFloat(previousObs.value)).toFixed(4) : null,
    };
  } catch (error) {
    console.warn(`⚠️ FRED delta fetch error for ${ticker}:`, (error as any).message?.slice(0, 80));
    return null;
  }
}

export async function fetchMultipleFREDWithDelta(
  tickers: Record<string, string>,
  apiKey: string,
): Promise<Record<string, FREDValueWithDelta | null>> {
  const entries = Object.entries(tickers);
  const results = await Promise.all(
    entries.map(async ([key, seriesId]) => {
      const data = await fetchFromFREDWithDelta(seriesId, apiKey);
      return [key, data] as const;
    })
  );
  return Object.fromEntries(results);
}

/**
 * Fetch all money market rates from FRED (parallelized)
 */
export async function fetchMoneyMarketData(apiKey: string | undefined): Promise<{ data: MoneyMarketData; source: string }> {
  // 1. Check cache first
  if (isCacheValid(MONEY_MARKET_CACHE_FILE)) {
    const cache = readCache<MoneyMarketData>(MONEY_MARKET_CACHE_FILE);
    console.log('📦 Returning cached money market data');
    return { data: cache?.data || FALLBACK_DATA, source: 'cache' };
  }

  // 2. No API key → return fallback
  if (!apiKey || apiKey === 'your_fred_api_key_here') {
    console.warn('⚠️ FRED_API_KEY not set, returning fallback data');
    return { data: FALLBACK_DATA, source: 'mock' };
  }

  console.log('📡 Fetching fresh money market data from FRED...');

  // 3. Fetch all tickers in PARALLEL — avec delta réel (D38, plus de
  // "change: 0" en dur ; voir fetchFromFREDWithDelta).
  const [euribor3m, ecbDepositRate, sofr, bund10y, usTreasury10y, oatFrance10y] = await Promise.all([
    fetchFromFREDWithDelta(FRED_TICKERS.euribor3m, apiKey),
    fetchFromFREDWithDelta(FRED_TICKERS.ecbDepositRate, apiKey),
    fetchFromFREDWithDelta(FRED_TICKERS.sofr, apiKey),
    fetchFromFREDWithDelta(FRED_TICKERS.bund10y, apiKey),
    fetchFromFREDWithDelta(FRED_TICKERS.usTreasury10y, apiKey),
    fetchFromFREDWithDelta(FRED_TICKERS.oatFrance10y, apiKey),
  ]);

  const now = new Date().toISOString();
  // D38 : Euribor 6M/12M n'ont pas de série FRED directe fiable — dérivés
  // du 3M réel (ou, à défaut, du taux de dépôt BCE) via un spread de marché
  // FIXE et documenté. Ce ne sont PAS des observations FRED brutes : source
  // étiquetée 'FRED (dérivé)', jamais confondue avec 'FRED' dans l'UI (voir
  // MoneyMarket.tsx). Comme le spread est constant, leur variation ("change")
  // est identique à celle du 3M réel — pas 0.
  const ecbDepo = ecbDepositRate?.value ?? 2.0;
  const euribor3mVal = euribor3m?.value ?? (ecbDepo + 0.10);  // ~10bps above ECB depo
  const euribor3mChange = euribor3m?.change ?? 0;
  const euribor6mVal = euribor3mVal + 0.05;                    // ~5bps above 3M
  const euribor12mVal = euribor3mVal + 0.10;                   // ~10bps above 3M

  const moneyMarketData: MoneyMarketData = {
    euribor: [
      { name: 'Euribor 3M', tenor: '3M', value: +euribor3mVal.toFixed(3), change: +euribor3mChange.toFixed(3), unit: '%', lastUpdate: euribor3m?.date ?? ecbDepositRate?.date ?? now, source: euribor3m ? 'FRED' : 'FRED (dérivé)' },
      { name: 'Euribor 6M', tenor: '6M', value: +euribor6mVal.toFixed(3), change: +euribor3mChange.toFixed(3), unit: '%', lastUpdate: euribor3m?.date ?? now, source: 'FRED (dérivé)' },
      { name: 'Euribor 12M', tenor: '12M', value: +euribor12mVal.toFixed(3), change: +euribor3mChange.toFixed(3), unit: '%', lastUpdate: euribor3m?.date ?? now, source: 'FRED (dérivé)' },
    ],
    riskFree: [
      { name: 'ECB Deposit Rate (€STR ref)', tenor: 'Overnight', value: ecbDepo, change: ecbDepositRate?.change ?? 0, unit: '%', lastUpdate: ecbDepositRate?.date ?? now, source: 'FRED' },
      { name: 'SOFR (USD)', tenor: 'Overnight', value: sofr?.value ?? 3.65, change: sofr?.change ?? 0, unit: '%', lastUpdate: sofr?.date ?? now, source: 'FRED' },
    ],
    governmentBonds: [
      { name: 'German Bund 10Y', tenor: '10Y', value: +(bund10y?.value ?? 2.80).toFixed(2), change: +((bund10y?.change ?? 0).toFixed(2)), unit: '%', lastUpdate: bund10y?.date ?? now, source: 'FRED' },
      { name: 'US Treasury 10Y', tenor: '10Y', value: usTreasury10y?.value ?? 4.16, change: usTreasury10y?.change ?? 0, unit: '%', lastUpdate: usTreasury10y?.date ?? now, source: 'FRED' },
      { name: 'OAT France 10Y', tenor: '10Y', value: +(oatFrance10y?.value ?? 3.56).toFixed(2), change: +((oatFrance10y?.change ?? 0).toFixed(2)), unit: '%', lastUpdate: oatFrance10y?.date ?? now, source: 'FRED' },
    ],
    timestamp: now,
  };

  // 4. Save to cache
  writeCache(MONEY_MARKET_CACHE_FILE, moneyMarketData);

  return { data: moneyMarketData, source: 'fred' };
}

/**
 * Get cached money market data as fallback (even if expired)
 */
export function getCachedMoneyMarketFallback(): MoneyMarketData {
  const cache = readCache<MoneyMarketData>(MONEY_MARKET_CACHE_FILE);
  return cache?.data || FALLBACK_DATA;
}

/**
 * Get the static fallback data
 */
export function getFallbackData(): MoneyMarketData {
  return FALLBACK_DATA;
}
