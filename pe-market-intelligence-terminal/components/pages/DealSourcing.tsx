
import React, { useState, useCallback, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../ui/Card';
import {
  Radar, Search, RefreshCw, CheckCircle, XCircle, Clock, Eye,
  Globe, Zap, AlertTriangle, TrendingUp, FileSpreadsheet, ExternalLink,
  Database, ChevronDown, ChevronUp, Cpu, X,
  Scale, Shield, Flag, ArrowUpRight, Minus, CircleDot,
  Users, Briefcase, Star, MapPin, BarChart3, Rocket,
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { useSourcedTargets, useRunScanMutation, useScanStatus, useDigitalDD, useLegalEvents, useTalentSignals, useSectorCalibration, useCompsTable, usePromoteTargetMutation } from '../../hooks/useQueries';
import { maEngineAPI } from '../../services/apiService';
import { DocumentUpload } from '../DocumentUpload';
import { ProvenanceBadge } from '../ProvenanceBadge';
import type {
  SourcedTargetMA, DigitalDDReport, TechStackItem, SearchTrendPoint,
  LegalEventsReport, CorporateEvent, MaSignal,
  TalentSignalsReport, JobOpening, JobCategory, TrendSignal,
  SectorCalibration, CompRow, CompsTableResponse, ScanStatus,
} from '../../types';

// ============================================
// Helpers
// ============================================

const getScoreColor = (s: number | null) => {
  if (s === null) return 'text-slate-500';
  if (s >= 70) return 'text-emerald-400';
  if (s >= 40) return 'text-cyan-400';
  if (s >= 20) return 'text-amber-400';
  return 'text-slate-400';
};

const getScoreBarColor = (s: number | null) => {
  if (s === null) return 'bg-slate-700';
  if (s >= 70) return 'bg-emerald-500';
  if (s >= 40) return 'bg-cyan-500';
  if (s >= 20) return 'bg-amber-500';
  return 'bg-slate-600';
};

// D46 (Tâche Finalisation, Partie D) : surligne la première occurrence du
// terme recherché — sert à rendre visible POURQUOI une cible dont le nom ne
// correspond pas apparaît quand même dans les résultats (elle matche sur sa
// description, pas son nom). Une seule occurrence surlignée volontairement :
// l'objectif est de montrer où, pas d'illuminer tout le paragraphe.
const highlightMatch = (text: string, query: string): React.ReactNode => {
  if (!query.trim()) return text;
  const idx = text.toLowerCase().indexOf(query.trim().toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-cyan-500/30 text-cyan-200 rounded-sm px-0.5">{text.slice(idx, idx + query.trim().length)}</mark>
      {text.slice(idx + query.trim().length)}
    </>
  );
};

const getStatusBadge = (status: string) => {
  switch (status) {
    case 'Active':
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-900/40 text-emerald-400 border border-emerald-800"><CheckCircle size={10} className="mr-1" /> ACTIVE</span>;
    case 'Deep Dive':
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-900/40 text-cyan-400 border border-cyan-800"><Eye size={10} className="mr-1" /> DEEP DIVE</span>;
    case 'Contacted':
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-violet-900/40 text-violet-400 border border-violet-800"><Zap size={10} className="mr-1" /> CONTACTED</span>;
    case 'Watchlist':
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-900/40 text-amber-400 border border-amber-800"><Clock size={10} className="mr-1" /> WATCH</span>;
    case 'Passed':
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-500 border border-slate-700"><XCircle size={10} className="mr-1" /> PASSED</span>;
    case 'Archived':
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-900 text-slate-600 border border-slate-800"><XCircle size={10} className="mr-1" /> ARCHIVED</span>;
    default:
      return <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-400 border border-slate-700">{status.toUpperCase()}</span>;
  }
};

const formatRevenue = (rev: number | null): string => {
  if (rev === null || rev === 0) return 'N/A';
  if (rev >= 1_000_000) return `${(rev / 1_000_000).toFixed(1)} M€`;
  if (rev >= 1_000) return `${(rev / 1_000).toFixed(0)} K€`;
  return `${rev.toFixed(0)} €`;
};

// D11 (Tâche B.3) — typologie par taille, uniquement pour les cibles issues
// du registre (CA réel connu). Absent (null) pour les cibles sans CA classé.
const getTargetTypeBadge = (targetType: string | null) => {
  if (targetType === 'platform') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-violet-950/40 text-violet-300 border border-violet-800" title="CA > 100M€ — plateforme de consolidation potentielle">
        PLATFORM
      </span>
    );
  }
  if (targetType === 'target') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-cyan-950/40 text-cyan-300 border border-cyan-800" title="CA 10-100M€ — cœur de thèse">
        TARGET
      </span>
    );
  }
  return null;
};


// ============================================
// Main Component
// ============================================

export const DealSourcing: React.FC = () => {
  // ── OSINT Radar state ──
  const [scanUrl, setScanUrl] = useState('');
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  // D46 (Tâche Finalisation, Partie B) : distinct du toast (qui s'efface
  // après 9s) — le lien recherche → résultats doit rester visible tant que
  // l'utilisateur ne l'a pas explicitement fermé ou relancé un scan, sinon
  // il doit se souvenir du toast pour retrouver ce qui a été trouvé.
  const [scanResult, setScanResult] = useState<ScanStatus | null>(null);

  // ── Pipeline filters ──
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<'' | 'target' | 'platform'>('');
  const [searchQuery, setSearchQuery] = useState('');
  // D47 (Tâche Finalisation, Partie B) : tri par colonne — le backend trie
  // par score décroissant par défaut (sourcing_service.py::list_targets),
  // repris ici comme valeur initiale pour ne rien changer au premier
  // rendu ; le tri lui-même reste côté client (tout est déjà chargé).
  type SortKey = 'score' | 'revenue' | 'name';
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  // ── Intelligence panel (DD + Legal + Talent) ──
  const [ddTargetId, setDdTargetId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'digital-dd' | 'legal' | 'talent' | 'comps'>('digital-dd');

  // D46 (Tâche Finalisation, Partie D) : la description (business_summary)
  // était tronquée en CSS (`truncate`) sans aucun moyen de lire le reste —
  // dépliage manuel par cible, jamais un dialogue/tooltip séparé qui
  // casserait l'alignement du tableau.
  const [expandedSummaryIds, setExpandedSummaryIds] = useState<Set<number>>(new Set());
  const toggleSummary = (id: number) => {
    setExpandedSummaryIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // ── Data hooks ──
  // D47 (Tâche Finalisation, Partie B) : plus de plafond caché à 50 — la
  // base est petite (~60-70 lignes), tout est chargé. 500 = le maximum
  // autorisé par le routeur (`Query(50, le=500)`, api/routers/sourcing.py)
  // ; au-delà, il faudrait un vrai "charger plus", pas nécessaire ici.
  const { data, isLoading, error, refetch, isFetching } = useSourcedTargets(0, 500, statusFilter || undefined);
  const promoteMutation = usePromoteTargetMutation();

  const handlePromote = (target: SourcedTargetMA) => {
    promoteMutation.mutate(target.id, {
      onSuccess: (res) => {
        setToast({ message: `✅ ${target.company_name} promue en deal #${res.deal_id}`, type: 'success' });
        setTimeout(() => setToast(null), 5000);
      },
      onError: (err) => {
        setToast({ message: `❌ ${err instanceof Error ? err.message : 'Échec de la promotion'}`, type: 'error' });
        setTimeout(() => setToast(null), 5000);
      },
    });
  };
  const scanMutation = useRunScanMutation();

  // D40 (Tâche Finalisation) — le scan est asynchrone (202 Accepted immédiat) ;
  // on poll le statut réel jusqu'à la fin pour ne jamais laisser un 0 résultat
  // comme un échec silencieux (voir useScanStatus).
  const [scanPolling, setScanPolling] = useState(false);
  const { data: scanStatus } = useScanStatus(scanPolling);

  useEffect(() => {
    if (!scanStatus || scanStatus.status === 'running') return;
    setScanPolling(false);

    // D46 (Tâche Finalisation, Partie B) : le résultat persistant (bandeau
    // ci-dessous) se met à jour dans tous les cas — échec, 0 résultat, ou
    // succès — jamais seulement le toast qui, lui, disparaît après 9s.
    if (scanStatus.status !== 'failed') {
      setScanResult(scanStatus);
    }

    // D47 (Tâche Finalisation, Partie A) : root cause du bug "cible à score
    // élevé étiquetée hors page" — `targets` (useSourcedTargets) n'était
    // rafraîchi que sur clic manuel sur Actualiser. Juste après un scan, les
    // cibles fraîchement créées étaient donc absentes de `targets` même
    // quand elles auraient dû être bien classées, et systématiquement
    // étiquetées "hors page (score bas)" — pour une mauvaise raison (données
    // périmées, pas un score réellement bas). Rafraîchi automatiquement dès
    // que le scan se termine, avec ou sans résultat.
    if ((scanStatus.targets_saved ?? 0) > 0) {
      refetch();
    }

    if (scanStatus.status === 'failed') {
      setToast({ message: `❌ Le scan a échoué : ${scanStatus.error ?? 'erreur inconnue'}`, type: 'error' });
    } else if ((scanStatus.targets_saved ?? 0) > 0) {
      setToast({
        message: `✅ ${scanStatus.targets_saved} cible${scanStatus.targets_saved !== 1 ? 's' : ''} TIC ajoutée${scanStatus.targets_saved !== 1 ? 's' : ''} pour ${scanStatus.platform_url}`,
        type: 'success',
      });
    } else {
      // 0 cible sauvegardée — jamais un écran vide muet : explique le
      // périmètre réel (D40) plutôt que de laisser deviner.
      const reason = scanStatus.error === 'Contenu plateforme insuffisant'
        ? "le site n'a pas pu être analysé (contenu insuffisant ou page bloquée)"
        : scanStatus.error === 'Extraction ADN échouée'
          ? "l'activité de la société n'a pas pu être identifiée depuis ce site"
          : (scanStatus.targets_found ?? 0) === 0
            ? "aucun candidat n'a été trouvé par la recherche"
            : "aucun candidat ne correspond au secteur TIC (test, inspection, certification, ingénierie technique) en France";
      setToast({
        message: `ℹ️ Aucune cible TIC trouvée pour ${scanStatus.platform_url} — ${reason}. L'outil cible les sociétés françaises de test/inspection/certification et ingénierie (NAF 71.20B/71.12B), pas n'importe quelle entreprise.`,
        type: 'info',
      });
    }
    const t = setTimeout(() => setToast(null), 9000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanStatus]);

  const targets = data?.targets ?? [];
  const totalCount = data?.total ?? 0;

  // ── Filter locally by search + type, then sort ──
  const filteredTargets = (searchQuery
    ? targets.filter(t =>
        t.company_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.url.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (t.business_summary ?? '').toLowerCase().includes(searchQuery.toLowerCase())
      )
    : targets
  ).filter(t => !typeFilter || t.target_type === typeFilter);

  // D47 (Tâche Finalisation, Partie B) : tri côté client — tout est déjà
  // chargé (plus de plafond à 50), donc pas besoin d'un paramètre de tri
  // côté API. `.slice()` avant `.sort()` : ne jamais muter le tableau de
  // react-query en place.
  const sortedTargets = filteredTargets.slice().sort((a, b) => {
    let cmp = 0;
    if (sortKey === 'score') cmp = (a.score ?? -1) - (b.score ?? -1);
    else if (sortKey === 'revenue') cmp = (a.revenue_estimate ?? -1) - (b.revenue_estimate ?? -1);
    else cmp = a.company_name.localeCompare(b.company_name);
    return sortDir === 'desc' ? -cmp : cmp;
  });

  // D46/D47 (Tâche Finalisation) : "N TARGETS IN DB" (en-tête) et "cibles
  // affichées" (ce sous-titre) sont deux métriques différentes — explicite
  // dans les deux cas (recherche active ou non), jamais un chiffre nu sans
  // dire par rapport à quoi. Le plafond de page a été retiré (D47) : la
  // clause "page limitée" ne se déclenche plus qu'au-delà de 500 lignes
  // (maximum du routeur), un cas qui n'existe pas avec la taille actuelle
  // de la base — gardée par sécurité, pas pour l'usage courant.
  const pipelineSubtitle = searchQuery
    ? `${filteredTargets.length} résultat${filteredTargets.length !== 1 ? 's' : ''} pour « ${searchQuery} » (recherche sur les ${targets.length} cibles chargées)`
    : `${filteredTargets.length} affichée${filteredTargets.length !== 1 ? 's' : ''} sur ${totalCount} en base` +
      (totalCount > targets.length ? ` — page limitée à ${targets.length}` : '');

  // ── Actions ──
  const handleScan = useCallback(() => {
    const url = scanUrl.trim();
    if (!url) return;
    if (!url.startsWith('http')) {
      setToast({ message: "L'URL doit commencer par http:// ou https://", type: 'error' });
      setTimeout(() => setToast(null), 4000);
      return;
    }
    scanMutation.mutate(url, {
      onSuccess: () => {
        // D40 : un 202 Accepted ne veut PAS dire "cibles trouvées" — le vrai
        // résultat arrive via le polling de statut (useScanStatus ci-dessus),
        // qui affichera le toast définitif (succès, échec, ou 0 résultat
        // expliqué) quand le scan sera réellement terminé.
        setToast({ message: `⏳ Scan en cours pour ${url} (1-3 min)...`, type: 'info' });
        setScanUrl('');
        setScanPolling(true);
        setScanResult(null);
      },
      onError: (err) => {
        setToast({ message: `❌ Erreur: ${err instanceof Error ? err.message : 'Échec'}`, type: 'error' });
        setTimeout(() => setToast(null), 5000);
      },
    });
  }, [scanUrl, scanMutation]);

  const handleExportCSV = useCallback(async () => {
    try {
      const blob = await maEngineAPI.exportCSV(statusFilter || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pe_targets_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setToast({ message: `❌ Aucune cible à exporter`, type: 'error' });
      setTimeout(() => setToast(null), 4000);
    }
  }, [statusFilter]);

  return (
    <div className="h-full w-full flex flex-col space-y-6">

      {/* ── Toast ── */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 max-w-md px-4 py-3 rounded-lg border shadow-2xl text-sm font-mono animate-pulse
          ${toast.type === 'success'
            ? 'bg-emerald-950/90 border-emerald-700 text-emerald-300'
            : toast.type === 'info'
              ? 'bg-amber-950/90 border-amber-700 text-amber-300'
              : 'bg-rose-950/90 border-rose-700 text-rose-300'
          }`}>
          {toast.message}
        </div>
      )}

      {/* ── Header ── */}
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
          <span className="text-cyan-500">///</span> Deal Sourcing Engine
          <span className="text-[10px] text-slate-500 font-mono border border-slate-800 rounded px-1.5 py-0.5 ml-2">OSINT</span>
        </h2>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-slate-500">{totalCount} TARGETS IN DB</span>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-[10px] font-mono px-3 py-1.5 rounded border border-slate-700 bg-slate-800/50 text-slate-400 hover:text-cyan-400 hover:border-cyan-800 transition-all inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw size={10} className={isFetching ? 'animate-spin' : ''} />
            {isFetching ? 'LOADING...' : 'ACTUALISER'}
          </button>
        </div>
      </div>

      {/* ══════════════════════════════════════════
          Section Haute — Le Radar OSINT
         ══════════════════════════════════════════ */}
      <Card title="OSINT Radar" subtitle="Scraping → NLP → Google Radar → Scoring → LBO → DB" className="border-cyan-900/50">
        {/* D40 (Tâche Finalisation) — cadrage explicite du périmètre, pour
            qu'une recherche hors thèse (ex. Doctolib, Danfoss...) ne
            ressemble pas à un bug. */}
        <div className="rounded-lg border border-amber-900/40 bg-amber-950/10 px-3 py-2.5 mb-4 text-[11px] text-slate-300 leading-relaxed">
          <p>
            <strong className="text-amber-300">Périmètre de l'outil :</strong> sociétés <strong>françaises</strong> du secteur{' '}
            <strong className="text-cyan-300">TIC — Test, Inspection, Certification &amp; ingénierie technique</strong> (codes
            NAF 71.20B / 71.12B). Le scan cherche des <em>concurrents/cibles similaires</em> à l'URL fournie — donnez
            l'URL d'une société de ce secteur (ex. <code className="text-cyan-400">https://www.socotec.fr</code>), pas
            n'importe quelle entreprise : hors de ce périmètre, le scan ne trouvera rien.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-4 items-end">
          <div className="flex-1 w-full">
            <label className="text-[10px] text-slate-400 font-bold uppercase mb-1.5 block">
              URL d'une société TIC (plateforme ou cible de référence)
            </label>
            <div className="relative">
              <Globe size={14} className="absolute left-3 top-2.5 text-slate-500" />
              <input
                type="url"
                value={scanUrl}
                onChange={(e) => setScanUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleScan()}
                placeholder="https://www.socotec.fr"
                className="w-full bg-slate-950 border border-slate-700 rounded py-2 pl-9 pr-3 text-xs text-white font-mono placeholder-slate-600 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none transition-colors"
              />
            </div>
          </div>
          <button
            onClick={handleScan}
            disabled={scanMutation.isPending || !scanUrl.trim()}
            className="px-5 py-2 rounded text-xs font-bold uppercase tracking-wider transition-all inline-flex items-center gap-2
              bg-cyan-600 hover:bg-cyan-500 text-white disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed
              border border-cyan-500 disabled:border-slate-600 shadow-lg shadow-cyan-900/30 disabled:shadow-none"
          >
            <Radar size={14} className={scanMutation.isPending ? 'animate-spin' : ''} />
            {scanMutation.isPending ? 'SCANNING...' : 'LANCER LE SCAN OSINT'}
          </button>
        </div>
        <p className="text-[10px] text-slate-600 mt-3 font-mono">
          Le scan tourne en arrière-plan (1-3 min). Cliquez sur « Actualiser » pour voir les nouvelles cibles.
        </p>

        {/* D46 (Tâche Finalisation, Partie B) — bandeau de résultat persistant :
            le lien recherche → résultats doit être explicite et rester visible
            (contrairement au toast, qui s'efface après 9s). Liste les cibles
            RÉELLEMENT trouvées par CE scan (scanResult.saved_targets, jamais
            déduites en re-devinant depuis le tableau paginé ci-dessous). */}
        {scanResult && (
          <div className="mt-4 rounded-lg border border-cyan-800/50 bg-cyan-950/10 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="text-sm text-slate-200 min-w-0">
                <p className="font-mono text-[11px] text-cyan-400 uppercase tracking-wider mb-1.5">Résultat du scan</p>
                {scanResult.seed_company_name ? (
                  <>
                    <p>
                      Recherche : <strong className="text-white">{scanResult.seed_company_name}</strong>{' '}
                      <span className="text-slate-500">(point de départ)</span> →{' '}
                      <strong className={(scanResult.targets_saved ?? 0) > 0 ? 'text-emerald-400' : 'text-amber-400'}>
                        {scanResult.targets_saved ?? 0} cible{(scanResult.targets_saved ?? 0) !== 1 ? 's' : ''} TIC découverte{(scanResult.targets_saved ?? 0) !== 1 ? 's' : ''}
                      </strong>
                    </p>
                    <p className="text-[11px] text-slate-500 mt-1">
                      {scanResult.seed_company_name} elle-même n'est <strong>pas ajoutée</strong> comme cible : elle sert uniquement de point de départ pour découvrir des cibles similaires dans le secteur TIC.
                    </p>
                  </>
                ) : (
                  <p className="text-amber-300">Scan terminé pour {scanResult.platform_url}.</p>
                )}
                <p className="text-[11px] text-slate-500 mt-1.5 font-mono">
                  {scanResult.targets_found ?? 0} candidat{(scanResult.targets_found ?? 0) !== 1 ? 's' : ''} analysé{(scanResult.targets_found ?? 0) !== 1 ? 's' : ''}
                  {' · '}{scanResult.targets_scored ?? 0} retenu{(scanResult.targets_scored ?? 0) !== 1 ? 's' : ''} après scoring
                  {' · '}{scanResult.targets_saved ?? 0} ajouté{(scanResult.targets_saved ?? 0) !== 1 ? 's' : ''} en base
                  {(scanResult.targets_skipped ?? 0) > 0 ? ` (${scanResult.targets_skipped} déjà existant${scanResult.targets_skipped !== 1 ? 's' : ''})` : ''}
                  {' — '}<span className="text-slate-600">à distinguer du total « {totalCount} TARGETS IN DB » ci-dessus, qui compte toute la base, pas seulement ce scan.</span>
                </p>
              </div>
              <button
                onClick={() => setScanResult(null)}
                className="text-slate-500 hover:text-white shrink-0"
                aria-label="Fermer"
              >
                <X size={14} />
              </button>
            </div>

            {scanResult.saved_targets && scanResult.saved_targets.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {scanResult.saved_targets.map((t) => {
                  const visibleOnPage = targets.some((x) => x.id === t.id);
                  return (
                    <div key={t.id} className="flex items-center justify-between gap-2 rounded border border-slate-800 bg-slate-950/50 px-3 py-1.5 text-xs">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`font-mono font-bold w-8 text-right shrink-0 ${getScoreColor(t.score)}`}>{t.score?.toFixed(0) ?? '—'}</span>
                        <span className="text-slate-200 truncate">{t.company_name}</span>
                      </div>
                      {visibleOnPage ? (
                        <button
                          onClick={() => { setSearchQuery(t.company_name); setStatusFilter(''); setTypeFilter(''); }}
                          className="text-cyan-400 hover:text-cyan-300 text-[10px] font-mono shrink-0 inline-flex items-center gap-1"
                        >
                          Voir dans le tableau <Eye size={11} />
                        </button>
                      ) : (
                        // D47 (Tâche Finalisation, Partie A) : depuis le retrait du
                        // plafond à 50 (Partie B) et le rafraîchissement automatique
                        // de `targets` à la fin d'un scan (ci-dessus), ce cas ne
                        // devrait plus se produire en usage normal. S'il apparaît
                        // quand même, la vraie cause est un chargement pas encore à
                        // jour — jamais présenté comme "score bas", qui était faux
                        // (une cible à 75 s'est déjà retrouvée ici par le passé).
                        <button
                          onClick={() => refetch()}
                          className="text-amber-400 hover:text-amber-300 text-[10px] font-mono shrink-0 inline-flex items-center gap-1"
                          title="Cette cible est en base mais pas encore dans la liste chargée — cliquez pour rafraîchir."
                        >
                          Rafraîchir pour la voir <RefreshCw size={10} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {(scanResult.targets_saved ?? 0) === 0 && (
              <p className="mt-2 text-[11px] text-amber-300">
                Aucune cible retenue —{' '}
                {scanResult.error === 'Contenu plateforme insuffisant'
                  ? "le site n'a pas pu être analysé (contenu insuffisant ou page bloquée)"
                  : scanResult.error === 'Extraction ADN échouée'
                    ? "l'activité de la société n'a pas pu être identifiée depuis ce site"
                    : (scanResult.targets_found ?? 0) === 0
                      ? "aucun candidat n'a été trouvé par la recherche"
                      : "aucun candidat ne correspond au secteur TIC (test, inspection, certification, ingénierie technique) en France"}
                . Rappel : l'outil cible les sociétés françaises de ce secteur (NAF 71.20B/71.12B), pas n'importe quelle entreprise.
              </p>
            )}
          </div>
        )}
      </Card>

      <DocumentUpload />

      {/* ══════════════════════════════════════════
          Section Basse — Le Pipeline
         ══════════════════════════════════════════ */}
      <Card
        title="Pipeline M&A"
        subtitle={pipelineSubtitle}
        className="flex-1 min-h-[400px]"
        action={
          <button
            onClick={handleExportCSV}
            className="text-[10px] font-mono px-2.5 py-1 rounded border border-slate-700 text-slate-400 hover:text-emerald-400 hover:border-emerald-800 transition-all inline-flex items-center gap-1.5"
          >
            <FileSpreadsheet size={10} /> EXPORT CSV
          </button>
        }
      >
        {/* Filters Row */}
        <div className="flex flex-wrap gap-3 mb-4 items-center">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Rechercher une cible..."
              className="w-full bg-slate-950 border border-slate-700 rounded py-2 pl-9 pr-3 text-xs text-white focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
          </div>
          {['', 'Watchlist', 'Deep Dive', 'Active', 'Contacted', 'Passed', 'Archived'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`text-[10px] font-mono px-2.5 py-1.5 rounded border transition-all
                ${statusFilter === st
                  ? 'text-cyan-400 border-cyan-700 bg-cyan-950/40'
                  : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600'
                }`}
            >
              {st || 'TOUS'}
            </button>
          ))}
          {/* D47 (Tâche Finalisation, Partie B) : filtre par type de cible,
              absent jusqu'ici — séparé du filtre statut par une bordure fine. */}
          <div className="w-px h-5 bg-slate-800 mx-0.5" />
          {([['', 'Tous types'], ['target', 'Target'], ['platform', 'Platform']] as const).map(([tv, label]) => (
            <button
              key={tv}
              onClick={() => setTypeFilter(tv)}
              className={`text-[10px] font-mono px-2.5 py-1.5 rounded border transition-all
                ${typeFilter === tv
                  ? 'text-violet-300 border-violet-700 bg-violet-950/40'
                  : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600'
                }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Loading / Error states */}
        {isLoading && (
          <div className="flex items-center justify-center py-12 gap-2 text-slate-500 font-mono text-xs">
            <RefreshCw size={14} className="animate-spin" /> Chargement des cibles...
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center py-12 gap-2 text-rose-400 font-mono text-xs">
            <AlertTriangle size={14} /> Erreur : {error instanceof Error ? error.message : 'Impossible de charger'}
          </div>
        )}

        {/* Targets Table */}
        {!isLoading && !error && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="text-[10px] text-slate-500 border-b border-slate-700 bg-slate-900/50 sticky top-0 uppercase tracking-wider">
                  {/* D47 (Tâche Finalisation, Partie B) : tri par colonne — score,
                      nom, CA. Le reste (IRR/MOIC/statut/actions) n'a pas de valeur
                      pour toutes les lignes (souvent "—") ou n'a pas de sens à
                      trier (statut/actions), donc pas rendu triable. */}
                  <th className="py-3 px-4 font-semibold w-16 text-center">
                    <button type="button" onClick={() => toggleSort('score')} className="inline-flex items-center gap-0.5 hover:text-cyan-400">
                      Score {sortKey === 'score' && (sortDir === 'desc' ? <ChevronDown size={10} /> : <ChevronUp size={10} />)}
                    </button>
                  </th>
                  <th className="py-3 px-4 font-semibold">
                    <button type="button" onClick={() => toggleSort('name')} className="inline-flex items-center gap-0.5 hover:text-cyan-400">
                      Entreprise {sortKey === 'name' && (sortDir === 'desc' ? <ChevronDown size={10} /> : <ChevronUp size={10} />)}
                    </button>
                  </th>
                  <th className="py-3 px-4 font-semibold text-right">
                    <button type="button" onClick={() => toggleSort('revenue')} className="inline-flex items-center gap-0.5 hover:text-cyan-400 ml-auto">
                      CA Estimé {sortKey === 'revenue' && (sortDir === 'desc' ? <ChevronDown size={10} /> : <ChevronUp size={10} />)}
                    </button>
                  </th>
                  <th className="py-3 px-4 font-semibold text-right">IRR</th>
                  <th className="py-3 px-4 font-semibold text-right">MOIC</th>
                  <th className="py-3 px-4 font-semibold text-center">Statut</th>
                  <th className="py-3 px-4 font-semibold text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="text-xs font-mono">
                {sortedTargets.map((target, idx) => (
                  <React.Fragment key={target.id}>
                  <tr
                    className={`border-b border-slate-800/50 hover:bg-slate-800/70 transition-colors group ${idx % 2 === 0 ? 'bg-slate-900/20' : ''}`}
                  >
                    {/* Score */}
                    <td className="py-3 px-4">
                      <div className="flex flex-col items-center gap-1">
                        <span className={`text-sm font-bold ${getScoreColor(target.score)} tabular-nums`}>
                          {target.score !== null ? target.score.toFixed(0) : '—'}
                        </span>
                        <div className="w-10 h-1 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${getScoreBarColor(target.score)}`}
                            style={{ width: `${target.score ?? 0}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Entreprise */}
                    <td className="py-3 px-4 max-w-[320px]">
                      <div className="flex items-center gap-2">
                        <div className="font-bold text-slate-200 font-sans text-sm group-hover:text-cyan-400 transition-colors truncate">
                          {target.company_name}
                        </div>
                        {getTargetTypeBadge(target.target_type)}
                      </div>
                      <div className="text-[10px] text-slate-600 truncate flex items-center gap-1 mt-0.5">
                        <ExternalLink size={8} />
                        <a
                          href={target.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-cyan-400 transition-colors"
                        >
                          {target.url}
                        </a>
                        {/* D47 (Tâche Finalisation, Partie C) : provenance de la
                            cible, discrète (texte, pas un badge coloré) — cohérent
                            avec le reste du projet (ProvenanceBadge, title natif). */}
                        {target.source && (
                          <span
                            className="shrink-0 text-slate-700"
                            title={
                              target.source === 'registry' ? "Sourcée via le registre officiel (Sirene)"
                              : target.source === 'google_radar' ? "Sourcée via recherche Google Radar (concurrents/similaires)"
                              : target.source === 'document_upload' ? "Sourcée depuis un document (teaser/CIM) uploadé"
                              : target.source
                            }
                          >
                            · {target.source === 'registry' ? 'registre' : target.source === 'google_radar' ? 'radar' : target.source === 'document_upload' ? 'document' : target.source}
                          </span>
                        )}
                      </div>
                      {target.business_summary && (() => {
                        // D46 (Tâche Finalisation, Partie D) : matche sur le nom/URL
                        // (déjà visible ci-dessus) ou sur la description (invisible
                        // tant qu'elle est tronquée) — dans ce second cas, on affiche
                        // la description en entier et surlignée d'office, sinon
                        // l'utilisateur ne peut pas voir POURQUOI cette cible est
                        // sortie de sa recherche.
                        const q = searchQuery.trim().toLowerCase();
                        const matchesName = q && target.company_name.toLowerCase().includes(q);
                        const matchesSummary = q && target.business_summary!.toLowerCase().includes(q);
                        const forceExpand = Boolean(matchesSummary && !matchesName);
                        const isExpanded = forceExpand || expandedSummaryIds.has(target.id);

                        return (
                          <div className="mt-0.5">
                            {matchesSummary && !matchesName && (
                              <div className="text-[9px] text-cyan-400 font-mono uppercase tracking-wide mb-0.5">
                                correspondance dans la description
                              </div>
                            )}
                            <div className={isExpanded ? 'text-[10px] text-slate-400 max-w-[300px] whitespace-pre-wrap' : 'text-[10px] text-slate-500 truncate max-w-[300px]'}>
                              {isExpanded && q ? highlightMatch(target.business_summary!, searchQuery) : target.business_summary}
                            </div>
                            {!forceExpand && (
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); toggleSummary(target.id); }}
                                className="text-[9px] text-slate-600 hover:text-cyan-400 font-mono inline-flex items-center gap-0.5 mt-0.5"
                              >
                                {expandedSummaryIds.has(target.id) ? <>voir moins <ChevronUp size={9} /></> : <>voir plus <ChevronDown size={9} /></>}
                              </button>
                            )}
                          </div>
                        );
                      })()}
                    </td>

                    {/* CA Estimé */}
                    <td className="py-3 px-4 text-right text-slate-200 tabular-nums">
                      {formatRevenue(target.revenue_estimate)}
                    </td>

                    {/* IRR */}
                    <td className={`py-3 px-4 text-right font-bold tabular-nums ${
                      target.lbo_irr !== null && target.lbo_irr >= 20
                        ? 'text-emerald-400'
                        : target.lbo_irr !== null && target.lbo_irr > 0
                          ? 'text-amber-400'
                          : 'text-slate-500'
                    }`}>
                      {target.lbo_irr !== null ? `${(target.lbo_irr * 100).toFixed(1)}%` : '—'}
                    </td>

                    {/* MOIC */}
                    <td className={`py-3 px-4 text-right font-bold tabular-nums ${
                      target.lbo_moic !== null && target.lbo_moic >= 2.5
                        ? 'text-emerald-400'
                        : target.lbo_moic !== null && target.lbo_moic > 0
                          ? 'text-amber-400'
                          : 'text-slate-500'
                    }`}>
                      {target.lbo_moic !== null ? `${target.lbo_moic.toFixed(2)}x` : '—'}
                    </td>

                    {/* Status */}
                    <td className="py-3 px-4 text-center">
                      {getStatusBadge(target.status)}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          onClick={() => {
                            if (ddTargetId === target.id) { setDdTargetId(null); }
                            else { setDdTargetId(target.id); setActiveTab('digital-dd'); }
                          }}
                          className={`text-[10px] font-sans font-medium border rounded px-2.5 py-1 inline-flex items-center gap-1.5 transition-all ${
                            ddTargetId === target.id && activeTab === 'digital-dd'
                              ? 'text-violet-300 border-violet-700 bg-violet-950/40'
                              : 'text-slate-400 hover:text-violet-300 border-slate-700 hover:border-violet-700 bg-slate-800/50 hover:bg-violet-950/30'
                          }`}
                          title="Digital Due Diligence"
                        >
                          <Database size={10} /> DD
                        </button>
                        <button
                          onClick={() => {
                            if (ddTargetId === target.id && activeTab === 'legal') { setDdTargetId(null); }
                            else { setDdTargetId(target.id); setActiveTab('legal'); }
                          }}
                          className={`text-[10px] font-sans font-medium border rounded px-2.5 py-1 inline-flex items-center gap-1.5 transition-all ${
                            ddTargetId === target.id && activeTab === 'legal'
                              ? 'text-amber-300 border-amber-700 bg-amber-950/40'
                              : 'text-slate-400 hover:text-amber-300 border-slate-700 hover:border-amber-700 bg-slate-800/50 hover:bg-amber-950/30'
                          }`}
                          title="Corporate & Legal Signals"
                        >
                          <Scale size={10} /> LEGAL
                        </button>
                        <button
                          onClick={() => {
                            if (ddTargetId === target.id && activeTab === 'talent') { setDdTargetId(null); }
                            else { setDdTargetId(target.id); setActiveTab('talent'); }
                          }}
                          className={`text-[10px] font-sans font-medium border rounded px-2.5 py-1 inline-flex items-center gap-1.5 transition-all ${
                            ddTargetId === target.id && activeTab === 'talent'
                              ? 'text-emerald-300 border-emerald-700 bg-emerald-950/40'
                              : 'text-slate-400 hover:text-emerald-300 border-slate-700 hover:border-emerald-700 bg-slate-800/50 hover:bg-emerald-950/30'
                          }`}
                          title="Talent & HR Intelligence"
                        >
                          <Users size={10} /> HR
                        </button>
                        <button
                          onClick={() => {
                            if (ddTargetId === target.id && activeTab === 'comps') { setDdTargetId(null); }
                            else { setDdTargetId(target.id); setActiveTab('comps'); }
                          }}
                          className={`text-[10px] font-sans font-medium border rounded px-2.5 py-1 inline-flex items-center gap-1.5 transition-all ${
                            ddTargetId === target.id && activeTab === 'comps'
                              ? 'text-cyan-300 border-cyan-700 bg-cyan-950/40'
                              : 'text-slate-400 hover:text-cyan-300 border-slate-700 hover:border-cyan-700 bg-slate-800/50 hover:bg-cyan-950/30'
                          }`}
                          title="Market Comparables"
                        >
                          <BarChart3 size={10} /> COMPS
                        </button>
                        {target.status !== 'Archived' && (
                          target.promoted_deal_id ? (
                            <span
                              className="text-[10px] font-sans font-medium text-emerald-400 border border-emerald-800 bg-emerald-950/30 rounded px-2.5 py-1 inline-flex items-center gap-1.5"
                              title={`Déjà promue en deal #${target.promoted_deal_id}`}
                            >
                              <Rocket size={10} /> PROMUE
                            </span>
                          ) : (
                            <button
                              onClick={() => handlePromote(target)}
                              disabled={promoteMutation.isPending}
                              className="text-[10px] font-sans font-medium text-slate-400 hover:text-emerald-300 border border-slate-700 hover:border-emerald-700 bg-slate-800/50 hover:bg-emerald-950/30 rounded px-2.5 py-1 inline-flex items-center gap-1.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                              title="Promouvoir en deal (D14, Tâche B.5)"
                            >
                              <Rocket size={10} /> PROMOUVOIR
                            </button>
                          )
                        )}
                      </div>
                    </td>
                  </tr>

                  {/* ── Intelligence Expandable Panel (DD + Legal) ── */}
                  {ddTargetId === target.id && (
                    <tr>
                      <td colSpan={7} className="p-0">
                        <IntelligencePanel
                          targetId={target.id}
                          companyName={target.company_name}
                          keywords={target.keywords}
                          activeTab={activeTab}
                          onTabChange={setActiveTab}
                          onClose={() => setDdTargetId(null)}
                        />
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                ))}

                {filteredTargets.length === 0 && !isLoading && (
                  <tr>
                    <td colSpan={7} className="py-16 text-center text-slate-600 font-mono">
                      <div className="flex flex-col items-center gap-3">
                        <Radar size={32} className="text-slate-700" />
                        <span className="text-xs">AUCUNE CIBLE TROUVÉE</span>
                        <span className="text-[10px] text-slate-700">
                          Lancez un scan OSINT ci-dessus pour alimenter le pipeline.
                        </span>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};


// ============================================
// Sub-component: Intelligence Panel (Tabbed: DD + Legal)
// ============================================

const TECH_COLOR_MAP: Record<string, string> = {
  cyan: 'bg-cyan-900/40 text-cyan-300 border-cyan-800',
  violet: 'bg-violet-900/40 text-violet-300 border-violet-800',
  emerald: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  amber: 'bg-amber-900/40 text-amber-300 border-amber-800',
  blue: 'bg-blue-900/40 text-blue-300 border-blue-800',
  rose: 'bg-rose-900/40 text-rose-300 border-rose-800',
  orange: 'bg-orange-900/40 text-orange-300 border-orange-800',
  slate: 'bg-slate-800/60 text-slate-300 border-slate-700',
};

interface IntelligencePanelProps {
  targetId: number;
  companyName: string;
  keywords: string[] | null;
  activeTab: 'digital-dd' | 'legal' | 'talent' | 'comps';
  onTabChange: (tab: 'digital-dd' | 'legal' | 'talent' | 'comps') => void;
  onClose: () => void;
}

const IntelligencePanel: React.FC<IntelligencePanelProps> = ({ targetId, companyName, keywords, activeTab, onTabChange, onClose }) => {
  const { data: ddReport, isLoading: ddLoading, error: ddError } = useDigitalDD(activeTab === 'digital-dd' ? targetId : null);
  const { data: legalReport, isLoading: legalLoading, error: legalError } = useLegalEvents(activeTab === 'legal' ? targetId : null);
  const { data: talentReport, isLoading: talentLoading, error: talentError } = useTalentSignals(activeTab === 'talent' ? targetId : null);

  // D49 (Tâche Finalisation) : la valorisation de la vue détail réutilise
  // désormais le CompSet TIC réel + le calibrage sectoriel existants — même
  // dérivation de secteur que sourcing_service.py::promote_target_to_deal
  // (`keywords[0]`), pour que le multiple affiché ici reste cohérent avec
  // celui que le LBO base-case calculera après promotion.
  const sectorOrNaf = keywords && keywords.length > 0 ? keywords[0] : '';
  const { data: calibration, isLoading: calibLoading, error: calibError } = useSectorCalibration(
    sectorOrNaf, null, activeTab === 'comps' && !!sectorOrNaf,
  );
  const compSetReady = !!calibration?.applicable && !!calibration?.sufficient;
  const { data: compsTable } = useCompsTable(compSetReady ? calibration!.comp_set_id : null);

  return (
    <div className="bg-slate-950/80 border-t border-b border-violet-900/30 px-6 py-5 animate-in slide-in-from-top-2">
      {/* Header + Tabs */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          {/* Tabs */}
          <button
            onClick={() => onTabChange('digital-dd')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-bold uppercase tracking-wider border transition-all ${
              activeTab === 'digital-dd'
                ? 'text-violet-300 border-violet-700 bg-violet-950/50 shadow-lg shadow-violet-900/20'
                : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600'
            }`}
          >
            <Database size={12} /> Digital DD
          </button>
          <button
            onClick={() => onTabChange('legal')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-bold uppercase tracking-wider border transition-all ${
              activeTab === 'legal'
                ? 'text-amber-300 border-amber-700 bg-amber-950/50 shadow-lg shadow-amber-900/20'
                : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600'
            }`}
          >
            <Scale size={12} /> Corporate & Legal
          </button>
          <button
            onClick={() => onTabChange('talent')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-bold uppercase tracking-wider border transition-all ${
              activeTab === 'talent'
                ? 'text-emerald-300 border-emerald-700 bg-emerald-950/50 shadow-lg shadow-emerald-900/20'
                : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600'
            }`}
          >
            <Users size={12} /> Talent & HR
          </button>
          <button
            onClick={() => onTabChange('comps')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-bold uppercase tracking-wider border transition-all ${
              activeTab === 'comps'
                ? 'text-cyan-300 border-cyan-700 bg-cyan-950/50 shadow-lg shadow-cyan-900/20'
                : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-600'
            }`}
          >
            <BarChart3 size={12} /> Market Comps
          </button>

          <span className="text-[10px] font-mono text-slate-500 border border-slate-800 rounded px-1.5 py-0.5 ml-1">
            {companyName}
          </span>

          {/* Source badge */}
          {activeTab === 'digital-dd' && ddReport && (
            <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
              ddReport.tech_stack.source === 'builtwith'
                ? 'text-emerald-400 border-emerald-800 bg-emerald-950/30'
                : 'text-amber-400 border-amber-800 bg-amber-950/30'
            }`}>
              {ddReport.tech_stack.source === 'builtwith' ? 'LIVE DATA' : 'MOCK DATA'}
            </span>
          )}
          {activeTab === 'legal' && legalReport && (
            <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
              legalReport.source === 'pappers'
                ? 'text-emerald-400 border-emerald-800 bg-emerald-950/30'
                : 'text-amber-400 border-amber-800 bg-amber-950/30'
            }`}>
              {legalReport.source === 'pappers' ? 'PAPPERS LIVE' : 'MOCK DATA'}
            </span>
          )}
          {activeTab === 'talent' && talentReport && (
            <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
              talentReport.source === 'adzuna'
                ? 'text-emerald-400 border-emerald-800 bg-emerald-950/30'
                : 'text-amber-400 border-amber-800 bg-amber-950/30'
            }`}>
              {talentReport.source === 'adzuna' ? 'ADZUNA LIVE' : 'MOCK DATA'}
            </span>
          )}
          {/* D49 (Tâche Finalisation) : reflète l'état réel du calibrage CompSet
              (applicable/suffisant), plus l'ancien "fallback" d'un mécanisme
              retiré — jamais de badge "LIVE" tant que le calcul n'a pas
              réellement abouti sur un panel réel. */}
          {activeTab === 'comps' && calibration && (
            <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
              compSetReady
                ? 'text-emerald-400 border-emerald-800 bg-emerald-950/30'
                : 'text-amber-400 border-amber-800 bg-amber-950/30'
            }`}>
              {compSetReady ? 'COMPSET RÉEL' : 'HORS PÉRIMÈTRE CALIBRÉ'}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {/* ── Tab: Digital DD ── */}
      {activeTab === 'digital-dd' && (
        <>
          {ddLoading && (
            <div className="flex items-center justify-center py-8 gap-2 text-slate-500 font-mono text-xs">
              <RefreshCw size={14} className="animate-spin text-violet-500" />
              Analyse Digital DD en cours...
            </div>
          )}
          {ddError && (
            <div className="flex items-center justify-center py-6 gap-2 text-rose-400 font-mono text-xs">
              <AlertTriangle size={14} />
              Erreur : {ddError instanceof Error ? ddError.message : 'Impossible de charger le rapport'}
            </div>
          )}
          {ddReport && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Tech Stack */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Cpu size={12} className="text-cyan-400" />
                  <span className="text-[11px] font-bold uppercase text-slate-300 tracking-wider">
                    Tech Stack
                  </span>
                  <span className="text-[9px] font-mono text-slate-600">
                    {ddReport.tech_stack.technologies.length} technos
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {ddReport.tech_stack.technologies.map((tech: TechStackItem, idx: number) => {
                    const colorClasses = TECH_COLOR_MAP[tech.color || 'slate'] || TECH_COLOR_MAP.slate;
                    return (
                      <span
                        key={idx}
                        className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-mono font-medium border ${colorClasses}`}
                        title={tech.category}
                      >
                        {tech.name}
                      </span>
                    );
                  })}
                </div>
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
                  {Array.from(new Set(ddReport.tech_stack.technologies.map((t: TechStackItem) => t.category))).map((cat) => (
                    <span key={String(cat)} className="text-[9px] text-slate-600 font-mono">
                      {String(cat)}
                    </span>
                  ))}
                </div>
              </div>

              {/* Search Trends */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp size={12} className="text-emerald-400" />
                  <span className="text-[11px] font-bold uppercase text-slate-300 tracking-wider">
                    Google Search Interest
                  </span>
                  <span className="text-[9px] font-mono text-slate-600">
                    12 mois · "{ddReport.search_trends.keyword}"
                  </span>
                </div>
                <div className="h-[180px] w-full bg-slate-900/40 border border-slate-800 rounded p-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={ddReport.search_trends.points}>
                      <defs>
                        <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#06b6d4" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 9, fill: '#64748b' }}
                        tickFormatter={(d: string) => {
                          const dt = new Date(d);
                          return dt.toLocaleDateString('fr-FR', { month: 'short' });
                        }}
                        interval={6}
                        axisLine={{ stroke: '#334155' }}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 9, fill: '#64748b' }}
                        domain={[0, 100]}
                        axisLine={false}
                        tickLine={false}
                        width={28}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: '6px',
                          fontSize: '11px',
                          fontFamily: 'monospace',
                        }}
                        labelFormatter={(d: string) => new Date(d).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}
                        formatter={(value: number) => [`${value}`, 'Intérêt']}
                      />
                      <Area
                        type="monotone"
                        dataKey="value"
                        stroke="#06b6d4"
                        strokeWidth={2}
                        fill="url(#trendGradient)"
                        dot={false}
                        activeDot={{ r: 3, fill: '#06b6d4', strokeWidth: 0 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                {ddReport.search_trends.points.length > 4 && (
                  <TrendSummary points={ddReport.search_trends.points} />
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Tab: Legal & Corporate ── */}
      {activeTab === 'legal' && (
        <>
          {legalLoading && (
            <div className="flex items-center justify-center py-8 gap-2 text-slate-500 font-mono text-xs">
              <RefreshCw size={14} className="animate-spin text-amber-500" />
              Interrogation du registre corporate...
            </div>
          )}
          {legalError && (
            <div className="flex items-center justify-center py-6 gap-2 text-rose-400 font-mono text-xs">
              <AlertTriangle size={14} />
              Erreur : {legalError instanceof Error ? legalError.message : 'Impossible de charger les événements'}
            </div>
          )}
          {legalReport && (
            <div>
              {/* SIREN + stats bar */}
              <div className="flex items-center gap-4 mb-5 text-[10px] font-mono text-slate-500">
                <span>SIREN : <b className="text-slate-300">{legalReport.siren}</b></span>
                <span className="text-slate-700">|</span>
                <span>{legalReport.events.length} événement{legalReport.events.length !== 1 ? 's' : ''}</span>
                <span className="text-slate-700">|</span>
                <SignalSummary events={legalReport.events} />
              </div>

              {/* Timeline */}
              <LegalTimeline events={legalReport.events} />
            </div>
          )}
        </>
      )}

      {/* ── Tab: Talent & HR Intelligence ── */}
      {activeTab === 'talent' && (
        <>
          {talentLoading && (
            <div className="flex items-center justify-center py-8 gap-2 text-slate-500 font-mono text-xs">
              <RefreshCw size={14} className="animate-spin text-emerald-500" />
              Analyse des signaux RH en cours...
            </div>
          )}
          {talentError && (
            <div className="flex items-center justify-center py-6 gap-2 text-rose-400 font-mono text-xs">
              <AlertTriangle size={14} />
              Erreur : {talentError instanceof Error ? talentError.message : 'Impossible de charger les signaux RH'}
            </div>
          )}
          {talentReport && <TalentPanel report={talentReport} />}
        </>
      )}

      {/* ── Tab: Market Comps (D49 : CompSet TIC réel + calibrage, plus de
          peers fabriqués) ── */}
      {activeTab === 'comps' && (
        <>
          {!sectorOrNaf && (
            <div className="flex items-center justify-center py-6 gap-2 text-amber-400 font-mono text-xs">
              <AlertTriangle size={14} />
              Aucun mot-clé de qualification connu pour cette cible — impossible de résoudre un secteur, donc de dériver un multiple.
            </div>
          )}
          {sectorOrNaf && calibLoading && (
            <div className="flex items-center justify-center py-8 gap-2 text-slate-500 font-mono text-xs">
              <RefreshCw size={14} className="animate-spin text-cyan-500" />
              Calcul de la médiane du CompSet…
            </div>
          )}
          {sectorOrNaf && calibError && (
            <div className="flex items-center justify-center py-6 gap-2 text-rose-400 font-mono text-xs">
              <AlertTriangle size={14} />
              Erreur : {calibError instanceof Error ? calibError.message : 'Impossible de charger le calibrage'}
            </div>
          )}
          {sectorOrNaf && !calibLoading && calibration && (
            <TargetValuationPanel companyName={companyName} calibration={calibration} compsTable={compsTable ?? null} />
          )}
        </>
      )}
    </div>
  );
};


// ============================================
// Sub-component: Signal Summary (counts)
// ============================================

const SignalSummary: React.FC<{ events: CorporateEvent[] }> = ({ events }) => {
  const bullish = events.filter(e => e.signal === 'Bullish').length;
  const neutral = events.filter(e => e.signal === 'Neutral').length;
  const redFlag = events.filter(e => e.signal === 'Red Flag').length;

  return (
    <span className="inline-flex items-center gap-3">
      {bullish > 0 && (
        <span className="inline-flex items-center gap-1 text-emerald-400">
          <ArrowUpRight size={10} /> {bullish} Bullish
        </span>
      )}
      {neutral > 0 && (
        <span className="inline-flex items-center gap-1 text-slate-400">
          <Minus size={10} /> {neutral} Neutral
        </span>
      )}
      {redFlag > 0 && (
        <span className="inline-flex items-center gap-1 text-rose-400">
          <Flag size={10} /> {redFlag} Red Flag
        </span>
      )}
    </span>
  );
};


// ============================================
// Sub-component: Legal Events Timeline
// ============================================

const SIGNAL_CONFIG: Record<MaSignal, { color: string; dotColor: string; borderColor: string; bgColor: string; icon: React.ReactNode }> = {
  'Bullish': {
    color: 'text-emerald-400',
    dotColor: 'bg-emerald-500',
    borderColor: 'border-emerald-800',
    bgColor: 'bg-emerald-950/30',
    icon: <ArrowUpRight size={10} />,
  },
  'Neutral': {
    color: 'text-slate-400',
    dotColor: 'bg-slate-500',
    borderColor: 'border-slate-700',
    bgColor: 'bg-slate-800/40',
    icon: <Minus size={10} />,
  },
  'Red Flag': {
    color: 'text-rose-400',
    dotColor: 'bg-rose-500',
    borderColor: 'border-rose-800',
    bgColor: 'bg-rose-950/30',
    icon: <Flag size={10} />,
  },
};

const LegalTimeline: React.FC<{ events: CorporateEvent[] }> = ({ events }) => {
  return (
    <div className="relative pl-6">
      {/* Vertical line */}
      <div className="absolute left-[9px] top-2 bottom-2 w-px bg-gradient-to-b from-slate-600 via-slate-700 to-slate-800" />

      <div className="space-y-4">
        {events.map((evt, idx) => {
          const config = SIGNAL_CONFIG[evt.signal] || SIGNAL_CONFIG['Neutral'];
          const formattedDate = evt.date
            ? new Date(evt.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
            : 'Date inconnue';

          return (
            <div key={idx} className="relative group">
              {/* Timeline dot */}
              <div className={`absolute -left-6 top-2.5 w-[11px] h-[11px] rounded-full border-2 border-slate-900 ${config.dotColor} shadow-lg shadow-black/50 group-hover:scale-125 transition-transform`} />

              {/* Event card */}
              <div className={`rounded-lg border ${config.borderColor} ${config.bgColor} p-3.5 hover:brightness-110 transition-all`}>
                <div className="flex items-start justify-between gap-3">
                  {/* Left: content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      {/* Date */}
                      <span className="text-[10px] font-mono text-slate-500 tabular-nums">
                        {formattedDate}
                      </span>
                      {/* Source badge */}
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/60 text-slate-500">
                        {evt.source}
                      </span>
                    </div>

                    {/* Label */}
                    <div className="text-[12px] font-bold text-slate-200 font-sans mb-1">
                      {evt.label}
                    </div>

                    {/* Description */}
                    {evt.description && (
                      <div className="text-[10px] text-slate-500 leading-relaxed line-clamp-2">
                        {evt.description}
                      </div>
                    )}
                  </div>

                  {/* Right: Signal badge */}
                  <div className={`flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold font-mono border ${config.borderColor} ${config.bgColor} ${config.color}`}>
                    {config.icon}
                    {evt.signal === 'Red Flag' ? 'RED FLAG' : evt.signal.toUpperCase()}
                  </div>
                </div>

                {/* Signal reason */}
                {evt.signal_reason && (
                  <div className={`mt-2 text-[9px] font-mono ${config.color} opacity-80`}>
                    → {evt.signal_reason}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};


// ============================================
// Sub-component: Talent & HR Panel
// ============================================

const TREND_SIGNAL_CONFIG: Record<string, { color: string; bgColor: string; borderColor: string; label: string }> = {
  'Hyper-Growth': { color: 'text-emerald-400', bgColor: 'bg-emerald-950/40', borderColor: 'border-emerald-800', label: 'HYPER-GROWTH' },
  'Growth': { color: 'text-cyan-400', bgColor: 'bg-cyan-950/40', borderColor: 'border-cyan-800', label: 'GROWTH' },
  'Stable': { color: 'text-slate-400', bgColor: 'bg-slate-800/50', borderColor: 'border-slate-700', label: 'STABLE' },
  'Contraction': { color: 'text-rose-400', bgColor: 'bg-rose-950/40', borderColor: 'border-rose-800', label: 'CONTRACTION' },
  'Low Activity': { color: 'text-amber-400', bgColor: 'bg-amber-950/40', borderColor: 'border-amber-800', label: 'LOW ACTIVITY' },
};

const JOB_CATEGORY_COLORS: Record<string, string> = {
  'Tech': 'bg-cyan-900/40 text-cyan-300 border-cyan-800',
  'Sales': 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  'Finance': 'bg-amber-900/40 text-amber-300 border-amber-800',
  'Operations': 'bg-blue-900/40 text-blue-300 border-blue-800',
  'Executive': 'bg-violet-900/40 text-violet-300 border-violet-800',
  'Other': 'bg-slate-800/50 text-slate-300 border-slate-700',
};

const TalentPanel: React.FC<{ report: TalentSignalsReport }> = ({ report }) => {
  const trendConfig = TREND_SIGNAL_CONFIG[report.trend_signal] || TREND_SIGNAL_CONFIG['Stable'];
  const velocityColor = report.hiring_velocity_score >= 70
    ? 'text-emerald-400'
    : report.hiring_velocity_score >= 40
      ? 'text-cyan-400'
      : report.hiring_velocity_score >= 20
        ? 'text-amber-400'
        : 'text-slate-400';
  const velocityBarColor = report.hiring_velocity_score >= 70
    ? 'bg-emerald-500'
    : report.hiring_velocity_score >= 40
      ? 'bg-cyan-500'
      : report.hiring_velocity_score >= 20
        ? 'bg-amber-500'
        : 'bg-slate-600';

  const execJobs = report.recent_job_openings.filter(j => j.is_executive);
  const regularJobs = report.recent_job_openings.filter(j => !j.is_executive);

  return (
    <div className="space-y-5">
      {/* ── KPI Row ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Hiring Velocity Score */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 size={12} className="text-emerald-400" />
            <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Vélocité RH</span>
          </div>
          <div className={`text-2xl font-black tabular-nums ${velocityColor}`}>
            {report.hiring_velocity_score}
            <span className="text-sm font-normal text-slate-500">/100</span>
          </div>
          <div className="mt-2 w-full h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${velocityBarColor}`}
              style={{ width: `${report.hiring_velocity_score}%` }}
            />
          </div>
        </div>

        {/* Headcount Trend */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={12} className="text-cyan-400" />
            <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Effectifs</span>
          </div>
          <div className={`text-2xl font-black tabular-nums ${
            report.headcount_trend.startsWith('+') && parseInt(report.headcount_trend) >= 10
              ? 'text-emerald-400'
              : report.headcount_trend.startsWith('+')
                ? 'text-cyan-400'
                : report.headcount_trend.startsWith('-')
                  ? 'text-rose-400'
                  : 'text-slate-400'
          }`}>
            {report.headcount_trend}
          </div>
          <div className="mt-2">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-bold font-mono border ${trendConfig.borderColor} ${trendConfig.bgColor} ${trendConfig.color}`}>
              {report.trend_signal === 'Hyper-Growth' && <ArrowUpRight size={9} />}
              {trendConfig.label}
            </span>
          </div>
        </div>

        {/* Total Openings */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <Briefcase size={12} className="text-violet-400" />
            <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Postes Ouverts</span>
          </div>
          <div className="text-2xl font-black tabular-nums text-slate-200">
            {report.total_openings}
          </div>
          <div className="mt-2 text-[9px] font-mono text-slate-500">
            {execJobs.length > 0 && (
              <span className="text-violet-400">{execJobs.length} executive</span>
            )}
            {execJobs.length > 0 && regularJobs.length > 0 && ' · '}
            {regularJobs.length > 0 && (
              <span>{regularJobs.length} opérationnels</span>
            )}
          </div>
        </div>

        {/* Department Breakdown */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <Users size={12} className="text-amber-400" />
            <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Par Département</span>
          </div>
          <div className="space-y-1.5">
            {Object.entries(report.department_breakdown)
              .sort(([, a], [, b]) => (b as number) - (a as number))
              .map(([dept, count]) => {
                const c = count as number;
                const total = report.recent_job_openings.length;
                const pct = total > 0 ? Math.round((c / total) * 100) : 0;
                return (
                  <div key={dept} className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-slate-500 w-16 truncate">{dept}</span>
                    <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          dept === 'Tech' ? 'bg-cyan-500' :
                          dept === 'Sales' ? 'bg-emerald-500' :
                          dept === 'Finance' ? 'bg-amber-500' :
                          dept === 'Executive' ? 'bg-violet-500' :
                          dept === 'Operations' ? 'bg-blue-500' : 'bg-slate-600'
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-[9px] font-mono text-slate-400 tabular-nums w-6 text-right">{count}</span>
                  </div>
                );
              })}
          </div>
        </div>
      </div>

      {/* ── Executive Hires (highlighted) ── */}
      {execJobs.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Star size={12} className="text-violet-400" />
            <span className="text-[11px] font-bold uppercase text-slate-300 tracking-wider">
              Executive Hires
            </span>
            <span className="text-[9px] font-mono text-violet-400">
              {execJobs.length} poste{execJobs.length > 1 ? 's' : ''} clé{execJobs.length > 1 ? 's' : ''}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {execJobs.map((job, idx) => (
              <div
                key={idx}
                className="bg-violet-950/30 border border-violet-800/60 rounded-lg p-3 hover:border-violet-600 transition-all group"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-bold text-violet-200 group-hover:text-violet-100 transition-colors truncate">
                      {job.title}
                    </div>
                    {job.location && (
                      <div className="flex items-center gap-1 mt-1 text-[9px] text-slate-500">
                        <MapPin size={8} /> {job.location}
                      </div>
                    )}
                    {job.posted_date && (
                      <div className="text-[9px] font-mono text-slate-600 mt-0.5">
                        {new Date(job.posted_date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
                      </div>
                    )}
                  </div>
                  <span className="flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[8px] font-bold font-mono border border-violet-700 bg-violet-900/50 text-violet-300">
                    <Star size={8} /> EXEC
                  </span>
                </div>
                {job.salary_range && (
                  <div className="mt-1.5 text-[9px] font-mono text-emerald-400">
                    {job.salary_range}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── All Job Openings ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Briefcase size={12} className="text-cyan-400" />
          <span className="text-[11px] font-bold uppercase text-slate-300 tracking-wider">
            Postes Récents
          </span>
          <span className="text-[9px] font-mono text-slate-600">
            {report.recent_job_openings.length} offres
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {report.recent_job_openings.map((job, idx) => {
            const catColors = JOB_CATEGORY_COLORS[job.category] || JOB_CATEGORY_COLORS['Other'];
            return (
              <div
                key={idx}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-mono border ${catColors} hover:brightness-125 transition-all`}
                title={`${job.category} · ${job.location || 'N/A'} · ${job.posted_date || ''}`}
              >
                {job.is_executive && <Star size={9} className="text-violet-400 flex-shrink-0" />}
                <span className="truncate max-w-[200px]">{job.title}</span>
                {job.location && (
                  <span className="text-[8px] opacity-60 flex-shrink-0">
                    {job.location.split(',')[0]}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};


// ============================================
// Sub-component: Trend Summary Stats
// ============================================

const TrendSummary: React.FC<{ points: SearchTrendPoint[] }> = ({ points }) => {
  const values = points.map(p => p.value);
  const current = values[values.length - 1] ?? 0;
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const max = Math.max(...values);
  const min = Math.min(...values);
  // Compare first quarter to last quarter
  const q1Avg = values.slice(0, Math.floor(values.length / 4)).reduce((a, b) => a + b, 0) / Math.floor(values.length / 4);
  const q4Avg = values.slice(-Math.floor(values.length / 4)).reduce((a, b) => a + b, 0) / Math.floor(values.length / 4);
  const momentum = q4Avg - q1Avg;

  return (
    <div className="mt-2 flex flex-wrap gap-4 text-[9px] font-mono text-slate-500">
      <span>Actuel : <b className="text-slate-300">{current}</b></span>
      <span>Moy. : <b className="text-slate-300">{avg.toFixed(0)}</b></span>
      <span>Peak : <b className="text-cyan-400">{max}</b></span>
      <span>Low : <b className="text-slate-400">{min}</b></span>
      <span>
        Momentum :{' '}
        <b className={momentum >= 5 ? 'text-emerald-400' : momentum <= -5 ? 'text-rose-400' : 'text-slate-300'}>
          {momentum >= 0 ? '+' : ''}{momentum.toFixed(0)}
          {momentum >= 5 ? ' ▲' : momentum <= -5 ? ' ▼' : ' →'}
        </b>
      </span>
    </div>
  );
};


// ============================================
// Sub-component: Target Valuation Panel (D49, Tâche Finalisation)
// ============================================
// Remplace l'ancien "Market Comps" (public peers LLM en texte libre, private
// peers fabriqués via un repli Pappers systématique — voir historique Git,
// api/services/comps_service.py). Un seul système de valorisation dans tout
// l'outil désormais : le CompSet TIC réel + le calibrage sectoriel déjà
// utilisés par le LBO Calculator et la page Comparables (D22).

const formatBigNumber = (value: number | null): string => {
  if (value === null) return '—';
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)} B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} K`;
  return `${value.toFixed(0)}`;
};

const TargetValuationPanel: React.FC<{
  companyName: string;
  calibration: SectorCalibration;
  compsTable: CompsTableResponse | null;
}> = ({ companyName, calibration, compsTable }) => {
  return (
    <div className="space-y-5">
      <div className="text-[11px] text-slate-400 leading-relaxed">
        Sociétés comparables servant à <strong className="text-slate-200">estimer la valorisation</strong> de{' '}
        <strong className="text-slate-200">{companyName}</strong> (multiple EV/EBITDA) —
        pas une liste de cibles d'acquisition (voir Buy &amp; Build pour ça).
      </div>

      {!calibration.applicable && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-800/60 bg-amber-950/20 p-4 text-xs text-amber-300">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{calibration.fallback_reason ?? 'Calibrage non applicable pour ce secteur.'}</span>
        </div>
      )}

      {calibration.applicable && !calibration.sufficient && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-800/60 bg-amber-950/20 p-4 text-xs text-amber-300">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{calibration.fallback_reason}</span>
        </div>
      )}

      {calibration.applicable && calibration.sufficient && (
        <>
          {/* Chaîne de raisonnement — même format que LBO Calculator (D22) */}
          <div className="bg-cyan-950/30 border border-cyan-800/60 rounded-lg p-4">
            <div className="text-[10px] font-bold uppercase text-cyan-300 tracking-wider mb-1 flex items-center gap-2">
              Multiple d'entrée dérivé
              <ProvenanceBadge provenance={calibration.entry_multiple_provenance} />
            </div>
            <div className="text-3xl font-black text-white tabular-nums">
              {calibration.derived_entry_multiple !== null ? `${calibration.derived_entry_multiple.toFixed(2)}x EBITDA` : 'N/A'}
            </div>
            <div className="font-mono text-[11px] text-slate-400 mt-2 space-y-0.5">
              <div>= {calibration.median_ev_ebitda?.toFixed(2)}x médiane comparables (n={calibration.sample_size}, FY{[...new Set(calibration.fiscal_years)].sort().join('-')})</div>
              <div className="text-rose-400">− {(calibration.size_illiquidity_discount * 100).toFixed(0)}% {calibration.discount_label}</div>
            </div>
          </div>

          {/* Positionnement — même principe que le deck IC (ic_deck_generator.py::_positioning_bar) */}
          {compsTable && compsTable.rows.some(r => r.ev_ebitda != null) && (() => {
            const values = compsTable.rows.map(r => r.ev_ebitda).filter((v): v is number => v != null);
            const lo = Math.min(...values, calibration.derived_entry_multiple ?? Infinity) - 0.5;
            const hi = Math.max(...values, calibration.derived_entry_multiple ?? -Infinity) + 0.5;
            const pct = (v: number) => Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100));
            return (
              <div className="px-1">
                <div className="relative h-1.5 bg-slate-800 rounded-full mb-1">
                  {calibration.median_ev_ebitda != null && (
                    <div className="absolute top-1/2 -translate-y-1/2 w-px h-3 bg-slate-500" style={{ left: `${pct(calibration.median_ev_ebitda)}%` }} title="Médiane" />
                  )}
                  {calibration.derived_entry_multiple != null && (
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-cyan-400 border border-cyan-200 shadow"
                      style={{ left: `${pct(calibration.derived_entry_multiple)}%`, transform: 'translate(-50%, -50%)' }}
                      title={`${calibration.derived_entry_multiple.toFixed(2)}x retenu`}
                    />
                  )}
                </div>
                <div className="flex justify-between text-[9px] text-slate-600 font-mono">
                  <span>{lo.toFixed(1)}x</span>
                  <span>médiane {calibration.median_ev_ebitda?.toFixed(1)}x</span>
                  <span>{hi.toFixed(1)}x</span>
                </div>
              </div>
            );
          })()}

          {/* Table des comparables réels du CompSet */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <BarChart3 size={12} className="text-cyan-400" />
              <span className="text-[11px] font-bold uppercase text-slate-300 tracking-wider">Comparables cotés — {calibration.comp_set_name}</span>
              <span className="text-[9px] font-mono text-slate-600">{compsTable?.rows.length ?? calibration.sample_size} sociétés</span>
            </div>
            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-[10px] text-slate-500 border-b border-slate-800 bg-slate-900/60 uppercase tracking-wider">
                    <th className="py-2 px-3 font-semibold">Ticker</th>
                    <th className="py-2 px-3 font-semibold">Nom</th>
                    <th className="py-2 px-3 font-semibold text-right">EV</th>
                    <th className="py-2 px-3 font-semibold text-right">EBITDA</th>
                    <th className="py-2 px-3 font-semibold text-right">EV/EBITDA</th>
                    <th className="py-2 px-3 font-semibold text-right">Exercice</th>
                  </tr>
                </thead>
                <tbody className="text-[11px] font-mono">
                  {(compsTable?.rows ?? []).map((row: CompRow) => (
                    <tr key={row.ticker} className="border-b border-slate-800/60 hover:bg-slate-900/40">
                      <td className="py-2 px-3 text-cyan-300 font-bold">{row.ticker}</td>
                      <td className="py-2 px-3 text-slate-300 max-w-[220px] truncate" title={row.name}>{row.name}</td>
                      <td className="py-2 px-3 text-right text-slate-300 tabular-nums">{formatBigNumber(row.enterprise_value)}</td>
                      <td className="py-2 px-3 text-right text-slate-300 tabular-nums">{formatBigNumber(row.ebitda)}</td>
                      <td className="py-2 px-3 text-right tabular-nums font-bold text-emerald-300">
                        <span className="inline-flex items-center gap-1">
                          {row.ev_ebitda !== null ? `${row.ev_ebitda.toFixed(2)}x` : '—'}
                          <ProvenanceBadge provenance={row.financial_provenance?.ev_ebitda} />
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right text-slate-400 tabular-nums">{row.fiscal_year ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between mt-2 text-[9px] text-slate-600 font-mono">
              <span>
                Marge EBITDA médiane {calibration.median_ebitda_margin != null ? (calibration.median_ebitda_margin * 100).toFixed(1) : '—'}%
                <ProvenanceBadge provenance={calibration.ebitda_margin_provenance} />
                {' '}— leaders mondiaux cotés, une PME française se situe généralement en dessous.
              </span>
              {calibration.comp_set_id != null && (
                <Link
                  to={`/comparables?compSetId=${calibration.comp_set_id}`}
                  className="shrink-0 text-cyan-400 hover:text-cyan-300 underline decoration-cyan-800 whitespace-nowrap ml-3"
                >
                  Voir la page Comparables complète →
                </Link>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
