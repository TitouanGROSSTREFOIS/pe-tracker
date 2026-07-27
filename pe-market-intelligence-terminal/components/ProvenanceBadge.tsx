import React from 'react';
import type { DataProvenance, FieldProvenance } from '../types';

/**
 * Indicateur discret de provenance d'un montant financier (D18, Tâche B.6).
 * Le détail (référence, exercice) est accessible au survol via `title` —
 * pas de tooltip JS pour rester sobre, un professionnel lit l'écran
 * normalement et vérifie l'origine seulement s'il le souhaite.
 */

const STYLES: Record<DataProvenance, { label: string; className: string }> = {
  REGISTRY: { label: 'Registre', className: 'border-emerald-700 bg-emerald-950/40 text-emerald-300' },
  DOCUMENT: { label: 'Document', className: 'border-cyan-700 bg-cyan-950/40 text-cyan-300' },
  MARKET: { label: 'Marché', className: 'border-indigo-700 bg-indigo-950/40 text-indigo-300' },
  ESTIMATE: { label: 'Estimé', className: 'border-amber-700 bg-amber-950/40 text-amber-300' },
  MANUAL: { label: 'Manuel', className: 'border-violet-700 bg-violet-950/40 text-violet-300' },
  UNKNOWN: { label: 'Origine inconnue', className: 'border-rose-700 bg-rose-950/40 text-rose-300' },
};

interface ProvenanceBadgeProps {
  provenance: FieldProvenance | null | undefined;
}

export const ProvenanceBadge: React.FC<ProvenanceBadgeProps> = ({ provenance }) => {
  if (!provenance) return null;
  const style = STYLES[provenance.provenance] ?? STYLES.UNKNOWN;
  const title = [
    provenance.reference,
    provenance.as_of ? `Exercice ${provenance.as_of}` : null,
  ].filter(Boolean).join(' — ') || 'Aucun détail disponible';

  return (
    <span
      title={title}
      className={`ml-1.5 inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wide cursor-help ${style.className}`}
    >
      {style.label}
    </span>
  );
};
