import React, { useState, useCallback, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Card } from '../ui/Card';
import {
  Calculator, DollarSign, Percent, Clock, TrendingUp, AlertCircle,
  Wifi, ChevronDown, RefreshCw, BarChart3, Landmark, Banknote, ArrowRight,
  FileSpreadsheet, PlusCircle, Trash2, Users, Shield, Award, Link2, X,
  Save, FolderOpen, ScanLine,
} from 'lucide-react';
import {
  useLBOMarketRates, useCalculateLboMutation, useExportLboMutation, useDeal,
  useSectorCalibration, useLboScenarios, useSaveLboScenarioMutation, useDeleteLboScenarioMutation,
} from '../../hooks/useQueries';
import { maEngineAPI } from '../../services/apiService';
import type { LBOCalculateRequest, LBOResult, LBOProjectionYear, DebtTranche, ManagementPackage, AmortizationType } from '../../types';

// ============================================
// Helpers
// ============================================

const fmt = (v: number): string => {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} M€`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)} K€`;
  return `${v.toFixed(0)} €`;
};

const pct = (v: number): string => `${(v * 100).toFixed(1)}%`;

const SECTORS = [
  'SaaS', 'Santé', 'Industrie', 'Services B2B', 'Fintech', 'E-commerce',
  'Éducation', 'Énergie', 'Agri-Food', 'Logistique', 'Média',
  // Tâche B.8 (D22) : TIC (Testing, Inspection, Certification) — secteur du
  // CompSet calibré. Sans cette entrée, "contrôle technique" (secteur réel
  // de BTP Consultants) retombait sur "Services B2B" par substring-matching
  // et ne bénéficiait jamais du calibrage sectoriel.
  'Contrôle Technique', 'Autre',
];

// Tâche "P2 : crédibilité de la thèse" (Partie A) — même seuil et même
// levier par défaut que lbo_scenario_service.py (valuation_engine.py::
// SMALL_CAP_REVENUE_THRESHOLD/SMALL_CAP_DEFAULT_LEVERAGE) : un LBO
// standalone mezzanine n'est pas finançable sous ce CA en pratique.
const SMALL_CAP_REVENUE_THRESHOLD = 10_000_000;
const SMALL_CAP_DEFAULT_LEVERAGE = 2.25;
const SIZING_NOTE_INDICATIVE = (
  "At this size, a standalone mezzanine LBO is not realistically financeable in the " +
  "French market — real senior bank debt capacity here is roughly 2.0-2.5x EBITDA, with " +
  "no mezzanine layer. This model uses a conservative bank-debt-only leverage and is " +
  "shown for INDICATIVE purposes only, not a financeable standalone structure. A " +
  "realistic structure at this size is a bolt-on add-on to an existing platform (see the " +
  "Buy & Build module), financed with bank debt at the platform level — not a standalone " +
  "mezzanine LBO."
);

const DEFAULT_TRANCHES: DebtTranche[] = [
  { name: 'Senior A', amount_turns: 2.5, interest_rate: 0.05, amortization: 'amortizing' },
  { name: 'Senior B', amount_turns: 1.0, interest_rate: 0.065, amortization: 'bullet' },
  { name: 'Mezzanine', amount_turns: 0.5, interest_rate: 0.10, amortization: 'bullet' },
];

const DEFAULT_MGMT: ManagementPackage = {
  sweet_equity_pct: 0.15,
  ratchet_irr_threshold: 0.25,
  ratchet_bonus_pct: 0.05,
};

// D16 (Tâche B.5) : le secteur d'un Deal (texte libre, ex. "contrôle
// technique" — premier mot-clé réel du sourcing) ne correspond pas
// forcément à une entrée de SECTORS. Rapprochement approximatif par
// sous-chaîne plutôt qu'une case vide ; repli sur "Services B2B" (le plus
// générique des profils métier disponibles) si rien ne correspond — jamais
// une valeur inventée, juste un choix de repli documenté.
const mapDealSectorToLboSector = (dealSector: string | null | undefined): string => {
  if (!dealSector) return 'Services B2B';
  const normalized = dealSector.toLowerCase();
  const found = SECTORS.find(
    (s) => normalized.includes(s.toLowerCase()) || s.toLowerCase().includes(normalized)
  );
  return found ?? 'Services B2B';
};

// ============================================
// Main Component
// ============================================

export const LBOCalculator: React.FC = () => {
  // ── Market rates (FRED) ──
  const { data: marketRates } = useLBOMarketRates();

  // ── D16 (Tâche B.5) : pré-remplissage depuis un deal via ?dealId= ──
  // Le calculateur continue de fonctionner en mode libre (sans dealId) :
  // toute la logique ci-dessous est un no-op tant que dealId est absent.
  const [searchParams] = useSearchParams();
  const dealIdParam = searchParams.get('dealId');
  const dealId = dealIdParam ? Number(dealIdParam) : null;
  const { data: prefillDeal, isLoading: prefillLoading, isError: prefillError } = useDeal(dealId);
  const [prefillApplied, setPrefillApplied] = useState(false);
  const [prefillDismissed, setPrefillDismissed] = useState(false);

  // ── Form state ──
  const [revenue, setRevenue] = useState<number>(10_000_000);
  const [sector, setSector] = useState<string>('SaaS');
  const [holdingPeriod, setHoldingPeriod] = useState<number>(5);
  const [entryMultiple, setEntryMultiple] = useState<number>(10);
  const [exitMultiple, setExitMultiple] = useState<number>(10);

  // ── V3: Multi-tranche debt ──
  const [useMultiTranche, setUseMultiTranche] = useState<boolean>(true);
  const [debtTranches, setDebtTranches] = useState<DebtTranche[]>(DEFAULT_TRANCHES);
  const [legacyLeverage, setLegacyLeverage] = useState<number>(4);

  // ── V3: Management Package ──
  const [enableMgmt, setEnableMgmt] = useState<boolean>(true);
  const [mgmt, setMgmt] = useState<ManagementPackage>(DEFAULT_MGMT);

  // ── D22 (Tâche B.8) : calibrage sectoriel dérivé du CompSet réel ──
  const [useCalibration, setUseCalibration] = useState<boolean>(false);
  const [discount, setDiscount] = useState<number>(0.35);
  const { data: calibration, isFetching: calibrationLoading } = useSectorCalibration(sector, discount, useCalibration);

  // Synchronise le multiple d'entrée sur la valeur calibrée dès qu'elle change
  // (activation, changement de secteur, ou ajustement de la décote). L'utilisateur
  // reste libre de retoucher le curseur ensuite — le prochain changement de décote
  // resynchronisera. Voir Étape 4 du RAPPORT B.8 pour la justification de ce choix.
  useEffect(() => {
    if (useCalibration && calibration?.sufficient && calibration.applicable && calibration.derived_entry_multiple) {
      setEntryMultiple(calibration.derived_entry_multiple);
      setExitMultiple(calibration.derived_entry_multiple);
    }
  }, [useCalibration, calibration?.derived_entry_multiple, calibration?.sufficient, calibration?.applicable]);

  // ── D23 (Tâche B.8) : scénarios LBO persistés ──
  const [scenarioLabel, setScenarioLabel] = useState<string>('');
  const [loadedScenarioResult, setLoadedScenarioResult] = useState<LBOResult | null>(null);
  // Tâche "P2" (Partie A) — bannière "indicatif / bolt-on" quand la cible
  // est sous le seuil de CA, chargée depuis le scénario réel si un base
  // case existe déjà, ou déterminée localement en mode "aucun scénario"/
  // "mode libre".
  const [sizingNote, setSizingNote] = useState<string | null>(null);
  const { data: scenarios } = useLboScenarios(dealId);
  const saveScenarioMutation = useSaveLboScenarioMutation();
  const deleteScenarioMutation = useDeleteLboScenarioMutation(dealId);
  const [loadingScenarioId, setLoadingScenarioId] = useState<number | null>(null);

  // ── Mutations ──
  const lboMutation = useCalculateLboMutation();
  const exportMutation = useExportLboMutation();
  // Un scénario rechargé (D23) s'affiche TEL QUEL — jamais recalculé — tant
  // qu'aucun nouveau calcul n'est explicitement demandé.
  const result: LBOResult | undefined = loadedScenarioResult ?? lboMutation.data;

  // ── Build payload ──
  const buildPayload = useCallback((): LBOCalculateRequest => {
    const payload: LBOCalculateRequest = {
      revenue,
      sector_or_naf: sector,
      holding_period: holdingPeriod,
      override_entry_mult: entryMultiple,
      override_exit_mult: exitMultiple,
    };

    if (useMultiTranche) {
      payload.debt_structure = debtTranches;
    } else {
      payload.override_leverage = legacyLeverage;
    }

    if (enableMgmt) {
      payload.management_package = mgmt;
    }

    if (useCalibration) {
      payload.use_sector_calibration = true;
      payload.size_illiquidity_discount = discount;
    }

    return payload;
  }, [revenue, sector, holdingPeriod, entryMultiple, exitMultiple, useMultiTranche, debtTranches, legacyLeverage, enableMgmt, mgmt, useCalibration, discount]);

  // ── D16 (Tâche B.5) : applique les données du deal dès qu'elles arrivent ──
  // Tâche "P0 : un seul deal dans les 3 documents" (Partie B) — CORRECTIF
  // CENTRAL. Ce pré-remplissage recalculait auparavant un "multiple
  // implicite" = enterprise_value du DEAL ÷ target_ebitda du DEAL (le
  // multiple historique posé au sourcing) et laissait la structure de dette
  // à la valeur par défaut du composant (DEFAULT_TRANCHES, 3 tranches) —
  // total découplage du scénario LBO canonique déjà utilisé par le mémo et
  // le deck de ce même deal. Une revue IC externe a constaté exactement ce
  // symptôme sur Ingebime (secteur non calibré) : Excel affichait 8,8x /
  // 3 tranches quand mémo et deck affichaient 6,0x / 1 tranche pour LE MÊME
  // DEAL. Corrigé : charge le VRAI scénario de référence du deal (même
  // heuristique "base" que lbo_scenario_service.get_reference_scenario côté
  // backend — label contenant "base", sinon le plus récent), tel quel,
  // jamais un recalcul indépendant. Le multiple utilisé est celui du
  // résultat déjà calculé (calibré ou générique), pas un ratio EV/EBITDA du
  // deal — ces deux notions restent légitimement différentes (voir la note
  // de réconciliation du mémo) mais ne doivent jamais alimenter le même
  // calculateur sous un même bouton "pré-rempli".
  useEffect(() => {
    if (!dealId || !prefillDeal || prefillApplied) return;
    if (scenarios === undefined) return; // attend la liste des scénarios (peut être vide, jamais indéfinie indéfiniment)

    const applyDealOnlyFallback = () => {
      if (prefillDeal.target_revenue) setRevenue(prefillDeal.target_revenue);
      setSector(mapDealSectorToLboSector(prefillDeal.sector));
      // Tâche "P2" (Partie A) — aucun scénario canonique n'existe encore :
      // pas de mezzanine par défaut ni de levier mid-market sous le seuil
      // de taille, cohérent avec ce que build_base_case_scenario générerait.
      if (prefillDeal.target_revenue && prefillDeal.target_revenue < SMALL_CAP_REVENUE_THRESHOLD) {
        setUseMultiTranche(false);
        setLegacyLeverage(SMALL_CAP_DEFAULT_LEVERAGE);
        setSizingNote(SIZING_NOTE_INDICATIVE);
      } else {
        setSizingNote(null);
      }
      setPrefillApplied(true);
    };

    const referenceScenario =
      scenarios.find((s) => s.label.toLowerCase().includes('base')) ?? scenarios[0];

    if (!referenceScenario) {
      // Aucun scénario sauvegardé pour ce deal : rien de canonique à
      // charger. Ne JAMAIS deviner un multiple depuis enterprise_value ÷
      // target_ebitda du deal — c'est exactement le bug corrigé ici.
      applyDealOnlyFallback();
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const full = await maEngineAPI.getLboScenario(referenceScenario.id);
        if (cancelled) return;
        const a = full.assumptions_json;
        const r = full.result_json;
        setRevenue(a.revenue);
        // Valeur brute du scénario (ex. "contrôle technique"), pas le
        // libellé du menu déroulant — recalculer depuis ce calculateur doit
        // reproduire le MÊME profil sectoriel que le scénario canonique.
        setSector(a.sector_or_naf || mapDealSectorToLboSector(prefillDeal.sector));
        setHoldingPeriod(a.holding_period ?? r.holding_period ?? 5);
        // Le scénario base-case auto-généré ne pose pas override_entry_mult/
        // override_exit_mult dans ses assumptions (calibré ou générique,
        // jamais une saisie manuelle) — le multiple réellement retenu est
        // dans le résultat déjà calculé.
        setEntryMultiple(a.override_entry_mult ?? r.entry_multiple ?? entryMultiple);
        setExitMultiple(a.override_exit_mult ?? r.exit_multiple ?? exitMultiple);
        if (a.debt_structure && a.debt_structure.length > 0) {
          setUseMultiTranche(true);
          setDebtTranches(a.debt_structure);
        } else {
          setUseMultiTranche(false);
          setLegacyLeverage(a.override_leverage ?? r.leverage_entry ?? legacyLeverage);
        }
        setEnableMgmt(!!a.management_package);
        if (a.management_package) setMgmt(a.management_package);
        setUseCalibration(!!a.use_sector_calibration);
        if (a.size_illiquidity_discount != null) setDiscount(a.size_illiquidity_discount);
        // Tâche "P2" (Partie A) — reflète l'étiquette "indicatif" déjà posée
        // par build_base_case_scenario sur ce scénario, jamais recalculée ici.
        setSizingNote(a.sizing_tier === 'indicative_bolt_on' ? (a.sizing_note ?? SIZING_NOTE_INDICATIVE) : null);
        setLoadedScenarioResult(r);
      } catch {
        if (!cancelled) applyDealOnlyFallback();
        return;
      } finally {
        if (!cancelled) setPrefillApplied(true);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dealId, prefillDeal, prefillApplied, scenarios]);

  // ── Auto-calculate on mount (mode libre), ou dès le pré-remplissage appliqué ──
  useEffect(() => {
    if (dealId && !prefillApplied) return; // attend les données du deal avant le premier calcul
    handleCalculate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillApplied]);

  const handleCalculate = useCallback(() => {
    setLoadedScenarioResult(null); // un nouveau calcul remplace tout scénario rechargé affiché
    lboMutation.mutate(buildPayload());
  }, [buildPayload, lboMutation]);

  // ── D23 (Tâche B.8) : enregistrement explicite d'un scénario ──
  const handleSaveScenario = useCallback(() => {
    if (!dealId || !result || !scenarioLabel.trim()) return;
    saveScenarioMutation.mutate(
      { deal_id: dealId, label: scenarioLabel.trim(), assumptions: buildPayload(), result },
      { onSuccess: () => setScenarioLabel('') }
    );
  }, [dealId, result, scenarioLabel, buildPayload, saveScenarioMutation]);

  // Recharge un scénario TEL QUEL (assumptions + résultat déjà sauvegardés,
  // aucun recalcul) — voir LBOScenario model docstring.
  const handleLoadScenario = useCallback(async (scenarioId: number) => {
    setLoadingScenarioId(scenarioId);
    try {
      const full = await maEngineAPI.getLboScenario(scenarioId);
      const a = full.assumptions_json;
      setRevenue(a.revenue);
      setSector(a.sector_or_naf ?? 'SaaS');
      setHoldingPeriod(a.holding_period ?? 5);
      if (a.override_entry_mult) setEntryMultiple(a.override_entry_mult);
      if (a.override_exit_mult) setExitMultiple(a.override_exit_mult);
      if (a.debt_structure && a.debt_structure.length > 0) {
        setUseMultiTranche(true);
        setDebtTranches(a.debt_structure);
      } else if (a.override_leverage != null) {
        setUseMultiTranche(false);
        setLegacyLeverage(a.override_leverage);
      }
      setEnableMgmt(!!a.management_package);
      if (a.management_package) setMgmt(a.management_package);
      setUseCalibration(!!a.use_sector_calibration);
      if (a.size_illiquidity_discount != null) setDiscount(a.size_illiquidity_discount);
      setLoadedScenarioResult(full.result_json);
    } finally {
      setLoadingScenarioId(null);
    }
  }, []);

  const handleDeleteScenario = useCallback((scenarioId: number) => {
    deleteScenarioMutation.mutate(scenarioId);
  }, [deleteScenarioMutation]);

  const handleExportExcel = useCallback(() => {
    exportMutation.mutate(buildPayload(), {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `LBO_Model_${sector}_${new Date().toISOString().slice(0, 10)}.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      },
    });
  }, [buildPayload, exportMutation, sector]);

  // ── Tranche management ──
  const addTranche = () => {
    setDebtTranches(prev => [
      ...prev,
      { name: `Tranche ${prev.length + 1}`, amount_turns: 1.0, interest_rate: 0.07, amortization: 'bullet' as AmortizationType },
    ]);
  };

  const removeTranche = (idx: number) => {
    setDebtTranches(prev => prev.filter((_, i) => i !== idx));
  };

  const updateTranche = (idx: number, field: keyof DebtTranche, value: string | number) => {
    setDebtTranches(prev => prev.map((t, i) => i === idx ? { ...t, [field]: value } : t));
  };

  const totalLeverage = useMultiTranche
    ? debtTranches.reduce((sum, t) => sum + t.amount_turns, 0)
    : legacyLeverage;

  return (
    <div className="h-full w-full flex flex-col space-y-6">

      {/* ── Header ── */}
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
          <span className="text-cyan-500">///</span> Paper LBO Engine
          <span className="text-[10px] text-emerald-400 font-mono border border-emerald-800 rounded px-1.5 py-0.5 ml-2">V3</span>
          <span className="text-[10px] text-slate-500 font-mono border border-slate-800 rounded px-1.5 py-0.5">PYTHON</span>
        </h2>
        <div className="flex items-center gap-3">
          {/* Excel export button */}
          <button
            onClick={handleExportExcel}
            disabled={!result || exportMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-bold uppercase tracking-wider transition-all
              bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 border border-emerald-700 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {exportMutation.isPending ? (
              <RefreshCw size={12} className="animate-spin" />
            ) : (
              <FileSpreadsheet size={12} />
            )}
            Export Excel
          </button>
          <div className="text-[10px] text-slate-500 font-mono">
            MOTEUR : FASTAPI :8000 / VALUATION_ENGINE V3
          </div>
        </div>
      </div>

      {/* ── D16 (Tâche B.5) : bandeau de pré-remplissage depuis un deal ── */}
      {dealId && !prefillDismissed && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-cyan-800 bg-cyan-950/30 px-4 py-2.5 text-xs">
          <div className="flex items-center gap-2 text-cyan-300">
            <Link2 size={13} />
            {prefillLoading && <span>Chargement des données du deal #{dealId}…</span>}
            {prefillError && <span className="text-rose-300">Impossible de charger le deal #{dealId} — hypothèses par défaut conservées.</span>}
            {prefillDeal && (
              <span>
                Pré-rempli depuis le deal <strong>#{prefillDeal.id} — {prefillDeal.target_name ?? 'sans nom'}</strong>
                {' '}(CA, secteur{prefillDeal.enterprise_value && prefillDeal.target_ebitda ? ', multiple implicite EV/EBITDA' : ''}). Toutes les hypothèses restent modifiables ci-dessous.
              </span>
            )}
          </div>
          <button
            onClick={() => setPrefillDismissed(true)}
            className="text-cyan-400 hover:text-white transition-colors"
            title="Masquer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* ── P2 (Partie A) : LBO indicatif sous le seuil de taille — jamais
          reléguée à un détail discret, renvoi explicite vers Buy & Build. ── */}
      {sizingNote && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-amber-800/60 bg-amber-950/20 px-4 py-2.5 text-xs text-amber-200">
          <p className="font-bold uppercase tracking-wide text-amber-400">LBO indicatif — hors seuil de financement standalone</p>
          <p className="leading-relaxed">{sizingNote}</p>
          <Link to="/buy-and-build" className="inline-flex items-center gap-1 font-semibold text-cyan-400 hover:text-cyan-300 w-fit">
            Voir le module Buy &amp; Build →
          </Link>
        </div>
      )}

      {/* ── Live Market Rates Bar ── */}
      {marketRates && (
        <div className="flex flex-wrap items-center gap-4 bg-slate-900/60 border border-slate-800 rounded px-4 py-2 text-[10px] font-mono">
          <Wifi size={12} className="text-emerald-400 animate-pulse" />
          <span className="text-slate-400">LIVE MARKET:</span>
          <span className="text-slate-300">5Y Treasury <span className="text-cyan-400 font-bold">{marketRates.riskFreeRate.toFixed(2)}%</span></span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-300">HY Spread <span className="text-amber-400 font-bold">+{(marketRates.hySpread * 100).toFixed(0)}bps</span></span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-300">Implied CoD <span className="text-rose-400 font-bold">{marketRates.impliedCostOfDebt.toFixed(2)}%</span></span>
          {marketRates.sofr != null && (
            <>
              <span className="text-slate-600">|</span>
              <span className="text-slate-300">SOFR <span className="text-cyan-400 font-bold">{marketRates.sofr.toFixed(2)}%</span></span>
            </>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">

        {/* ═══════════════════════════════════════
            LEFT — Panneau de Contrôle (Inputs)
           ═══════════════════════════════════════ */}
        <div className="col-span-1 xl:col-span-4 space-y-4">
          <Card title="Hypothèses LBO" subtitle="Multi-tranche · Management Package">
            <div className="p-4 space-y-6">

              {/* ── Revenue ── */}
              <div className="space-y-4 border-b border-slate-800 pb-6">
                <div className="flex items-center space-x-2 text-cyan-400 mb-2">
                  <DollarSign size={16} />
                  <span className="text-xs font-bold uppercase">Chiffre d'Affaires</span>
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-slate-400">CA Année 0 (€)</span>
                    <span className="font-mono text-white">{fmt(revenue)}</span>
                  </div>
                  <input
                    type="number" step={500_000} min={100_000}
                    value={revenue}
                    onChange={(e) => setRevenue(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700 rounded py-2 px-3 text-xs text-white font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                  />
                </div>

                {/* ── Sector ── */}
                <div>
                  <label className="text-[10px] text-slate-400 font-bold uppercase mb-1.5 block">Secteur</label>
                  <div className="relative">
                    <select
                      value={sector}
                      onChange={(e) => setSector(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded py-2 px-3 text-xs text-white appearance-none focus:border-cyan-500 outline-none cursor-pointer"
                    >
                      {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <ChevronDown size={14} className="absolute right-3 top-2.5 text-slate-500 pointer-events-none" />
                  </div>
                </div>
              </div>

              {/* ── D22 (Tâche B.8) : Calibrage sectoriel dérivé du CompSet réel ── */}
              <div className="border-b border-slate-800 pb-6">
                <button
                  onClick={() => setUseCalibration(prev => !prev)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded border text-xs font-bold uppercase tracking-wide transition-all ${
                    useCalibration
                      ? 'text-cyan-300 border-cyan-700 bg-cyan-950/30'
                      : 'text-slate-500 border-slate-700 hover:text-slate-300'
                  }`}
                >
                  <span className="flex items-center gap-2"><ScanLine size={13} /> Calibrage Sectoriel (CompSet réel)</span>
                  <span className="text-[9px] font-mono">{useCalibration ? 'ACTIVÉ' : 'DÉSACTIVÉ'}</span>
                </button>

                {useCalibration && (
                  <div className="mt-3 rounded border border-slate-800 bg-slate-950/60 p-3 space-y-3">
                    {calibrationLoading && (
                      <div className="text-[10px] text-slate-500 font-mono flex items-center gap-1.5">
                        <RefreshCw size={10} className="animate-spin" /> Calcul de la médiane du CompSet…
                      </div>
                    )}

                    {!calibrationLoading && calibration && !calibration.applicable && (
                      <div className="text-[10px] text-amber-400 font-mono flex items-start gap-1.5">
                        <AlertCircle size={11} className="mt-0.5 shrink-0" />
                        <span>{calibration.fallback_reason ?? 'Calibrage non applicable pour ce secteur — profil générique utilisé.'}</span>
                      </div>
                    )}

                    {!calibrationLoading && calibration && calibration.applicable && !calibration.sufficient && (
                      <div className="text-[10px] text-amber-400 font-mono flex items-start gap-1.5">
                        <AlertCircle size={11} className="mt-0.5 shrink-0" />
                        <span>{calibration.fallback_reason}</span>
                      </div>
                    )}

                    {!calibrationLoading && calibration?.sufficient && calibration.applicable && (
                      <>
                        {/* La chaîne de raisonnement — lisible en 3 secondes */}
                        <div className="font-mono text-xs space-y-1">
                          <div className="flex justify-between text-white font-bold">
                            <span>Entry multiple</span>
                            <span className="text-cyan-400">{calibration.derived_entry_multiple?.toFixed(2)}x</span>
                          </div>
                          <div className="flex justify-between text-slate-400 pl-3">
                            <span>= {calibration.median_ev_ebitda?.toFixed(2)}x listed comparables median</span>
                            <span className="text-slate-500">(n={calibration.sample_size}, FY{[...new Set(calibration.fiscal_years)].sort().join('-')})</span>
                          </div>
                          <div className="flex justify-between text-rose-400 pl-3">
                            <span>− {(calibration.size_illiquidity_discount * 100).toFixed(0)}% {calibration.discount_label}</span>
                          </div>
                        </div>

                        {/* Décote modifiable */}
                        <div>
                          <div className="flex justify-between text-[10px] mb-1">
                            <span className="text-slate-400">Décote taille &amp; illiquidité</span>
                            <span className="font-mono text-white">{(discount * 100).toFixed(0)}%</span>
                          </div>
                          <input
                            type="range" min="0" max="70" step="1"
                            value={discount * 100}
                            onChange={(e) => setDiscount(Number(e.target.value) / 100)}
                            className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-rose-500"
                          />
                        </div>

                        <div className="text-[9px] text-slate-500 font-mono flex items-center justify-between gap-2">
                          <span>Comparables : {calibration.tickers.join(', ')}</span>
                          {calibration.comp_set_id != null && (
                            <Link
                              to={`/comparables?compSetId=${calibration.comp_set_id}${dealId ? `&dealId=${dealId}` : ''}`}
                              className="shrink-0 text-cyan-400 hover:text-cyan-300 underline decoration-cyan-800 whitespace-nowrap"
                            >
                              Voir la table complète →
                            </Link>
                          )}
                        </div>
                        <div className="text-[9px] text-slate-600 italic">
                          Marge EBITDA médiane {calibration.median_ebitda_margin != null ? (calibration.median_ebitda_margin * 100).toFixed(1) : '—'}% —
                          {' '}leaders mondiaux cotés, une PME française se situe généralement en dessous. Valeur par défaut, modifiable.
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* ── Multiples ── */}
              <div className="space-y-4 border-b border-slate-800 pb-6">
                <div className="flex items-center space-x-2 text-emerald-400 mb-2">
                  <TrendingUp size={16} />
                  <span className="text-xs font-bold uppercase">Multiples</span>
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-slate-400">Multiple d'Entrée (EV/EBITDA)</span>
                    <span className="font-mono text-white">{entryMultiple.toFixed(1)}x</span>
                  </div>
                  <input
                    type="range" min="4" max="15" step="0.5"
                    value={entryMultiple}
                    onChange={(e) => setEntryMultiple(Number(e.target.value))}
                    className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-slate-400">Multiple de Sortie (EV/EBITDA)</span>
                    <span className="font-mono text-white">{exitMultiple.toFixed(1)}x</span>
                  </div>
                  <input
                    type="range" min="4" max="15" step="0.5"
                    value={exitMultiple}
                    onChange={(e) => setExitMultiple(Number(e.target.value))}
                    className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                  />
                </div>
              </div>

              {/* ── Debt Structure (V3 Multi-tranche OR Legacy) ── */}
              <div className="space-y-4 border-b border-slate-800 pb-6">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2 text-rose-400">
                    <Percent size={16} />
                    <span className="text-xs font-bold uppercase">Structure de Dette</span>
                  </div>
                  <button
                    onClick={() => setUseMultiTranche(prev => !prev)}
                    className={`text-[9px] font-mono px-2 py-0.5 rounded border transition-all ${
                      useMultiTranche
                        ? 'text-emerald-400 border-emerald-700 bg-emerald-950/30'
                        : 'text-slate-500 border-slate-700 hover:text-slate-300'
                    }`}
                  >
                    {useMultiTranche ? 'MULTI-TRANCHE' : 'SIMPLE'}
                  </button>
                </div>

                {useMultiTranche ? (
                  <>
                    {/* Tranche list */}
                    <div className="space-y-3">
                      {debtTranches.map((t, idx) => (
                        <div key={idx} className="bg-slate-950/60 border border-slate-800 rounded p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <input
                              type="text"
                              value={t.name}
                              onChange={(e) => updateTranche(idx, 'name', e.target.value)}
                              className="bg-transparent text-xs font-bold text-white border-none outline-none flex-1"
                              placeholder="Nom tranche"
                            />
                            <button
                              onClick={() => removeTranche(idx)}
                              className="text-slate-600 hover:text-rose-400 transition-colors ml-2"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            <div>
                              <label className="text-[9px] text-slate-500 block mb-0.5">× EBITDA</label>
                              <input
                                type="number" step={0.25} min={0} max={10}
                                value={t.amount_turns}
                                onChange={(e) => updateTranche(idx, 'amount_turns', Number(e.target.value))}
                                className="w-full bg-slate-900 border border-slate-700 rounded py-1 px-2 text-[11px] text-white font-mono focus:border-cyan-500 outline-none"
                              />
                            </div>
                            <div>
                              <label className="text-[9px] text-slate-500 block mb-0.5">Taux (%)</label>
                              <input
                                type="number" step={0.5} min={0} max={25}
                                value={(t.interest_rate * 100).toFixed(1)}
                                onChange={(e) => updateTranche(idx, 'interest_rate', Number(e.target.value) / 100)}
                                className="w-full bg-slate-900 border border-slate-700 rounded py-1 px-2 text-[11px] text-white font-mono focus:border-cyan-500 outline-none"
                              />
                            </div>
                            <div>
                              <label className="text-[9px] text-slate-500 block mb-0.5">Profil</label>
                              <select
                                value={t.amortization}
                                onChange={(e) => updateTranche(idx, 'amortization', e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded py-1 px-2 text-[11px] text-white appearance-none focus:border-cyan-500 outline-none cursor-pointer"
                              >
                                <option value="amortizing">Amort.</option>
                                <option value="bullet">Bullet</option>
                              </select>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Add tranche + Total leverage */}
                    <div className="flex items-center justify-between">
                      <button
                        onClick={addTranche}
                        className="inline-flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors font-mono"
                      >
                        <PlusCircle size={12} /> Ajouter une tranche
                      </button>
                      <span className="text-[10px] font-mono text-slate-400">
                        Total : <b className="text-white">{totalLeverage.toFixed(1)}×</b> EBITDA
                      </span>
                    </div>
                  </>
                ) : (
                  /* Legacy single slider */
                  <div>
                    <div className="flex justify-between text-xs mb-1.5">
                      <span className="text-slate-400">Levier Dette / EBITDA</span>
                      <span className="font-mono text-white">{legacyLeverage.toFixed(1)}x</span>
                    </div>
                    <input
                      type="range" min="0" max="7" step="0.5"
                      value={legacyLeverage}
                      onChange={(e) => setLegacyLeverage(Number(e.target.value))}
                      className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-rose-500"
                    />
                  </div>
                )}

                {entryMultiple - totalLeverage < 2 && totalLeverage > 0 && (
                  <div className="mt-1 flex items-center text-[10px] text-rose-500">
                    <AlertCircle size={10} className="mr-1" />
                    Equity slice fine ({(entryMultiple - totalLeverage).toFixed(1)}x)
                  </div>
                )}
              </div>

              {/* ── Management Package (V3) ── */}
              <div className="space-y-4 border-b border-slate-800 pb-6">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2 text-violet-400">
                    <Users size={16} />
                    <span className="text-xs font-bold uppercase">Management Package</span>
                  </div>
                  <button
                    onClick={() => setEnableMgmt(prev => !prev)}
                    className={`text-[9px] font-mono px-2 py-0.5 rounded border transition-all ${
                      enableMgmt
                        ? 'text-violet-400 border-violet-700 bg-violet-950/30'
                        : 'text-slate-500 border-slate-700 hover:text-slate-300'
                    }`}
                  >
                    {enableMgmt ? 'ON' : 'OFF'}
                  </button>
                </div>

                {enableMgmt && (
                  <div className="space-y-3 bg-slate-950/60 border border-slate-800 rounded p-3">
                    <div>
                      <div className="flex justify-between text-[10px] mb-1">
                        <span className="text-slate-400">Sweet Equity (%)</span>
                        <span className="font-mono text-white">{(mgmt.sweet_equity_pct * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range" min="0" max="30" step="1"
                        value={mgmt.sweet_equity_pct * 100}
                        onChange={(e) => setMgmt(prev => ({ ...prev, sweet_equity_pct: Number(e.target.value) / 100 }))}
                        className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-violet-500"
                      />
                    </div>
                    <div>
                      <div className="flex justify-between text-[10px] mb-1">
                        <span className="text-slate-400">Ratchet Threshold (IRR)</span>
                        <span className="font-mono text-white">{(mgmt.ratchet_irr_threshold * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range" min="15" max="40" step="1"
                        value={mgmt.ratchet_irr_threshold * 100}
                        onChange={(e) => setMgmt(prev => ({ ...prev, ratchet_irr_threshold: Number(e.target.value) / 100 }))}
                        className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-violet-500"
                      />
                    </div>
                    <div>
                      <div className="flex justify-between text-[10px] mb-1">
                        <span className="text-slate-400">Ratchet Bonus (%)</span>
                        <span className="font-mono text-white">+{(mgmt.ratchet_bonus_pct * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range" min="0" max="15" step="1"
                        value={mgmt.ratchet_bonus_pct * 100}
                        onChange={(e) => setMgmt(prev => ({ ...prev, ratchet_bonus_pct: Number(e.target.value) / 100 }))}
                        className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-violet-500"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* ── Holding Period ── */}
              <div className="space-y-3">
                <div className="flex items-center space-x-2 text-amber-400 mb-2">
                  <Clock size={16} />
                  <span className="text-xs font-bold uppercase">Horizon</span>
                </div>
                <div className="grid grid-cols-5 gap-1.5">
                  {[3, 4, 5, 6, 7].map(y => (
                    <button
                      key={y}
                      onClick={() => setHoldingPeriod(y)}
                      className={`py-1.5 rounded text-xs font-mono font-bold transition-all border
                        ${holdingPeriod === y
                          ? 'text-cyan-400 border-cyan-700 bg-cyan-950/40'
                          : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600'
                        }`}
                    >
                      {y} ans
                    </button>
                  ))}
                </div>
              </div>

              {/* ── CTA ── */}
              <button
                onClick={handleCalculate}
                disabled={lboMutation.isPending}
                className="w-full mt-4 py-3 rounded text-sm font-bold uppercase tracking-wider transition-all inline-flex items-center justify-center gap-2
                  bg-cyan-600 hover:bg-cyan-500 text-white disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed
                  border border-cyan-500 disabled:border-slate-600 shadow-lg shadow-cyan-900/30 disabled:shadow-none"
              >
                {lboMutation.isPending ? (
                  <><RefreshCw size={14} className="animate-spin" /> CALCUL EN COURS...</>
                ) : (
                  <><Calculator size={14} /> RECALCULER LE LBO</>
                )}
              </button>

              {lboMutation.isError && (
                <div className="mt-2 text-[10px] text-rose-400 font-mono bg-rose-950/30 border border-rose-900 rounded p-2">
                  Erreur : {lboMutation.error instanceof Error ? lboMutation.error.message : 'Échec du calcul'}
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* ═══════════════════════════════════════
            RIGHT — Résultats (Outputs)
           ═══════════════════════════════════════ */}
        <div className="col-span-1 xl:col-span-8 flex flex-col gap-6">

          {/* ── D23 (Tâche B.8) : Scénarios LBO (uniquement rattaché à un deal) ── */}
          {dealId && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-bold uppercase text-slate-300">
                  <FolderOpen size={13} className="text-cyan-400" /> Scénarios LBO — Deal #{dealId}
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={scenarioLabel}
                    onChange={(e) => setScenarioLabel(e.target.value)}
                    placeholder="Libellé (ex. Base case)"
                    className="bg-slate-950 border border-slate-700 rounded py-1 px-2 text-[11px] text-white font-mono focus:border-cyan-500 outline-none w-40"
                  />
                  <button
                    onClick={handleSaveScenario}
                    disabled={!result || !scenarioLabel.trim() || saveScenarioMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-all
                      bg-cyan-600/20 hover:bg-cyan-600/40 text-cyan-300 border border-cyan-700 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Save size={11} /> Enregistrer ce scénario
                  </button>
                </div>
              </div>

              {scenarios && scenarios.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[10px] font-mono">
                    <thead>
                      <tr className="text-slate-500 uppercase border-b border-slate-800">
                        <th className="py-1 pr-3">Libellé</th>
                        <th className="py-1 pr-3">Enregistré</th>
                        <th className="py-1 pr-3 text-right">Entry</th>
                        <th className="py-1 pr-3 text-right">Exit</th>
                        <th className="py-1 pr-3 text-right">IRR</th>
                        <th className="py-1 pr-3 text-right">MOIC</th>
                        <th className="py-1"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {scenarios.map((s) => (
                        <tr key={s.id} className="border-b border-slate-900 hover:bg-slate-800/40">
                          <td className="py-1.5 pr-3 text-white font-bold">{s.label}</td>
                          <td className="py-1.5 pr-3 text-slate-500">{new Date(s.created_at).toLocaleString('fr-FR')}</td>
                          <td className="py-1.5 pr-3 text-right text-cyan-400">{s.entry_multiple?.toFixed(1) ?? '—'}x</td>
                          <td className="py-1.5 pr-3 text-right text-emerald-400">{s.exit_multiple?.toFixed(1) ?? '—'}x</td>
                          <td className="py-1.5 pr-3 text-right text-slate-200">{s.irr != null ? pct(s.irr) : '—'}</td>
                          <td className="py-1.5 pr-3 text-right text-slate-200">{s.moic != null ? `${s.moic.toFixed(2)}x` : '—'}</td>
                          <td className="py-1.5 flex items-center gap-2 justify-end">
                            <button
                              onClick={() => handleLoadScenario(s.id)}
                              disabled={loadingScenarioId === s.id}
                              title="Charger dans le calculateur"
                              className="text-cyan-400 hover:text-cyan-300 disabled:opacity-40"
                            >
                              {loadingScenarioId === s.id ? <RefreshCw size={11} className="animate-spin" /> : <FolderOpen size={11} />}
                            </button>
                            <button
                              onClick={() => handleDeleteScenario(s.id)}
                              title="Supprimer"
                              className="text-slate-600 hover:text-rose-400"
                            >
                              <Trash2 size={11} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-[10px] text-slate-600 font-mono">Aucun scénario enregistré pour ce deal.</div>
              )}
              {loadedScenarioResult && (
                <div className="text-[10px] text-amber-400 font-mono flex items-center gap-1.5">
                  <AlertCircle size={10} /> Scénario rechargé tel qu'enregistré — cliquez « Recalculer le LBO » pour repartir d'un calcul frais.
                </div>
              )}
            </div>
          )}

          {/* ── KPIs Principaux ── */}
          {result ? (
            <>
              {/* Sources & Uses bar */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <KpiTile
                  label="Enterprise Value"
                  value={fmt(result.entry_ev)}
                  icon={<Landmark size={14} />}
                  accent="cyan"
                />
                <KpiTile
                  label="Dette Entrée"
                  value={fmt(result.entry_debt)}
                  icon={<Banknote size={14} />}
                  accent="rose"
                />
                <KpiTile
                  label="Equity Check"
                  value={fmt(result.entry_equity)}
                  icon={<DollarSign size={14} />}
                  accent="emerald"
                />
                <KpiTile
                  label="IRR (Brut)"
                  value={pct(result.irr)}
                  icon={<TrendingUp size={14} />}
                  accent={result.irr >= 0.20 ? 'emerald' : result.irr >= 0.15 ? 'amber' : 'rose'}
                  large
                />
                <KpiTile
                  label="MOIC"
                  value={`${result.moic.toFixed(2)}x`}
                  icon={<BarChart3 size={14} />}
                  accent="cyan"
                  large
                />
              </div>

              {/* ── Detail strip ── */}
              <div className="flex flex-wrap gap-4 bg-slate-900/60 border border-slate-800 rounded px-4 py-2.5 text-[10px] font-mono text-slate-400">
                {result.calibration?.sufficient && result.calibration.applicable && (
                  <>
                    <span className="inline-flex items-center gap-1 text-cyan-300 border border-cyan-800 rounded px-1.5 py-0.5">
                      <ScanLine size={10} /> CALIBRÉ CompSet (n={result.calibration.sample_size})
                    </span>
                    <span className="text-slate-700">|</span>
                  </>
                )}
                <span>Profil : <b className="text-slate-200">{result.sector_profile}</b></span>
                <span className="text-slate-700">|</span>
                <span>Marge EBITDA : <b className="text-slate-200">{pct(result.ebitda_margin)}</b></span>
                <span className="text-slate-700">|</span>
                <span>Croissance CA : <b className="text-slate-200">{pct(result.revenue_growth)}</b></span>
                <span className="text-slate-700">|</span>
                <span>Entry Mult. : <b className="text-cyan-400">{result.entry_multiple.toFixed(1)}x</b></span>
                <span className="text-slate-700">|</span>
                <span>Exit Mult. : <b className="text-emerald-400">{result.exit_multiple.toFixed(1)}x</b></span>
                <span className="text-slate-700">|</span>
                <span>Levier E. : <b className="text-rose-400">{result.leverage_entry.toFixed(1)}x</b></span>
                <ArrowRight size={10} className="text-slate-600" />
                <span>Levier S. : <b className="text-slate-200">{result.leverage_exit.toFixed(1)}x</b></span>
                {result.interest_rate > 0 && (
                  <>
                    <span className="text-slate-700">|</span>
                    <span>Coût Moyen Dette : <b className="text-amber-400">{pct(result.interest_rate)}</b></span>
                  </>
                )}
              </div>

              {/* ── V3: Debt Tranches Detail ── */}
              {result.debt_tranches_detail && result.debt_tranches_detail.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {result.debt_tranches_detail.map((td: any, idx: number) => (
                    <div key={idx} className="bg-slate-900/60 border border-slate-800 rounded p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Shield size={12} className="text-rose-400" />
                        <span className="text-xs font-bold text-white">{td.name}</span>
                        <span className={`ml-auto text-[9px] font-mono px-1.5 py-0.5 rounded ${
                          td.amortization === 'amortizing'
                            ? 'text-cyan-400 bg-cyan-950/30 border border-cyan-900'
                            : 'text-amber-400 bg-amber-950/30 border border-amber-900'
                        }`}>
                          {td.amortization === 'amortizing' ? 'AMORT' : 'BULLET'}
                        </span>
                      </div>
                      <div className="text-[10px] font-mono space-y-0.5">
                        <div className="flex justify-between text-slate-400">
                          <span>Montant</span>
                          <span className="text-white">{fmt(td.amount)}</span>
                        </div>
                        <div className="flex justify-between text-slate-400">
                          <span>Taux</span>
                          <span className="text-white">{pct(td.interest_rate)}</span>
                        </div>
                        <div className="flex justify-between text-slate-400">
                          <span>× EBITDA</span>
                          <span className="text-white">{td.amount_turns?.toFixed(1)}×</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* ── V3: Waterfall (Fund vs Management) ── */}
              {result.waterfall && (
                <Card title="Waterfall — Fund vs Management" subtitle="Distribution de l'equity à la sortie" className="overflow-hidden">
                  <div className="p-4 space-y-4">
                    {/* Visual bar */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-[10px] font-mono text-slate-400">
                        <span>Total Exit Equity : <b className="text-white">{fmt(result.waterfall.total_exit_equity)}</b></span>
                      </div>
                      <div className="h-6 rounded overflow-hidden flex">
                        <div
                          className="bg-cyan-600 flex items-center justify-center text-[9px] font-mono text-white font-bold transition-all"
                          style={{ width: `${(1 - result.waterfall.management_total_pct) * 100}%` }}
                        >
                          Fund {((1 - result.waterfall.management_total_pct) * 100).toFixed(0)}%
                        </div>
                        {result.waterfall.management_total_pct > 0 && (
                          <div
                            className="bg-violet-600 flex items-center justify-center text-[9px] font-mono text-white font-bold transition-all"
                            style={{ width: `${result.waterfall.management_total_pct * 100}%` }}
                          >
                            Mgmt {(result.waterfall.management_total_pct * 100).toFixed(0)}%
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Waterfall metrics grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <WaterfallMetric
                        label="Fund Proceeds"
                        value={fmt(result.waterfall.fund_proceeds)}
                        icon={<Landmark size={12} />}
                        color="cyan"
                      />
                      <WaterfallMetric
                        label="Fund MOIC"
                        value={`${result.waterfall.fund_moic.toFixed(2)}x`}
                        icon={<BarChart3 size={12} />}
                        color="cyan"
                      />
                      <WaterfallMetric
                        label="Fund IRR"
                        value={pct(result.waterfall.fund_irr)}
                        icon={<TrendingUp size={12} />}
                        color={result.waterfall.fund_irr >= 0.20 ? 'emerald' : 'amber'}
                      />
                      <WaterfallMetric
                        label="Mgmt Proceeds"
                        value={fmt(result.waterfall.management_proceeds)}
                        icon={<Users size={12} />}
                        color="violet"
                      />
                    </div>

                    {/* Ratchet info */}
                    <div className="flex items-center gap-3 text-[10px] font-mono">
                      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded border ${
                        result.waterfall.ratchet_triggered
                          ? 'text-emerald-400 border-emerald-800 bg-emerald-950/30'
                          : 'text-slate-500 border-slate-700 bg-slate-900/40'
                      }`}>
                        <Award size={10} />
                        Ratchet : {result.waterfall.ratchet_triggered ? 'DÉCLENCHÉ' : 'NON DÉCLENCHÉ'}
                      </span>
                      <span className="text-slate-500">
                        Sweet Equity : <b className="text-violet-400">{(result.waterfall.management_sweet_pct * 100).toFixed(0)}%</b>
                      </span>
                      {result.waterfall.management_moic > 0 && (
                        <span className="text-slate-500">
                          Mgmt MOIC : <b className="text-violet-400">{result.waterfall.management_moic.toFixed(1)}x</b>
                        </span>
                      )}
                    </div>
                  </div>
                </Card>
              )}

              {/* ── Projections Table ── */}
              <Card title="Projections Cash-Flow" subtitle={`${result.holding_period} ans — V3 Multi-Tranche`} className="flex-1 min-h-[250px]">
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="text-[10px] text-slate-500 border-b border-slate-700 bg-slate-900/50 uppercase tracking-wider">
                        <th className="py-3 px-4 font-semibold text-center">Année</th>
                        <th className="py-3 px-4 font-semibold text-right">CA</th>
                        <th className="py-3 px-4 font-semibold text-right">EBITDA</th>
                        <th className="py-3 px-4 font-semibold text-right">Intérêts</th>
                        <th className="py-3 px-4 font-semibold text-right">FCF</th>
                        <th className="py-3 px-4 font-semibold text-right">Remb. Dette</th>
                        <th className="py-3 px-4 font-semibold text-right">Dette Restante</th>
                      </tr>
                    </thead>
                    <tbody className="text-xs font-mono">
                      {result.projections.map((yr: LBOProjectionYear, idx: number) => (
                        <tr
                          key={yr.year}
                          className={`border-b border-slate-800/50 hover:bg-slate-800/70 transition-colors ${idx % 2 === 0 ? 'bg-slate-900/20' : ''}`}
                        >
                          <td className="py-2.5 px-4 text-center">
                            <span className="text-cyan-400 font-bold">Y{yr.year}</span>
                          </td>
                          <td className="py-2.5 px-4 text-right text-slate-200 tabular-nums">{fmt(yr.revenue)}</td>
                          <td className="py-2.5 px-4 text-right text-slate-200 tabular-nums">{fmt(yr.ebitda)}</td>
                          <td className="py-2.5 px-4 text-right text-rose-400 tabular-nums">{fmt(yr.interest)}</td>
                          <td className={`py-2.5 px-4 text-right font-bold tabular-nums ${yr.fcf >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {fmt(yr.fcf)}
                          </td>
                          <td className="py-2.5 px-4 text-right text-amber-400 tabular-nums">{fmt(yr.debt_paydown)}</td>
                          <td className="py-2.5 px-4 text-right text-slate-300 tabular-nums">{fmt(yr.debt_eoy)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Exit summary row */}
                <div className="mt-4 px-4 pb-2 flex flex-wrap gap-6 text-[10px] font-mono border-t border-slate-800 pt-3">
                  <span className="text-slate-400">Exit EV : <b className="text-slate-200">{fmt(result.exit_ev)}</b></span>
                  <span className="text-slate-400">Exit EBITDA : <b className="text-slate-200">{fmt(result.exit_ebitda)}</b></span>
                  <span className="text-slate-400">Dette Résiduelle : <b className="text-rose-400">{fmt(result.exit_debt)}</b></span>
                  <span className="text-slate-400">Equity Sortie : <b className="text-emerald-400">{fmt(result.exit_equity)}</b></span>
                </div>
              </Card>
            </>
          ) : (
            /* ── Empty / loading state ── */
            <div className="flex-1 flex items-center justify-center">
              {lboMutation.isPending ? (
                <div className="flex flex-col items-center gap-3 text-slate-500">
                  <RefreshCw size={32} className="animate-spin text-cyan-600" />
                  <span className="text-xs font-mono">CALCUL DU MODÈLE LBO V3...</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3 text-slate-600">
                  <Calculator size={40} className="text-slate-700" />
                  <span className="text-xs font-mono">CONFIGUREZ LES PARAMÈTRES PUIS LANCEZ LE CALCUL</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};


// ============================================
// Sub-components
// ============================================

interface KpiTileProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  accent: 'cyan' | 'emerald' | 'rose' | 'amber';
  large?: boolean;
}

const accentMap = {
  cyan:    { border: 'border-cyan-900/50',    text: 'text-cyan-400',    bg: 'bg-cyan-950/20' },
  emerald: { border: 'border-emerald-900/50', text: 'text-emerald-400', bg: 'bg-emerald-950/20' },
  rose:    { border: 'border-rose-900/50',    text: 'text-rose-400',    bg: 'bg-rose-950/20' },
  amber:   { border: 'border-amber-900/50',   text: 'text-amber-400',   bg: 'bg-amber-950/20' },
};

const KpiTile: React.FC<KpiTileProps> = ({ label, value, icon, accent, large }) => {
  const a = accentMap[accent];
  return (
    <div className={`rounded border ${a.border} ${a.bg} bg-slate-900 p-3 flex flex-col items-center justify-center gap-1`}>
      <div className={`${a.text} mb-1`}>{icon}</div>
      <div className={`${large ? 'text-2xl' : 'text-lg'} font-mono font-bold ${a.text} tabular-nums tracking-tight`}>
        {value}
      </div>
      <div className="text-[9px] text-slate-500 uppercase tracking-wider text-center">{label}</div>
    </div>
  );
};


interface WaterfallMetricProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: 'cyan' | 'emerald' | 'violet' | 'amber';
}

const waterfallColorMap = {
  cyan:    'text-cyan-400',
  emerald: 'text-emerald-400',
  violet:  'text-violet-400',
  amber:   'text-amber-400',
};

const WaterfallMetric: React.FC<WaterfallMetricProps> = ({ label, value, icon, color }) => (
  <div className="bg-slate-900/80 border border-slate-800 rounded p-2.5 text-center">
    <div className={`${waterfallColorMap[color]} mb-1 flex justify-center`}>{icon}</div>
    <div className={`text-sm font-mono font-bold ${waterfallColorMap[color]} tabular-nums`}>{value}</div>
    <div className="text-[8px] text-slate-500 uppercase tracking-wider mt-0.5">{label}</div>
  </div>
);
