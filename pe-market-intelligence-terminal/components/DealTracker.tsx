import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Copy, Download, FileText, FileSpreadsheet, Loader2, MessageSquarePlus, Sparkles, Calculator } from 'lucide-react';
import { marked } from 'marked';
import { Card } from './ui/Card';
import { ProvenanceBadge } from './ProvenanceBadge';
import { useGenerateMemoMutation, useLboScenarios, useLboScenario } from '../hooks/useQueries';
import { dealsAPI } from '../services/apiService';
import { Deal, DealActivity, DealActivityListResponse } from '../../shared/types';

// D18 (Tâche B.6) : montants toujours affichés à côté de leur badge de
// provenance (voir ProvenanceBadge.tsx) — jamais un chiffre financier seul.
const fmtMoney = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  if (Math.abs(v) >= 1_000_000) return `€${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `€${(v / 1_000).toFixed(0)}K`;
  return `€${v.toFixed(0)}`;
};

interface DealTrackerProps {
  deals: Deal[];
}

const getSectorColor = (sector: string) => {
  const colors: Record<string, string> = {
    Technology: 'bg-blue-900/50 text-blue-300 border border-blue-800',
    Healthcare: 'bg-emerald-900/50 text-emerald-300 border border-emerald-800',
    'Real Estate': 'bg-amber-900/50 text-amber-300 border border-amber-800',
    Fintech: 'bg-violet-900/50 text-violet-300 border border-violet-800',
    Industrials: 'bg-orange-900/50 text-orange-300 border border-orange-800',
    Consumer: 'bg-pink-900/50 text-pink-300 border border-pink-800',
    Infrastructure: 'bg-teal-900/50 text-teal-300 border border-teal-800',
  };
  return colors[sector] || 'bg-slate-800 text-slate-300 border border-slate-700';
};

const getTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    LBO: 'bg-cyan-900/40 text-cyan-300',
    'M&A': 'bg-yellow-900/40 text-yellow-300',
    Growth: 'bg-emerald-900/40 text-emerald-300',
    'Carve-out': 'bg-purple-900/40 text-purple-300',
    Recap: 'bg-rose-900/40 text-rose-300',
    Secondary: 'bg-indigo-900/40 text-indigo-300',
  };
  return colors[type] || 'bg-slate-800 text-slate-300';
};

const formatActivityDate = (value: string) =>
  new Date(value).toLocaleString('fr-FR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });

// D31 (Tâche Review Produit — Partie A) : IRR/MOIC du scénario LBO de
// référence (même heuristique que get_reference_scenario côté backend :
// libellé contenant "base", sinon le plus récent) — composant séparé car
// chaque ligne a besoin de son propre hook `useLboScenarios`.
const DealReturnsCells: React.FC<{ dealId: number }> = ({ dealId }) => {
  const { data: scenarios } = useLboScenarios(dealId);
  const reference = scenarios && scenarios.length > 0
    ? scenarios.find((s) => s.label.toLowerCase().includes('base')) ?? scenarios[0]
    : null;

  return (
    <>
      <td className={`px-3 py-2 text-right font-semibold ${reference?.irr != null ? (reference.irr >= 0.2 ? 'text-emerald-400' : 'text-amber-400') : 'text-slate-600'}`}>
        {reference?.irr != null ? `${(reference.irr * 100).toFixed(1)}%` : '—'}
      </td>
      <td className={`px-3 py-2 text-right font-semibold ${reference?.moic != null ? (reference.moic >= 2.5 ? 'text-emerald-400' : 'text-amber-400') : 'text-slate-600'}`}>
        {reference?.moic != null ? `${reference.moic.toFixed(2)}x` : '—'}
      </td>
    </>
  );
};

// D45 (Tâche Finalisation, Partie F) : hypothèses (entry multiple, marge
// EBITDA) du scénario LBO de référence, avec leur provenance — même
// heuristique de sélection du scénario de référence que DealReturnsCells
// ci-dessus, mais nécessite le détail complet (useLboScenario) puisque
// financial_provenance n'est pas exposé par la liste allégée.
const ReferenceScenarioProvenance: React.FC<{ dealId: number }> = ({ dealId }) => {
  const { data: scenarios } = useLboScenarios(dealId);
  const referenceId = scenarios && scenarios.length > 0
    ? (scenarios.find((s) => s.label.toLowerCase().includes('base')) ?? scenarios[0]).id
    : null;
  const { data: scenario } = useLboScenario(referenceId);
  const prov = scenario?.result_json?.financial_provenance;
  if (!scenario || !prov) return null;

  return (
    <>
      <p className="flex items-center">
        <span className="text-slate-500">LBO — Multiple d'entrée retenu:</span>&nbsp;
        {scenario.result_json.entry_multiple.toFixed(2)}x
        <ProvenanceBadge provenance={prov.entry_multiple} />
      </p>
      <p className="flex items-center">
        <span className="text-slate-500">LBO — Marge EBITDA (hyp.):</span>&nbsp;
        {(scenario.result_json.ebitda_margin * 100).toFixed(1)}%
        <ProvenanceBadge provenance={prov.ebitda_margin} />
      </p>
    </>
  );
};

// Tâche "P2 : crédibilité de la thèse" (Partie A) — sous le seuil de CA,
// le scénario de base généré automatiquement est étiqueté "indicatif"
// (assumptions_json.sizing_tier === "indicative_bolt_on", voir
// lbo_scenario_service.build_base_case_scenario) : affiche la même mise en
// garde que le mémo/deck directement sur l'écran du deal, avec un renvoi
// explicite vers Buy & Build — jamais reléguée à un détail discret.
const SizingGuidanceBanner: React.FC<{ dealId: number }> = ({ dealId }) => {
  const { data: scenarios } = useLboScenarios(dealId);
  const referenceId = scenarios && scenarios.length > 0
    ? (scenarios.find((s) => s.label.toLowerCase().includes('base')) ?? scenarios[0]).id
    : null;
  const { data: scenario } = useLboScenario(referenceId);
  const assumptions = scenario?.assumptions_json;
  if (!assumptions || assumptions.sizing_tier !== 'indicative_bolt_on' || !assumptions.sizing_note) return null;

  return (
    <div className="mt-2 rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-200">
      <p className="font-bold uppercase tracking-wide text-amber-400 mb-1">LBO indicatif — hors seuil de financement standalone</p>
      <p className="leading-relaxed">{assumptions.sizing_note}</p>
      <Link to="/buy-and-build" className="mt-1 inline-flex items-center gap-1 font-semibold text-cyan-400 hover:text-cyan-300">
        Voir le module Buy &amp; Build →
      </Link>
    </div>
  );
};

export const DealTracker: React.FC<DealTrackerProps> = ({ deals }) => {
  const [selectedDealId, setSelectedDealId] = useState<number | null>(deals[0]?.id ?? null);
  const [memoText, setMemoText] = useState<string>('');
  const [toast, setToast] = useState<string | null>(null);
  const [activities, setActivities] = useState<DealActivity[]>([]);
  const [noteText, setNoteText] = useState('');
  const [loadingActivities, setLoadingActivities] = useState(false);
  const [creatingNote, setCreatingNote] = useState(false);
  const generateMemoMutation = useGenerateMemoMutation();

  const selectedDeal = useMemo(
    () => deals.find((deal) => deal.id === selectedDealId) ?? null,
    [deals, selectedDealId],
  );

  useEffect(() => {
    if (!selectedDealId && deals[0]) {
      setSelectedDealId(deals[0].id);
    }
  }, [deals, selectedDealId]);

  useEffect(() => {
    setMemoText(selectedDeal?.ic_memo ?? '');
  }, [selectedDeal?.ic_memo, selectedDealId]);

  useEffect(() => {
    if (!toast) return;
    const timeoutId = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timeoutId);
  }, [toast]);

  useEffect(() => {
    let active = true;

    const loadActivities = async () => {
      if (!selectedDeal) {
        setActivities([]);
        return;
      }

      setLoadingActivities(true);
      try {
        const response = (await dealsAPI.getActivities(selectedDeal.id)) as DealActivityListResponse;
        if (active) {
          setActivities(response.activities ?? []);
        }
      } catch {
        if (active) {
          setActivities([]);
        }
      } finally {
        if (active) {
          setLoadingActivities(false);
        }
      }
    };

    loadActivities();

    return () => {
      active = false;
    };
  }, [selectedDeal]);

  const renderedMemo = useMemo(() => {
    if (!memoText) return '';
    return marked.parse(memoText, { async: false }) as string;
  }, [memoText]);

  const showToast = (message: string) => setToast(message);

  const sanitizeFileName = (value: string) =>
    value.replace(/[^a-z0-9-_]+/gi, '_').replace(/_+/g, '_').replace(/^_|_$/g, '');

  const refreshActivities = async () => {
    if (!selectedDeal) return;
    const response = await dealsAPI.getActivities(selectedDeal.id);
    setActivities(response.activities ?? []);
  };

  const handleGenerateMemo = () => {
    if (!selectedDeal) return;
    generateMemoMutation.mutate(selectedDeal.id, {
      onSuccess: (result) => {
        setMemoText(result.ic_memo);
        refreshActivities().catch(() => undefined);
      },
    });
  };

  const handleCopyMemo = async () => {
    if (!memoText) return;
    try {
      await navigator.clipboard.writeText(memoText);
      showToast('Mémo copié dans le presse-papiers');
    } catch {
      showToast('Impossible de copier le mémo');
    }
  };

  const handleDownloadMemo = () => {
    if (!memoText || !selectedDeal) return;

    const fileName = `Memo_${sanitizeFileName(selectedDeal.target_name || 'Deal')}.md`;
    const blob = new Blob([memoText], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
    showToast('Mémo téléchargé au format .md');
  };

  const downloadBlob = (blob: Blob, fileName: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  // D28 — export Word mis en forme, téléchargement principal du mémo.
  const [docxDownloading, setDocxDownloading] = useState(false);
  const handleDownloadDocx = async () => {
    if (!selectedDeal || !memoText) return;
    setDocxDownloading(true);
    try {
      const blob = await dealsAPI.exportMemoDocx(selectedDeal.id);
      downloadBlob(blob, `Memo_IC_${sanitizeFileName(selectedDeal.target_name || 'Deal')}.docx`);
      showToast('Mémo téléchargé au format .docx');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Échec du téléchargement .docx');
    } finally {
      setDocxDownloading(false);
    }
  };

  // D30 — deck de comité d'investissement.
  const [deckDownloading, setDeckDownloading] = useState(false);
  const handleDownloadDeck = async () => {
    if (!selectedDeal) return;
    setDeckDownloading(true);
    try {
      const blob = await dealsAPI.exportDeckPptx(selectedDeal.id);
      downloadBlob(blob, `Deck_IC_${sanitizeFileName(selectedDeal.target_name || 'Deal')}.pptx`);
      showToast('Deck IC téléchargé au format .pptx');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Échec du téléchargement du deck');
    } finally {
      setDeckDownloading(false);
    }
  };

  // Tâche "P0 : un seul deal dans les 3 documents" — export Excel CANONIQUE
  // du scénario LBO de référence de ce deal (jamais l'état libre du
  // calculateur manuel, qui peut afficher un multiple/une structure de dette
  // totalement différents de ceux du mémo/deck du même deal).
  const [excelDownloading, setExcelDownloading] = useState(false);
  const handleDownloadExcel = async () => {
    if (!selectedDeal) return;
    setExcelDownloading(true);
    try {
      const blob = await dealsAPI.exportLboExcel(selectedDeal.id);
      downloadBlob(blob, `LBO_Model_${sanitizeFileName(selectedDeal.target_name || 'Deal')}.xlsx`);
      showToast('Modèle LBO téléchargé au format .xlsx');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Échec du téléchargement du modèle Excel');
    } finally {
      setExcelDownloading(false);
    }
  };

  const handleAddNote = async () => {
    if (!selectedDeal || !noteText.trim()) return;

    setCreatingNote(true);
    try {
      await dealsAPI.addNote(selectedDeal.id, { content: noteText.trim() });
      setNoteText('');
      await refreshActivities();
      showToast('Note ajoutée à l’activité');
    } catch {
      showToast('Impossible d’ajouter la note');
    } finally {
      setCreatingNote(false);
    }
  };

  const renderActivity = (activity: DealActivity) => {
    const isNote = activity.action_type === 'user_note';
    return (
      <div key={activity.id} className="relative pl-7">
        <span className={`absolute left-1.5 top-2 h-2.5 w-2.5 rounded-full ${isNote ? 'bg-cyan-400' : 'bg-amber-400'}`} />
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-wider text-slate-500">
            <span>{isNote ? 'Note' : 'Événement système'}</span>
            <span>{formatActivityDate(activity.created_at)}</span>
          </div>
          <p className="mt-2 text-sm text-slate-200 whitespace-pre-line">{activity.content}</p>
        </div>
      </div>
    );
  };

  return (
    <Card title="Global Deal Tracker" subtitle="Recent Major PE Transactions" className="h-full">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="sticky top-0 border-b border-slate-700 bg-slate-900/50 text-xs text-slate-400">
              <th className="px-3 py-2 font-semibold">Date</th>
              <th className="px-3 py-2 font-semibold">Target Company</th>
              <th className="px-3 py-2 font-semibold">Acquirer (GP)</th>
              <th className="px-3 py-2 font-semibold text-right">Size ($B)</th>
              <th className="px-3 py-2 font-semibold">Sector</th>
              <th className="px-3 py-2 font-semibold">Type</th>
              <th className="px-3 py-2 font-semibold text-right">EV/EBITDA</th>
              <th className="px-3 py-2 font-semibold text-right">IRR</th>
              <th className="px-3 py-2 font-semibold text-right">MOIC</th>
              <th className="px-3 py-2 font-semibold text-right">Memo</th>
            </tr>
          </thead>
          <tbody className="text-xs font-mono">
            {deals.map((deal, idx) => (
              <tr
                key={deal.id}
                className={`cursor-pointer border-b border-slate-800/50 transition-colors hover:bg-slate-800 ${selectedDealId === deal.id ? 'bg-slate-800/80' : idx % 2 === 0 ? 'bg-slate-900' : 'bg-slate-900/30'}`}
                onClick={() => setSelectedDealId(deal.id)}
              >
                <td className="px-3 py-2 text-slate-400">{deal.announcement_date ? new Date(deal.announcement_date).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' }) : '—'}</td>
                <td className="px-3 py-2 font-bold text-cyan-400">{deal.target_name ?? '—'}</td>
                <td className="px-3 py-2 text-slate-200">{deal.acquirer_name}</td>
                <td className="px-3 py-2 text-right font-semibold text-slate-100">{deal.deal_value != null ? `$${(deal.deal_value / 1e9).toFixed(1)}B` : '—'}</td>
                <td className="px-3 py-2 text-slate-300">
                  <span className={`rounded px-2 py-0.5 text-[10px] font-sans font-medium ${getSectorColor(deal.sector ?? '')}`}>
                    {deal.sector ?? '—'}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={`rounded px-2 py-0.5 text-[10px] font-sans font-medium ${getTypeColor(deal.deal_type ?? '')}`}>
                    {deal.deal_type ?? '—'}
                  </span>
                </td>
                <td className={`px-3 py-2 text-right font-semibold ${deal.ev_ebitda_multiple && deal.ev_ebitda_multiple > 18 ? 'text-rose-400' : deal.ev_ebitda_multiple && deal.ev_ebitda_multiple < 10 ? 'text-emerald-400' : 'text-slate-300'}`}>
                  {deal.ev_ebitda_multiple ? `${deal.ev_ebitda_multiple.toFixed(1)}x` : '-'}
                </td>
                <DealReturnsCells dealId={deal.id} />
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedDealId(deal.id);
                      generateMemoMutation.mutate(deal.id, {
                        onSuccess: (result) => {
                          setMemoText(result.ic_memo);
                          refreshActivities().catch(() => undefined);
                        },
                      });
                    }}
                    className="inline-flex items-center gap-1 rounded border border-cyan-800 bg-cyan-950/30 px-2 py-1 text-[10px] font-semibold text-cyan-300 transition hover:border-cyan-600 hover:bg-cyan-950/60 disabled:opacity-50"
                  >
                    {generateMemoMutation.isPending && selectedDealId === deal.id ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                    Générer IC Memo
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 border-t border-slate-800 pt-4">
        {selectedDeal ? (
          <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
            <div className="space-y-4 rounded-lg border border-slate-800 bg-slate-950/60 p-4">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Deal selected</p>
                <h4 className="mt-1 text-base font-bold text-white">{selectedDeal.target_name ?? '—'}</h4>
                <p className="mt-1 text-xs text-slate-400">{selectedDeal.acquirer_name}</p>
              </div>
              <div className="space-y-2 text-[11px] text-slate-300">
                <p><span className="text-slate-500">Date:</span> {selectedDeal.announcement_date ?? '—'}</p>
                <p><span className="text-slate-500">Sector:</span> {selectedDeal.sector ?? '—'}</p>
                <p><span className="text-slate-500">Type:</span> {selectedDeal.deal_type ?? '—'}</p>
                <p className="flex items-center">
                  <span className="text-slate-500">Revenue:</span>&nbsp;{fmtMoney(selectedDeal.target_revenue)}
                  <ProvenanceBadge provenance={selectedDeal.financial_provenance?.target_revenue} />
                </p>
                <p className="flex items-center">
                  <span className="text-slate-500">EBITDA:</span>&nbsp;{fmtMoney(selectedDeal.target_ebitda)}
                  <ProvenanceBadge provenance={selectedDeal.financial_provenance?.target_ebitda} />
                </p>
                <p className="flex items-center">
                  <span className="text-slate-500">Enterprise value:</span>&nbsp;{fmtMoney(selectedDeal.enterprise_value)}
                  <ProvenanceBadge provenance={selectedDeal.financial_provenance?.enterprise_value} />
                </p>
                <p className="flex items-center">
                  <span className="text-slate-500">EV/EBITDA:</span>&nbsp;{selectedDeal.ev_ebitda_multiple ? `${selectedDeal.ev_ebitda_multiple.toFixed(2)}x` : '—'}
                  <ProvenanceBadge provenance={selectedDeal.financial_provenance?.ev_ebitda_multiple} />
                </p>
                <ReferenceScenarioProvenance dealId={selectedDeal.id} />
              </div>
              <SizingGuidanceBanner dealId={selectedDeal.id} />
              <button
                type="button"
                onClick={handleGenerateMemo}
                disabled={generateMemoMutation.isPending}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-cyan-500 bg-cyan-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {generateMemoMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
                {generateMemoMutation.isPending ? 'Rédaction par l’IA en cours...' : 'Générer IC Memo'}
              </button>
              {/* Tâche B.11, Étape 3.3 : un échec IA doit renvoyer un message actionnable,
                  sans effacer le mémo déjà présent (memoText n'est modifié que dans onSuccess
                  ci-dessus — un échec le laisse strictement inchangé). */}
              {generateMemoMutation.isError && (
                <div className="rounded-lg border border-rose-900/60 bg-rose-950/20 px-3 py-2 text-xs text-rose-300">
                  Échec de la génération du mémo : {generateMemoMutation.error?.message ?? 'Erreur inconnue'}.
                  {memoText ? ' Le dernier mémo généré reste affiché ci-dessous.' : ''}
                </div>
              )}
              {/* D16 (Tâche B.5) : accès direct au LBO pré-rempli depuis ce deal */}
              <Link
                to={`/lbo?dealId=${selectedDeal.id}`}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-emerald-600 hover:text-emerald-300"
              >
                <Calculator size={16} />
                Ouvrir le LBO pré-rempli
              </Link>
            </div>

            <div className="min-h-[340px] rounded-lg border border-slate-800 bg-slate-950/60 p-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
                <div>
                  {memoText ? (
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Actions rapides</div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={handleCopyMemo}
                            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-700 hover:text-cyan-300"
                          >
                            <Copy size={14} />
                            Copier le texte
                          </button>
                          <button
                            type="button"
                            onClick={handleDownloadDocx}
                            disabled={docxDownloading}
                            className="inline-flex items-center gap-2 rounded-lg border border-cyan-500 bg-cyan-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-cyan-500 disabled:opacity-60"
                          >
                            {docxDownloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                            Télécharger .docx
                          </button>
                          <button
                            type="button"
                            onClick={handleDownloadMemo}
                            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-700 hover:text-cyan-300"
                          >
                            <Download size={14} />
                            .md
                          </button>
                          <button
                            type="button"
                            onClick={handleDownloadDeck}
                            disabled={deckDownloading}
                            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-700 hover:text-cyan-300 disabled:opacity-60"
                          >
                            {deckDownloading ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                            Deck IC (.pptx)
                          </button>
                          <button
                            type="button"
                            onClick={handleDownloadExcel}
                            disabled={excelDownloading}
                            title="Modèle LBO du scénario de référence de ce deal — mêmes chiffres que le mémo et le deck"
                            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-emerald-700 hover:text-emerald-300 disabled:opacity-60"
                          >
                            {excelDownloading ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} />}
                            Modèle LBO (.xlsx)
                          </button>
                        </div>
                      </div>

                      <article
                        className="prose prose-invert max-w-none prose-headings:font-semibold prose-p:text-slate-300 prose-li:text-slate-300 prose-strong:text-white"
                        dangerouslySetInnerHTML={{ __html: renderedMemo }}
                      />
                    </div>
                  ) : (
                    <div className="flex h-full min-h-[260px] items-center justify-center rounded-lg border border-dashed border-slate-800 bg-slate-900/30 text-center">
                      <div>
                        <p className="text-sm font-medium text-slate-300">Aucun mémo généré pour ce deal.</p>
                        <p className="mt-1 text-xs text-slate-500">Lancez la génération IA pour produire le mémo d’investissement.</p>
                      </div>
                    </div>
                  )}
                </div>

                <div className="space-y-4 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-white">
                      <MessageSquarePlus size={16} className="text-cyan-400" />
                      Historique & Notes
                    </div>
                    <p className="mt-1 text-xs text-slate-500">Journal d’audit et collaboration sur ce deal.</p>
                  </div>

                  <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Nouvelle note</label>
                    <textarea
                      value={noteText}
                      onChange={(event) => setNoteText(event.target.value)}
                      rows={4}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-cyan-600"
                      placeholder="Partager un commentaire, une décision, un rappel..."
                    />
                    <button
                      type="button"
                      onClick={handleAddNote}
                      disabled={creatingNote || !noteText.trim()}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-500 bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {creatingNote ? <Loader2 size={16} className="animate-spin" /> : <MessageSquarePlus size={16} />}
                      Ajouter une note
                    </button>
                  </div>

                  <div className="max-h-[360px] space-y-3 overflow-y-auto pr-1">
                    {loadingActivities ? (
                      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
                        Chargement de l’historique...
                      </div>
                    ) : activities.length > 0 ? (
                      activities.map(renderActivity)
                    ) : (
                      <div className="rounded-lg border border-dashed border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
                        Aucun événement enregistré pour le moment.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {toast ? (
        <div className="fixed bottom-4 right-4 z-50 rounded-lg border border-slate-700 bg-slate-950/95 px-4 py-3 text-sm text-slate-100 shadow-2xl shadow-black/30">
          {toast}
        </div>
      ) : null}
    </Card>
  );
};
