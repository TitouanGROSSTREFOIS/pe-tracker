import { Router, Request, Response } from 'express';
import axios from 'axios';
import type { MarketIndex } from '../../shared/types.js';

const router = Router();

// Market indices configuration
const INDICES_CONFIG = [
  { symbol: '^GSPC', name: 'S&P 500' },
  { symbol: '^IXIC', name: 'NASDAQ' },
  { symbol: '^DJI', name: 'DOW 30' },
  { symbol: '^FTSE', name: 'FTSE 100' },
  { symbol: '^N225', name: 'NIKKEI 225' },
  { symbol: '^GDAXI', name: 'DAX' },
  { symbol: '^HSI', name: 'HANG SENG' },
  { symbol: 'CL=F', name: 'CRUDE OIL' },
  { symbol: 'GC=F', name: 'GOLD' },
  { symbol: 'BTC-USD', name: 'BITCOIN' },
  { symbol: 'EURUSD=X', name: 'EUR/USD' },
  { symbol: 'GBPUSD=X', name: 'GBP/USD' },
];

// In-memory cache for market indices (5 min TTL)
const MARKET_CACHE_TTL = 5 * 60 * 1000;
let marketCache: { data: MarketIndex[]; timestamp: number } | null = null;

// Delay helper
const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

// ──────────────────────────────────────────────
// Yahoo v8 Chart API — Direct HTTP (bypasses broken yahoo-finance2 library)
// ──────────────────────────────────────────────
async function fetchViaChartAPI(symbol: string): Promise<{ price: number; change: number; changePercent: number } | null> {
  try {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}`;
    const res = await axios.get(url, {
      params: { interval: '1d', range: '2d' },
      headers: { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)' },
      timeout: 10000,
    });

    const meta = res.data?.chart?.result?.[0]?.meta;
    if (!meta?.regularMarketPrice) return null;

    const price = meta.regularMarketPrice;
    const prevClose = meta.chartPreviousClose ?? meta.previousClose ?? price;
    const change = price - prevClose;
    const changePercent = prevClose > 0 ? (change / prevClose) * 100 : 0;

    return { price, change, changePercent };
  } catch (err) {
    console.warn(`⚠️ Chart API failed for ${symbol}:`, (err as Error).message?.slice(0, 60));
    return null;
  }
}

// Fetch all indices using direct chart API with small delay between calls
async function fetchQuotesSafely(): Promise<MarketIndex[]> {
  const results: MarketIndex[] = [];

  for (const cfg of INDICES_CONFIG) {
    const data = await fetchViaChartAPI(cfg.symbol);
    results.push({
      symbol: cfg.name,
      value: data?.price ?? 0,
      change: data?.change ?? 0,
      changePercent: data?.changePercent ?? 0,
    });
    await delay(300); // small delay to avoid rate limiting
  }

  return results;
}

// GET /api/quotes — Multiple quotes (uses chart API)
router.get('/quotes', async (req: Request, res: Response) => {
  const symbols = req.query.symbols as string;
  if (!symbols) {
    return res.status(400).json({ error: 'Symbols query parameter is required' });
  }

  try {
    const symbolList = symbols.split(',');
    const results = await Promise.all(symbolList.map(async (sym) => {
      const data = await fetchViaChartAPI(sym.trim());
      return {
        symbol: sym.trim(),
        regularMarketPrice: data?.price ?? 0,
        regularMarketChange: data?.change ?? 0,
        regularMarketChangePercent: data?.changePercent ?? 0,
      };
    }));
    res.json(results);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to fetch quotes' });
  }
});

// GET /api/quote/:symbol — Single quote via Chart API
router.get('/quote/:symbol', async (req: Request, res: Response) => {
  const { symbol } = req.params;
  try {
    const data = await fetchViaChartAPI(symbol);
    if (data) {
      return res.json({
        symbol,
        regularMarketPrice: data.price,
        regularMarketChange: data.change,
        regularMarketChangePercent: data.changePercent,
        longName: symbol,
      });
    }
    res.status(404).json({ error: 'Symbol not found' });
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to fetch quote' });
  }
});

// GET /api/market-indices — Global indices (cached 5 min)
router.get('/market-indices', async (req: Request, res: Response) => {
  // Return cached data if still fresh
  if (marketCache && Date.now() - marketCache.timestamp < MARKET_CACHE_TTL) {
    return res.json(marketCache.data);
  }

  try {
    console.log('📡 Fetching market indices via Chart API...');
    const formatted = await fetchQuotesSafely();

    // Only cache if we got at least some real data
    const hasRealData = formatted.some(f => f.value > 0);
    if (hasRealData) {
      marketCache = { data: formatted, timestamp: Date.now() };
      console.log(`✅ Market indices updated: ${formatted.filter(f => f.value > 0).length}/${formatted.length} symbols`);
    }

    res.json(formatted);
  } catch (error) {
    console.error('Failed to fetch market indices:', error);
    // Return stale cache if available
    res.json(marketCache?.data ?? INDICES_CONFIG.map(c => ({ symbol: c.name, value: 0, change: 0, changePercent: 0 })));
  }
});

export default router;
