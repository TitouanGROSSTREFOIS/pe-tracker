import React from 'react';
import { Card } from '../ui/Card';
import { TrendingUp, TrendingDown, Minus, ExternalLink } from 'lucide-react';
import { useNewsSignals } from '../../hooks/useQueries';

interface NewsArticle {
  id: string;
  title: string;
  source: string;
  publishedAt: string;
  url: string;
  description: string;
  sentiment: 'Bullish' | 'Bearish' | 'Neutral';
  category: string;
}

// D33 (Tâche Review Produit — Partie C) : 3 catégories thématiques alignées
// sur la thèse, chacune portée par sa propre requête NewsAPI ciblée côté
// backend (voir backend/services/newsService.ts) — la catégorie n'est plus
// devinée après coup par mots-clés.
const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  'TIC & Réglementation': 'Test, Inspection, Certification & réglementation construction/industrie',
  'Macro & Financement': 'Taux, crédit, conditions de financement LBO',
  'Deal Activity PE': 'M&A / LBO mid-market France & Europe',
};

export const NewsSignals: React.FC = () => {
  const categories = ['TIC & Réglementation', 'Macro & Financement', 'Deal Activity PE'];
  const { data: signals = [], isLoading: loading, error: queryError } = useNewsSignals();
  const error = queryError ? (queryError instanceof Error ? queryError.message : 'Failed to load') : null;

  const getSentimentIcon = (sentiment: string) => {
    switch (sentiment) {
      case 'Bullish': return <TrendingUp size={14} className="text-emerald-500" />;
      case 'Bearish': return <TrendingDown size={14} className="text-rose-500" />;
      default: return <Minus size={14} className="text-slate-500" />;
    }
  };

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'Bullish': return 'text-emerald-400 bg-emerald-950/30 border-emerald-900/50';
      case 'Bearish': return 'text-rose-400 bg-rose-950/30 border-rose-900/50';
      default: return 'text-slate-400 bg-slate-800/50 border-slate-700';
    }
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString('fr-FR', { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div className="h-full w-full flex flex-col space-y-6">
       <div>
            <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
                    <span className="text-cyan-500">///</span> News & Signals
                </h2>
                <span className="text-xs text-slate-500 font-mono border border-slate-800 rounded px-2 py-0.5">LIVE FEED</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
                Flux organisé par thème pertinent pour la thèse TIC — pas une liste de mots-clés PE génériques.
            </p>
       </div>

        {loading && <p className="text-slate-400">Chargement des données...</p>}
        {error && <p className="text-rose-400">Erreur: {error}</p>}

        <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-4 min-h-0 overflow-hidden">
            {categories.map((category) => (
                <div key={category} className="flex flex-col h-full min-h-0 bg-slate-900/50 border border-slate-800 rounded-sm">
                    {/* Column Header */}
                    <div className="p-3 border-b border-slate-800 bg-slate-900 sticky top-0 z-10">
                        <div className="flex justify-between items-center">
                            <h3 className="font-bold text-sm text-slate-200 uppercase tracking-wider">{category}</h3>
                            <span className="text-[10px] font-mono text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">
                                {signals.filter(n => n.category === category).length}
                            </span>
                        </div>
                        <p className="text-[10px] text-slate-500 mt-1">{CATEGORY_DESCRIPTIONS[category]}</p>
                    </div>

                    {/* Scrollable Column Content */}
                    <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar">
                        {signals.filter(n => n.category === category).map((news) => (
                            <a 
                              key={news.id} 
                              href={news.url} 
                              target="_blank" 
                              rel="noopener noreferrer"
                              className="bg-slate-950 border border-slate-800 p-3 rounded hover:border-slate-600 transition-colors cursor-pointer group shadow-sm block"
                            >
                                <div className="flex justify-between items-start mb-2">
                                    <span className="text-[10px] font-bold text-cyan-600 uppercase tracking-wide">{news.source}</span>
                                    <div className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${getSentimentColor(news.sentiment)}`}>
                                        {getSentimentIcon(news.sentiment)}
                                        <span className="font-medium">{news.sentiment}</span>
                                    </div>
                                </div>
                                
                                <h4 className="text-sm font-semibold text-slate-200 leading-snug mb-3 group-hover:text-cyan-400 transition-colors line-clamp-2">
                                    {news.title}
                                </h4>
                                
                                <p className="text-xs text-slate-400 line-clamp-2 mb-2">
                                    {news.description}
                                </p>
                                
                                <div className="flex justify-between items-center border-t border-slate-900 pt-2 mt-2">
                                    <span className="text-[10px] text-slate-500 font-mono">{formatDate(news.publishedAt)}</span>
                                    <ExternalLink size={12} className="text-slate-600 group-hover:text-slate-400" />
                                </div>
                            </a>
                        ))}
                    </div>
                </div>
            ))}
        </div>
        <style>{`
            .custom-scrollbar::-webkit-scrollbar {
                width: 4px;
            }
            .custom-scrollbar::-webkit-scrollbar-track {
                background: #0f172a; 
            }
            .custom-scrollbar::-webkit-scrollbar-thumb {
                background: #334155; 
                border-radius: 2px;
            }
        `}</style>
    </div>
  );
};