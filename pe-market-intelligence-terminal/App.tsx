import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { MarketIndex } from './types';
import { MarketIntelligence } from './components/pages/MarketIntelligence';
import { DealSourcing } from './components/pages/DealSourcing';
import { DealPipeline } from './components/pages/DealPipeline';
import { NewsSignals } from './components/pages/NewsSignals';
import { LBOCalculator } from './components/pages/LBOCalculator';
import { CreditMacro } from './components/pages/CreditMacro';
import { MoneyMarket } from './components/pages/MoneyMarket';
import { BuyAndBuild } from './components/pages/BuyAndBuild';
import { Methodology } from './components/pages/Methodology';
import { Comparables } from './components/pages/Comparables';

const App: React.FC = () => {
  const [indices, setIndices] = useState<MarketIndex[]>([]);
  // D46 (Tâche Finalisation, Partie 5) : distinct de `indices` — un échec
  // réseau/API ne doit jamais effacer la dernière valeur connue (déjà le cas
  // avant ce correctif : setIndices n'est appelé que dans le bloc try) ni
  // rester silencieux (le bandeau affichait "LIVE" en continu même en échec,
  // constaté 3/10 chargements pendant la revue). `indicesStale` distingue
  // "jamais chargé" (indices vides, aucune tentative réussie) de "chargé une
  // fois puis en échec depuis" (indices non vides mais périmés) pour que
  // Header.tsx puisse afficher un état honnête dans les deux cas.
  const [indicesStale, setIndicesStale] = useState(false);

  useEffect(() => {
    const fetchIndices = async () => {
      try {
        const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001/api';
        const response = await fetch(`${API_URL}/market-indices`);
        if (!response.ok) {
          throw new Error(`market-indices HTTP ${response.status}`);
        }
        const data = await response.json();
        if (!Array.isArray(data)) {
          throw new Error('market-indices: unexpected response shape');
        }
        setIndices(data);
        setIndicesStale(false);
      } catch (error) {
        console.error("Failed to fetch indices:", error);
        setIndicesStale(true);
      }
    };

    fetchIndices();
    const interval = setInterval(fetchIndices, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-cyan-500/30 flex">
      
      {/* Fixed Sidebar */}
      <Sidebar />

      {/* Main Content Wrapper - Shifted right by Sidebar width */}
      <div className="flex-1 flex flex-col ml-64 min-w-0">
        
        {/* Sticky Ticker */}
        <Header indices={indices} stale={indicesStale} />

        {/* Dynamic Content Area */}
        <main className="flex-1 p-4 lg:p-8 overflow-y-auto max-w-[1920px] mx-auto w-full">
          <Routes>
            <Route path="/" element={<MarketIntelligence />} />
            <Route path="/sourcing" element={<DealSourcing />} />
            <Route path="/pipeline" element={<DealPipeline />} />
            <Route path="/news" element={<NewsSignals />} />
            <Route path="/lbo" element={<LBOCalculator />} />
            <Route path="/comparables" element={<Comparables />} />
            <Route path="/buy-and-build" element={<BuyAndBuild />} />
            <Route path="/credit" element={<CreditMacro />} />
            <Route path="/money-market" element={<MoneyMarket />} />
            <Route path="/methodology" element={<Methodology />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          
          {/* Global Footer */}
          <footer className="border-t border-slate-800/50 mt-12 pt-6 pb-8 text-center text-[10px] text-slate-600 font-mono">
            <p className="mb-2">LIVE MARKET DATA: YAHOO FINANCE • FRED API • NEWSAPI. INDICES DELAYED 15 MIN.</p>
            <p>© 2025 PE INTELLIGENCE TERMINAL. CONFIDENTIAL & PROPRIETARY.</p>
          </footer>
        </main>
      </div>

    </div>
  );
};

export default App;