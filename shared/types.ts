// ============================================
// SHARED TYPES — Single source of truth
// Used by both backend and frontend
// ============================================

// --- Market Data ---
export interface MarketIndex {
  symbol: string;
  value: number;
  change: number;
  changePercent: number;
}

// --- Provenance des données financières (D18, Tâche B.6) ---
// Miroir de api/schemas/provenance.py.
export type DataProvenance = 'REGISTRY' | 'DOCUMENT' | 'MARKET' | 'ESTIMATE' | 'MANUAL' | 'UNKNOWN';

export interface FieldProvenance {
  provenance: DataProvenance;
  as_of?: string | null;    // exercice concerné, ex. "2022"
  reference?: string | null; // URL, nom de fichier, ou méthode d'estimation
}

// --- PE Deals ---
// Miroir exact de api/schemas/deals.py::DealOut (FastAPI /deals, source de vérité M&A).
export interface Deal {
  id: number;
  acquirer_name: string;
  target_name: string | null;
  sourced_target_id: number | null; // D14 (Tâche B.5) — lien vers la cible sourcing d'origine, si promue
  target_type: string | null; // 'target' | 'platform' (D11), lu depuis la cible sourcing liée
  announcement_date: string | null;
  close_date: string | null;
  deal_type: string | null;
  status: string;
  deal_value: number | null; // $ (montant brut, pas en milliards) — taille de transaction, PAS l'EV cible
  target_revenue: number | null; // D15 — CA de la cible
  target_ebitda: number | null; // D15 — EBITDA de la cible (saisi en human-in-the-loop)
  enterprise_value: number | null; // D15 — EV de la cible, jamais dérivée de deal_value
  ev_revenue_multiple: number | null;
  ev_ebitda_multiple: number | null;
  premium_paid: number | null;
  sector: string | null;
  country: string | null;
  description: string | null;
  ic_memo?: string | null;
  updated_at?: string | null;
  financial_provenance?: Record<string, FieldProvenance> | null; // D18 (Tâche B.6)
}

export interface DealCreateInput {
  acquirer_name?: string;
  target_name?: string;
  sourced_target_id?: number | null;
  announcement_date?: string | null;
  close_date?: string | null;
  deal_type?: string | null;
  status?: string;
  deal_value?: number | null;
  equity_value?: number | null;
  enterprise_value_deal?: number | null;
  target_revenue?: number | null;
  target_ebitda?: number | null;
  enterprise_value?: number | null;
  ev_revenue_multiple?: number | null;
  ev_ebitda_multiple?: number | null;
  pe_multiple?: number | null;
  premium_paid?: number | null;
  sector?: string | null;
  industry?: string | null;
  country?: string | null;
  description?: string | null;
  source?: string | null;
  source_url?: string | null;
  financial_provenance?: Record<string, FieldProvenance> | null; // D18 (Tâche B.6)
}

// Miroir de api/schemas/deals.py::DealListResponse (GET /deals)
export interface DealListResponse {
  total: number;
  offset: number;
  limit: number;
  deals: Deal[];
}

export type DealActivityType = 'system_event' | 'user_note';

export interface DealActivity {
  id: number;
  deal_id: number;
  action_type: DealActivityType;
  content: string;
  created_at: string;
}

export interface DealActivityListResponse {
  deal_id: number;
  total: number;
  activities: DealActivity[];
}

export interface DealNoteInput {
  content: string;
}

// --- PE Funds ---
export interface Fund {
  id: string;
  name: string;
  manager: string;
  vintage: number;
  aum: number; // Billions
  irr: number; // Percentage
  moic: number; // Multiple
  dpi: number; // Percentage
  strategy: string;
}

// --- Sectors ---
export interface SectorMetric {
  name: string;
  dealVolumeYTD: number; // Billions
  dealCountYTD: number;
  avgMultiple: number;
  trend: 'up' | 'down' | 'stable';
}

// --- News & Signals ---
// D33 (Tâche Review Produit — Partie C) : catégories thématiques alignées sur
// la thèse (TIC/réglementation, macro/financement, deal activity PE
// mid-market France/Europe) — remplace les 5 catégories PE génériques
// devinées a posteriori par score de mots-clés (voir newsService.ts).
export type NewsCategory = 'TIC & Réglementation' | 'Macro & Financement' | 'Deal Activity PE';
export type Sentiment = 'Bullish' | 'Bearish' | 'Neutral';

export interface NewsSignal {
  id: string;
  category: NewsCategory;
  title: string;
  source: string;
  timestamp: string;
  sentiment: Sentiment;
}

export interface NewsArticle {
  id: string;
  title: string;
  source: string;
  publishedAt: string;
  url: string;
  description: string;
  sentiment: Sentiment;
  category: NewsCategory;
}

// --- Deal Sourcing ---
export type DealStatus = 'Watchlist' | 'Deep Dive' | 'Passed' | 'Active';

export interface SourcingTarget {
  id: string;
  name: string;
  sector: string;
  revenue: number; // $M
  ebitdaMargin: number; // %
  growthRate: number; // % YoY
  status: DealStatus;
  description: string;
}

// --- Central Bank Rates ---
export interface CentralBankRate {
  name: string;
  region?: string;
  rate: number;
  previousRate?: number;
  change?: number;
  // D38 (Revue Produit) : trend est désormais dérivé de `change` réel
  // (voir classifyTrend() dans backend/routes/macro.ts), jamais une
  // constante. nextMeeting a été retiré : aucune source réelle (calendrier
  // de politique monétaire) n'est branchée — afficher une date inventée
  // était plus trompeur que de ne rien afficher.
  trend?: 'hawkish' | 'dovish' | 'hold';
  lastUpdate: string;
  dataSource?: 'fred' | 'static' | 'fallback';
}

// --- Macro ---
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
  // D38 : dérivé d'une variation FRED réelle, plus jamais une constante fixe.
  trend: 'improving' | 'stable' | 'deteriorating';
  lastUpdate?: string;
}

// --- Money Market ---
export interface MoneyMarketRate {
  name: string;
  tenor: string;
  value: number;
  change: number;
  unit: string;
  lastUpdate: string;
  // 'FRED (dérivé)' (D38, Revue Produit) : valeur calculée à partir d'une
  // série FRED réelle par une convention de marché documentée (spread fixe),
  // PAS une observation FRED brute — jamais confondue avec 'FRED' dans
  // l'affichage (voir fredService.ts, Euribor 6M/12M).
  source: 'FRED' | 'FRED (dérivé)' | 'Yahoo' | 'Cache';
}

export interface MoneyMarketData {
  euribor: MoneyMarketRate[];
  riskFree: MoneyMarketRate[];
  governmentBonds: MoneyMarketRate[];
  timestamp: string;
}

// --- Portfolio ---
export interface PortfolioSummary {
  aum: number;
  activeDeals: number;
  exitedDeals: number;
  averageIRR: number;
  averageMOIC: number;
  portfolioValue: number;
  gainLoss: number;
}

// --- Cache ---
export interface CacheFile<T = any> {
  timestamp: number;
  data: T;
}

// --- Document Ingestion ---
export interface SourcedTargetMatch {
  id: number;
  company_name: string;
  siren: string | null;
  similarity: number; // 0-1, jamais appliqué automatiquement (Tâche B.5, Étape 3)
}

// D25 (Tâche B.10) : drapeau de vraisemblance serveur — ne corrige rien,
// signale une valeur suspecte pour la modale de review (jamais une
// correction automatique, toujours humaine).
export interface ExtractionFlag {
  field: string;
  reason: string;
  severity: string;
}

export interface DocumentExtraction {
  company_name: string;
  business_summary: string;
  estimated_revenue: number | null;
  estimated_ebitda: number | null;
  // D44 (Tâche Finalisation) : exercice de référence des montants ci-dessus,
  // jamais deviné — null si non déterminable depuis le document.
  fiscal_year: number | null;
  sourced_target_matches: SourcedTargetMatch[];
  flags: ExtractionFlag[];
}

// ============================================
// M&A ENGINE TYPES (FastAPI backend :8000)
// Maps to Pydantic schemas in api/schemas/
// ============================================

// --- Sourced Target (from OSINT pipeline) ---
export type SourcedTargetStatus = 'Watchlist' | 'Deep Dive' | 'Passed' | 'Active' | 'Contacted' | 'Archived';
export type PipelineStage = 'Screening' | 'NDA Signed' | 'Management Meeting' | 'Due Diligence' | 'IC Memo' | 'Closed' | 'Passed' | 'Archived';
export type TargetType = 'target' | 'platform';

export interface SourcedTargetMA {
  id: number;
  company_name: string;
  url: string;
  company_id: number | null;
  siren: string | null;
  source: string | null;
  target_type: TargetType | null;
  business_summary: string | null;
  keywords: string[] | null;
  score: number | null;

  // Financials estimés
  revenue_estimate: number | null;
  ebitda_estimate: number | null;
  enterprise_value: number | null;

  // OSINT signals
  growth_signals: string[] | null;
  red_flags: string[] | null;
  competitors: string[] | null;

  // LBO quick-screen
  lbo_irr: number | null;
  lbo_moic: number | null;
  entry_multiple: number | null;
  lbo_projections: Record<string, any> | null;

  // Pipeline
  status: SourcedTargetStatus;
  pipeline_stage: PipelineStage;
  created_at: string;
  updated_at: string;

  // D14 (Tâche B.5) — non-null si la cible a déjà été promue en Deal
  promoted_deal_id: number | null;
}

export interface TargetPromoteResponse {
  deal_id: number;
  sourced_target_id: number;
  message: string;
}

export interface SourcedTargetListResponse {
  total: number;
  offset: number;
  limit: number;
  targets: SourcedTargetMA[];
}

export interface ScanResponse {
  message: string;
  platform_url: string;
}

// D46 (Tâche Finalisation, Partie B) — miroir de api/schemas/sourcing.py::ScanSavedTarget.
export interface ScanSavedTarget {
  id: number;
  company_name: string;
  url: string;
  score: number | null;
}

// D40/D46 (Tâche Finalisation) — miroir de api/schemas/sourcing.py::ScanStatus.
export interface ScanStatus {
  platform_url: string;
  status: 'running' | 'completed' | 'failed';
  started_at: string;
  finished_at: string | null;
  seed_company_name: string | null;
  targets_found: number | null;
  targets_scored: number | null;
  targets_saved: number | null;
  targets_skipped: number | null;
  saved_targets: ScanSavedTarget[] | null;
  error: string | null;
}

export interface BatchScanResponse {
  message: string;
  total_urls: number;
  urls: string[];
}

// --- Digital Due Diligence (Alt Data) ---

export interface TechStackItem {
  name: string;
  category: string;
  color?: string;
}

export interface TechStackResult {
  technologies: TechStackItem[];
  source: 'builtwith' | 'mock' | 'error';
  domain: string;
}

export interface SearchTrendPoint {
  date: string;
  value: number;
}

export interface SearchTrendsResult {
  keyword: string;
  points: SearchTrendPoint[];
  source: 'google_trends' | 'mock' | 'error';
}

export interface DigitalDDReport {
  domain: string;
  company_name: string;
  tech_stack: TechStackResult;
  search_trends: SearchTrendsResult;
  generated_at: string;
}

// --- Legal & Corporate Watch (Sprint 3 — "Le Greffier Automatique") ---

export type MaSignal = 'Bullish' | 'Neutral' | 'Red Flag';

export interface CorporateEvent {
  date: string;
  label: string;
  description: string;
  source: 'BODACC' | 'Greffe' | string;
  signal: MaSignal;
  signal_reason: string;
}

export interface LegalEventsReport {
  company_name: string;
  siren: string;
  events: CorporateEvent[];
  source: 'pappers' | 'mock';
  generated_at: string;
}

// --- Talent & HR Intelligence (Sprint 4 — "Le Recrutement comme Leading Indicator") ---

export type TrendSignal = 'Hyper-Growth' | 'Growth' | 'Stable' | 'Contraction' | 'Low Activity';
export type JobCategory = 'Tech' | 'Sales' | 'Finance' | 'Operations' | 'Executive' | 'Other';

export interface JobOpening {
  title: string;
  category: JobCategory;
  is_executive: boolean;
  location: string;
  posted_date: string;
  salary_range: string | null;
  company: string;
  url: string;
}

export interface TalentSignalsReport {
  company_name: string;
  total_openings: number;
  hiring_velocity_score: number;
  headcount_trend: string;
  trend_signal: TrendSignal;
  department_breakdown: Record<string, number>;
  recent_job_openings: JobOpening[];
  source: 'adzuna' | 'mock';
  generated_at: string;
}

// D49 (Tâche Finalisation) : PublicPeer/PrivatePeer/CompsReport (Sprint 7,
// "Comparable Intelligence" par cible — public peers LLM en texte libre,
// private peers fabriqués via un repli Pappers systématique) retirés. La
// vue détail valorise désormais via SectorCalibration + CompsTableResponse
// ci-dessous (CompSet TIC réel), déjà utilisés par LBOCalculator/Comparables.

// --- Trading Comps Engine (Tâche B.3/B.4, page frontend Tâche B.10) ---
// Miroir exact de api/schemas/comps.py — sondé sur l'API réelle (RAPPORT
// B.10, Étape 2.1), pas supposé. AUCUN champ de provenance (financial_
// provenance) n'est exposé par ces endpoints malgré son existence sur les
// modèles Company/Financial depuis B.7 — champ manquant documenté au rapport,
// pas ajouté ici (lecture seule imposée sur le Comps Engine, Tâche B.10).

export interface CompSetSummary {
  id: number;
  name: string;
  description: string | null;
  base_year: number | null;
  ticker_count: number;
  created_at: string;
}

export interface CompRow {
  ticker: string;
  name: string;
  sector: string | null;
  country: string | null;
  market_cap: number | null;
  enterprise_value: number | null;
  revenue: number | null;
  ebitda: number | null;
  net_income: number | null;
  revenue_growth: number | null;
  gross_margin: number | null;
  ebitda_margin: number | null;   // en points de %, ex. 19.97 = 19,97 %
  net_margin: number | null;      // idem
  ev_revenue: number | null;
  ev_ebitda: number | null;
  pe_ratio: number | null;
  price_to_book: number | null;
  roe: number | null;
  debt_to_equity: number | null;
  net_debt_to_ebitda: number | null;
  fcf_yield: number | null;
  current_ratio: number | null;
  // D18/D19, branché Tâche B.11 : exercice fiscal de la ligne (le champ
  // base_year du comp set est global, ERF.PA porte un exercice différent —
  // constaté en B.10) et provenance par champ chiffré (même format que
  // Deal.financial_provenance).
  fiscal_year: number | null;
  financial_provenance: Record<string, FieldProvenance>;
}

export interface CompStatsBlock {
  ev_revenue?: number | null;
  ev_ebitda?: number | null;
  pe_ratio?: number | null;
  price_to_book?: number | null;
  gross_margin?: number | null;
  ebitda_margin?: number | null;
  net_margin?: number | null;
  roe?: number | null;
  revenue_growth?: number | null;
  debt_to_equity?: number | null;
  current_ratio?: number | null;
}

export interface CompStats {
  mean: CompStatsBlock;
  median: CompStatsBlock;
  p25: CompStatsBlock;
  p75: CompStatsBlock;
}

export interface CompsTableResponse {
  comp_set_id: number;
  comp_set_name: string;
  base_year: number;
  rows: CompRow[];
  stats: CompStats;
}

// --- Portfolio Monitoring (Sprint 6) ---

export interface PortfolioCompany {
  id: number;
  sourced_target_id: number;
  company_name: string;
  entry_date: string;
  created_at: string;
  updated_at: string;
}

export interface PortfolioCompanyListResponse {
  total: number;
  companies: PortfolioCompany[];
}

export interface MonthlyKPI {
  id: number;
  portfolio_company_id: number;
  month_date: string;
  actual_revenue: number;
  budget_revenue: number;
  actual_ebitda: number;
  budget_ebitda: number;
  cash_balance: number;
  created_at: string;
  updated_at: string;
}

export interface MonthlyKPIListResponse {
  portfolio_company_id: number;
  company_name: string;
  total: number;
  kpis: MonthlyKPI[];
}

// --- LBO Model — V3 (Multi-Tranche Debt, Management Package, Waterfall) ---

export type AmortizationType = 'bullet' | 'amortizing';

export interface DebtTranche {
  name: string;
  amount_turns: number;
  interest_rate: number;
  amortization: AmortizationType;
}

export interface ManagementPackage {
  sweet_equity_pct: number;
  ratchet_irr_threshold: number;
  ratchet_bonus_pct: number;
}

export interface WaterfallOutput {
  total_exit_equity: number;
  management_sweet_pct: number;
  ratchet_triggered: boolean;
  management_total_pct: number;
  management_proceeds: number;
  fund_proceeds: number;
  fund_moic: number;
  fund_irr: number;
  management_moic: number;
}

export interface DebtTrancheYear {
  name: string;
  interest: number;
  amortization: number;
  balance_eoy: number;
}

export interface LBOProjectionYear {
  year: number;
  revenue: number;
  ebitda: number;
  interest: number;
  capex?: number;
  delta_wcr?: number;
  taxable_income?: number;
  tax?: number;
  fcf: number;
  debt_paydown: number;
  debt_eoy: number;
  // V3: per-tranche breakdown
  tranches?: DebtTrancheYear[];
}

export interface LBOCalculateRequest {
  revenue: number;
  sector_or_naf?: string;
  holding_period?: number;
  override_entry_mult?: number | null;
  override_exit_mult?: number | null;
  override_leverage?: number | null;
  // V3: multi-tranche debt
  debt_structure?: DebtTranche[];
  // V3: management package
  management_package?: ManagementPackage | null;
  // D22 (Tâche B.8) : calibrage sectoriel dérivé du CompSet réel
  use_sector_calibration?: boolean;
  size_illiquidity_discount?: number | null;
  // D27 : métadonnées d'un scénario auto-généré (build_base_case_scenario/
  // build_downside_scenario) — absentes des payloads du calculateur manuel.
  auto_generated?: boolean;
  auto_generated_reason?: string;
  // Tâche "P2 : crédibilité de la thèse" (Partie A) — étiquette "indicatif"
  // sous le seuil de taille, posée par build_base_case_scenario.
  sizing_tier?: 'standalone' | 'indicative_bolt_on';
  sizing_note?: string | null;
  // Tâche "P2" (Partie B) — métadonnées du cas baissier, posées par
  // build_downside_scenario (absentes du base case).
  downside_of_revenue?: number;
  downside_revenue_haircut_pct?: number;
  downside_exit_multiple_delta?: number;
}

// --- Sector Calibration (D22, Tâche B.8) — miroir de api/schemas/lbo.py::SectorCalibrationOut ---
export interface SectorCalibration {
  sufficient: boolean;
  fallback_reason: string | null;
  applicable: boolean;
  sample_size: number;
  comp_set_id: number | null;
  comp_set_name: string | null;
  tickers: string[];
  fiscal_years: number[];
  median_ebitda_margin: number | null;
  ebitda_margin_min: number | null;
  ebitda_margin_max: number | null;
  median_ev_ebitda: number | null;
  ev_ebitda_min: number | null;
  ev_ebitda_max: number | null;
  size_illiquidity_discount: number;
  discount_label: string;
  derived_entry_multiple: number | null;
  entry_multiple_provenance: FieldProvenance | null;
  ebitda_margin_provenance: FieldProvenance | null;
}

export interface LBOResult {
  // Sources & Uses
  entry_revenue: number;
  entry_ebitda: number;
  entry_ev: number;
  entry_debt: number;
  entry_equity: number;
  leverage_entry: number;
  ebitda_margin: number;
  multiple: number;
  entry_multiple: number;
  exit_multiple: number;
  sector_profile: string;
  revenue_growth: number;
  holding_period: number;
  interest_rate: number;

  // V3: per-tranche sources
  debt_tranches_detail: Array<Record<string, any>>;

  // Exit
  exit_revenue: number;
  exit_ebitda: number;
  exit_ev: number;
  exit_debt: number;
  exit_equity: number;
  leverage_exit: number;

  // Returns (gross, pre-waterfall)
  moic: number;
  irr: number;

  // V3: Waterfall (Fund vs Management)
  waterfall: WaterfallOutput | null;

  // Projections
  projections: LBOProjectionYear[];

  // D22 (Tâche B.8) : présent uniquement si use_sector_calibration=true a été demandé
  calibration?: SectorCalibration;

  // D45 (Tâche Finalisation, Partie F) : provenance des hypothèses du
  // scénario base-case (revenue, entry_multiple, ebitda_margin), au même
  // format FieldProvenance que Deal.financial_provenance / CompRow.financial_provenance
  // — voir api/services/lbo_scenario_service.py::_build_scenario_provenance.
  // Uniquement présent sur un scénario sauvegardé (LBOScenario.result_json),
  // jamais sur le résultat d'un calcul LBO interactif non sauvegardé.
  financial_provenance?: Record<string, FieldProvenance>;
}

// --- LBO Scenarios (D23, Tâche B.8) — miroir de api/schemas/lbo.py ---
export interface LBOScenarioCreate {
  deal_id: number;
  label: string;
  assumptions: LBOCalculateRequest;
  result: LBOResult;
}

export interface LBOScenario {
  id: number;
  deal_id: number;
  label: string;
  assumptions_json: LBOCalculateRequest;
  result_json: LBOResult;
  created_at: string;
}

export interface LBOScenarioListItem {
  id: number;
  deal_id: number;
  label: string;
  created_at: string;
  entry_multiple: number | null;
  exit_multiple: number | null;
  irr: number | null;
  moic: number | null;
}

// --- Build-up / Multiple Arbitrage ---
export interface BuildupAddonDetail {
  url: string;
  revenue: number;
  ebitda: number;
  ev: number;
  entry_multiple: number;
  estimated: boolean;
}

// D37 (Revue Produit) : hypothèses par défaut = profil sectoriel TIC
// calibré ("professional_svc"), toutes surchargeables.
export interface BuildupRequest {
  platform_target: Record<string, any>;
  addon_targets: Record<string, any>[];
  synergy_pct?: number;
  capex_pct?: number | null;
  wcr_pct?: number | null;
  leverage_turns?: number | null;
  growth_override?: number | null;
}

export interface BuildupAssumptions {
  growth_rate: number;
  growth_source: string;
  capex_pct: number;
  capex_source: string;
  wcr_pct: number;
  wcr_source: string;
  leverage_turns: number;
  leverage_source: string;
  interest_rate: number;
  tax_rate: number;
  synergy_pct: number;
  sector_profile_reference: string;
}

export interface BuildupResult {
  // Consolidation Year 0
  consolidated_revenue: number;
  consolidated_ebitda_pre_syn: number;
  synergies: number;
  synergy_pct: number;
  consolidated_ebitda_post_syn: number;
  consolidated_margin: number;
  growth_rate: number;

  // Acquisition
  platform_ev: number;
  platform_multiple: number;
  platform_url: string;
  platform_estimated: boolean;
  addons_ev: number;
  addons_count: number;
  addon_details: BuildupAddonDetail[];
  excluded_addons: string[];
  total_acquisition_cost: number;
  blended_entry_multiple: number;

  // Financement
  entry_debt: number;
  entry_equity: number;

  // Exit
  exit_ebitda: number;
  exit_ev: number;
  exit_debt: number;
  exit_equity: number;
  exit_multiple_applied: number;

  // Returns
  moic_buildup: number;
  irr_buildup: number;
  moic_standalone: number;
  irr_standalone: number;
  delta_irr: number;

  // Projections
  projections: LBOProjectionYear[];

  // Hypothèses effectivement appliquées (D37)
  assumptions_used: BuildupAssumptions;
}
