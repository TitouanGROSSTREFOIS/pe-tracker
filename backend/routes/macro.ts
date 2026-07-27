import { Router, Request, Response } from 'express';
import axios from 'axios';
import { CentralBankRate, MacroIndicator, YieldCurvePoint, CreditIndicator } from '../../shared/types';
import { CENTRAL_BANK_DATA } from '../data/mockData';
import {
  fetchMoneyMarketData, getCachedMoneyMarketFallback, getFallbackData,
  fetchMultipleFRED, fetchMultipleFREDWithDelta,
} from '../services/fredService';

const router = Router();

// Helper to get FRED API key
const getFredKey = () => process.env.FRED_API_KEY;

// D38 (Revue Produit) — seuil de classification Hawkish/Dovish/Hold.
// Basé sur la variation RÉELLE (dernière valeur FRED vs dernière valeur
// distincte précédente) du taux directeur/proxy, pas une constante fixe.
// ±5 points de base est le seuil usuel pour distinguer un vrai mouvement
// d'un bruit d'arrondi sur une série quotidienne (les vrais mouvements de
// politique monétaire sont par paliers de 25bps). Documenté ici ET dans la
// légende affichée sur la page (CreditMacro.tsx).
const TREND_THRESHOLD_PP = 0.05;

function classifyTrend(change: number | null): 'hawkish' | 'dovish' | 'hold' {
  if (change === null) return 'hold';
  if (change >= TREND_THRESHOLD_PP) return 'hawkish';
  if (change <= -TREND_THRESHOLD_PP) return 'dovish';
  return 'hold';
}

// ============================================
// CENTRAL BANK RATES  (FRED — taux ET tendance dérivés de données réelles)
// ============================================
router.get('/central-bank-rates', async (_req: Request, res: Response) => {
  try {
    const apiKey = getFredKey();
    if (apiKey) {
      // BoJ : aucune série FRED fiable et à jour trouvée pour le taux
      // directeur japonais (candidate testée — IRSTCB01JPM156N — figée
      // depuis 2023-12, donc plus périmée que jamais "live"). Plutôt que
      // d'afficher une donnée fausse comme "live", le taux BoJ reste une
      // valeur statique documentée et clairement signalée `dataSource:
      // 'static'` — jamais présentée comme FRED.
      const data = await fetchMultipleFREDWithDelta({
        fedFunds: 'DFF',
        ecbMain: 'ECBMRRFR',
        boeRate: 'IUDSOIA',   // UK Overnight Index Average (BoE proxy)
      }, apiKey);

      const now = new Date().toISOString();

      const rates: CentralBankRate[] = [
        {
          name: 'FED',
          rate: data.fedFunds?.value ?? 4.33,
          previousRate: data.fedFunds?.previousValue ?? undefined,
          change: data.fedFunds?.change ?? 0,
          trend: classifyTrend(data.fedFunds?.change ?? null),
          lastUpdate: data.fedFunds?.date ?? now,
          dataSource: 'fred',
        },
        {
          name: 'ECB',
          rate: data.ecbMain?.value ?? 2.15,
          previousRate: data.ecbMain?.previousValue ?? undefined,
          change: data.ecbMain?.change ?? 0,
          trend: classifyTrend(data.ecbMain?.change ?? null),
          lastUpdate: data.ecbMain?.date ?? now,
          dataSource: 'fred',
        },
        {
          name: 'BoE',
          rate: data.boeRate?.value ?? 4.50,
          previousRate: data.boeRate?.previousValue ?? undefined,
          change: data.boeRate?.change ?? 0,
          trend: classifyTrend(data.boeRate?.change ?? null),
          lastUpdate: data.boeRate?.date ?? now,
          dataSource: 'fred',
        },
        {
          name: 'BoJ',
          rate: 0.50,
          lastUpdate: '2025-03-14',
          dataSource: 'static',
        },
      ];

      return res.json({ status: 'success', timestamp: now, rates, source: 'fred' });
    }

    // No FRED key — return static data
    res.json({ status: 'success', timestamp: new Date().toISOString(), rates: CENTRAL_BANK_DATA, source: 'fallback' });
  } catch (error) {
    console.warn('⚠️ Central bank rates fetch error:', (error as any).message);
    res.json({ status: 'success_cached', timestamp: new Date().toISOString(), rates: CENTRAL_BANK_DATA, source: 'fallback' });
  }
});

// ============================================
// MACRO INDICATORS  (FRED when key available)
// ============================================

// Fallback data
const MACRO_FALLBACK: MacroIndicator[] = [
  { name: 'US Unemployment Rate', value: 4.0, change: -0.1, unit: '%', lastUpdate: '2025-01-10', impact: 'High' },
  { name: 'VIX Index', value: 15.8, change: -1.2, unit: '', lastUpdate: '2025-02-10', impact: 'High' },
  { name: 'HY Spreads (OAS)', value: 320, change: -10, unit: 'bps', lastUpdate: '2025-02-10', impact: 'High' },
  { name: 'IG Spreads (OAS)', value: 95, change: -5, unit: 'bps', lastUpdate: '2025-02-10', impact: 'Medium' },
  { name: 'US 10Y Treasury', value: 4.50, change: -0.08, unit: '%', lastUpdate: '2025-02-10', impact: 'High' },
  { name: 'Fed Funds Rate', value: 4.33, change: 0.00, unit: '%', lastUpdate: '2025-02-10', impact: 'High' },
];

router.get('/macro-indicators', async (_req: Request, res: Response) => {
  const apiKey = getFredKey();

  if (!apiKey) {
    return res.json({ status: 'success', timestamp: new Date().toISOString(), indicators: MACRO_FALLBACK, source: 'fallback' });
  }

  try {
    // D38 : delta réel (plus jamais "change: 0" en dur) — voir fredService.ts.
    const data = await fetchMultipleFREDWithDelta({
      unrate: 'UNRATE',
      vix: 'VIXCLS',
      hySpread: 'BAMLH0A0HYM2',
      igSpread: 'BAMLC0A0CM',
      dgs10: 'DGS10',
      fedFunds: 'DFF',
    }, apiKey);

    // Spreads FRED sont en points de %, affichés en bps (×100) — le delta
    // doit subir la même conversion pour rester cohérent avec la valeur.
    const bps = (d: { value: number; change: number | null } | null | undefined) =>
      d ? { value: Math.round(d.value * 100), change: d.change != null ? Math.round(d.change * 100) : 0 } : { value: 0, change: 0 };
    const hy = bps(data.hySpread);
    const ig = bps(data.igSpread);

    const indicators: MacroIndicator[] = [
      { name: 'US Unemployment Rate', value: data.unrate?.value ?? 4.0, change: data.unrate?.change ?? 0, unit: '%', lastUpdate: data.unrate?.date ?? '', impact: 'High' },
      { name: 'VIX Index', value: data.vix?.value ?? 15.8, change: data.vix?.change ?? 0, unit: '', lastUpdate: data.vix?.date ?? '', impact: 'High' },
      { name: 'HY Spreads (OAS)', value: hy.value, change: hy.change, unit: 'bps', lastUpdate: data.hySpread?.date ?? '', impact: 'High' },
      { name: 'IG Spreads (OAS)', value: ig.value, change: ig.change, unit: 'bps', lastUpdate: data.igSpread?.date ?? '', impact: 'Medium' },
      { name: 'US 10Y Treasury', value: data.dgs10?.value ?? 4.50, change: data.dgs10?.change ?? 0, unit: '%', lastUpdate: data.dgs10?.date ?? '', impact: 'High' },
      { name: 'Fed Funds Rate', value: data.fedFunds?.value ?? 4.33, change: data.fedFunds?.change ?? 0, unit: '%', lastUpdate: data.fedFunds?.date ?? '', impact: 'High' },
    ];

    res.json({ status: 'success', timestamp: new Date().toISOString(), indicators, source: 'fred' });
  } catch (error) {
    console.error('❌ Macro indicators FRED error:', (error as any).message);
    res.json({ status: 'success', timestamp: new Date().toISOString(), indicators: MACRO_FALLBACK, source: 'fallback' });
  }
});

// ============================================
// YIELD CURVE  (FRED when key available)
// ============================================

const YIELD_FALLBACK: YieldCurvePoint[] = [
  { tenor: '1M', yield: 3.60, change: 0 },
  { tenor: '3M', yield: 3.55, change: 0 },
  { tenor: '6M', yield: 3.50, change: 0 },
  { tenor: '1Y', yield: 3.45, change: 0 },
  { tenor: '2Y', yield: 3.50, change: 0 },
  { tenor: '5Y', yield: 3.90, change: 0 },
  { tenor: '10Y', yield: 4.16, change: 0 },
  { tenor: '30Y', yield: 4.50, change: 0 },
];

router.get('/yield-curve', async (_req: Request, res: Response) => {
  const apiKey = getFredKey();

  if (!apiKey) {
    const y2 = YIELD_FALLBACK.find(c => c.tenor === '2Y');
    const y10 = YIELD_FALLBACK.find(c => c.tenor === '10Y');
    return res.json({
      status: 'success', timestamp: new Date().toISOString(), curve: YIELD_FALLBACK,
      region: 'US Treasury', curve2Y10Y: (y10?.yield ?? 0) - (y2?.yield ?? 0), source: 'fallback',
    });
  }

  try {
    const data = await fetchMultipleFRED({
      dgs1m: 'DGS1MO', dgs3m: 'DGS3MO', dgs6m: 'DGS6MO', dgs1: 'DGS1',
      dgs2: 'DGS2', dgs5: 'DGS5', dgs10: 'DGS10', dgs30: 'DGS30',
    }, apiKey);

    // Chaque point vient d'une série FRED distincte, potentiellement publiée
    // à des dates différentes (les tenors longs sont parfois retardés d'un
    // jour ouvré) — lastUpdate par point, jamais une date globale supposée.
    const curve: YieldCurvePoint[] = [
      { tenor: '1M', yield: data.dgs1m?.value ?? 3.60, change: 0, lastUpdate: data.dgs1m?.date },
      { tenor: '3M', yield: data.dgs3m?.value ?? 3.55, change: 0, lastUpdate: data.dgs3m?.date },
      { tenor: '6M', yield: data.dgs6m?.value ?? 3.50, change: 0, lastUpdate: data.dgs6m?.date },
      { tenor: '1Y', yield: data.dgs1?.value ?? 3.45, change: 0, lastUpdate: data.dgs1?.date },
      { tenor: '2Y', yield: data.dgs2?.value ?? 3.50, change: 0, lastUpdate: data.dgs2?.date },
      { tenor: '5Y', yield: data.dgs5?.value ?? 3.90, change: 0, lastUpdate: data.dgs5?.date },
      { tenor: '10Y', yield: data.dgs10?.value ?? 4.16, change: 0, lastUpdate: data.dgs10?.date },
      { tenor: '30Y', yield: data.dgs30?.value ?? 4.50, change: 0, lastUpdate: data.dgs30?.date },
    ];

    // Find the 2Y and 10Y entries for spread calculation
    const y2 = curve.find(c => c.tenor === '2Y');
    const y10 = curve.find(c => c.tenor === '10Y');
    const spread2y10y = (y10?.yield ?? 0) - (y2?.yield ?? 0);

    res.json({
      status: 'success', timestamp: new Date().toISOString(), curve,
      region: 'US Treasury', curve2Y10Y: spread2y10y, source: 'fred',
    });
  } catch (error) {
    console.error('❌ Yield curve FRED error:', (error as any).message);
    const y2 = YIELD_FALLBACK.find(c => c.tenor === '2Y');
    const y10 = YIELD_FALLBACK.find(c => c.tenor === '10Y');
    res.json({
      status: 'success', timestamp: new Date().toISOString(), curve: YIELD_FALLBACK,
      region: 'US Treasury', curve2Y10Y: (y10?.yield ?? 0) - (y2?.yield ?? 0), source: 'fallback',
    });
  }
});

// ============================================
// CREDIT STRESS INDICATORS  (FRED when key available)
// ============================================

const CREDIT_FALLBACK: CreditIndicator[] = [
  { name: 'HY OAS Spread', level: 'Low', value: 320, threshold: 500, trend: 'improving' },
  { name: 'IG OAS Spread', level: 'Low', value: 95, threshold: 200, trend: 'stable' },
  { name: 'Fed Funds Rate', level: 'Medium', value: 4.33, threshold: 5.50, trend: 'stable' },
  { name: 'VIX Volatility', level: 'Low', value: 15.8, threshold: 30, trend: 'improving' },
];

// D38 (Revue Produit) — logique de classification EXPLICITE et documentée
// (reprise à l'identique dans la légende affichée sur CreditMacro.tsx et
// dans la page Méthodologie) :
//   level  = position de la valeur courante dans son seuil de stress :
//            ratio = valeur / seuil ; ≥85% → High, ≥50% → Medium, sinon Low.
//   trend  = direction du dernier mouvement RÉEL (delta FRED vs dernière
//            valeur distincte précédente) — jamais une constante. Convention
//            UNIFORME pour les 4 indicateurs : une hausse de spread/VIX/taux
//            directeur signifie des conditions de crédit qui SE TENDENT
//            ("deteriorating"), une baisse signifie qu'elles SE DÉTENDENT
//            ("improving"). |delta| non significatif → "stable".
function getLevel(value: number, threshold: number): 'Low' | 'Medium' | 'High' {
  const ratio = value / threshold;
  if (ratio >= 0.85) return 'High';
  if (ratio >= 0.5) return 'Medium';
  return 'Low';
}

function getTrend(change: number | null, epsilon: number): 'improving' | 'stable' | 'deteriorating' {
  if (change === null || Math.abs(change) < epsilon) return 'stable';
  return change < 0 ? 'improving' : 'deteriorating';
}

router.get('/credit-stress', async (_req: Request, res: Response) => {
  const apiKey = getFredKey();

  if (!apiKey) {
    return res.json({ status: 'success', timestamp: new Date().toISOString(), indicators: CREDIT_FALLBACK, overallRisk: 'Low', source: 'fallback' });
  }

  try {
    const data = await fetchMultipleFREDWithDelta({
      hySpread: 'BAMLH0A0HYM2',
      igSpread: 'BAMLC0A0CM',
      fedFunds: 'DFF',
      vix: 'VIXCLS',
    }, apiKey);

    const hyVal = Math.round((data.hySpread?.value ?? 3.2) * 100);
    const hyChange = data.hySpread?.change != null ? Math.round(data.hySpread.change * 100) : null;
    const igVal = Math.round((data.igSpread?.value ?? 0.95) * 100);
    const igChange = data.igSpread?.change != null ? Math.round(data.igSpread.change * 100) : null;
    const fedVal = data.fedFunds?.value ?? 4.33;
    const vixVal = data.vix?.value ?? 15.8;

    const indicators: CreditIndicator[] = [
      { name: 'HY OAS Spread', level: getLevel(hyVal, 500), value: hyVal, threshold: 500, trend: getTrend(hyChange, 1), lastUpdate: data.hySpread?.date },
      { name: 'IG OAS Spread', level: getLevel(igVal, 200), value: igVal, threshold: 200, trend: getTrend(igChange, 1), lastUpdate: data.igSpread?.date },
      { name: 'Fed Funds Rate', level: getLevel(fedVal, 5.5), value: fedVal, threshold: 5.50, trend: getTrend(data.fedFunds?.change ?? null, 0.01), lastUpdate: data.fedFunds?.date },
      { name: 'VIX Volatility', level: getLevel(vixVal, 30), value: vixVal, threshold: 30, trend: getTrend(data.vix?.change ?? null, 0.1), lastUpdate: data.vix?.date },
    ];

    const overallRisk = indicators.some(i => i.level === 'High') ? 'High' : indicators.some(i => i.level === 'Medium') ? 'Medium' : 'Low';

    res.json({ status: 'success', timestamp: new Date().toISOString(), indicators, overallRisk, source: 'fred' });
  } catch (error) {
    console.error('❌ Credit stress FRED error:', (error as any).message);
    res.json({ status: 'success', timestamp: new Date().toISOString(), indicators: CREDIT_FALLBACK, overallRisk: 'Low', source: 'fallback' });
  }
});

// ============================================
// LBO MARKET RATES — current risk-free + spread for LBO cost of debt
// ============================================
router.get('/lbo-market-rates', async (_req: Request, res: Response) => {
  const apiKey = getFredKey();
  const now = new Date().toISOString();

  if (!apiKey) {
    return res.json({
      status: 'success',
      timestamp: now,
      riskFreeRate: 4.25,
      hySpread: 3.50,
      impliedCostOfDebt: 7.75,
      seniorSpread: 2.50,
      impliedSeniorRate: 6.75,
      leveragedLoanIndex: 5.80,
      source: 'fallback',
    });
  }

  try {
    const data = await fetchMultipleFRED({
      sofr: 'SOFR',
      treasury5y: 'DGS5',
      hySpread: 'BAMLH0A0HYM2',
      igSpread: 'BAMLC0A0CM',
    }, apiKey);

    const riskFree = data.treasury5y?.value ?? 4.25;
    const hySpread = data.hySpread?.value ?? 3.50; // FRED returns in percentage points (e.g., 2.86 = 286bps)
    const igSpread = data.igSpread?.value ?? 1.00;

    res.json({
      status: 'success',
      timestamp: now,
      riskFreeRate: riskFree,
      hySpread: hySpread,
      impliedCostOfDebt: +(riskFree + hySpread).toFixed(2),
      seniorSpread: igSpread,
      impliedSeniorRate: +(riskFree + igSpread).toFixed(2),
      sofr: data.sofr?.value ?? null,
      source: 'fred',
    });
  } catch (error) {
    console.warn('⚠️ LBO market rates error:', (error as any).message);
    res.json({
      status: 'success_fallback',
      timestamp: now,
      riskFreeRate: 4.25,
      hySpread: 3.50,
      impliedCostOfDebt: 7.75,
      seniorSpread: 2.50,
      impliedSeniorRate: 6.75,
      source: 'fallback',
    });
  }
});

// ============================================
// MONEY MARKET & RATES (FRED)
// ============================================
router.get('/macro/euribor-rates', async (_req: Request, res: Response) => {
  try {
    const { data, source } = await fetchMoneyMarketData(process.env.FRED_API_KEY);
    res.json({ status: 'success', source, data });
  } catch (error) {
    console.error('❌ Error fetching money market data:', (error as any).message);

    // Fallback: expired cache
    const cachedData = getCachedMoneyMarketFallback();
    if (cachedData.timestamp !== getFallbackData().timestamp) {
      return res.json({
        status: 'success_cached',
        source: 'cache_fallback',
        data: cachedData,
        warning: 'Using cached data due to API error',
      });
    }

    // Final fallback: static mock
    res.json({
      status: 'success_mock',
      source: 'mock',
      data: getFallbackData(),
      warning: 'Using mock data - API unavailable',
    });
  }
});

export default router;
