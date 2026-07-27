import React, { useMemo, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Card } from '../ui/Card';
import { ProvenanceBadge } from '../ProvenanceBadge';
import { ArrowUpDown, ArrowUp, ArrowDown, Info, RefreshCw, Building2, Target, ExternalLink } from 'lucide-react';
import { useCompSets, useCompsTable, useDeal, useLboScenarios } from '../../hooks/useQueries';
import type { CompRow } from '../../types';

// ============================================
// Helpers
// ============================================

const fmtMoney = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  const abs = Math.abs(v);
  if (abs >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toFixed(0);
};

const fmtPct = (v: number | null | undefined): string => (v === null || v === undefined ? '—' : `${v.toFixed(1)}%`);
const fmtMult = (v: number | null | undefined): string => (v === null || v === undefined ? '—' : `${v.toFixed(1)}x`);

// Dérivation client-side place de cotation / devise à partir du suffixe du
// ticker — l'API /comps ne renseigne ni l'un ni l'autre par ligne (voir
// RAPPORT B.10 §Champs manquants : Company.currency existe en base et est
// exposé par /company/{ticker}, mais PAS par /comps/{id}). Mapping
// déterministe, standard (convention Bloomberg/Reuters des suffixes de
// place), pas une donnée financière inventée.
const EXCHANGE_BY_SUFFIX: Record<string, { exchange: string; currency: string }> = {
  '.PA': { exchange: 'Euronext Paris', currency: 'EUR' },
  '.SW': { exchange: 'SIX Swiss Exchange', currency: 'CHF' },
  '.L': { exchange: 'London Stock Exchange', currency: 'GBP' },
  '.AX': { exchange: 'ASX (Australia)', currency: 'AUD' },
  '.TO': { exchange: 'Toronto Stock Exchange', currency: 'CAD' },
};

const deriveExchange = (ticker: string): { exchange: string; currency: string } => {
  const suffix = Object.keys(EXCHANGE_BY_SUFFIX).find((s) => ticker.endsWith(s));
  return suffix ? EXCHANGE_BY_SUFFIX[suffix] : { exchange: 'NYSE / NASDAQ', currency: 'USD' };
};

type SortKey = 'name' | 'market_cap' | 'enterprise_value' | 'revenue' | 'ebitda' | 'ebitda_margin' | 'ev_revenue' | 'ev_ebitda';

const SORT_LABELS: Record<SortKey, string> = {
  name: 'Société', market_cap: 'Market Cap', enterprise_value: 'EV', revenue: 'Revenue',
  ebitda: 'EBITDA', ebitda_margin: 'Marge EBITDA', ev_revenue: 'EV/Revenue', ev_ebitda: 'EV/EBITDA',
};

// ============================================
// Main Component
// ============================================

export const Comparables: React.FC = () => {
  const [searchParams] = useSearchParams();
  const compSetIdParam = searchParams.get('compSetId');
  // D36 (Tâche Review Produit — Partie F) : positionne une cible/deal précis
  // face au CompSet, si on arrive ici depuis le LBO Calculator avec un deal
  // chargé (lien étendu — voir LBOCalculator.tsx "Voir la table complète").
  const dealIdParam = searchParams.get('dealId');
  const dealId = dealIdParam ? Number(dealIdParam) : null;

  const { data: compSets, isLoading: setsLoading } = useCompSets();
  const [selectedSetId, setSelectedSetId] = useState<number | null>(compSetIdParam ? Number(compSetIdParam) : null);

  const effectiveSetId = selectedSetId ?? (compSets && compSets.length > 0 ? compSets[0].id : null);

  const { data: table, isLoading: tableLoading, isFetching, isError, refetch } = useCompsTable(effectiveSetId);

  const { data: positionedDeal } = useDeal(dealId);
  const { data: dealScenarios } = useLboScenarios(dealId);
  const referenceScenario = useMemo(() => {
    if (!dealScenarios || dealScenarios.length === 0) return null;
    return dealScenarios.find((s) => s.label.toLowerCase().includes('base')) ?? dealScenarios[0];
  }, [dealScenarios]);

  const [sortKey, setSortKey] = useState<SortKey>('ev_ebitda');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const sortedRows = useMemo<CompRow[]>(() => {
    if (!table) return [];
    const rows = [...table.rows];
    rows.sort((a, b) => {
      let va: number | string | null = sortKey === 'name' ? a.name : a[sortKey];
      let vb: number | string | null = sortKey === 'name' ? b.name : b[sortKey];
      // Les valeurs manquantes vont toujours en fin de liste, quel que soit le sens du tri —
      // un trou de donnée ne doit jamais se retrouver "en tête" par accident de tri numérique.
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      if (typeof va === 'string' || typeof vb === 'string') {
        const cmp = String(va).localeCompare(String(vb));
        return sortDir === 'asc' ? cmp : -cmp;
      }
      const cmp = (va as number) - (vb as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return rows;
  }, [table, sortKey, sortDir]);

  const realMultipleCount = table ? table.rows.filter((r) => r.ev_ebitda !== null).length : 0;

  const SortHeader: React.FC<{ sortKeyName: SortKey; align?: 'left' | 'right' }> = ({ sortKeyName, align = 'right' }) => (
    <th
      onClick={() => toggleSort(sortKeyName)}
      className={`py-2.5 px-3 font-semibold cursor-pointer select-none hover:text-cyan-300 transition-colors ${align === 'right' ? 'text-right' : 'text-left'}`}
    >
      <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
        {SORT_LABELS[sortKeyName]}
        {sortKey === sortKeyName ? (
          sortDir === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
        ) : (
          <ArrowUpDown size={11} className="opacity-30" />
        )}
      </span>
    </th>
  );

  return (
    <div className="h-full w-full flex flex-col space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
          <Building2 size={18} className="text-cyan-400" /> Comparables
          <span className="text-[10px] text-slate-500 font-mono border border-slate-800 rounded px-1.5 py-0.5 ml-1">TRADING COMPS</span>
        </h2>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="text-[10px] font-mono px-3 py-1.5 rounded border border-slate-700 bg-slate-800/50 text-slate-400 hover:text-cyan-400 hover:border-cyan-800 transition-all inline-flex items-center gap-1.5 disabled:opacity-50"
        >
          <RefreshCw size={10} className={isFetching ? 'animate-spin' : ''} />
          {isFetching ? 'CHARGEMENT...' : 'ACTUALISER'}
        </button>
      </div>

      {/* D36 — à quoi sert cette page, en clair, avant tout tableau */}
      <div className="rounded-lg border border-cyan-900/40 bg-cyan-950/10 px-4 py-3 text-[11px] text-slate-300 leading-relaxed">
        <p>
          Ces sociétés sont des <strong className="text-cyan-400">leaders cotés du secteur TIC</strong> (Test, Inspection,
          Certification &amp; ingénierie technique — Bureau Veritas, SGS, Intertek, Eurofins…). Elles ne sont
          pas là à titre informatif : leur <strong className="text-white">multiple EV/EBITDA médian</strong>, moins une décote
          taille/illiquidité, donne le <strong className="text-white">multiple d'entrée</strong> utilisé pour valoriser une cible
          non cotée de la même thèse dans le LBO Calculator.
        </p>
        <p className="mt-1.5 font-mono text-cyan-300">
          Médiane comparables − décote taille/illiquidité = multiple d'entrée retenu
          {' '}
          <Link to="/lbo" className="ml-2 inline-flex items-center gap-1 text-cyan-400 hover:text-cyan-300 underline decoration-cyan-800 not-italic">
            Voir dans le LBO Calculator <ExternalLink size={10} />
          </Link>
        </p>
      </div>

      {setsLoading && (
        <div className="border border-slate-800 rounded-lg bg-slate-900/50 p-6 text-sm text-slate-400 font-mono">
          Chargement des comp sets...
        </div>
      )}

      {!setsLoading && (!compSets || compSets.length === 0) && (
        <div className="border border-slate-800 rounded-lg bg-slate-900/50 p-6 text-sm text-slate-400 font-mono">
          Aucun comp set en base.
        </div>
      )}

      {compSets && compSets.length > 1 && (
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-slate-500 uppercase font-bold">Comp set :</span>
          <select
            value={effectiveSetId ?? ''}
            onChange={(e) => setSelectedSetId(Number(e.target.value))}
            className="bg-slate-950 border border-slate-700 rounded py-1.5 px-2 text-xs text-white outline-none focus:border-cyan-500"
          >
            {compSets.map((cs) => (
              <option key={cs.id} value={cs.id}>{cs.name} ({cs.ticker_count})</option>
            ))}
          </select>
        </div>
      )}

      {isError && (
        <div className="border border-rose-900 rounded-lg bg-rose-950/20 p-4 text-sm text-rose-300 font-mono">
          Échec du chargement de la table de comparables — réessayez.
        </div>
      )}

      {tableLoading && !table && (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-slate-500">
            <RefreshCw size={32} className="animate-spin text-cyan-600" />
            <span className="text-xs font-mono">CHARGEMENT DE LA TABLE DE COMPARABLES...</span>
          </div>
        </div>
      )}

      {table && (
        <>
          {/* ── Comp set header ── */}
          <div className="flex flex-wrap items-center gap-4 bg-slate-900/60 border border-slate-800 rounded px-4 py-2.5 text-[11px] font-mono text-slate-400">
            <span className="text-white font-bold">{table.comp_set_name}</span>
            <span className="text-slate-700">|</span>
            <span>Exercice de référence : <b className="text-slate-200">{table.base_year}</b></span>
            <span className="text-slate-700">|</span>
            <span>
              Multiple EV/EBITDA réel : <b className="text-cyan-400">{realMultipleCount}/{table.rows.length}</b> sociétés
            </span>
          </div>

          {/* ── Provenance notice (D18/D19, branchée Tâche B.11) ── */}
          <div className="flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-[10px] text-slate-400">
            <Info size={13} className="mt-0.5 shrink-0 text-cyan-400" />
            <span>
              Survolez un badge de provenance (à côté d'une valeur) pour voir sa source, son exercice et sa méthode de
              calcul — market cap/EV/revenue/EBITDA et les multiples dérivés sont sourcés (D18/D19). Les ratios non
              affichés ici (P/E, ROE, gross margin…) ne portent pas encore de provenance côté API.
            </span>
          </div>

          {/* ── P2 (Partie D) : honnêteté de taille — la médiane du CompSet est un
              ancrage de marché, jamais un multiple directement applicable à une
              cible PME face à des comparables cotés méga/mid-cap. ── */}
          {(() => {
            const marketCaps = table.rows.map((r) => r.market_cap).filter((v): v is number => v != null && v > 0);
            if (marketCaps.length === 0) return null;
            const mcapLo = Math.min(...marketCaps) / 1e9;
            const mcapHi = Math.max(...marketCaps) / 1e9;
            const adjacent = table.rows.filter((r) => r.ticker === 'CLB' || r.ticker === 'MG');
            return (
              <div className="flex flex-col gap-1.5 rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2 text-[10px] text-amber-200">
                <span>
                  <b>Écart de taille</b> — comparables cotés de €{mcapLo.toFixed(1)}Md à €{mcapHi.toFixed(1)}Md de
                  capitalisation
                  {positionedDeal?.target_revenue
                    ? ` vs ${fmtMoney(positionedDeal.target_revenue)}€ de CA pour ${positionedDeal.target_name ?? 'la cible'}`
                    : ''}
                  . La médiane ci-dessous est un <b>ancrage de marché indicatif</b>, jamais un multiple
                  directement applicable avant une décote de taille/illiquidité massive.
                </span>
                {adjacent.length > 0 && (
                  <span>
                    <b>Comparables adjacents (pas TIC pur)</b> :{' '}
                    {adjacent.map((r) => r.name).join(', ')} — services pétroliers / inspection industrielle adjacente.
                  </span>
                )}
              </div>
            );
          })()}

          {/* ── D36 : positionnement d'un deal précis face au CompSet ── */}
          {dealId && positionedDeal && (
            <DealPositionCard
              dealName={positionedDeal.target_name ?? `Deal #${dealId}`}
              entryMultiple={referenceScenario?.entry_multiple ?? null}
              medianEvEbitda={table.stats.median.ev_ebitda ?? null}
              p25={table.stats.p25.ev_ebitda ?? null}
              p75={table.stats.p75.ev_ebitda ?? null}
            />
          )}

          {/* ── Aggregate stats ── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="EV/Revenue médian" value={fmtMult(table.stats.median.ev_revenue)} range={`P25-P75 : ${fmtMult(table.stats.p25.ev_revenue)} – ${fmtMult(table.stats.p75.ev_revenue)}`} accent="cyan" />
            <StatTile label="EV/EBITDA médian" value={fmtMult(table.stats.median.ev_ebitda)} range={`P25-P75 : ${fmtMult(table.stats.p25.ev_ebitda)} – ${fmtMult(table.stats.p75.ev_ebitda)}`} accent="emerald" large />
            <StatTile label="Marge EBITDA médiane" value={fmtPct(table.stats.median.ebitda_margin)} range={`P25-P75 : ${fmtPct(table.stats.p25.ebitda_margin)} – ${fmtPct(table.stats.p75.ebitda_margin)}`} accent="amber" />
            <StatTile label="Marge nette médiane" value={fmtPct(table.stats.median.net_margin)} range={`Moyenne : ${fmtPct(table.stats.mean.net_margin)}`} accent="rose" />
          </div>

          {/* ── Table ── */}
          <Card title="Comparables cotés" subtitle={`${table.rows.length} sociétés — cliquez un en-tête pour trier`} className="flex-1 min-h-[300px]">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-[10px] text-slate-500 border-b border-slate-700 bg-slate-900/50 uppercase tracking-wider">
                    <SortHeader sortKeyName="name" align="left" />
                    <th className="py-2.5 px-3 font-semibold text-left">Place</th>
                    <SortHeader sortKeyName="market_cap" />
                    <SortHeader sortKeyName="enterprise_value" />
                    <SortHeader sortKeyName="revenue" />
                    <SortHeader sortKeyName="ebitda" />
                    <SortHeader sortKeyName="ebitda_margin" />
                    <SortHeader sortKeyName="ev_revenue" />
                    <SortHeader sortKeyName="ev_ebitda" />
                  </tr>
                </thead>
                <tbody className="text-xs font-mono">
                  {sortedRows.map((row, idx) => {
                    const { exchange, currency } = deriveExchange(row.ticker);
                    const hasRealMultiple = row.ev_ebitda !== null;
                    return (
                      <tr
                        key={row.ticker}
                        className={`border-b border-slate-800/50 hover:bg-slate-800/70 transition-colors ${idx % 2 === 0 ? 'bg-slate-900/20' : ''} ${!hasRealMultiple ? 'opacity-60' : ''}`}
                      >
                        <td className="py-2.5 px-3">
                          <div className="text-slate-100 font-bold">{row.name}</div>
                          <div className="text-[10px] text-slate-500">
                            {row.ticker} · {row.country ?? '—'}
                            {row.fiscal_year && <span className="text-slate-600"> · FY{row.fiscal_year}</span>}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-slate-400 text-[10px]">{exchange}<br /><span className="text-slate-600">{currency}</span></td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">
                          {fmtMoney(row.market_cap)}
                          <ProvenanceBadge provenance={row.financial_provenance.market_cap} />
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">
                          {fmtMoney(row.enterprise_value)}
                          <ProvenanceBadge provenance={row.financial_provenance.enterprise_value} />
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">
                          {fmtMoney(row.revenue)}
                          <ProvenanceBadge provenance={row.financial_provenance.revenue} />
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">
                          {fmtMoney(row.ebitda)}
                          <ProvenanceBadge provenance={row.financial_provenance.ebitda} />
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">
                          {fmtPct(row.ebitda_margin)}
                          <ProvenanceBadge provenance={row.financial_provenance.ebitda_margin} />
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">
                          {fmtMult(row.ev_revenue)}
                          <ProvenanceBadge provenance={row.financial_provenance.ev_revenue} />
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums">
                          {hasRealMultiple ? (
                            <span className="text-emerald-400 font-bold">{fmtMult(row.ev_ebitda)}</span>
                          ) : (
                            <span
                              className="text-slate-600 border border-dashed border-slate-700 rounded px-1.5 py-0.5 cursor-help"
                              title="Aucun état financier réel disponible pour ce comparable — jamais comblé par une estimation."
                            >
                              n/d
                            </span>
                          )}
                          <ProvenanceBadge provenance={row.financial_provenance.ev_ebitda} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
};

// ============================================
// Sub-components
// ============================================

interface StatTileProps {
  label: string;
  value: string;
  range: string;
  accent: 'cyan' | 'emerald' | 'amber' | 'rose';
  large?: boolean;
}

const accentMap = {
  cyan: { border: 'border-cyan-900/50', text: 'text-cyan-400', bg: 'bg-cyan-950/20' },
  emerald: { border: 'border-emerald-900/50', text: 'text-emerald-400', bg: 'bg-emerald-950/20' },
  amber: { border: 'border-amber-900/50', text: 'text-amber-400', bg: 'bg-amber-950/20' },
  rose: { border: 'border-rose-900/50', text: 'text-rose-400', bg: 'bg-rose-950/20' },
};

// D36 (Tâche Review Produit — Partie F) : positionne le multiple d'entrée
// dérivé d'un deal précis sur une échelle simple face à la fourchette
// P25-P75 et à la médiane du CompSet — répond concrètement à "à quoi sert
// cette page" en montrant l'usage réel (pas juste une table de sociétés).
interface DealPositionCardProps {
  dealName: string;
  entryMultiple: number | null;
  medianEvEbitda: number | null;
  p25: number | null;
  p75: number | null;
}

const DealPositionCard: React.FC<DealPositionCardProps> = ({ dealName, entryMultiple, medianEvEbitda, p25, p75 }) => {
  if (entryMultiple === null || medianEvEbitda === null || p25 === null || p75 === null) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3 text-[11px] text-slate-500 flex items-center gap-2">
        <Target size={13} className="text-slate-600" />
        Aucun scénario LBO avec multiple d'entrée dérivé pour « {dealName} » — positionnement non disponible.
      </div>
    );
  }

  // Échelle visuelle bornée [min(p25, entry) - marge, max(p75, entry) + marge]
  const low = Math.min(p25, entryMultiple) * 0.85;
  const high = Math.max(p75, entryMultiple) * 1.15;
  const toPct = (v: number) => Math.max(2, Math.min(98, ((v - low) / (high - low)) * 100));

  return (
    <div className="rounded-lg border border-cyan-900/50 bg-cyan-950/10 px-4 py-3">
      <div className="flex items-center gap-2 mb-3">
        <Target size={13} className="text-cyan-400" />
        <span className="text-[11px] font-bold text-white">Positionnement — {dealName}</span>
        <span className="ml-auto text-[11px] font-mono text-cyan-400 font-bold">{entryMultiple.toFixed(2)}x EV/EBITDA (multiple d'entrée retenu)</span>
      </div>
      <div className="relative h-8">
        {/* Bande P25-P75 */}
        <div
          className="absolute top-3 h-2 bg-slate-700/60 rounded"
          style={{ left: `${toPct(p25)}%`, width: `${toPct(p75) - toPct(p25)}%` }}
        />
        {/* Médiane */}
        <div className="absolute top-1 h-4 w-0.5 bg-slate-400" style={{ left: `${toPct(medianEvEbitda)}%` }} />
        <div className="absolute top-6 text-[8px] text-slate-500 -translate-x-1/2" style={{ left: `${toPct(medianEvEbitda)}%` }}>
          médiane {medianEvEbitda.toFixed(1)}x
        </div>
        {/* Marqueur du deal */}
        <div className="absolute top-0 h-6 w-0.5 bg-cyan-400" style={{ left: `${toPct(entryMultiple)}%` }} />
        <div
          className="absolute -top-0.5 w-2.5 h-2.5 rounded-full bg-cyan-400 border-2 border-slate-950 -translate-x-1/2"
          style={{ left: `${toPct(entryMultiple)}%` }}
        />
      </div>
      <p className="text-[10px] text-slate-500 mt-2">
        Le multiple d'entrée de ce deal ({entryMultiple.toFixed(2)}x) est dérivé de cette médiane
        (§ chaîne de calibrage, voir Méthodologie) moins une décote taille/illiquidité — jamais fixé
        arbitrairement.
      </p>
    </div>
  );
};

const StatTile: React.FC<StatTileProps> = ({ label, value, range, accent, large }) => {
  const a = accentMap[accent];
  return (
    <div className={`rounded border ${a.border} ${a.bg} bg-slate-900 p-3 flex flex-col gap-1`}>
      <div className="text-[9px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`${large ? 'text-2xl' : 'text-lg'} font-mono font-bold ${a.text} tabular-nums tracking-tight`}>
        {value}
      </div>
      <div className="text-[9px] text-slate-600 font-mono">{range}</div>
    </div>
  );
};
