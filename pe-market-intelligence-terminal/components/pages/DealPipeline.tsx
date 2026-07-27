import React, { useEffect, useMemo, useState } from 'react';
import { KanbanSquare, Building2, BadgeEuro, TrendingUp, Loader2, RefreshCw, GripVertical, Layers } from 'lucide-react';
import {
  DndContext,
  DragOverlay,
  MouseSensor,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
  useDroppable,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useDeals, useUpdateDealStatusMutation, useLboScenarios } from '../../hooks/useQueries';
import type { Deal } from '../../../shared/types';

// D31 (Tâche Review Produit — Partie A) : Deal Pipeline suit désormais le
// cycle de vie réel d'un deal PROMU (table `deals`, `Deal.status`) — pas la
// qualification pré-promotion des cibles sourcing (ça, c'est Deal Sourcing).
// Un mémo généré fait automatiquement avancer un deal de Screening à IC
// Review (voir api/routers/deals.py::generate_memo) ; le reste se déplace
// manuellement par glisser-déposer.
type DealStage = 'Screening' | 'IC Review' | 'Approved' | 'Closed' | 'Passed';

const DEAL_STAGES: DealStage[] = ['Screening', 'IC Review', 'Approved', 'Closed', 'Passed'];

const STAGE_THEME: Record<DealStage, string> = {
  Screening: 'border-cyan-900/60 bg-cyan-950/10',
  'IC Review': 'border-fuchsia-900/60 bg-fuchsia-950/10',
  Approved: 'border-emerald-900/60 bg-emerald-950/10',
  Closed: 'border-slate-600 bg-slate-800/40',
  Passed: 'border-slate-700 bg-slate-900/60',
};

const formatMoney = (value: number | null): string => {
  if (!value) return 'N/D';
  if (value >= 1_000_000_000) return `€${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `€${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `€${(value / 1_000).toFixed(0)}K`;
  return `€${value.toFixed(0)}`;
};

const resolveStage = (deal: Deal): DealStage =>
  (DEAL_STAGES as string[]).includes(deal.status) ? (deal.status as DealStage) : 'Screening';

/** Scénario de référence côté client — même heuristique que
 * `lbo_scenario_service.get_reference_scenario` côté backend (libellé
 * contenant "base", sinon le plus récent) : garde le mémo et la carte
 * cohérents sur le même scénario cité. */
const useReferenceScenario = (dealId: number) => {
  const { data: scenarios, isLoading } = useLboScenarios(dealId);
  const reference = useMemo(() => {
    if (!scenarios || scenarios.length === 0) return null;
    return scenarios.find((s) => s.label.toLowerCase().includes('base')) ?? scenarios[0];
  }, [scenarios]);
  return { reference, isLoading, hasScenario: !!scenarios && scenarios.length > 0 };
};

interface DealCardProps {
  deal: Deal;
  stage: DealStage;
  isSaving: boolean;
}

const DealCard: React.FC<DealCardProps> = ({ deal, stage, isSaving }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: `card:${deal.id}`,
    data: { stage, dealId: deal.id },
  });
  const { reference, isLoading: scenarioLoading, hasScenario } = useReferenceScenario(deal.id);

  const style = { transform: CSS.Transform.toString(transform), transition };
  const irr = reference?.irr;
  const moic = reference?.moic;
  const irrColor = irr != null ? (irr >= 0.2 ? 'text-emerald-400' : 'text-amber-400') : 'text-slate-600';
  const moicColor = moic != null ? (moic >= 2.5 ? 'text-emerald-400' : 'text-amber-400') : 'text-slate-600';

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`bg-slate-900 border rounded-lg p-3 space-y-2.5 shadow-lg transition-all ${
        isDragging ? 'opacity-70 border-cyan-500/70 shadow-2xl shadow-cyan-900/40' : 'border-slate-800'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">{deal.target_name ?? 'Deal sans nom'}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            {deal.target_type && (
              <span
                className={`text-[9px] font-mono px-1 py-0.5 rounded border uppercase ${
                  deal.target_type === 'platform'
                    ? 'text-violet-300 border-violet-800 bg-violet-950/30'
                    : 'text-cyan-300 border-cyan-800 bg-cyan-950/30'
                }`}
              >
                {deal.target_type}
              </span>
            )}
            <p className="text-[10px] text-slate-500 uppercase tracking-wider truncate">{deal.sector ?? 'N/D'}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {isSaving && <Loader2 size={14} className="text-cyan-400 animate-spin flex-shrink-0 mt-0.5" />}
          <button
            type="button"
            className="p-1 rounded border border-slate-700 bg-slate-800/70 text-slate-500 hover:text-cyan-300 hover:border-cyan-700 cursor-grab active:cursor-grabbing"
            {...attributes}
            {...listeners}
            aria-label="Drag deal card"
          >
            <GripVertical size={12} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px] font-mono">
        <div className="flex items-center gap-1.5 text-slate-300">
          <BadgeEuro size={11} className="text-slate-500 flex-shrink-0" />
          <span>CA {formatMoney(deal.target_revenue)}</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-300">
          <Building2 size={11} className="text-slate-500 flex-shrink-0" />
          <span>EBITDA {formatMoney(deal.target_ebitda)}</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-300">
          <Layers size={11} className="text-slate-500 flex-shrink-0" />
          <span>Entrée {reference?.entry_multiple != null ? `${reference.entry_multiple.toFixed(1)}x` : '—'}</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-300">
          <TrendingUp size={11} className="text-slate-500 flex-shrink-0" />
          <span className={irrColor}>
            IRR {irr != null ? `${(irr * 100).toFixed(1)}%` : '—'}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between pt-1 border-t border-slate-800/60">
        <span className={`text-[11px] font-mono font-bold ${moicColor}`}>
          MOIC {moic != null ? `${moic.toFixed(2)}x` : '—'}
        </span>
        <div className="flex items-center gap-1">
          <span
            className={`text-[8px] font-mono px-1.5 py-0.5 rounded border ${
              scenarioLoading
                ? 'text-slate-600 border-slate-800'
                : hasScenario
                  ? 'text-emerald-400 border-emerald-900 bg-emerald-950/20'
                  : 'text-slate-600 border-slate-800'
            }`}
          >
            LBO {hasScenario ? '✓' : '—'}
          </span>
          <span
            className={`text-[8px] font-mono px-1.5 py-0.5 rounded border ${
              deal.ic_memo
                ? 'text-emerald-400 border-emerald-900 bg-emerald-950/20'
                : 'text-slate-600 border-slate-800'
            }`}
          >
            MÉMO {deal.ic_memo ? '✓' : '—'}
          </span>
        </div>
      </div>
    </div>
  );
};

interface StageColumnProps {
  stage: DealStage;
  dealIds: number[];
  dealsById: Record<number, Deal>;
  savingIds: Set<number>;
}

const StageColumn: React.FC<StageColumnProps> = ({ stage, dealIds, dealsById, savingIds }) => {
  const { setNodeRef, isOver } = useDroppable({ id: `col:${stage}` });

  return (
    <div
      ref={setNodeRef}
      className={`min-w-[300px] w-[300px] rounded-lg border ${STAGE_THEME[stage]} flex flex-col max-h-[calc(100vh-220px)] transition-all ${
        isOver ? 'ring-1 ring-cyan-500/60 shadow-xl shadow-cyan-900/20' : ''
      }`}
    >
      <div className="px-3 py-2.5 border-b border-slate-800 flex items-center justify-between sticky top-0 bg-slate-950/90 backdrop-blur z-10">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-200">{stage}</p>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">{dealIds.length}</span>
      </div>

      <SortableContext items={dealIds.map((id) => `card:${id}`)} strategy={verticalListSortingStrategy}>
        <div className="p-2.5 space-y-2 overflow-y-auto min-h-24">
          {dealIds.length === 0 && (
            <div className="text-[11px] font-mono text-slate-600 border border-dashed border-slate-800 rounded p-3 text-center">
              Aucun deal ici
            </div>
          )}
          {dealIds.map((id) => {
            const deal = dealsById[id];
            if (!deal) return null;
            return <DealCard key={deal.id} deal={deal} stage={stage} isSaving={savingIds.has(deal.id)} />;
          })}
        </div>
      </SortableContext>
    </div>
  );
};

interface BoardState {
  dealsById: Record<number, Deal>;
  columns: Record<DealStage, number[]>;
}

const emptyColumns = (): Record<DealStage, number[]> => ({
  Screening: [],
  'IC Review': [],
  Approved: [],
  Closed: [],
  Passed: [],
});

const buildBoardState = (deals: Deal[] = []): BoardState => {
  const columns = emptyColumns();
  const dealsById: Record<number, Deal> = {};
  for (const deal of deals) {
    dealsById[deal.id] = deal;
    columns[resolveStage(deal)].push(deal.id);
  }
  return { dealsById, columns };
};

const parseCardId = (id: string): number | null => {
  if (!id.startsWith('card:')) return null;
  const value = Number(id.replace('card:', ''));
  return Number.isFinite(value) ? value : null;
};

const parseColumnId = (id: string): DealStage | null => {
  if (!id.startsWith('col:')) return null;
  const stage = id.replace('col:', '') as DealStage;
  return (DEAL_STAGES as string[]).includes(stage) ? stage : null;
};

export const DealPipeline: React.FC = () => {
  const { data: deals, isLoading, error, refetch, isFetching } = useDeals();
  const updateStatusMutation = useUpdateDealStatusMutation();
  const [board, setBoard] = useState<BoardState>(() => buildBoardState());
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());
  const [activeDragId, setActiveDragId] = useState<number | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
  );

  useEffect(() => {
    setBoard(buildBoardState(deals ?? []));
  }, [deals]);

  const totalDeals = useMemo(
    () => DEAL_STAGES.reduce((sum, stage) => sum + board.columns[stage].length, 0),
    [board.columns],
  );

  const activeDragDeal = useMemo(
    () => (activeDragId ? board.dealsById[activeDragId] : undefined),
    [activeDragId, board.dealsById],
  );

  const handleDragStart = (event: DragStartEvent) => setActiveDragId(parseCardId(String(event.active.id)));
  const handleDragCancel = () => setActiveDragId(null);

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveDragId(null);
    const { active, over } = event;
    if (!over) return;

    const activeCardId = parseCardId(String(active.id));
    if (!activeCardId) return;

    const sourceStage = active.data.current?.stage as DealStage | undefined;
    if (!sourceStage) return;

    const overId = String(over.id);
    const overColumnStage = parseColumnId(overId);
    const overCardId = parseCardId(overId);

    const destinationStage = overColumnStage
      ?? (over.data.current?.stage as DealStage | undefined)
      ?? (overCardId ? DEAL_STAGES.find((stage) => board.columns[stage].includes(overCardId)) : undefined);

    if (!destinationStage) return;

    if (sourceStage === destinationStage) {
      if (!overCardId || overCardId === activeCardId) return;
      setBoard((prev) => {
        const sourceIds = prev.columns[sourceStage];
        const oldIndex = sourceIds.indexOf(activeCardId);
        const newIndex = sourceIds.indexOf(overCardId);
        if (oldIndex < 0 || newIndex < 0 || oldIndex === newIndex) return prev;
        return { ...prev, columns: { ...prev.columns, [sourceStage]: arrayMove(sourceIds, oldIndex, newIndex) } };
      });
      return;
    }

    setBoard((prev) => {
      const nextColumns = { ...prev.columns };
      const sourceIds = [...nextColumns[sourceStage]];
      const destinationIds = [...nextColumns[destinationStage]];
      nextColumns[sourceStage] = sourceIds.filter((id) => id !== activeCardId);

      if (overCardId && destinationIds.includes(overCardId)) {
        destinationIds.splice(destinationIds.indexOf(overCardId), 0, activeCardId);
      } else {
        destinationIds.push(activeCardId);
      }
      nextColumns[destinationStage] = destinationIds;

      const current = prev.dealsById[activeCardId];
      return {
        dealsById: { ...prev.dealsById, [activeCardId]: current ? { ...current, status: destinationStage } : current },
        columns: nextColumns,
      };
    });

    setSavingIds((prev) => new Set(prev).add(activeCardId));
    updateStatusMutation.mutate(
      { id: activeCardId, status: destinationStage },
      {
        onSettled: () => setSavingIds((prev) => { const next = new Set(prev); next.delete(activeCardId); return next; }),
      },
    );
  };

  return (
    <div className="h-full w-full flex flex-col space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2">
            <KanbanSquare size={18} className="text-cyan-400" /> Deal Pipeline
            <span className="text-[10px] text-slate-500 font-mono border border-slate-800 rounded px-1.5 py-0.5 ml-1">IC</span>
          </h2>
          <p className="text-[11px] text-slate-500 mt-1">
            Suivi des deals promus (pas des cibles en qualification — pour ça, voir Deal Sourcing). Un mémo IC généré fait
            automatiquement avancer un deal de Screening à IC Review.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-slate-500">{totalDeals} DEALS</span>
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

      {isLoading && (
        <div className="border border-slate-800 rounded-lg bg-slate-900/50 p-6 text-sm text-slate-400 font-mono">
          Chargement du pipeline...
        </div>
      )}

      {error && (
        <div className="border border-rose-900/60 rounded-lg bg-rose-950/20 p-6 text-sm text-rose-300 font-mono">
          Erreur de chargement du pipeline.
        </div>
      )}

      {!isLoading && !error && totalDeals === 0 && (
        <div className="border border-dashed border-slate-800 rounded-lg bg-slate-900/30 p-8 text-center">
          <p className="text-sm text-slate-400">Aucun deal promu pour l'instant.</p>
          <p className="text-[11px] text-slate-600 mt-1">
            Promouvez une cible qualifiée depuis Deal Sourcing pour la voir apparaître ici.
          </p>
        </div>
      )}

      {!isLoading && !error && totalDeals > 0 && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragCancel={handleDragCancel}
          onDragEnd={handleDragEnd}
        >
          <div className="flex gap-4 overflow-x-auto pb-2">
            {DEAL_STAGES.map((stage) => (
              <StageColumn key={stage} stage={stage} dealIds={board.columns[stage] ?? []} dealsById={board.dealsById} savingIds={savingIds} />
            ))}
          </div>

          <DragOverlay>
            {activeDragDeal ? (
              <div className="w-[280px] bg-slate-900 border border-cyan-600/70 rounded-lg p-3 space-y-2.5 shadow-2xl shadow-cyan-900/40 opacity-95">
                <p className="text-sm font-semibold text-slate-100 truncate">{activeDragDeal.target_name}</p>
                <p className="text-[11px] font-mono text-slate-400">CA {formatMoney(activeDragDeal.target_revenue)}</p>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}
    </div>
  );
};
