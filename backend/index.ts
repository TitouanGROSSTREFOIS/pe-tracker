import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

// Route modules — couche Marché / Macro / News uniquement (voir D1).
// Le domaine M&A (deals, sourcing, portefeuille, comps, LBO, mémos IC) est
// servi exclusivement par FastAPI (api/), qui en est la seule source de
// vérité (D2). Les anciennes routes Express /api/deals, /api/funds,
// /api/sourcing-targets et /api/sectors servaient des données 100% fictives
// codées en dur et ont été supprimées.
import newsRouter from './routes/news';
import marketRouter from './routes/market';
import macroRouter from './routes/macro';

dotenv.config();

const app = express();
const port = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// ============================================
// HEALTH CHECK
// ============================================
app.get('/api/test', (_req, res) => {
  res.json({ message: 'Success: Backend is connected!' });
});

// ============================================
// ROUTE MOUNTING
// ============================================
app.use('/api/news-signals', newsRouter);
app.use('/api', marketRouter);           // /api/market-indices, /api/quote/:symbol, /api/quotes
app.use('/api', macroRouter);            // /api/central-bank-rates, /api/macro-indicators, /api/yield-curve, /api/credit-stress, /api/macro/euribor-rates

// ============================================
// SERVER START
// ============================================
app.listen(port, () => {
  console.log(`\n🚀 PE Tracker Backend (Market/Macro/News) running at http://localhost:${port}`);
  console.log(`   Health check: http://localhost:${port}/api/test\n`);
});
