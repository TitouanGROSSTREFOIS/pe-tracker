import React from 'react';
import { DealTracker } from '../DealTracker';
import { DryPowderChart } from '../DryPowderChart';
import { ExitRoutesChart } from '../ExitRoutesChart';
import { Layers, Wallet, LogOut, Activity } from 'lucide-react';
import { useDeals, useMacroIndicators, useCentralBankRates } from '../../hooks/useQueries';

// NOTE (D3 + règle anti-invention) : la section "Fund Performance Intelligence"
// et la tuile "Portfolio KPIs" (AUM, IRR, MOIC, DPI) ont été retirées. Elles
// consommaient /api/funds et /api/portfolio-summary côté Express, tous deux
// calculés sur des données de fonds 100% fictives (aucun modèle Fund n'existe
// côté FastAPI). Aucune donnée de remplacement n'a été inventée.

export const MarketIntelligence: React.FC = () => {
  const { data: deals = [], isLoading, error } = useDeals();
  const { data: macroIndicators = [] } = useMacroIndicators();
  const { data: centralBanks = [] } = useCentralBankRates();

  return (
    <div className="flex flex-col gap-6 w-full">
      {/* PE Market Pulse — Key Metrics Bar */}
      <div className="bg-slate-900/50 border border-slate-800/50 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={16} className="text-cyan-500" />
          <h3 className="text-sm font-bold text-white uppercase tracking-tight">PE Market Pulse</h3>
          <span className="text-[10px] text-slate-500 font-mono border border-slate-800 rounded px-1.5 py-0.5">LIVE</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
          {centralBanks.slice(0, 2).map((bank) => (
            <div key={bank.name} className="bg-slate-800/50 rounded p-3 border border-slate-700/50">
              <p className="text-[10px] text-slate-500 uppercase">{bank.name} Rate</p>
              <p className="text-lg font-bold text-cyan-400 font-mono">{bank.rate.toFixed(2)}%</p>
              {bank.trend && <p className="text-[10px] text-slate-500 capitalize">{bank.trend}</p>}
            </div>
          ))}
          {macroIndicators.slice(0, 4).map((ind) => (
            <div key={ind.name} className="bg-slate-800/50 rounded p-3 border border-slate-700/50">
              <p className="text-[10px] text-slate-500 uppercase truncate">{ind.name.replace('US ', '')}</p>
              <p className="text-lg font-bold text-cyan-400 font-mono">{typeof ind.value === 'number' ? ind.value.toFixed(1) : ind.value}{ind.unit === 'bps' ? <span className="text-xs text-slate-500">bps</span> : ind.unit === '%' ? '%' : ''}</p>
              <p className={`text-[10px] ${ind.change < 0 ? 'text-emerald-500' : ind.change > 0 ? 'text-rose-500' : 'text-slate-500'}`}>
                {ind.change > 0 ? '+' : ''}{ind.change || '—'}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Top Row: Global LBO Tracker */}
      <section className="w-full">
        <div className="flex items-center mb-3 space-x-2 text-cyan-500">
          <Layers size={18} />
          <h2 className="text-lg font-bold tracking-tight text-white uppercase">Deal Flow</h2>
        </div>
        {/* min-h (pas h) : Tâche B.6, le panneau détail affiche désormais
            Revenue/EBITDA/EV + badges de provenance, contenu variable qui ne
            doit plus être tronqué sous une hauteur fixe (constaté visuellement
            à la relecture — les nouvelles lignes étaient invisibles, recouvertes
            par la section suivante). */}
        <div className="min-h-[400px]">
          <DealTracker deals={deals} />
        </div>
      </section>

      {/* Third Row: Dry Powder */}
      <section className="w-full">
        <div className="flex items-center mb-3 space-x-2 text-cyan-500">
            <Wallet size={18} />
            <h2 className="text-lg font-bold tracking-tight text-white uppercase">Capital Overhang</h2>
        </div>
        <div>
            <DryPowderChart />
        </div>
      </section>

      {/* Bottom Row: Exit Routes Analysis */}
      <section className="w-full mb-8">
        <div className="flex items-center mb-3 space-x-2 text-amber-500">
            <LogOut size={18} />
            <h2 className="text-lg font-bold tracking-tight text-white uppercase">Macro Trends: Exit Routes</h2>
        </div>
        <div>
            <ExitRoutesChart />
        </div>
      </section>
    </div>
  );
};