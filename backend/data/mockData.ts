import { CentralBankRate } from '../../shared/types';

// ============================================
// MOCK DATA — fallback statique de la couche Marché/Macro (D1) uniquement.
// Les tableaux DEALS/FUNDS/SOURCING_TARGETS/SECTORS/NEWS_SIGNALS ont été
// supprimés (D3) : ils servaient des données M&A 100% fictives sans aucune
// base réelle, désormais remplacées par FastAPI (D2). CENTRAL_BANK_DATA
// reste nécessaire comme repli quand FRED_API_KEY est absente ou en erreur
// dans backend/routes/macro.ts.
// ============================================

export const CENTRAL_BANK_DATA: CentralBankRate[] = [
  { name: 'FED', rate: 3.75, previousRate: 4.25, trend: 'hold', lastUpdate: '2025-06-18', dataSource: 'fallback' },
  { name: 'ECB', rate: 2.15, previousRate: 2.40, trend: 'dovish', lastUpdate: '2025-06-05', dataSource: 'fallback' },
  { name: 'BoE', rate: 4.25, previousRate: 4.50, trend: 'dovish', lastUpdate: '2025-06-19', dataSource: 'fallback' },
  { name: 'BoJ', rate: 0.50, previousRate: 0.25, trend: 'hawkish', lastUpdate: '2025-03-14', dataSource: 'fallback' },
];
