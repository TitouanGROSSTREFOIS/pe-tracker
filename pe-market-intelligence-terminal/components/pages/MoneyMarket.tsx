import React from 'react';
import { MoneyMarketData } from '../../services/apiService';
import { TrendingUp, TrendingDown, DollarSign, Building2, Zap } from 'lucide-react';
import { useMoneyMarketRates } from '../../hooks/useQueries';

export const MoneyMarket: React.FC = () => {
  const { data, isLoading: loading, error: queryError } = useMoneyMarketRates();
  const error = queryError ? (queryError instanceof Error ? queryError.message : 'Failed to load') : null;

  const getTrendIcon = (change: number) => {
    if (change > 0) return <TrendingUp size={14} className="text-rose-500" />;
    if (change < 0) return <TrendingDown size={14} className="text-emerald-500" />;
    return <Zap size={14} className="text-slate-500" />;
  };

  const getTrendColor = (change: number) => {
    if (change > 0) return 'text-rose-400';
    if (change < 0) return 'text-emerald-400';
    return 'text-slate-400';
  };

  if (loading) return <div className="text-slate-400 p-6">Chargement des données money market...</div>;
  if (error) return <div className="text-rose-400 p-6">Erreur: {error}</div>;
  if (!data) return <div className="text-slate-400 p-6">Aucune donnée disponible</div>;

  return (
    <div className="h-full w-full flex flex-col space-y-6 overflow-y-auto p-6">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
          <span className="text-cyan-500">///</span> Money Market & Rates
        </h2>
        <span className="text-xs text-slate-500 font-mono border border-slate-800 rounded px-2 py-0.5">LIVE DATA</span>
      </div>

      {/* Légende — sources et convention de couleur (D38) */}
      <div className="rounded-lg border border-cyan-900/40 bg-cyan-950/10 px-4 py-3 text-[11px] text-slate-300 leading-relaxed">
        <p>
          Toutes les valeurs viennent de l'API <strong>FRED</strong>, mise en cache serveur 60 minutes (voir date de
          dernier rafraîchissement en pied de page). <span className="text-emerald-400 font-mono">Vert</span> = taux en
          baisse (financement LBO moins cher) ; <span className="text-rose-400 font-mono">Rouge</span> = taux en hausse
          (financement plus cher) — variation réelle vs la dernière valeur distincte précédente, jamais une constante.
        </p>
        <p className="mt-1.5 text-slate-400">
          Badge source : <span className="font-mono text-slate-300">FRED</span> = observation brute de la série ·{' '}
          <span className="font-mono text-amber-300">FRED (dérivé)</span> = calculée depuis une série FRED réelle via
          un spread de marché documenté (Euribor 6M/12M — aucune série FRED directe fiable identifiée pour ces tenors,
          dérivés du 3M réel + spread constant) · <span className="font-mono text-slate-300">Cache</span> = repli
          statique (FRED indisponible).
        </p>
      </div>

      {/* Euribor Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <DollarSign size={16} className="text-cyan-500" />
          <h3 className="font-bold text-slate-300 uppercase text-sm">Euribor Benchmark Rates</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {data.euribor.map((rate) => (
            <div key={rate.tenor} className="bg-slate-900/50 border border-slate-800 rounded p-4 space-y-2">
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-bold text-cyan-400 text-sm">{rate.name}</p>
                  <p className="text-xs text-slate-500">{rate.tenor}</p>
                </div>
                <span className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-400">{rate.source}</span>
              </div>
              <div className="flex justify-between items-end pt-2 border-t border-slate-700">
                <div>
                  <p className="text-2xl font-bold text-white">{rate.value.toFixed(2)}<span className="text-lg text-slate-500">%</span></p>
                  <div className={`flex items-center gap-1 text-xs ${getTrendColor(rate.change)}`}>
                    {getTrendIcon(rate.change)}
                    {rate.change > 0 ? '+' : ''}{rate.change.toFixed(2)}%
                  </div>
                </div>
              </div>
              <p className="text-[10px] text-slate-500 pt-1">{new Date(rate.lastUpdate).toLocaleDateString('fr-FR')}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Risk-Free Rates Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-emerald-500" />
          <h3 className="font-bold text-slate-300 uppercase text-sm">Risk-Free Overnight Rates</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.riskFree.map((rate) => (
            <div key={rate.name} className="bg-slate-900/50 border border-slate-800 rounded p-4">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <p className="font-bold text-emerald-400 text-sm">{rate.name}</p>
                  <p className="text-xs text-slate-500">{rate.tenor}</p>
                </div>
                <span className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-400">{rate.source}</span>
              </div>
              <div className="flex justify-between items-end">
                <div>
                  <p className="text-3xl font-bold text-white">{rate.value.toFixed(2)}<span className="text-lg text-slate-500">%</span></p>
                  <div className={`flex items-center gap-1 text-xs ${getTrendColor(rate.change)}`}>
                    {getTrendIcon(rate.change)}
                    {rate.change > 0 ? '+' : ''}{rate.change.toFixed(2)}%
                  </div>
                </div>
              </div>
              <p className="text-[10px] text-slate-500 pt-1">{new Date(rate.lastUpdate).toLocaleDateString('fr-FR')}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Government Bonds Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Building2 size={16} className="text-yellow-500" />
          <h3 className="font-bold text-slate-300 uppercase text-sm">Government Bond Yields (10Y)</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {data.governmentBonds.map((rate) => (
            <div key={rate.name} className="bg-slate-900/50 border border-slate-800 rounded p-4 space-y-2">
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-bold text-yellow-400 text-sm">{rate.name}</p>
                  <p className="text-xs text-slate-500">{rate.tenor}</p>
                </div>
                <span className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-400">{rate.source}</span>
              </div>
              <div className="flex justify-between items-end pt-2 border-t border-slate-700">
                <div>
                  <p className="text-2xl font-bold text-white">{rate.value.toFixed(2)}<span className="text-lg text-slate-500">%</span></p>
                  <div className={`flex items-center gap-1 text-xs ${getTrendColor(rate.change)}`}>
                    {getTrendIcon(rate.change)}
                    {rate.change > 0 ? '+' : ''}{rate.change.toFixed(2)}%
                  </div>
                </div>
              </div>
              <p className="text-[10px] text-slate-500 pt-1">{new Date(rate.lastUpdate).toLocaleDateString('fr-FR')}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Spreads Analysis */}
      <div className="space-y-3">
        <h3 className="font-bold text-slate-300 uppercase text-sm">Key Spreads</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {(() => {
            const euribor3m = data.euribor.find(r => r.tenor === '3M');
            const sofr = data.riskFree.find(r => r.name.includes('SOFR'));
            const bund = data.governmentBonds.find(r => r.name.includes('Bund'));
            const oat = data.governmentBonds.find(r => r.name.includes('OAT'));
            const ust = data.governmentBonds.find(r => r.name.includes('Treasury'));
            return (
              <>
                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                  <p className="text-xs text-slate-500 mb-2">Euribor 3M - SOFR</p>
                  <p className="text-2xl font-bold text-cyan-400">
                    {euribor3m && sofr ? (euribor3m.value - sofr.value).toFixed(2) : '—'}%
                  </p>
                  <p className="text-xs text-slate-500 mt-2">€/$ Basis</p>
                </div>

                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                  <p className="text-xs text-slate-500 mb-2">OAT 10Y - Bund 10Y</p>
                  <p className="text-2xl font-bold text-yellow-400">
                    {oat && bund ? ((oat.value - bund.value) * 100).toFixed(0) : '—'}<span className="text-sm text-slate-500">bps</span>
                  </p>
                  <p className="text-xs text-slate-500 mt-2">France-Germany Spread</p>
                </div>

                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                  <p className="text-xs text-slate-500 mb-2">US Treasury - Bund 10Y</p>
                  <p className="text-2xl font-bold text-emerald-400">
                    {ust && bund ? ((ust.value - bund.value) * 100).toFixed(0) : '—'}<span className="text-sm text-slate-500">bps</span>
                  </p>
                  <p className="text-xs text-slate-500 mt-2">Transatlantic Spread</p>
                </div>
              </>
            );
          })()}
        </div>
      </div>

      {/* Footer */}
      <div className="pt-4 border-t border-slate-800 text-xs text-slate-500 space-y-1">
        <p>🔄 Data updated every 60 minutes from FRED API</p>
        <p>📊 All rates in percentage (%)</p>
        <p>Last refresh: {new Date(data.timestamp).toLocaleString('fr-FR')}</p>
      </div>
    </div>
  );
};
