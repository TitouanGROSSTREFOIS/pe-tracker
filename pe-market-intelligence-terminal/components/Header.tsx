import React from 'react';
import { MarketIndex } from '../types';
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';

interface HeaderProps {
  indices: MarketIndex[];
  // D46 (Tâche Finalisation, Partie 5) : true si le dernier appel à
  // /api/market-indices a échoué (le ticker peut alors afficher une valeur
  // périmée, ou rien si aucun chargement n'a jamais réussi) — jamais déduit
  // silencieusement de indices.length, qui ne distingue pas "vide car en
  // échec" de "vide car le marché n'a simplement aucun indice à montrer".
  stale?: boolean;
}

export const Header: React.FC<HeaderProps> = ({ indices, stale = false }) => {
  const repeatedIndices = Array(15).fill(indices).flat();

  return (
    <header className="w-full bg-slate-950 border-b border-slate-800 h-12 flex items-center sticky top-0 z-50 shadow-lg">
      {/* Left Logo Section */}
      <div className="px-6 bg-slate-900/80 h-full flex items-center border-r border-slate-700/50 shrink-0">
        <span className="font-bold text-cyan-400 text-sm tracking-widest">⚡ TERMINAL</span>
      </div>

      {/* Marquee Container */}
      <div className="flex-1 h-full overflow-hidden relative group">
        {indices.length === 0 && (
          <div className="h-full flex items-center px-6 gap-2 text-xs font-mono text-amber-400">
            <AlertTriangle size={13} />
            <span>{stale ? 'Données de marché indisponibles — nouvelle tentative dans 60s' : 'Chargement des données de marché…'}</span>
          </div>
        )}
        {indices.length > 0 && (
          <div className="ticker-container h-full">
            <div className="ticker-content h-full flex items-center whitespace-nowrap">
              {repeatedIndices.map((idx, i) => (
                <div
                  key={`${idx.symbol}-${i}`}
                  className="ticker-item flex items-center px-6 h-full border-r border-slate-800/30 hover:bg-slate-800/20 transition-colors shrink-0"
                >
                  <span className="text-xs font-bold text-slate-300 min-w-fit">{idx.symbol}</span>
                  <span className="text-xs font-mono text-white ml-2 min-w-fit">
                    {idx.value.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </span>
                  <div
                    className={`flex items-center text-xs font-mono ml-2 min-w-fit ${
                      idx.change >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {idx.change > 0 ? (
                      <TrendingUp size={12} className="mr-1" />
                    ) : idx.change < 0 ? (
                      <TrendingDown size={12} className="mr-1" />
                    ) : (
                      <Minus size={12} className="mr-1" />
                    )}
                    {idx.change > 0 ? '+' : ''}{idx.changePercent.toFixed(2)}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Right Status Section */}
      <div className="px-4 bg-slate-900/80 h-full flex items-center border-l border-slate-700/50 shrink-0 gap-3">
        <div className="flex flex-col items-end">
          <span className="text-[9px] text-slate-500 font-mono leading-none">
            {new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
          </span>
          <span className="text-[8px] text-slate-600 font-mono leading-none mt-0.5">
            {indices.filter(i => i.value > 0).length}/{indices.length} MKT
          </span>
        </div>
        <div className="flex items-center gap-1.5" title={stale ? 'Dernier appel à /api/market-indices en échec' : undefined}>
          <span className={`text-[10px] font-bold hidden sm:inline ${stale ? 'text-amber-400' : 'text-emerald-400'}`}>
            {stale ? 'DEGRADED' : 'LIVE'}
          </span>
          <div className={`w-2 h-2 rounded-full shadow-lg ${
            stale
              ? 'bg-amber-500 shadow-amber-500/50'
              : 'bg-emerald-500 animate-pulse shadow-emerald-500/50'
          }`}></div>
        </div>
      </div>

      <style>{`
        .ticker-container {
          width: 100%;
          overflow: hidden;
        }

        .ticker-content {
          animation: marquee 120s linear infinite;
          width: fit-content;
        }

        .ticker-container:hover .ticker-content {
          animation-play-state: paused;
        }

        @keyframes marquee {
          0% {
            transform: translateX(0);
          }
          100% {
            transform: translateX(-50%);
          }
        }
      `}</style>
    </header>
  );
};
