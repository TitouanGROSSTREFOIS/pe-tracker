import React, { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, Loader2, X, AlertTriangle } from 'lucide-react';
import { dealsAPI } from '../services/apiService';
import type { Deal, DealCreateInput, DocumentExtraction, FieldProvenance, ExtractionFlag } from '../types';

interface DocumentReviewModalProps {
  extraction: DocumentExtraction;
  sourceFileName: string | null;
  onClose: () => void;
  onCreated: (deal: Deal) => void;
}

type FormState = {
  company_name: string;
  business_summary: string;
  estimated_revenue: string;
  estimated_ebitda: string;
  enterprise_value: string;
};

const toFieldValue = (value: number | null): string => (value === null || value === undefined ? '' : String(value));

// L'extraction (document_parser.py) renvoie estimated_revenue/estimated_ebitda
// en MILLIONS D'EUROS (contrat explicite du prompt LLM, ex. "61.1" pour
// 61,1 M€) — mais Deal.target_revenue/target_ebitda sont stockés en EUROS
// ABSOLUS partout ailleurs dans l'app (ex. BTP Consultants : 61 078 515, pas
// 61.1). Ce facteur convertit la valeur affichée (millions, lisible en face
// du document) vers l'unité réellement stockée — jamais appliqué ailleurs
// que dans ce payload de soumission, pour ne pas casser l'affichage/la
// comparaison DOCUMENT vs MANUAL ci-dessus, qui reste en millions.
const MILLIONS_TO_EUROS = 1_000_000;
const toAbsoluteEuros = (millionsStr: string): number | null =>
  millionsStr.trim() ? Number(millionsStr) * MILLIONS_TO_EUROS : null;

// Sentinelle pour le radio "ne pas rattacher" (Tâche B.5, Étape 3) — distincte
// de `null` tant que rien n'a été choisi, pour forcer une décision explicite
// plutôt que de présumer un rattachement par défaut.
const NO_MATCH = 'none' as const;

export const DocumentReviewModal: React.FC<DocumentReviewModalProps> = ({ extraction, sourceFileName, onClose, onCreated }) => {
  const [form, setForm] = useState<FormState>({
    company_name: extraction.company_name,
    business_summary: extraction.business_summary,
    estimated_revenue: toFieldValue(extraction.estimated_revenue),
    estimated_ebitda: toFieldValue(extraction.estimated_ebitda),
    enterprise_value: '',
  });
  const [matchChoice, setMatchChoice] = useState<number | typeof NO_MATCH | null>(null);

  useEffect(() => {
    setForm({
      company_name: extraction.company_name,
      business_summary: extraction.business_summary,
      estimated_revenue: toFieldValue(extraction.estimated_revenue),
      estimated_ebitda: toFieldValue(extraction.estimated_ebitda),
      enterprise_value: '',
    });
    setMatchChoice(null);
  }, [extraction]);

  const mutation = useMutation<Deal, Error, DealCreateInput>({
    mutationFn: (payload) => dealsAPI.create(payload),
    onSuccess: (data) => {
      onCreated(data);
    },
  });

  const setField = (field: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  // D25 (Tâche B.10), Étape 1.3 : le drapeau reste rattaché à la valeur
  // extraite à l'origine — il ne disparaît pas tant que l'utilisateur n'a
  // pas explicitement corrigé le champ (à ce moment la provenance passe à
  // MANUAL de toute façon, voir buildFieldProvenance ci-dessous).
  const flagsFor = (field: 'estimated_revenue' | 'estimated_ebitda'): ExtractionFlag[] =>
    (extraction.flags ?? []).filter((f) => f.field === field);

  // D18 (Tâche B.6) : la provenance se décide au moment de la soumission, en
  // comparant la valeur finale à ce que l'extraction LLM avait proposé —
  // inchangé → DOCUMENT (référence = nom du fichier) ; modifié → MANUAL
  // (l'utilisateur a corrigé la donnée en human-in-the-loop). L'enterprise
  // value n'a aucune voie d'extraction LLM aujourd'hui : toujours MANUAL
  // dès qu'elle est renseignée.
  // D44 (Tâche Finalisation) : `as_of` est renseigné avec l'exercice détecté
  // par l'extraction (extraction.fiscal_year) dès qu'il est connu — pour
  // DOCUMENT comme pour MANUAL, le chiffre corrigé décrit toujours le même
  // exercice que celui rapporté dans le document, seule la valeur change.
  // Jamais inventé : reste undefined si l'extraction n'a pas trouvé d'année.
  const buildFieldProvenance = (
    currentValue: string,
    originalValue: number | null,
  ): FieldProvenance | undefined => {
    if (!currentValue.trim()) return undefined;
    const unchanged = toFieldValue(originalValue) === currentValue;
    const as_of = extraction.fiscal_year != null ? String(extraction.fiscal_year) : undefined;
    return unchanged
      ? { provenance: 'DOCUMENT', reference: sourceFileName ?? 'uploaded document (filename not retained)', as_of }
      : { provenance: 'MANUAL', reference: 'Corrected in the human-in-the-loop review modal', as_of };
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();

    const financial_provenance: Record<string, FieldProvenance> = {};
    const revenueProv = buildFieldProvenance(form.estimated_revenue, extraction.estimated_revenue);
    if (revenueProv) financial_provenance.target_revenue = revenueProv;
    const ebitdaProv = buildFieldProvenance(form.estimated_ebitda, extraction.estimated_ebitda);
    if (ebitdaProv) financial_provenance.target_ebitda = ebitdaProv;
    if (form.enterprise_value.trim()) {
      financial_provenance.enterprise_value = {
        provenance: 'MANUAL',
        reference: 'Manually entered — no LLM extraction currently provides enterprise value',
      };
    }

    // D15 (Tâche B.5) : plus aucune dérivation de enterprise_value_deal /
    // deal_value à partir du CA — l'EV de la cible est soit saisie
    // explicitement dans son propre champ, soit laissée nulle.
    const payload: DealCreateInput = {
      acquirer_name: 'TBD',
      target_name: form.company_name.trim(),
      sourced_target_id: typeof matchChoice === 'number' ? matchChoice : null,
      deal_type: 'M&A',
      status: 'Screening',
      description: form.business_summary.trim(),
      source: 'Document Ingestion',
      source_url: 'document://manual-review',
      // D18 bis (cette tâche) : conversion M€ → € absolus à la soumission
      // uniquement — corrige un facteur ×1 000 000 qui faisait passer, par
      // ex., un CA réel de 61,1 M€ en un target_revenue de 61,1 € en base.
      target_revenue: toAbsoluteEuros(form.estimated_revenue),
      target_ebitda: toAbsoluteEuros(form.estimated_ebitda),
      enterprise_value: form.enterprise_value.trim() ? Number(form.enterprise_value) : null,
      financial_provenance,
    };

    mutation.mutate(payload);
  };

  const matches = extraction.sourced_target_matches ?? [];
  const requiresMatchDecision = matches.length > 0 && matchChoice === null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 py-6 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={mutation.isPending ? undefined : onClose} />

      <div className="relative z-10 w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-800/50 px-5 py-4">
          <div>
            <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-cyan-300">Human-in-the-loop review</p>
            <h3 className="mt-1 text-lg font-bold text-white">Valider l’extraction avant création</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="rounded-full border border-slate-700 p-2 text-slate-400 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Close modal"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 p-5">
          {(extraction.flags ?? []).length > 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-700 bg-amber-950/30 px-3 py-2.5">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-400" />
              <div className="text-xs text-amber-200">
                <p className="font-bold uppercase tracking-wider text-amber-300">
                  {extraction.flags.length === 1 ? 'Valeur suspecte détectée' : `${extraction.flags.length} valeurs suspectes détectées`}
                </p>
                <p className="mt-0.5 text-amber-200/90">
                  Vérifiez les champs surlignés ci-dessous avant de valider — la correction reste manuelle.
                </p>
              </div>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 md:col-span-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Company name</span>
              <input
                value={form.company_name}
                onChange={(event) => setField('company_name', event.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
              />
            </label>

            <label className="space-y-2 md:col-span-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Business summary</span>
              <textarea
                value={form.business_summary}
                onChange={(event) => setField('business_summary', event.target.value)}
                rows={5}
                className="w-full resize-y rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
              />
            </label>

            {/* D46 (Tâche Finalisation, Partie 3) : l'exercice détecté (fiscal_year)
                était déjà capté et propagé en provenance (as_of) mais jamais montré
                au réviseur avant validation — il ne le découvrait qu'après création
                du deal, au survol du badge de provenance. Affiché ici, à côté des
                deux champs qu'il qualifie, jamais inventé si l'extraction n'a rien
                trouvé (voir libellé "non détecté" ci-dessous). */}
            <div className="md:col-span-2 flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-300">
              <span className="font-bold uppercase tracking-wider text-slate-500">Exercice détecté :</span>
              {extraction.fiscal_year != null ? (
                <span className="font-mono text-cyan-300">{extraction.fiscal_year}</span>
              ) : (
                <span className="font-mono text-slate-500">non détecté dans le document</span>
              )}
              <span className="text-slate-500">— s'applique au CA et à l'EBITDA ci-dessous.</span>
            </div>

            <label className="space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Estimated revenue (M€)</span>
              <input
                type="number"
                step="0.01"
                value={form.estimated_revenue}
                onChange={(event) => setField('estimated_revenue', event.target.value)}
                className={`w-full rounded-lg border bg-slate-950/80 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:ring-1 ${
                  flagsFor('estimated_revenue').length > 0
                    ? 'border-amber-600 focus:border-amber-500 focus:ring-amber-500'
                    : 'border-slate-700 focus:border-cyan-500 focus:ring-cyan-500'
                }`}
                placeholder="Optional"
              />
              {flagsFor('estimated_revenue').map((f, i) => (
                <p key={i} className="flex items-start gap-1.5 text-[11px] leading-snug text-amber-300">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  <span>{f.reason}</span>
                </p>
              ))}
            </label>

            <label className="space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Estimated EBITDA (M€)</span>
              <input
                type="number"
                step="0.01"
                value={form.estimated_ebitda}
                onChange={(event) => setField('estimated_ebitda', event.target.value)}
                className={`w-full rounded-lg border bg-slate-950/80 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:ring-1 ${
                  flagsFor('estimated_ebitda').length > 0
                    ? 'border-amber-600 focus:border-amber-500 focus:ring-amber-500'
                    : 'border-slate-700 focus:border-cyan-500 focus:ring-cyan-500'
                }`}
                placeholder="Optional"
              />
              {flagsFor('estimated_ebitda').map((f, i) => (
                <p key={i} className="flex items-start gap-1.5 text-[11px] leading-snug text-amber-300">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  <span>{f.reason}</span>
                </p>
              ))}
            </label>

            <label className="space-y-2 md:col-span-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Enterprise value in € — optional, not M€</span>
              <input
                type="number"
                step="0.01"
                value={form.enterprise_value}
                onChange={(event) => setField('enterprise_value', event.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
                placeholder="Laisser vide si inconnue — jamais déduite du CA"
              />
            </label>
          </div>

          {matches.length > 0 && (
            <div className="space-y-2 rounded-lg border border-amber-900/50 bg-amber-950/20 p-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-amber-300">
                Cible déjà sourcée ? (Tâche B.5)
              </p>
              <p className="text-xs text-slate-400">
                {matches.length === 1 ? 'Une cible existante ressemble' : `${matches.length} cibles existantes ressemblent`} à « {form.company_name} ». Rattacher pour éviter un doublon, ou continuer sans lien.
              </p>
              <div className="space-y-1.5 pt-1">
                {matches.map((m) => (
                  <label key={m.id} className="flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="radio"
                      name="sourced-target-match"
                      checked={matchChoice === m.id}
                      onChange={() => setMatchChoice(m.id)}
                    />
                    <span>{m.company_name}</span>
                    <span className="text-xs text-slate-500">({Math.round(m.similarity * 100)}% similaire{m.siren ? `, SIREN ${m.siren}` : ''})</span>
                  </label>
                ))}
                <label className="flex items-center gap-2 text-sm text-slate-200">
                  <input
                    type="radio"
                    name="sourced-target-match"
                    checked={matchChoice === NO_MATCH}
                    onChange={() => setMatchChoice(NO_MATCH)}
                  />
                  <span>Ne pas rattacher — nouvelle cible</span>
                </label>
              </div>
            </div>
          )}

          {mutation.isError && (
            <div className="rounded-lg border border-rose-900/60 bg-rose-950/20 px-3 py-2 text-sm text-rose-300">
              {mutation.error?.message ?? 'Une erreur est survenue lors de la création du deal.'}
            </div>
          )}

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onClose}
              disabled={mutation.isPending}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={mutation.isPending || requiresMatchDecision}
              title={requiresMatchDecision ? 'Choisissez un rattachement ou "Ne pas rattacher" ci-dessus' : undefined}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-500 bg-cyan-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {mutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
              Valider & Créer le Deal
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};