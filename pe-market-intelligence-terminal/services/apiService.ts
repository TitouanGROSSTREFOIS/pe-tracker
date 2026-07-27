// src/services/apiService.ts - Centralized API service

const BASE_URL = (typeof process !== 'undefined' && process.env?.VITE_API_URL) 
  ? process.env.VITE_API_URL 
  : 'http://localhost:3001/api';

// FastAPI M&A Engine backend (Python)
const FASTAPI_BASE_URL = (typeof process !== 'undefined' && process.env?.VITE_FASTAPI_URL)
  ? process.env.VITE_FASTAPI_URL
  : 'http://localhost:8000';

// ============================================
// DEALS API — FastAPI /deals (source de vérité M&A, voir D2)
// ============================================

import type {
  Deal,
  DealListResponse,
  DealActivity,
  DealActivityListResponse,
  DealNoteInput,
  DealCreateInput,
  DocumentExtraction,
} from '../../shared/types';

export type { Deal, DealActivity, DealActivityListResponse, DealNoteInput, DealCreateInput };

// D15 (Tâche B.5) : `deal_value` (taille de transaction) et `enterprise_value`
// (valeur d'entreprise de la cible) sont deux notions distinctes — ni l'une
// ni l'autre n'est plus dérivée automatiquement du CA. Un deal issu d'un
// upload de teaser en Screening n'a typiquement AUCUNE taille de transaction
// connue : `deal_value` reste null tant qu'il n'est pas saisi explicitement,
// exactement comme `enterprise_value`.
const buildDealPayload = (deal: DealCreateInput) => ({
  acquirer_name: deal.acquirer_name ?? 'TBD',
  target_name: deal.target_name ?? null,
  sourced_target_id: deal.sourced_target_id ?? null,
  announcement_date: deal.announcement_date ?? null,
  close_date: deal.close_date ?? null,
  deal_type: deal.deal_type ?? 'M&A',
  status: deal.status ?? 'Screening',
  deal_value: deal.deal_value ?? null,
  equity_value: deal.equity_value ?? null,
  enterprise_value_deal: deal.enterprise_value_deal ?? null,
  target_revenue: deal.target_revenue ?? null,
  target_ebitda: deal.target_ebitda ?? null,
  enterprise_value: deal.enterprise_value ?? null,
  financial_provenance: deal.financial_provenance ?? null, // D18 (Tâche B.6)
  ev_revenue_multiple: deal.ev_revenue_multiple ?? null,
  ev_ebitda_multiple: deal.ev_ebitda_multiple ?? null,
  pe_multiple: deal.pe_multiple ?? null,
  premium_paid: deal.premium_paid ?? null,
  sector: deal.sector ?? null,
  industry: deal.industry ?? null,
  country: deal.country ?? null,
  description: deal.description ?? null,
  source: deal.source ?? 'Document Ingestion',
  source_url: deal.source_url ?? null,
});

export const dealsAPI = {
  getAll: (sector?: string): Promise<Deal[]> => {
    const url = sector ? `${FASTAPI_BASE_URL}/deals?sector=${sector}` : `${FASTAPI_BASE_URL}/deals`;
    return fetch(url).then(r => {
      if (!r.ok) throw new Error(`dealsAPI.getAll failed: ${r.status}`);
      return r.json();
    }).then((data: DealListResponse) => data.deals);
  },

  getById: (id: number): Promise<Deal> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${id}`).then(r => {
      if (!r.ok) throw new Error(`dealsAPI.getById(${id}) failed: ${r.status}`);
      return r.json();
    }),

  create: (deal: DealCreateInput): Promise<Deal> =>
    fetch(`${FASTAPI_BASE_URL}/deals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildDealPayload(deal))
    }).then(async r => {
      if (!r.ok) {
        // Tâche B.5 : le detail FastAPI (ex. 409 "already linked to deal #X")
        // était auparavant ignoré — l'utilisateur ne voyait qu'un code HTTP nu.
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `dealsAPI.create failed: ${r.status}`);
      }
      return r.json();
    }),

  /** D31 — met à jour le statut (cycle de vie IC) d'un deal promu. */
  updateStatus: (dealId: number, status: string): Promise<Deal> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${dealId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }).then(async r => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `dealsAPI.updateStatus failed: ${r.status}`);
      }
      return r.json();
    }),

  generateMemo: (dealId: number): Promise<{ deal_id: number; ic_memo: string }> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${dealId}/generate-memo`, {
      method: 'POST',
    }).then(async r => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `generateMemo failed: ${r.status}`);
      }
      return r.json();
    }),

  /** D28 — Export du mémo IC en Word (.docx), déjà mis en forme. */
  exportMemoDocx: (dealId: number): Promise<Blob> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${dealId}/export-memo-docx`).then(async r => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `exportMemoDocx failed: ${r.status}`);
      }
      return r.blob();
    }),

  /** D30 — Export du deck de comité d'investissement (.pptx). */
  exportDeckPptx: (dealId: number): Promise<Blob> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${dealId}/export-deck-pptx`).then(async r => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `exportDeckPptx failed: ${r.status}`);
      }
      return r.blob();
    }),

  /** Tâche "P0 : un seul deal dans les 3 documents" — export du modèle LBO
   * (.xlsx) DEPUIS LE SCÉNARIO DE RÉFÉRENCE DU DEAL, jamais depuis l'état
   * courant du calculateur manuel (POST /lbo/export-excel) : c'est ce qui
   * garantit que l'Excel affiche EXACTEMENT le même multiple/EV/dette/equity
   * que le mémo et le deck du même deal. */
  exportLboExcel: (dealId: number): Promise<Blob> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${dealId}/export-lbo-excel`).then(async r => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `exportLboExcel failed: ${r.status}`);
      }
      return r.blob();
    }),

  getActivities: (dealId: number): Promise<DealActivityListResponse> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${dealId}/activities`).then(r => {
      if (!r.ok) throw new Error(`getActivities failed: ${r.status}`);
      return r.json();
    }),

  addNote: (dealId: number, note: DealNoteInput): Promise<DealActivity> =>
    fetch(`${FASTAPI_BASE_URL}/deals/${dealId}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(note),
    }).then(r => {
      if (!r.ok) throw new Error(`addNote failed: ${r.status}`);
      return r.json();
    }),
};

// NOTE (D3 + règle anti-invention) : les wrappers `fundsAPI` (/api/funds),
// `sourcingAPI` (/api/sourcing-targets), `sectorsAPI` (/api/sectors) et
// `portfolioAPI.getSummary` (/api/portfolio-summary) ont été supprimés avec
// les routes Express fictives correspondantes (backend/routes/*.ts,
// backend/data/mockData.ts). Aucun de ces trois domaines n'a d'équivalent
// FastAPI : il n'existe aucun modèle `Fund` en base, `sourcingAPI` et
// `sectorsAPI` n'étaient déjà appelés par aucun composant, et
// `portfolio-summary` dépendait des mêmes données de fonds fictives. Le vrai
// pipeline de sourcing/portefeuille vit dans `maEngineAPI` (FastAPI :8000).

// ============================================
// DOCUMENT INGESTION API
// ============================================

export const documentsAPI = {
  extract: (file: File): Promise<DocumentExtraction> => {
    const formData = new FormData();
    formData.append('file', file);

    return fetch(`${FASTAPI_BASE_URL}/documents/extract`, {
      method: 'POST',
      body: formData,
    }).then(async r => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `documentsAPI.extract failed: ${r.status}`);
      }
      return r.json();
    });
  },

  ingest: (file: File): Promise<DocumentExtraction> => documentsAPI.extract(file),
};

// ============================================
// NEWS SIGNALS API
// ============================================

export interface NewsSignal {
  id: string;
  category: string;
  title: string;
  source: string;
  timestamp: string;
  sentiment: string;
}

export const newsAPI = {
  getAll: (category?: string, sentiment?: string): Promise<NewsSignal[] | { articles: NewsSignal[]; status: string; count: number; message?: string }> => {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (sentiment) params.append('sentiment', sentiment);
    
    const url = `${BASE_URL}/news-signals${params.toString() ? `?${params}` : ''}`;
    return fetch(url).then(r => r.json());
  },
  
  getById: (id: string): Promise<NewsSignal> =>
    fetch(`${BASE_URL}/news-signals/${id}`).then(r => r.json()),
};

// ============================================
// MARKET DATA API
// ============================================

export const marketAPI = {
  getIndices: (): Promise<any[]> =>
    fetch(`${BASE_URL}/market-indices`).then(r => r.json()),
  
  getQuote: (symbol: string): Promise<any> =>
    fetch(`${BASE_URL}/quote/${symbol}`).then(r => r.json()),
  
  getQuotes: (symbols: string[]): Promise<any[]> =>
    fetch(`${BASE_URL}/quotes?symbols=${symbols.join(',')}`).then(r => r.json()),
  
  getCentralBankRates: (): Promise<any[]> =>
    fetch(`${BASE_URL}/central-bank-rates`).then(r => r.json()),
};

// ============================================
// MACRO & CREDIT ENDPOINTS
// ============================================

export interface CentralBankRate {
  name: string;
  region?: string;
  rate: number;
  previousRate?: number;
  change?: number;
  // D38 : trend dérivé d'une variation FRED réelle (voir classifyTrend()
  // côté backend) ; nextMeeting/sentiment retirés (non sourcés).
  trend?: 'hawkish' | 'dovish' | 'hold';
  lastUpdate: string;
  dataSource?: 'fred' | 'static' | 'fallback';
}

export interface MacroIndicator {
  name: string;
  value: number | string;
  change: number;
  unit: string;
  lastUpdate: string;
  impact: 'High' | 'Medium' | 'Low';
}

export interface YieldCurvePoint {
  tenor: string;
  yield: number;
  change: number;
  lastUpdate?: string;
}

export interface CreditIndicator {
  name: string;
  level: 'Low' | 'Medium' | 'High';
  value: number;
  threshold: number;
  // D38 : dérivé d'une variation FRED réelle (delta vs dernière valeur
  // distincte précédente), plus jamais une constante fixe.
  trend: 'improving' | 'stable' | 'deteriorating';
  lastUpdate?: string;
}

export interface LBOMarketRates {
  status: string;
  timestamp: string;
  riskFreeRate: number;
  hySpread: number;
  impliedCostOfDebt: number;
  seniorSpread: number;
  impliedSeniorRate: number;
  sofr?: number | null;
  source: string;
}

export const macroAPI = {
  getCentralBankRates: (): Promise<{ status: string; rates: CentralBankRate[]; timestamp: string; source: string }> =>
    fetch(`${BASE_URL}/central-bank-rates`).then(r => r.json()),

  getMacroIndicators: (): Promise<{ status: string; indicators: MacroIndicator[]; timestamp: string; source: string }> =>
    fetch(`${BASE_URL}/macro-indicators`).then(r => r.json()),

  getYieldCurve: (): Promise<{ status: string; curve: YieldCurvePoint[]; curve2Y10Y: number; timestamp: string; source: string }> =>
    fetch(`${BASE_URL}/yield-curve`).then(r => r.json()),

  getCreditStress: (): Promise<{ status: string; indicators: CreditIndicator[]; overallRisk: string; timestamp: string; source: string }> =>
    fetch(`${BASE_URL}/credit-stress`).then(r => r.json()),
  
  getLBOMarketRates: (): Promise<LBOMarketRates> =>
    fetch(`${BASE_URL}/lbo-market-rates`).then(r => r.json()),
};

// ============================================
// MONEY MARKET & RATES
// ============================================

export interface MoneyMarketRate {
  name: string;
  tenor: string;
  value: number;
  change: number;
  unit: string;
  lastUpdate: string;
  // 'FRED (dérivé)' (D38) : calculé depuis une série FRED réelle via une
  // convention de spread documentée, pas une observation brute — voir
  // fredService.ts (Euribor 6M/12M, absents de FRED en direct).
  source: 'FRED' | 'FRED (dérivé)' | 'Yahoo' | 'Cache';
}

export interface MoneyMarketData {
  euribor: MoneyMarketRate[];
  riskFree: MoneyMarketRate[];
  governmentBonds: MoneyMarketRate[];
  timestamp: string;
}

export const moneyMarketAPI = {
  getEuriborRates: (): Promise<{ status: string; source: string; data: MoneyMarketData }> =>
    fetch(`${BASE_URL}/macro/euribor-rates`).then(r => r.json()),
};

// ============================================
// M&A ENGINE API (FastAPI :8000)
// ============================================

import type {
  SourcedTargetMA,
  PipelineStage,
  SourcedTargetListResponse,
  ScanResponse,
  ScanStatus,
  BatchScanResponse,
  DigitalDDReport,
  LegalEventsReport,
  TalentSignalsReport,
  PortfolioCompanyListResponse,
  MonthlyKPIListResponse,
  LBOCalculateRequest,
  LBOResult,
  BuildupRequest,
  BuildupResult,
  TargetPromoteResponse,
  SectorCalibration,
  LBOScenarioCreate,
  LBOScenario,
  LBOScenarioListItem,
  CompSetSummary,
  CompsTableResponse,
} from '../types';

export const maEngineAPI = {
  // ── Sourcing ────────────────────────────────

  /** Déclenche un scan OSINT complet en background. 202 Accepted. */
  scanTarget: (platform_url: string): Promise<ScanResponse> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ platform_url }),
    }).then(r => {
      if (!r.ok) throw new Error(`Scan failed: ${r.status}`);
      return r.json();
    }),

  /** D40 — statut réel du dernier scan (running/completed/failed), pour ne
   * jamais laisser un scan à 0 résultat comme un échec silencieux. */
  getScanStatus: (): Promise<ScanStatus | null> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/scan/status`).then(r => {
      if (!r.ok) throw new Error(`Scan status failed: ${r.status}`);
      return r.json();
    }),

  /** Liste paginée des cibles M&A sourcées. */
  getTargets: (offset = 0, limit = 50, status?: string): Promise<SourcedTargetListResponse> => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (status) params.append('status', status);
    return fetch(`${FASTAPI_BASE_URL}/sourcing?${params}`).then(r => {
      if (!r.ok) throw new Error(`getTargets failed: ${r.status}`);
      return r.json();
    });
  },

  /** Détail d'une cible M&A. */
  getTarget: (id: number): Promise<SourcedTargetMA> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/${id}`).then(r => {
      if (!r.ok) throw new Error(`getTarget(${id}) failed: ${r.status}`);
      return r.json();
    }),

  /** Promeut une cible qualifiée en Deal exécutable (D14, Tâche B.5). 409 si déjà promue. */
  promoteTarget: (id: number): Promise<TargetPromoteResponse> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/${id}/promote`, { method: 'POST' }).then(async r => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `promoteTarget(${id}) failed: ${r.status}`);
      }
      return r.json();
    }),

  /** Met à jour l'étape pipeline Kanban d'une cible. */
  updateTargetStage: (id: number, stage: PipelineStage): Promise<SourcedTargetMA> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/${id}/stage`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage }),
    }).then(r => {
      if (!r.ok) throw new Error(`updateTargetStage(${id}) failed: ${r.status}`);
      return r.json();
    }),

  /** Rapport Digital DD (Tech Stack + Google Trends) pour une cible. */
  getDigitalDD: (id: number): Promise<DigitalDDReport> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/${id}/digital-dd`).then(r => {
      if (!r.ok) throw new Error(`getDigitalDD(${id}) failed: ${r.status}`);
      return r.json();
    }),

  /** Historique légal & corporate (Pappers / mock) pour une cible. */
  getLegalEvents: (id: number): Promise<LegalEventsReport> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/${id}/legal-events`).then(r => {
      if (!r.ok) throw new Error(`getLegalEvents(${id}) failed: ${r.status}`);
      return r.json();
    }),

  /** Talent & HR Intelligence (Adzuna / mock) pour une cible. */
  getTalentSignals: (id: number): Promise<TalentSignalsReport> =>
    fetch(`${FASTAPI_BASE_URL}/sourcing/${id}/talent-signals`).then(r => {
      if (!r.ok) throw new Error(`getTalentSignals(${id}) failed: ${r.status}`);
      return r.json();
    }),

  /** Liste des participations (portfolio companies). */
  getPortfolioCompanies: (): Promise<PortfolioCompanyListResponse> =>
    fetch(`${FASTAPI_BASE_URL}/portfolio`).then(r => {
      if (!r.ok) throw new Error(`getPortfolioCompanies failed: ${r.status}`);
      return r.json();
    }),

  /** Historique des KPIs mensuels d'une participation. */
  getPortfolioKPIs: (portfolioCompanyId: number): Promise<MonthlyKPIListResponse> =>
    fetch(`${FASTAPI_BASE_URL}/portfolio/${portfolioCompanyId}/kpis`).then(r => {
      if (!r.ok) throw new Error(`getPortfolioKPIs(${portfolioCompanyId}) failed: ${r.status}`);
      return r.json();
    }),

  /** Export CSV de toutes les cibles. Retourne un Blob. */
  exportCSV: (status?: string): Promise<Blob> => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    return fetch(`${FASTAPI_BASE_URL}/sourcing/export?${params}`).then(r => {
      if (!r.ok) throw new Error(`exportCSV failed: ${r.status}`);
      return r.blob();
    });
  },

  /** Upload batch CSV et lance les scans en background. */
  batchScan: (file: File): Promise<BatchScanResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${FASTAPI_BASE_URL}/sourcing/batch`, {
      method: 'POST',
      body: formData,
    }).then(r => {
      if (!r.ok) throw new Error(`batchScan failed: ${r.status}`);
      return r.json();
    });
  },

  /** Upload PDF teaser/CIM to create a new deal via AI extraction. */
  uploadTeaser: (file: File): Promise<SourcedTargetMA> => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${FASTAPI_BASE_URL}/sourcing/upload-teaser`, {
      method: 'POST',
      body: formData,
    }).then(r => {
      if (!r.ok) throw new Error(`uploadTeaser failed: ${r.status}`);
      return r.json();
    });
  },

  // ── LBO Engine ──────────────────────────────

  /** Exécute un Paper LBO (curseurs ajustables en direct). */
  calculateLbo: (payload: LBOCalculateRequest): Promise<LBOResult> =>
    fetch(`${FASTAPI_BASE_URL}/lbo/calculate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => {
      if (!r.ok) throw new Error(`calculateLbo failed: ${r.status}`);
      return r.json();
    }),

  /** Exporte le modèle LBO au format Excel (.xlsx). Retourne un Blob. */
  exportLboExcel: (payload: LBOCalculateRequest): Promise<Blob> =>
    fetch(`${FASTAPI_BASE_URL}/lbo/export-excel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => {
      if (!r.ok) throw new Error(`exportLboExcel failed: ${r.status}`);
      return r.blob();
    }),

  /** Simule un Build-up (Multiple Arbitrage). */
  calculateBuildup: (payload: BuildupRequest): Promise<BuildupResult> =>
    fetch(`${FASTAPI_BASE_URL}/lbo/buildup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => {
      if (!r.ok) throw new Error(`calculateBuildup failed: ${r.status}`);
      return r.json();
    }),

  /** Chaîne de calibrage sectoriel dérivée du CompSet réel (D22, Tâche B.8). */
  getLboCalibration: (sectorOrNaf: string, discount?: number | null): Promise<SectorCalibration> => {
    const params = new URLSearchParams({ sector_or_naf: sectorOrNaf });
    if (discount != null) params.append('size_illiquidity_discount', String(discount));
    return fetch(`${FASTAPI_BASE_URL}/lbo/calibration?${params}`).then(r => {
      if (!r.ok) throw new Error(`getLboCalibration failed: ${r.status}`);
      return r.json();
    });
  },

  // ── LBO Scenarios (D23, Tâche B.8) ──────────

  /** Sauvegarde explicite d'un scénario LBO rattaché à un deal. */
  saveLboScenario: (payload: LBOScenarioCreate): Promise<LBOScenario> =>
    fetch(`${FASTAPI_BASE_URL}/lbo/scenarios`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => {
      if (!r.ok) throw new Error(`saveLboScenario failed: ${r.status}`);
      return r.json();
    }),

  /** Liste les scénarios LBO sauvegardés pour un deal. */
  getLboScenarios: (dealId: number): Promise<LBOScenarioListItem[]> =>
    fetch(`${FASTAPI_BASE_URL}/lbo/scenarios?deal_id=${dealId}`).then(r => {
      if (!r.ok) throw new Error(`getLboScenarios failed: ${r.status}`);
      return r.json();
    }),

  /** Détail complet d'un scénario LBO (pour rechargement dans le calculateur). */
  getLboScenario: (scenarioId: number): Promise<LBOScenario> =>
    fetch(`${FASTAPI_BASE_URL}/lbo/scenarios/${scenarioId}`).then(r => {
      if (!r.ok) throw new Error(`getLboScenario(${scenarioId}) failed: ${r.status}`);
      return r.json();
    }),

  /** Supprime un scénario LBO. */
  deleteLboScenario: (scenarioId: number): Promise<{ status: string; id: number }> =>
    fetch(`${FASTAPI_BASE_URL}/lbo/scenarios/${scenarioId}`, { method: 'DELETE' }).then(r => {
      if (!r.ok) throw new Error(`deleteLboScenario(${scenarioId}) failed: ${r.status}`);
      return r.json();
    }),

  // ── Trading Comps Engine (Tâche B.10) — lecture seule, endpoints B.3/B.4 ──

  /** Liste les comp sets existants. */
  getCompSets: (): Promise<CompSetSummary[]> =>
    fetch(`${FASTAPI_BASE_URL}/comps`).then(r => {
      if (!r.ok) throw new Error(`getCompSets failed: ${r.status}`);
      return r.json();
    }),

  /** Table de comparables complète (lignes + stats agrégées) pour un comp set. */
  getCompsTable: (compSetId: number): Promise<CompsTableResponse> =>
    fetch(`${FASTAPI_BASE_URL}/comps/${compSetId}`).then(r => {
      if (!r.ok) throw new Error(`getCompsTable(${compSetId}) failed: ${r.status}`);
      return r.json();
    }),

  // ── Health ──────────────────────────────────

  /** Health check FastAPI. */
  health: (): Promise<{ status: string; version: string }> =>
    fetch(`${FASTAPI_BASE_URL}/health`).then(r => r.json()),
};
