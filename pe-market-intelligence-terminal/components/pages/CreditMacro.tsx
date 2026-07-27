import React from 'react';
import { Card } from '../ui/Card';
import { CentralBankRate, MacroIndicator, YieldCurvePoint, CreditIndicator } from '../../services/apiService';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ScatterChart, Scatter, Cell } from 'recharts';
import { Activity, TrendingUp, TrendingDown, AlertTriangle, Zap, DollarSign } from 'lucide-react';
import {
    useCentralBankRates, useMacroIndicators, useYieldCurve, useCreditStress,
    useCentralBankRatesMeta, useMacroIndicatorsMeta, useYieldCurveMeta, useCreditStressMeta,
} from '../../hooks/useQueries';

export const CreditMacro: React.FC = () => {
    const { data: centralBanks = [], isLoading: loadingRates } = useCentralBankRates();
    const { data: macroIndicators = [], isLoading: loadingMacro } = useMacroIndicators();
    const { data: yieldCurve = [], isLoading: loadingYield } = useYieldCurve();
    const { data: creditStress = [], isLoading: loadingCredit } = useCreditStress();

    const { data: metaRates } = useCentralBankRatesMeta();
    const { data: metaMacro } = useMacroIndicatorsMeta();
    const { data: metaYield } = useYieldCurveMeta();
    const { data: metaCredit } = useCreditStressMeta();

    const loading = loadingRates || loadingMacro || loadingYield || loadingCredit;
    const error = null; // React Query handles retries; errors are shown per-query if needed

    // D38 : badge d'origine agrégé — si UNE SEULE des 4 sources n'est pas
    // 'fred' (clé API absente, erreur réseau...), on l'affiche honnêtement
    // plutôt que d'afficher un "LIVE DATA" générique qui mentirait pour
    // cette source-là.
    const metaSources = [metaRates?.source, metaMacro?.source, metaYield?.source, metaCredit?.source];
    const allLive = metaSources.every(s => s === 'fred');
    const anyLive = metaSources.some(s => s === 'fred');

    const getSentimentColor = (bank: any) => {
        if (bank.trend === 'hawkish') return 'bg-rose-900/40 text-rose-400 border-rose-800';
        if (bank.trend === 'dovish') return 'bg-emerald-900/40 text-emerald-400 border-emerald-800';
        return 'bg-slate-800 text-slate-400 border-slate-700';
    };

    const getSentimentLabel = (bank: any) => {
        return bank.trend ? bank.trend.charAt(0).toUpperCase() + bank.trend.slice(1) : 'Hold';
    };

    const formatDate = (d?: string) => {
        if (!d) return '—';
        const parsed = new Date(d);
        return isNaN(parsed.getTime()) ? d : parsed.toLocaleDateString('fr-FR');
    };

    const getRiskColor = (level: string) => {
        if (level === 'High') return 'text-rose-400 bg-rose-950/20';
        if (level === 'Medium') return 'text-yellow-400 bg-yellow-950/20';
        return 'text-emerald-400 bg-emerald-950/20';
    };

    const getTrendIcon = (trend: string) => {
        if (trend === 'improving') return <TrendingDown size={14} className="text-emerald-500" />;
        if (trend === 'deteriorating') return <TrendingUp size={14} className="text-rose-500" />;
        return <TrendingUp size={14} className="text-slate-500" />;
    };

    if (loading) return <div className="text-slate-400 p-6">Chargement des données macro...</div>;
    if (error) return <div className="text-rose-400 p-6">Erreur: {error}</div>;

    return (
        <div className="h-full w-full flex flex-col space-y-6 overflow-y-auto p-6">
            <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
                    <span className="text-cyan-500">///</span> Credit & Macro Dashboard
                </h2>
                {allLive ? (
                    <span className="text-xs text-emerald-400 font-mono border border-emerald-900 rounded px-2 py-0.5">LIVE — FRED</span>
                ) : anyLive ? (
                    <span className="text-xs text-amber-400 font-mono border border-amber-900 rounded px-2 py-0.5">PARTIEL — une source en repli</span>
                ) : (
                    <span className="text-xs text-rose-400 font-mono border border-rose-900 rounded px-2 py-0.5">DONNÉES DE REPLI (FRED indisponible)</span>
                )}
            </div>

            {/* Légende — logique des verdicts qualitatifs (D38) */}
            <div className="rounded-lg border border-cyan-900/40 bg-cyan-950/10 px-4 py-3 text-[11px] text-slate-300 leading-relaxed">
                <p>
                    Toutes les valeurs viennent de l'API <strong>FRED</strong> (Federal Reserve Economic Data), interrogée en
                    direct à chaque chargement (pas de cache serveur ici — le rafraîchissement client est fixé à 10 min).
                    Les étiquettes qualitatives ci-dessous ne sont jamais des constantes : elles sont recalculées à partir
                    de la variation réelle entre la dernière valeur publiée et la dernière valeur distincte précédente.
                </p>
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 font-mono text-slate-400">
                    <span><b className="text-rose-400">Hawkish</b> / <b className="text-emerald-400">Dovish</b> / Hold : variation ≥ ±5bps du taux directeur (sinon Hold)</span>
                    <span><b className="text-rose-400">High</b> / <b className="text-yellow-400">Medium</b> / <b className="text-emerald-400">Low</b> : valeur / seuil de stress ≥85% / ≥50% / &lt;50%</span>
                    <span><TrendingDown size={10} className="inline text-emerald-500" /> improving / <TrendingUp size={10} className="inline text-rose-500" /> deteriorating : sens de la dernière variation (baisse = détente, hausse = tension)</span>
                    <span>BoJ : aucune série FRED fiable à jour identifiée — valeur statique signalée, jamais présentée comme live</span>
                </div>
            </div>

            {/* Central Bank Rates Section */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {centralBanks.map((bank) => (
                    <div key={bank.name} className="bg-slate-900/50 border border-slate-800 rounded p-4 space-y-3">
                        <div className="flex justify-between items-start">
                            <div>
                                <h3 className="font-bold text-cyan-400">{bank.name}</h3>
                                <p className="text-xs text-slate-500">{bank.region || ''}</p>
                            </div>
                            <span className={`text-xs px-2 py-1 rounded border ${getSentimentColor(bank)}`}>
                                {getSentimentLabel(bank)}
                            </span>
                        </div>
                        
                        <div className="space-y-1">
                            <div className="flex justify-between">
                                <span className="text-sm text-slate-400">Rate:</span>
                                <span className="text-lg font-bold text-white">{bank.rate.toFixed(2)}%</span>
                            </div>
                            {bank.previousRate != null && (
                                <div className="flex justify-between items-center">
                                    <span className="text-sm text-slate-400">Previous:</span>
                                    <span className="text-sm text-slate-500">{bank.previousRate.toFixed(2)}%</span>
                                </div>
                            )}
                            {bank.change != null && (
                                <div className="flex justify-between items-center">
                                    <span className="text-sm text-slate-400">Change:</span>
                                    <span className={bank.change < 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                        {bank.change > 0 ? '+' : ''}{bank.change.toFixed(2)}%
                                    </span>
                                </div>
                            )}
                            <div className="flex justify-between items-center text-xs text-slate-500 pt-2 border-t border-slate-800">
                                <span>Màj : {formatDate(bank.lastUpdate)}</span>
                                {bank.dataSource === 'static' ? (
                                    <span className="text-amber-500 font-mono text-[10px]">STATIQUE</span>
                                ) : bank.dataSource === 'fallback' ? (
                                    <span className="text-rose-500 font-mono text-[10px]">REPLI</span>
                                ) : (
                                    <span className="text-emerald-500 font-mono text-[10px]">FRED</span>
                                )}
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Macro Indicators */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-slate-900/50 border border-slate-800 rounded p-4 space-y-3">
                    <h3 className="font-bold text-slate-200 uppercase text-sm">Key Macro Indicators</h3>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                        {macroIndicators.map((indicator) => (
                            <div key={indicator.name} className="flex justify-between items-center p-2 bg-slate-800/30 rounded border border-slate-700/50">
                                <div className="flex-1">
                                    <p className="text-xs font-semibold text-slate-300">{indicator.name}</p>
                                    <p className="text-[10px] text-slate-500">{indicator.lastUpdate}</p>
                                </div>
                                <div className="text-right">
                                    <div className="text-sm font-bold text-cyan-400">{indicator.value}{indicator.unit}</div>
                                    <div className={indicator.change < 0 ? 'text-emerald-400 text-xs' : 'text-rose-400 text-xs'}>
                                        {indicator.change > 0 ? '+' : ''}{indicator.change}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Yield Curve */}
                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                    <h3 className="font-bold text-slate-200 uppercase text-sm mb-4">US Treasury Yield Curve</h3>
                    <ResponsiveContainer width="100%" height={200} minHeight={200}>
                        <LineChart data={yieldCurve}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                            <XAxis dataKey="tenor" stroke="#94a3b8" fontSize={12} />
                            <YAxis stroke="#94a3b8" fontSize={12} domain={['auto', 'auto']} tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
                            <Tooltip 
                                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
                                labelStyle={{ color: '#e2e8f0' }}
                                formatter={(value: any) => `${(value as number).toFixed(2)}%`}
                            />
                            <Line 
                                type="monotone" 
                                dataKey="yield" 
                                stroke="#06b6d4" 
                                strokeWidth={2}
                                dot={{ fill: '#06b6d4', r: 5, strokeWidth: 2, stroke: '#0e7490' }}
                                activeDot={{ r: 7, fill: '#22d3ee' }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                    {yieldCurve.length >= 3 && (() => {
                        const y2 = yieldCurve.find(c => c.tenor === '2Y');
                        const y10 = yieldCurve.find(c => c.tenor === '10Y');
                        const spread = ((y10?.yield ?? 0) - (y2?.yield ?? 0)) * 100;
                        return (
                            <div className="flex justify-between mt-3 text-xs">
                                <span className="text-slate-500">2Y-10Y Spread: <span className={`font-bold ${spread < 0 ? 'text-rose-400' : 'text-emerald-400'}`}>{spread.toFixed(0)}bps</span></span>
                                <span className="text-slate-500">10Y: <span className="font-bold text-cyan-400">{y10?.yield?.toFixed(2) || '—'}%</span></span>
                            </div>
                        );
                    })()}
                    {yieldCurve.some(c => c.lastUpdate) && (
                        <p className="text-[9px] text-slate-600 mt-2 font-mono">
                            Chaque tenor est une série FRED distincte — dates de publication : {' '}
                            {[...new Set(yieldCurve.map(c => c.lastUpdate).filter(Boolean))].map(formatDate).join(' · ')}
                        </p>
                    )}
                </div>
            </div>

            {/* Credit Stress Indicators */}
            <div className="bg-slate-900/50 border border-slate-800 rounded p-4 space-y-4">
                <h3 className="font-bold text-slate-200 uppercase text-sm">Credit Stress Indicators</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                    {creditStress.map((indicator) => (
                        <div key={indicator.name} className={`p-3 rounded border ${getRiskColor(indicator.level)}`}>
                            <div className="flex items-start justify-between mb-2">
                                <p className="text-xs font-semibold">{indicator.name}</p>
                                <div className="text-xs font-bold px-2 py-0.5 bg-slate-900/40 rounded">
                                    {indicator.level}
                                </div>
                            </div>
                            <div className="flex justify-between items-end">
                                <div>
                                    <p className="text-lg font-bold">{indicator.value}</p>
                                    <p className="text-[10px] opacity-70">Threshold: {indicator.threshold}</p>
                                </div>
                                <div>
                                    {getTrendIcon(indicator.trend)}
                                </div>
                            </div>
                            <p className="text-[9px] opacity-60 mt-1">Màj : {formatDate(indicator.lastUpdate)}</p>
                        </div>
                    ))}
                </div>
            </div>

            {/* Market Summary — Dynamic */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pb-4">
                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Zap size={16} className="text-cyan-500" />
                        <h4 className="font-bold text-sm text-slate-300">Rate Environment</h4>
                    </div>
                    {(() => {
                        // D38 : corrigé — l'ancienne logique retombait sur
                        // "Hawkish" par défaut dès que 0 banque n'était
                        // dovish, même si toutes étaient réellement "Hold"
                        // (neutre). Comparaison explicite hawkish vs dovish.
                        const dovishCount = centralBanks.filter(b => b.trend === 'dovish').length;
                        const hawkishCount = centralBanks.filter(b => b.trend === 'hawkish').length;
                        const env = dovishCount > hawkishCount ? 'Dovish' : hawkishCount > dovishCount ? 'Hawkish' : 'Neutral';
                        const envColor = env === 'Dovish' ? 'text-emerald-400' : env === 'Hawkish' ? 'text-rose-400' : 'text-yellow-400';
                        return (
                            <>
                                <p className={`text-2xl font-bold ${envColor}`}>{env}</p>
                                <p className="text-xs text-slate-400 mt-2">{dovishCount} dovish · {hawkishCount} hawkish · {centralBanks.length - dovishCount - hawkishCount} hold (sur {centralBanks.length})</p>
                            </>
                        );
                    })()}
                </div>

                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Activity size={16} className="text-yellow-500" />
                        <h4 className="font-bold text-sm text-slate-300">Credit Conditions</h4>
                    </div>
                    {(() => {
                        const overallRisk = creditStress.some(i => i.level === 'High') ? 'Elevated' : creditStress.some(i => i.level === 'Medium') ? 'Stable' : 'Benign';
                        const riskColor = overallRisk === 'Elevated' ? 'text-rose-400' : overallRisk === 'Stable' ? 'text-yellow-400' : 'text-emerald-400';
                        const improving = creditStress.filter(i => i.trend === 'improving').length;
                        return (
                            <>
                                <p className={`text-2xl font-bold ${riskColor}`}>{overallRisk}</p>
                                <p className="text-xs text-slate-400 mt-2">{improving}/{creditStress.length} indicators improving</p>
                            </>
                        );
                    })()}
                </div>

                <div className="bg-slate-900/50 border border-slate-800 rounded p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle size={16} className="text-rose-500" />
                        <h4 className="font-bold text-sm text-slate-300">Key Risk</h4>
                    </div>
                    {(() => {
                        // Find worst credit indicator
                        const worst = [...creditStress].sort((a, b) => (b.value / b.threshold) - (a.value / a.threshold))[0];
                        const vix = macroIndicators.find(i => i.name.includes('VIX'));
                        const vixVal = typeof vix?.value === 'number' ? vix.value : 0;
                        const riskLabel = vixVal > 25 ? 'Volatility' : worst?.name?.includes('HY') ? 'HY Spreads' : 'Repricing Risk';
                        return (
                            <>
                                <p className="text-2xl font-bold text-rose-400">{riskLabel}</p>
                                <p className="text-xs text-slate-400 mt-2">
                                    {worst ? `${worst.name}: ${worst.value} (threshold: ${worst.threshold})` : 'Monitor spreads closely'}
                                </p>
                            </>
                        );
                    })()}
                </div>
            </div>
        </div>
    );
};