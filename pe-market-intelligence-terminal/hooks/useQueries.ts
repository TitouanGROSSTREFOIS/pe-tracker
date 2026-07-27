import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { NewsArticle, LBOCalculateRequest, BuildupRequest, PipelineStage, LBOScenarioCreate } from '../../shared/types';
import {
  dealsAPI,
  newsAPI,
  macroAPI,
  moneyMarketAPI,
  marketAPI,
  maEngineAPI,
} from '../services/apiService';

// ============================================
// REACT QUERY HOOKS — Replace manual useEffect+useState
// ============================================

// --- Deals ---
export function useDeals(sector?: string) {
  return useQuery({
    queryKey: ['deals', sector],
    queryFn: () => dealsAPI.getAll(sector),
    staleTime: 5 * 60 * 1000, // 5 min
  });
}

// --- Single deal (D16, Tâche B.5 — pré-remplissage du LBO Calculator) ---
export function useDeal(dealId: number | null) {
  return useQuery({
    queryKey: ['deal', dealId],
    queryFn: () => dealsAPI.getById(dealId!),
    enabled: dealId !== null && dealId > 0,
    staleTime: 60 * 1000,
  });
}

// --- Mutation: update deal status (D31 — Deal Pipeline) ---
export function useUpdateDealStatusMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      dealsAPI.updateStatus(id, status),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['deals'] });
      queryClient.invalidateQueries({ queryKey: ['deal', variables.id] });
    },
  });
}

// --- Quote ---
export function useQuote(symbol: string) {
  return useQuery({
    queryKey: ['quote', symbol],
    queryFn: () => marketAPI.getQuote(symbol),
    staleTime: 60 * 1000, // 1 min
    enabled: !!symbol,
  });
}

// --- News Signals ---
export function useNewsSignals(category?: string, sentiment?: string) {
  return useQuery<NewsArticle[]>({
    queryKey: ['news-signals', category, sentiment],
    queryFn: async () => {
      const data = await newsAPI.getAll(category, sentiment);
      // Normalize polymorphic response
      const articles = Array.isArray(data) ? data : (data?.articles || []);
      return articles as unknown as NewsArticle[];
    },
    staleTime: 2 * 60 * 1000, // 2 min
  });
}

// --- Macro: Central Bank Rates ---
// D38 (Revue Produit) — le hook "array" ET le hook "meta" doivent partager
// EXACTEMENT le même queryFn pour la même queryKey (React Query met en cache
// le résultat brut du PREMIER queryFn exécuté sous cette clé ; deux queryFn
// différents sous la même clé désynchronisent silencieusement `select`,
// c'est ce qui causait un faux badge "repli" alors que FRED répondait bien
// — bug détecté et corrigé pendant cette tâche). `select` fait toute la
// projection, jamais le queryFn.
export function useCentralBankRates() {
  return useQuery({
    queryKey: ['central-bank-rates'],
    queryFn: () => macroAPI.getCentralBankRates(),
    staleTime: 10 * 60 * 1000, // 10 min
    select: (res) => res.rates,
  });
}

// --- Macro: Indicators ---
export function useMacroIndicators() {
  return useQuery({
    queryKey: ['macro-indicators'],
    queryFn: () => macroAPI.getMacroIndicators(),
    staleTime: 10 * 60 * 1000,
    select: (res) => res.indicators,
  });
}

// --- Macro: Yield Curve ---
export function useYieldCurve() {
  return useQuery({
    queryKey: ['yield-curve'],
    queryFn: () => macroAPI.getYieldCurve(),
    staleTime: 10 * 60 * 1000,
    select: (res) => res.curve,
  });
}

// --- Macro: Credit Stress ---
export function useCreditStress() {
  return useQuery({
    queryKey: ['credit-stress'],
    queryFn: () => macroAPI.getCreditStress(),
    staleTime: 10 * 60 * 1000,
    select: (res) => res.indicators,
  });
}

// Méta-hooks partageant la même queryKey/queryFn que les hooks ci-dessus
// (même requête réseau, pas de fetch supplémentaire) pour exposer
// `source`/`timestamp` à CreditMacro.tsx (badge de fraîcheur/origine des
// données) sans changer la forme (tableau) attendue par les autres
// consommateurs (ex. MarketIntelligence.tsx).
export function useCentralBankRatesMeta() {
  return useQuery({
    queryKey: ['central-bank-rates'],
    queryFn: () => macroAPI.getCentralBankRates(),
    staleTime: 10 * 60 * 1000,
    select: (res) => ({ source: res.source, timestamp: res.timestamp }),
  });
}

export function useMacroIndicatorsMeta() {
  return useQuery({
    queryKey: ['macro-indicators'],
    queryFn: () => macroAPI.getMacroIndicators(),
    staleTime: 10 * 60 * 1000,
    select: (res) => ({ source: res.source, timestamp: res.timestamp }),
  });
}

export function useYieldCurveMeta() {
  return useQuery({
    queryKey: ['yield-curve'],
    queryFn: () => macroAPI.getYieldCurve(),
    staleTime: 10 * 60 * 1000,
    select: (res) => ({ source: res.source, timestamp: res.timestamp }),
  });
}

export function useCreditStressMeta() {
  return useQuery({
    queryKey: ['credit-stress'],
    queryFn: () => macroAPI.getCreditStress(),
    staleTime: 10 * 60 * 1000,
    select: (res) => ({ source: res.source, timestamp: res.timestamp, overallRisk: res.overallRisk }),
  });
}

// --- Money Market ---
export function useMoneyMarketRates() {
  return useQuery({
    queryKey: ['money-market-rates'],
    queryFn: async () => {
      const res = await moneyMarketAPI.getEuriborRates();
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// --- LBO Market Rates ---
export function useLBOMarketRates() {
  return useQuery({
    queryKey: ['lbo-market-rates'],
    queryFn: () => macroAPI.getLBOMarketRates(),
    staleTime: 10 * 60 * 1000,
  });
}


// ============================================
// M&A ENGINE HOOKS (FastAPI :8000)
// ============================================

// --- Sourced Targets (paginated) ---
export function useSourcedTargets(offset = 0, limit = 50, status?: string) {
  return useQuery({
    queryKey: ['sourced-targets', offset, limit, status],
    queryFn: () => maEngineAPI.getTargets(offset, limit, status),
    staleTime: 30 * 1000, // 30s — targets change when scans complete
  });
}

// --- Single Sourced Target ---
export function useSourcedTarget(id: number | null) {
  return useQuery({
    queryKey: ['sourced-target', id],
    queryFn: () => maEngineAPI.getTarget(id!),
    enabled: id !== null && id > 0,
    staleTime: 60 * 1000,
  });
}

// --- Digital DD (Alt Data) ---
export function useDigitalDD(targetId: number | null) {
  return useQuery({
    queryKey: ['digital-dd', targetId],
    queryFn: () => maEngineAPI.getDigitalDD(targetId!),
    enabled: targetId !== null && targetId > 0,
    staleTime: 10 * 60 * 1000, // 10 min — alt data doesn't change fast
  });
}

// --- Legal & Corporate Watch ---
export function useLegalEvents(targetId: number | null) {
  return useQuery({
    queryKey: ['legal-events', targetId],
    queryFn: () => maEngineAPI.getLegalEvents(targetId!),
    enabled: targetId !== null && targetId > 0,
    staleTime: 10 * 60 * 1000, // 10 min — legal events are static
  });
}

// --- Talent & HR Intelligence ---
export function useTalentSignals(targetId: number | null) {
  return useQuery({
    queryKey: ['talent-signals', targetId],
    queryFn: () => maEngineAPI.getTalentSignals(targetId!),
    enabled: targetId !== null && targetId > 0,
    staleTime: 10 * 60 * 1000, // 10 min — job listings don't change fast
  });
}

// D49 (Tâche Finalisation) : useComps (public/private peers fabriqués)
// retiré — la vue détail valorise désormais via useSectorCalibration +
// useCompsTable (CompSet TIC réel), déjà définis ci-dessous pour
// LBOCalculator/Comparables.

// --- Portfolio companies ---
export function usePortfolioCompanies() {
  return useQuery({
    queryKey: ['portfolio-companies'],
    queryFn: () => maEngineAPI.getPortfolioCompanies(),
    staleTime: 60 * 1000,
  });
}

// --- Portfolio KPIs ---
export function usePortfolioKPIs(portfolioCompanyId: number | null) {
  return useQuery({
    queryKey: ['portfolio-kpis', portfolioCompanyId],
    queryFn: () => maEngineAPI.getPortfolioKPIs(portfolioCompanyId!),
    enabled: portfolioCompanyId !== null && portfolioCompanyId > 0,
    staleTime: 60 * 1000,
  });
}

// --- Mutation: Update pipeline stage ---
export function useUpdateStageMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, stage }: { id: number; stage: PipelineStage }) =>
      maEngineAPI.updateTargetStage(id, stage),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sourced-targets'] });
      queryClient.invalidateQueries({ queryKey: ['sourced-target', variables.id] });
    },
  });
}

// --- Mutation: Promote a sourced target to a Deal (D14, Tâche B.5) ---
export function usePromoteTargetMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => maEngineAPI.promoteTarget(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['sourced-targets'] });
      queryClient.invalidateQueries({ queryKey: ['sourced-target', id] });
      queryClient.invalidateQueries({ queryKey: ['deals'] });
    },
  });
}

// --- Mutation: Run OSINT Scan ---
export function useRunScanMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (platformUrl: string) => maEngineAPI.scanTarget(platformUrl),
    onSuccess: () => {
      // Invalidate targets list so it refreshes when scan completes
      queryClient.invalidateQueries({ queryKey: ['sourced-targets'] });
    },
  });
}

// D40 (Tâche Finalisation) — le scan tourne en tâche de fond (202 Accepted
// immédiat) ; ce hook poll le statut réel jusqu'à ce qu'il ne soit plus
// "running", pour que l'UI puisse afficher l'issue véritable (N cibles
// ajoutées, ou pourquoi 0) plutôt qu'un message générique "scan lancé" sans
// suite. `enabled` contrôle le polling (activé seulement pendant/après un
// scan lancé depuis cette session, pas en continu au chargement de page).
export function useScanStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['scan-status'],
    queryFn: () => maEngineAPI.getScanStatus(),
    enabled,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  });
}

// --- Mutation: Calculate LBO ---
export function useCalculateLboMutation() {
  return useMutation({
    mutationFn: (payload: LBOCalculateRequest) => maEngineAPI.calculateLbo(payload),
  });
}

// --- Mutation: Export LBO Excel ---
export function useExportLboMutation() {
  return useMutation({
    mutationFn: (payload: LBOCalculateRequest) => maEngineAPI.exportLboExcel(payload),
  });
}

// --- Mutation: Calculate Build-up ---
export function useCalculateBuildupMutation() {
  return useMutation({
    mutationFn: (payload: BuildupRequest) => maEngineAPI.calculateBuildup(payload),
  });
}

// --- Sector calibration (D22, Tâche B.8) ---
export function useSectorCalibration(sectorOrNaf: string, discount: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ['lbo-calibration', sectorOrNaf, discount],
    queryFn: () => maEngineAPI.getLboCalibration(sectorOrNaf, discount),
    enabled: enabled && !!sectorOrNaf,
    staleTime: 60 * 1000,
  });
}

// --- LBO Scenarios (D23, Tâche B.8) ---
export function useLboScenarios(dealId: number | null) {
  return useQuery({
    queryKey: ['lbo-scenarios', dealId],
    queryFn: () => maEngineAPI.getLboScenarios(dealId!),
    enabled: dealId !== null && dealId > 0,
    staleTime: 30 * 1000,
  });
}

// D45 (Tâche Finalisation, Partie F) : détail complet d'un scénario
// (result_json.financial_provenance inclus) — la liste `useLboScenarios`
// ne renvoie que LBOScenarioListItem, allégé, sans ce champ.
export function useLboScenario(scenarioId: number | null) {
  return useQuery({
    queryKey: ['lbo-scenario', scenarioId],
    queryFn: () => maEngineAPI.getLboScenario(scenarioId!),
    enabled: scenarioId !== null && scenarioId > 0,
    staleTime: 30 * 1000,
  });
}

export function useSaveLboScenarioMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LBOScenarioCreate) => maEngineAPI.saveLboScenario(payload),
    onSuccess: (scenario) => {
      queryClient.invalidateQueries({ queryKey: ['lbo-scenarios', scenario.deal_id] });
    },
  });
}

export function useDeleteLboScenarioMutation(dealId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scenarioId: number) => maEngineAPI.deleteLboScenario(scenarioId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lbo-scenarios', dealId] });
    },
  });
}

// --- Trading Comps Engine (Tâche B.10) ---
export function useCompSets() {
  return useQuery({
    queryKey: ['comp-sets'],
    queryFn: () => maEngineAPI.getCompSets(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCompsTable(compSetId: number | null) {
  return useQuery({
    queryKey: ['comps-table', compSetId],
    queryFn: () => maEngineAPI.getCompsTable(compSetId!),
    enabled: compSetId !== null,
    staleTime: 5 * 60 * 1000,
  });
}

// --- Mutation: Generate IC Memo ---
export function useGenerateMemoMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dealId: number) => dealsAPI.generateMemo(dealId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deals'] });
    },
  });
}

// --- Mutation: Batch Scan (CSV upload) ---
export function useBatchScanMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => maEngineAPI.batchScan(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourced-targets'] });
    },
  });
}

// --- Mutation: Upload Teaser/CIM (PDF upload) ---
export function useUploadTeaserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => maEngineAPI.uploadTeaser(file),
    onSuccess: () => {
      // Invalidate targets list so new deal appears immediately
      queryClient.invalidateQueries({ queryKey: ['sourced-targets'] });
    },
  });
}
