import React, { useState, useCallback, useMemo } from 'react';
import { Card } from '../ui/Card';
import {
  Network, Plus, Trash2, RefreshCw, Calculator, ChevronDown,
  DollarSign, TrendingUp, BarChart3, Landmark, Banknote,
  ArrowRight, Percent, Zap, Target, Crown,
} from 'lucide-react';
import { useSourcedTargets, useCalculateBuildupMutation } from '../../hooks/useQueries';
import type { SourcedTargetMA, BuildupRequest, BuildupResult, LBOProjectionYear } from '../../types';

// Défauts sectoriels TIC ("Conseil, Juridique & Ingénierie" — professional_svc,
// LBO_PROFILES) — c'est le secteur réel de toutes les cibles sourcées par ce
// projet (filtrage NAF 71.20B/71.12B). Le moteur applique ces mêmes valeurs
// côté serveur si aucune surcharge n'est envoyée (voir buildup_engine.py D37).
const SECTOR_DEFAULT_CAPEX_PCT = 2;
const SECTOR_DEFAULT_WCR_PCT = 15;
const SECTOR_DEFAULT_LEVERAGE = 4.0;
const SECTOR_DEFAULT_GROWTH_PCT = 4;
const SECTOR_DEFAULT_ENTRY_MULTIPLE = 7;

// ============================================
// Helpers
// ============================================

const fmt = (v: number): string => {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} M€`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)} K€`;
  return `${v.toFixed(0)} €`;
};

const pct = (v: number): string => `${(v * 100).toFixed(1)}%`;

interface ManualAddon {
  id: number;
  name: string;
  revenue: number;
  ebitdaMargin: number;
  multiple: number;
}

// ============================================
// Main Component
// ============================================

export const BuyAndBuild: React.FC = () => {
  // ── Data from DB ──
  const { data: targetsData, isLoading: targetsLoading } = useSourcedTargets(0, 100);
  const dbTargets = targetsData?.targets ?? [];

  // ── Selection state ──
  const [platformId, setPlatformId] = useState<number | null>(null);
  const [addonIds, setAddonIds] = useState<number[]>([]);

  // ── Manual add-ons ──
  const [manualAddons, setManualAddons] = useState<ManualAddon[]>([]);
  const [newAddonName, setNewAddonName] = useState('');
  const [newAddonRevenue, setNewAddonRevenue] = useState<number>(2_000_000);
  const [newAddonMargin, setNewAddonMargin] = useState<number>(15); // défaut sectoriel TIC (professional_svc)
  const [newAddonMultiple, setNewAddonMultiple] = useState<number>(7);
  const [nextAddonId, setNextAddonId] = useState(1);

  // ── Synergy slider ──
  const [synergyPct, setSynergyPct] = useState<number>(5);

  // ── Hypothèses avancées (D37) — désactivées = profil sectoriel TIC par défaut ──
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [overrideCapex, setOverrideCapex] = useState(false);
  const [capexPct, setCapexPct] = useState<number>(SECTOR_DEFAULT_CAPEX_PCT);
  const [overrideWcr, setOverrideWcr] = useState(false);
  const [wcrPct, setWcrPct] = useState<number>(SECTOR_DEFAULT_WCR_PCT);
  const [overrideLeverage, setOverrideLeverage] = useState(false);
  const [leverageTurns, setLeverageTurns] = useState<number>(SECTOR_DEFAULT_LEVERAGE);
  const [overrideGrowth, setOverrideGrowth] = useState(false);
  const [growthPct, setGrowthPct] = useState<number>(SECTOR_DEFAULT_GROWTH_PCT);

  // ── Mutation ──
  const buildupMutation = useCalculateBuildupMutation();
  const result: BuildupResult | undefined = buildupMutation.data;

  // ── Derived: available add-ons (exclude selected platform) ──
  const availableAddons = useMemo(
    () => dbTargets.filter(t => t.id !== platformId),
    [dbTargets, platformId],
  );

  const selectedPlatform = useMemo(
    () => dbTargets.find(t => t.id === platformId) ?? null,
    [dbTargets, platformId],
  );

  // ── Manual add-on CRUD ──
  const handleAddManualAddon = useCallback(() => {
    if (!newAddonName.trim()) return;
    const ebitda = newAddonRevenue * (newAddonMargin / 100);
    const addon: ManualAddon = {
      id: nextAddonId,
      name: newAddonName.trim(),
      revenue: newAddonRevenue,
      ebitdaMargin: newAddonMargin,
      multiple: newAddonMultiple,
    };
    setManualAddons(prev => [...prev, addon]);
    setNextAddonId(prev => prev + 1);
    setNewAddonName('');
    setNewAddonRevenue(2_000_000);
    setNewAddonMargin(15);
    setNewAddonMultiple(7);
  }, [newAddonName, newAddonRevenue, newAddonMargin, newAddonMultiple, nextAddonId]);

  const handleRemoveManualAddon = useCallback((id: number) => {
    setManualAddons(prev => prev.filter(a => a.id !== id));
  }, []);

  // ── Toggle DB add-on ──
  const toggleAddonId = useCallback((id: number) => {
    setAddonIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    );
  }, []);

  // ── Simulate ──
  const handleSimulate = useCallback(() => {
    if (!selectedPlatform) return;

    // Build platform target dict. entry_multiple/ebitda/ev sont laissés à 0
    // (jamais une valeur arbitraire type "8x" côté client) quand absents en
    // base : le moteur applique alors le profil sectoriel TIC documenté et
    // le signale via `platform_estimated` (D37). lbo_projections est
    // transmis pour permettre l'inférence de la croissance réelle de la
    // cible (auparavant omis par erreur — la simulation retombait toujours
    // sur 3 % fixe, cf. RAPPORT D37).
    const platformTarget: Record<string, any> = {
      url: selectedPlatform.url,
      estimated_revenue: selectedPlatform.revenue_estimate ?? 0,
      ebitda: selectedPlatform.ebitda_estimate ?? 0,
      ev: selectedPlatform.enterprise_value ?? 0,
      entry_multiple: selectedPlatform.entry_multiple ?? 0,
      irr: selectedPlatform.lbo_irr ?? 0,
      moic: selectedPlatform.lbo_moic ?? 0,
      lbo_projections: selectedPlatform.lbo_projections ?? null,
    };

    // Build add-on targets list (DB + manual)
    const addonTargets: Record<string, any>[] = [];

    // DB add-ons
    addonIds.forEach(id => {
      const t = dbTargets.find(x => x.id === id);
      if (t) {
        addonTargets.push({
          url: t.url,
          estimated_revenue: t.revenue_estimate ?? 0,
          ebitda: t.ebitda_estimate ?? 0,
          ev: t.enterprise_value ?? 0,
          entry_multiple: t.entry_multiple ?? 0,
          lbo_projections: t.lbo_projections ?? null,
        });
      }
    });

    // Manual add-ons
    manualAddons.forEach(a => {
      const ebitda = a.revenue * (a.ebitdaMargin / 100);
      addonTargets.push({
        url: `manual://${a.name.replace(/\s+/g, '-').toLowerCase()}`,
        estimated_revenue: a.revenue,
        ebitda,
        ev: ebitda * a.multiple,
        entry_multiple: a.multiple,
      });
    });

    const payload: BuildupRequest = {
      platform_target: platformTarget,
      addon_targets: addonTargets,
      synergy_pct: synergyPct / 100,
      capex_pct: overrideCapex ? capexPct / 100 : null,
      wcr_pct: overrideWcr ? wcrPct / 100 : null,
      leverage_turns: overrideLeverage ? leverageTurns : null,
      growth_override: overrideGrowth ? growthPct / 100 : null,
    };

    buildupMutation.mutate(payload);
  }, [
    selectedPlatform, addonIds, dbTargets, manualAddons, synergyPct, buildupMutation,
    overrideCapex, capexPct, overrideWcr, wcrPct, overrideLeverage, leverageTurns,
    overrideGrowth, growthPct,
  ]);

  const totalAddons = addonIds.length + manualAddons.length;
  const canSimulate = selectedPlatform !== null && totalAddons > 0;

  return (
    <div className="h-full w-full flex flex-col space-y-6">

      {/* ── Header ── */}
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
          <span className="text-cyan-500">///</span> Buy &amp; Build Simulator
          <span className="text-[10px] text-slate-500 font-mono border border-slate-800 rounded px-1.5 py-0.5 ml-2">MULTIPLE ARBITRAGE</span>
        </h2>
        <div className="text-[10px] text-slate-500 font-mono">
          MOTEUR : FASTAPI :8000 / BUILDUP_ENGINE
        </div>
      </div>

      {/* ── Explication du modèle (D37) ── */}
      <div className="rounded-lg border border-cyan-900/40 bg-cyan-950/10 px-4 py-3 text-[11px] text-slate-300 leading-relaxed">
        <p>
          Simule une stratégie de <strong>consolidation ("roll-up")</strong> : une <strong>plateforme</strong> (idéalement
          une cible réelle marquée <span className="text-violet-300 font-mono">PLATFORM</span>, ex. Artelia, Dekra)
          acquiert des <strong>add-ons</strong> (cibles <span className="text-cyan-300 font-mono">TARGET</span> du pipeline
          ou add-ons fictifs), consolide leur CA/EBITDA avec des synergies d'échelle, puis sort <em>au multiple de la
          plateforme</em> plutôt qu'au multiple (souvent plus faible) auquel chaque add-on a été acheté — c'est
          l'<strong>arbitrage de multiple</strong> : la valeur créée ne vient pas seulement de la croissance ou du
          désendettement, mais de la re-cotation de tout le groupe consolidé au multiple du plus gros acteur.
        </p>
        <p className="mt-1.5 font-mono text-cyan-300">
          Multiple mixte à l'achat (add-ons + plateforme) {'<'} Multiple de sortie (plateforme) = gain d'arbitrage
        </p>
        <p className="mt-1.5 text-slate-400">
          Hypothèses de croissance/Capex/BFR/levier par défaut = profil sectoriel <strong>TIC</strong> calibré
          ("Conseil, Juridique &amp; Ingénierie", le secteur réel de toutes les cibles sourcées par ce projet) —
          toutes modifiables dans le panneau « Hypothèses avancées ». Les cibles réelles sans quick-screen financier
          (grandes plateformes marché) sont estimées avec ce même profil et signalées <span className="text-amber-300 font-mono">« estimé »</span>.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">

        {/* ═══════════════════════════════════════
            LEFT — Configuration Panel
           ═══════════════════════════════════════ */}
        <div className="col-span-1 xl:col-span-5 space-y-4">

          {/* ── Platform Selection ── */}
          <Card title="Sélection Plateforme" subtitle="Choisir la cible principale">
            <div className="p-4 space-y-4">
              <div className="flex items-center space-x-2 text-cyan-400 mb-1">
                <Crown size={16} />
                <span className="text-xs font-bold uppercase">Plateforme (depuis la DB)</span>
              </div>
              {targetsLoading ? (
                <div className="text-xs text-slate-500 font-mono flex items-center gap-2">
                  <RefreshCw size={12} className="animate-spin" /> Chargement des cibles...
                </div>
              ) : dbTargets.length === 0 ? (
                <div className="text-xs text-slate-500 font-mono">
                  Aucune cible en base. Lancez un scan OSINT d'abord.
                </div>
              ) : (
                <div className="relative">
                  <select
                    value={platformId ?? ''}
                    onChange={e => {
                      const id = e.target.value ? Number(e.target.value) : null;
                      setPlatformId(id);
                      // Remove from add-ons if selected as platform
                      if (id) setAddonIds(prev => prev.filter(x => x !== id));
                    }}
                    className="w-full bg-slate-950 border border-slate-700 rounded py-2 px-3 text-xs text-white appearance-none focus:border-cyan-500 outline-none cursor-pointer"
                  >
                    <option value="">— Sélectionner une plateforme —</option>
                    <optgroup label="Plateformes réelles (target_type=platform)">
                      {dbTargets.filter(t => t.target_type === 'platform').map(t => (
                        <option key={t.id} value={t.id}>
                          {t.company_name} — {t.revenue_estimate ? fmt(t.revenue_estimate) : 'CA ?'}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="Autres cibles sourcées">
                      {dbTargets.filter(t => t.target_type !== 'platform').map(t => (
                        <option key={t.id} value={t.id}>
                          {t.company_name} — {t.revenue_estimate ? fmt(t.revenue_estimate) : 'CA ?'} — Score {t.score ?? '—'}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                  <ChevronDown size={14} className="absolute right-3 top-2.5 text-slate-500 pointer-events-none" />
                </div>
              )}

              {/* Platform preview */}
              {selectedPlatform && (
                <div className="bg-slate-950 border border-cyan-900/40 rounded p-3 text-[10px] font-mono space-y-1">
                  <div className="text-cyan-400 font-bold text-xs mb-1 flex items-center gap-2">
                    {selectedPlatform.company_name}
                    {selectedPlatform.target_type === 'platform' && (
                      <span className="text-violet-300 border border-violet-800 rounded px-1 py-0.5 text-[9px]">PLATFORM</span>
                    )}
                  </div>
                  <div className="text-slate-400">CA : <b className="text-slate-200">{selectedPlatform.revenue_estimate ? fmt(selectedPlatform.revenue_estimate) : 'N/A'}</b></div>
                  <div className="text-slate-400">EBITDA : <b className="text-slate-200">{selectedPlatform.ebitda_estimate ? fmt(selectedPlatform.ebitda_estimate) : 'N/A'}</b></div>
                  <div className="text-slate-400">EV : <b className="text-slate-200">{selectedPlatform.enterprise_value ? fmt(selectedPlatform.enterprise_value) : 'N/A'}</b></div>
                  <div className="text-slate-400">Multiple : <b className="text-cyan-400">{selectedPlatform.entry_multiple?.toFixed(1) ?? '—'}x</b></div>
                  <div className="text-slate-400">IRR Standalone : <b className="text-emerald-400">{selectedPlatform.lbo_irr != null ? pct(selectedPlatform.lbo_irr) : '—'}</b></div>
                  {!selectedPlatform.ebitda_estimate && (
                    <div className="text-amber-400 pt-1 border-t border-slate-800 mt-1">
                      Pas de quick-screen financier — EBITDA/EV seront estimés au profil sectoriel TIC (marge 15%, {SECTOR_DEFAULT_ENTRY_MULTIPLE}x) à la simulation.
                    </div>
                  )}
                </div>
              )}
            </div>
          </Card>

          {/* ── DB Add-ons Selection ── */}
          <Card title="Add-ons (DB)" subtitle={`${addonIds.length} sélectionné${addonIds.length !== 1 ? 's' : ''}`}>
            <div className="p-4 space-y-3">
              <div className="flex items-center space-x-2 text-emerald-400 mb-1">
                <Target size={16} />
                <span className="text-xs font-bold uppercase">Cibles Add-on (multi-sélection)</span>
              </div>
              {availableAddons.length === 0 ? (
                <div className="text-[10px] text-slate-500 font-mono">
                  {platformId ? 'Aucune autre cible disponible.' : 'Sélectionnez d\'abord une plateforme.'}
                </div>
              ) : (
                <div className="max-h-[200px] overflow-y-auto space-y-1.5 pr-1">
                  {availableAddons.map(t => {
                    const checked = addonIds.includes(t.id);
                    return (
                      <label
                        key={t.id}
                        className={`flex items-center gap-3 px-3 py-2 rounded border cursor-pointer transition-all text-xs
                          ${checked
                            ? 'bg-emerald-950/30 border-emerald-800 text-emerald-300'
                            : 'bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
                          }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleAddonId(t.id)}
                          className="accent-emerald-500"
                        />
                        <div className="flex-1 min-w-0">
                          <span className="font-bold text-slate-200 font-sans">{t.company_name}</span>
                          <span className="text-[10px] text-slate-500 ml-2 font-mono">
                            {t.revenue_estimate ? fmt(t.revenue_estimate) : 'N/D'} · {t.entry_multiple != null ? `${t.entry_multiple.toFixed(1)}x` : 'N/D'}
                          </span>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>

          {/* ── Manual Add-ons (Scenario Builder) ── */}
          <Card title="Scenario Builder" subtitle="Add-ons fictifs">
            <div className="p-4 space-y-4">
              <div className="flex items-center space-x-2 text-amber-400 mb-1">
                <Plus size={16} />
                <span className="text-xs font-bold uppercase">Créer un Add-on Fictif</span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="text-[10px] text-slate-400 font-bold uppercase mb-1 block">Nom</label>
                  <input
                    type="text"
                    value={newAddonName}
                    onChange={e => setNewAddonName(e.target.value)}
                    placeholder="Ex: FinTech Alpha"
                    className="w-full bg-slate-950 border border-slate-700 rounded py-1.5 px-3 text-xs text-white focus:border-amber-500 outline-none"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 font-bold uppercase mb-1 block">CA (€)</label>
                  <input
                    type="number" step={100_000} min={0}
                    value={newAddonRevenue}
                    onChange={e => setNewAddonRevenue(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700 rounded py-1.5 px-3 text-xs text-white font-mono focus:border-amber-500 outline-none"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 font-bold uppercase mb-1 block">Marge EBITDA (%)</label>
                  <input
                    type="number" step={1} min={0} max={80}
                    value={newAddonMargin}
                    onChange={e => setNewAddonMargin(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700 rounded py-1.5 px-3 text-xs text-white font-mono focus:border-amber-500 outline-none"
                  />
                  <span className="text-[9px] text-slate-600 font-mono">défaut secteur TIC : 15%</span>
                </div>
                <div className="col-span-2">
                  <label className="text-[10px] text-slate-400 font-bold uppercase mb-1 block">Multiple d'Entrée</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range" min="3" max="15" step="0.5"
                      value={newAddonMultiple}
                      onChange={e => setNewAddonMultiple(Number(e.target.value))}
                      className="flex-1 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                    />
                    <span className="text-xs text-white font-mono w-10 text-right">{newAddonMultiple.toFixed(1)}x</span>
                  </div>
                </div>
              </div>

              <button
                onClick={handleAddManualAddon}
                disabled={!newAddonName.trim()}
                className="w-full py-2 rounded text-xs font-bold uppercase tracking-wider transition-all inline-flex items-center justify-center gap-2
                  bg-amber-700 hover:bg-amber-600 text-white disabled:bg-slate-700 disabled:text-slate-500
                  border border-amber-600 disabled:border-slate-600"
              >
                <Plus size={12} /> Ajouter Add-on Fictif
              </button>

              {/* List of manual add-ons */}
              {manualAddons.length > 0 && (
                <div className="space-y-1.5 mt-2">
                  {manualAddons.map(a => (
                    <div key={a.id} className="flex items-center justify-between bg-amber-950/20 border border-amber-900/40 rounded px-3 py-2 text-[10px] font-mono">
                      <div>
                        <span className="text-amber-300 font-bold text-xs">{a.name}</span>
                        <span className="text-slate-500 ml-2">{fmt(a.revenue)} · {a.ebitdaMargin}% · {a.multiple}x</span>
                      </div>
                      <button
                        onClick={() => handleRemoveManualAddon(a.id)}
                        className="text-slate-500 hover:text-rose-400 transition-colors"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* ── Synergies ── */}
          <Card title="Synergies" className="border-emerald-900/30">
            <div className="p-4">
              <div className="flex justify-between text-xs mb-2">
                <span className="text-slate-400">Synergies CA Consolidé</span>
                <span className="font-mono text-emerald-400 font-bold">{synergyPct}%</span>
              </div>
              <input
                type="range" min="0" max="15" step="0.5"
                value={synergyPct}
                onChange={e => setSynergyPct(Number(e.target.value))}
                className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
              <div className="flex justify-between text-[10px] text-slate-600 mt-1 font-mono">
                <span>0%</span>
                <span>15%</span>
              </div>
              <p className="text-[9px] text-slate-600 mt-2">
                Économies d'échelle attendues d'une consolidation de services professionnels (achats groupés,
                mutualisation SG&amp;A) : usuellement 3-8% du CA — Bain &amp; Company, études de roll-up PE. 5% par
                défaut, à ajuster selon le niveau réel de duplication des fonctions support entre plateforme et add-ons.
              </p>
            </div>
          </Card>

          {/* ── Hypothèses avancées (D37) ── */}
          <Card title="Hypothèses avancées" subtitle="Défaut = profil sectoriel TIC, modifiable" className="border-slate-700">
            <div className="p-4">
              <button
                onClick={() => setShowAdvanced(v => !v)}
                className="w-full flex items-center justify-between text-[11px] text-slate-400 hover:text-slate-200 font-mono"
              >
                <span>{showAdvanced ? 'Masquer' : 'Afficher'} croissance / Capex / BFR / levier</span>
                <ChevronDown size={12} className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              </button>

              {showAdvanced && (
                <div className="mt-3 space-y-3">
                  <AssumptionRow
                    label="Croissance CA consolidé"
                    explanation="Par défaut : inférée des projections LBO réelles des cibles (Y0→Y1), sinon profil sectoriel TIC (4%/an)."
                    enabled={overrideGrowth}
                    onToggle={() => setOverrideGrowth(v => !v)}
                    value={growthPct}
                    onChange={setGrowthPct}
                    suffix="%"
                    min={-20} max={30} step={0.5}
                    defaultLabel={`${SECTOR_DEFAULT_GROWTH_PCT}%`}
                  />
                  <AssumptionRow
                    label="Capex (% du CA)"
                    explanation="Investissements récurrents en % du CA. Défaut : profil TIC 'Conseil, Juridique & Ingénierie' (activité peu capitalistique)."
                    enabled={overrideCapex}
                    onToggle={() => setOverrideCapex(v => !v)}
                    value={capexPct}
                    onChange={setCapexPct}
                    suffix="%"
                    min={0} max={15} step={0.5}
                    defaultLabel={`${SECTOR_DEFAULT_CAPEX_PCT}%`}
                  />
                  <AssumptionRow
                    label="BFR (% de ΔCA)"
                    explanation="Besoin en fonds de roulement additionnel généré par la croissance du CA. Défaut : profil TIC (15% de la variation de CA)."
                    enabled={overrideWcr}
                    onToggle={() => setOverrideWcr(v => !v)}
                    value={wcrPct}
                    onChange={setWcrPct}
                    suffix="%"
                    min={0} max={40} step={1}
                    defaultLabel={`${SECTOR_DEFAULT_WCR_PCT}%`}
                  />
                  <AssumptionRow
                    label="Levier d'entrée"
                    explanation="Dette bancaire à l'entrée, en multiple de l'EBITDA consolidé post-synergies (plafonné à 60% de l'EV, comme le LBO standalone). Défaut : 4.0x, identique au moteur LBO standalone."
                    enabled={overrideLeverage}
                    onToggle={() => setOverrideLeverage(v => !v)}
                    value={leverageTurns}
                    onChange={setLeverageTurns}
                    suffix="x"
                    min={0} max={6} step={0.25}
                    defaultLabel={`${SECTOR_DEFAULT_LEVERAGE}x`}
                  />
                  <p className="text-[9px] text-slate-600 pt-1 border-t border-slate-800">
                    Taux d'intérêt (7%) et IS (25%) restent alignés sur le moteur LBO standalone — non modifiables ici
                    pour rester cohérents avec le calculateur LBO (voir Méthodologie).
                  </p>
                </div>
              )}
            </div>
          </Card>

          {/* ── CTA ── */}
          <button
            onClick={handleSimulate}
            disabled={buildupMutation.isPending || !canSimulate}
            className="w-full py-3.5 rounded text-sm font-bold uppercase tracking-wider transition-all inline-flex items-center justify-center gap-2
              bg-cyan-600 hover:bg-cyan-500 text-white disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed
              border border-cyan-500 disabled:border-slate-600 shadow-lg shadow-cyan-900/30 disabled:shadow-none"
          >
            {buildupMutation.isPending ? (
              <><RefreshCw size={14} className="animate-spin" /> SIMULATION EN COURS...</>
            ) : (
              <><Network size={14} /> SIMULER LA CONSOLIDATION</>
            )}
          </button>
          {!canSimulate && !buildupMutation.isPending && (
            <p className="text-[10px] text-slate-600 font-mono text-center mt-1">
              Sélectionnez une plateforme et au moins 1 add-on.
            </p>
          )}

          {buildupMutation.isError && (
            <div className="mt-2 text-[10px] text-rose-400 font-mono bg-rose-950/30 border border-rose-900 rounded p-2">
              Erreur : {buildupMutation.error instanceof Error ? buildupMutation.error.message : 'Échec de la simulation'}
            </div>
          )}
        </div>

        {/* ═══════════════════════════════════════
            RIGHT — Résultats
           ═══════════════════════════════════════ */}
        <div className="col-span-1 xl:col-span-7 flex flex-col gap-6">

          {result ? (
            <>
              {/* ── KPIs d'Acquisition ── */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KpiTile
                  label="Coût Total"
                  value={fmt(result.total_acquisition_cost)}
                  icon={<Landmark size={14} />}
                  accent="cyan"
                />
                <KpiTile
                  label="Blended Multiple"
                  value={`${result.blended_entry_multiple.toFixed(1)}x`}
                  icon={<BarChart3 size={14} />}
                  accent="cyan"
                />
                <KpiTile
                  label="EBITDA Consolidé"
                  value={fmt(result.consolidated_ebitda_post_syn)}
                  icon={<TrendingUp size={14} />}
                  accent="emerald"
                  sub={`Marge ${pct(result.consolidated_margin)}`}
                />
                <KpiTile
                  label="Synergies"
                  value={fmt(result.synergies)}
                  icon={<Zap size={14} />}
                  accent="amber"
                  sub={`${pct(result.synergy_pct)} du CA`}
                />
              </div>

              {/* ── La Comparaison Magique ── */}
              <Card title="L'Arbitrage de Multiple" subtitle="Standalone vs. Build-up consolidé">
                <div className="p-4">
                  <div className="grid grid-cols-3 gap-4 items-stretch">

                    {/* Standalone */}
                    <div className="bg-slate-950 border border-slate-700 rounded-lg p-4 flex flex-col items-center justify-center gap-2">
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Standalone</span>
                      <div className={`text-3xl font-mono font-bold tabular-nums ${
                        result.irr_standalone >= 0.20 ? 'text-emerald-400'
                          : result.irr_standalone >= 0.15 ? 'text-amber-400'
                          : 'text-rose-400'
                      }`}>
                        {pct(result.irr_standalone)}
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">IRR</span>
                      <div className="text-lg font-mono font-bold text-slate-300 tabular-nums">
                        {result.moic_standalone.toFixed(2)}x
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">MOIC</span>
                    </div>

                    {/* Arrow + Delta */}
                    <div className="flex flex-col items-center justify-center gap-2">
                      <ArrowRight size={28} className="text-slate-600" />
                      <div className={`text-2xl font-mono font-bold tabular-nums px-3 py-1.5 rounded-lg border ${
                        result.delta_irr > 0
                          ? 'text-emerald-400 bg-emerald-950/30 border-emerald-800'
                          : result.delta_irr === 0
                            ? 'text-slate-400 bg-slate-800 border-slate-700'
                            : 'text-rose-400 bg-rose-950/30 border-rose-800'
                      }`}>
                        {result.delta_irr > 0 ? '+' : ''}{(result.delta_irr * 100).toFixed(1)} pts
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono uppercase">Delta IRR</span>
                    </div>

                    {/* Build-up */}
                    <div className="bg-cyan-950/20 border border-cyan-800/50 rounded-lg p-4 flex flex-col items-center justify-center gap-2">
                      <span className="text-[10px] text-cyan-400 uppercase tracking-wider font-bold">Build-up</span>
                      <div className={`text-3xl font-mono font-bold tabular-nums ${
                        result.irr_buildup >= 0.20 ? 'text-emerald-400'
                          : result.irr_buildup >= 0.15 ? 'text-amber-400'
                          : 'text-rose-400'
                      }`}>
                        {pct(result.irr_buildup)}
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">IRR</span>
                      <div className="text-lg font-mono font-bold text-cyan-300 tabular-nums">
                        {result.moic_buildup.toFixed(2)}x
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">MOIC</span>
                    </div>
                  </div>

                  {/* Details strip */}
                  <div className="flex flex-wrap gap-4 mt-4 pt-3 border-t border-slate-800 text-[10px] font-mono text-slate-400">
                    <span>Plateforme : <b className="text-cyan-400">{result.platform_url}</b></span>
                    <span className="text-slate-700">|</span>
                    <span>Mult. Plateforme : <b className="text-slate-200">{result.platform_multiple.toFixed(1)}x</b></span>
                    <span className="text-slate-700">|</span>
                    <span>Add-ons : <b className="text-slate-200">{result.addons_count}</b> ({fmt(result.addons_ev)})</span>
                    <span className="text-slate-700">|</span>
                    <span>Exit Mult. : <b className="text-emerald-400">{result.exit_multiple_applied.toFixed(1)}x</b></span>
                  </div>

                  {(result.platform_estimated || result.addon_details.some(a => a.estimated) || result.excluded_addons.length > 0) && (
                    <div className="mt-3 pt-3 border-t border-slate-800 space-y-1 text-[10px] font-mono">
                      {result.platform_estimated && (
                        <div className="text-amber-400">⚠ Plateforme : EBITDA/EV estimés au profil sectoriel TIC (pas de quick-screen financier propre à cette cible).</div>
                      )}
                      {result.addon_details.filter(a => a.estimated).map(a => (
                        <div key={a.url} className="text-amber-400">⚠ Add-on « {a.url} » : EBITDA/EV estimés au profil sectoriel TIC.</div>
                      ))}
                      {result.excluded_addons.length > 0 && (
                        <div className="text-rose-400">✕ Exclu(s) — aucune donnée exploitable : {result.excluded_addons.join(', ')}</div>
                      )}
                    </div>
                  )}

                  {/* Hypothèses effectivement appliquées (D37) */}
                  <div className="mt-3 pt-3 border-t border-slate-800 flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-slate-500">
                    <span>Croissance : <b className="text-slate-300">{pct(result.assumptions_used.growth_rate)}</b></span>
                    <span>Capex : <b className="text-slate-300">{pct(result.assumptions_used.capex_pct)}</b> CA</span>
                    <span>BFR : <b className="text-slate-300">{pct(result.assumptions_used.wcr_pct)}</b> ΔCA</span>
                    <span>Levier : <b className="text-slate-300">{result.assumptions_used.leverage_turns.toFixed(1)}x</b></span>
                    <span>Taux : <b className="text-slate-300">{pct(result.assumptions_used.interest_rate)}</b></span>
                  </div>
                </div>
              </Card>

              {/* ── Sources & Uses ── */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <KpiTile label="EV Plateforme" value={fmt(result.platform_ev)} icon={<Crown size={14} />} accent="cyan" />
                <KpiTile label="EV Add-ons" value={fmt(result.addons_ev)} icon={<Target size={14} />} accent="amber" />
                <KpiTile label="Dette Entrée" value={fmt(result.entry_debt)} icon={<Banknote size={14} />} accent="rose" />
              </div>

              {/* ── Projections Table ── */}
              <Card title="Projections Consolidées" subtitle={`${result.projections.length} années`} className="flex-1 min-h-[250px]">
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
                        <th className="py-3 px-4 font-semibold text-right">Dette Fin</th>
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

                {/* Exit summary */}
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
            <div className="flex-1 flex items-center justify-center min-h-[400px]">
              {buildupMutation.isPending ? (
                <div className="flex flex-col items-center gap-3 text-slate-500">
                  <RefreshCw size={32} className="animate-spin text-cyan-600" />
                  <span className="text-xs font-mono">SIMULATION BUY &amp; BUILD...</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-4 text-slate-600">
                  <Network size={48} className="text-slate-700" />
                  <span className="text-sm font-mono">BUY &amp; BUILD SIMULATOR</span>
                  <span className="text-[10px] text-slate-700 font-mono text-center max-w-[320px]">
                    Sélectionnez une plateforme et des add-ons puis lancez la simulation pour voir l'arbitrage de multiple.
                  </span>
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
// Sub-component: KPI Tile
// ============================================

interface KpiTileProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  accent: 'cyan' | 'emerald' | 'rose' | 'amber';
  sub?: string;
}

const accentMap = {
  cyan:    { border: 'border-cyan-900/50',    text: 'text-cyan-400',    bg: 'bg-cyan-950/20' },
  emerald: { border: 'border-emerald-900/50', text: 'text-emerald-400', bg: 'bg-emerald-950/20' },
  rose:    { border: 'border-rose-900/50',    text: 'text-rose-400',    bg: 'bg-rose-950/20' },
  amber:   { border: 'border-amber-900/50',   text: 'text-amber-400',   bg: 'bg-amber-950/20' },
};

const KpiTile: React.FC<KpiTileProps> = ({ label, value, icon, accent, sub }) => {
  const a = accentMap[accent];
  return (
    <div className={`rounded border ${a.border} ${a.bg} bg-slate-900 p-3 flex flex-col items-center justify-center gap-1`}>
      <div className={`${a.text} mb-1`}>{icon}</div>
      <div className={`text-lg font-mono font-bold ${a.text} tabular-nums tracking-tight`}>
        {value}
      </div>
      <div className="text-[9px] text-slate-500 uppercase tracking-wider text-center">{label}</div>
      {sub && <div className="text-[9px] text-slate-600 font-mono">{sub}</div>}
    </div>
  );
};

// ============================================================
// Sub-component: Assumption Row (D37 — hypothèse éditable + documentée)
// ============================================================

interface AssumptionRowProps {
  label: string;
  explanation: string;
  enabled: boolean;
  onToggle: () => void;
  value: number;
  onChange: (v: number) => void;
  suffix: string;
  min: number;
  max: number;
  step: number;
  defaultLabel: string;
}

const AssumptionRow: React.FC<AssumptionRowProps> = ({
  label, explanation, enabled, onToggle, value, onChange, suffix, min, max, step, defaultLabel,
}) => (
  <div className={`rounded border px-3 py-2 ${enabled ? 'border-amber-800 bg-amber-950/10' : 'border-slate-800 bg-slate-900/40'}`}>
    <div className="flex items-center justify-between gap-2">
      <label className="flex items-center gap-2 text-[11px] text-slate-300 font-bold cursor-pointer">
        <input type="checkbox" checked={enabled} onChange={onToggle} className="accent-amber-500" />
        {label}
      </label>
      {enabled ? (
        <div className="flex items-center gap-2">
          <input
            type="number" min={min} max={max} step={step}
            value={value}
            onChange={e => onChange(Number(e.target.value))}
            className="w-16 bg-slate-950 border border-slate-700 rounded py-1 px-2 text-xs text-white font-mono focus:border-amber-500 outline-none text-right"
          />
          <span className="text-[10px] text-amber-400 font-mono">{suffix}</span>
        </div>
      ) : (
        <span className="text-[10px] text-slate-500 font-mono">défaut : {defaultLabel}</span>
      )}
    </div>
    <p className="text-[9px] text-slate-600 mt-1 leading-snug">{explanation}</p>
  </div>
);
