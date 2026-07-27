import React, { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, FileText, Loader2, UploadCloud, Sparkles } from 'lucide-react';
import { documentsAPI } from '../services/apiService';
import type { DocumentExtraction } from '../types';
import { DocumentReviewModal } from './DocumentReviewModal';

type ToastState = {
  kind: 'success' | 'error';
  message: string;
};

const toastClassNames: Record<ToastState['kind'], string> = {
  success: 'bg-emerald-950/90 border-emerald-700 text-emerald-300',
  error: 'bg-rose-950/90 border-rose-700 text-rose-300',
};

export const DocumentUpload: React.FC = () => {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [extraction, setExtraction] = useState<DocumentExtraction | null>(null);
  // D18 (Tâche B.6) : conservé au-delà de la fin de l'upload (contrairement
  // à `fileName`, réinitialisé) pour être cité comme référence de provenance
  // DOCUMENT dans la modale de review.
  const [sourceFileName, setSourceFileName] = useState<string | null>(null);

  const clearToastLater = (nextToast: ToastState) => {
    setToast(nextToast);
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    timeoutRef.current = window.setTimeout(() => setToast(null), 5000);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  const mutation = useMutation<DocumentExtraction, Error, File>({
    mutationFn: (file) => documentsAPI.extract(file),
    onSuccess: (data) => {
      clearToastLater({ kind: 'success', message: `Extraction terminée: ${data.company_name}` });
      setExtraction(data);
      setFileName(null);
    },
    onError: (error) => {
      clearToastLater({ kind: 'error', message: error.message || 'Échec de l’analyse du document' });
      setFileName(null);
    },
  });

  const ingestFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      clearToastLater({ kind: 'error', message: 'Seuls les fichiers PDF sont acceptés' });
      return;
    }

    setFileName(file.name);
    setSourceFileName(file.name);
    mutation.mutate(file);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) ingestFile(file);
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) ingestFile(file);
    event.target.value = '';
  };

  return (
    <div className="relative">
      {extraction && (
        <DocumentReviewModal
          extraction={extraction}
          sourceFileName={sourceFileName}
          onClose={() => setExtraction(null)}
          onCreated={(deal) => {
            clearToastLater({ kind: 'success', message: `Deal créé: ${deal.target_name ?? 'Deal'}` });
            setExtraction(null);
            queryClient.invalidateQueries({ queryKey: ['deals'] });
            queryClient.invalidateQueries({ queryKey: ['sourced-targets'] });
          }}
        />
      )}

      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg border shadow-2xl text-sm font-mono ${toastClassNames[toast.kind]}`}>
          {toast.message}
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-lg">
        <div className="px-4 py-3 border-b border-slate-800 bg-slate-800/50 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-100">Document Ingestion</h3>
            <p className="text-xs text-slate-400 mt-0.5">Teaser / CIM → GPT-4o-mini → Screening target</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-1 rounded border border-cyan-800 bg-cyan-950/40 text-cyan-300">
            Sprint 8
          </span>
        </div>

        <div className="p-4 space-y-4">
          <div
            onDrop={handleDrop}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setIsDragging(false);
            }}
            onClick={() => inputRef.current?.click()}
            className={`group relative cursor-pointer rounded-xl border-2 border-dashed p-8 transition-all duration-200 ${
              isDragging
                ? 'border-cyan-400 bg-cyan-950/20 shadow-[0_0_0_1px_rgba(34,211,238,0.25)]'
                : 'border-slate-700 bg-slate-950/40 hover:border-cyan-700 hover:bg-slate-950/70'
            } ${mutation.isPending ? 'pointer-events-none opacity-70' : ''}`}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              onChange={handleInputChange}
              className="hidden"
            />

            <div className="flex flex-col items-center justify-center text-center gap-3">
              <div className={`rounded-full p-3 transition-all ${isDragging ? 'bg-cyan-500/15' : 'bg-slate-800/70 group-hover:bg-cyan-500/10'}`}>
                {mutation.isPending ? (
                  <Loader2 size={24} className="animate-spin text-cyan-300" />
                ) : (
                  <UploadCloud size={24} className="text-cyan-300" />
                )}
              </div>

              {mutation.isPending ? (
                <>
                  <p className="text-sm font-semibold text-cyan-300">Analyse du document en cours...</p>
                  <p className="text-xs text-slate-400 font-mono">
                    {fileName ? `Lecture de ${fileName}` : 'Extraction texte → JSON structuré → DB'}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm font-semibold text-slate-100">
                    Glissez-déposez un PDF ici ou <span className="text-cyan-300 underline decoration-cyan-400/60">cliquez pour parcourir</span>
                  </p>
                  <p className="text-xs text-slate-400 font-mono">
                    Teasers, CIMs et Info Memos acceptés. Limitation à 5 pages pour l’extraction initiale.
                  </p>
                </>
              )}
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-lg border border-cyan-900/40 bg-cyan-950/20 p-3 text-[10px] text-cyan-200">
            <Sparkles size={12} className="mt-0.5 shrink-0 text-cyan-300" />
            <p className="font-mono leading-relaxed">
              Le document est analysé par GPT-4o-mini, qui extrait un JSON strict avec le nom de société, le résumé et les estimations de CA / EBITDA avant création automatique en statut Screening.
            </p>
          </div>

          <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500">
            <FileText size={11} className="text-slate-500" />
            <span>Feedback instantané et rafraîchissement automatique du Kanban après ingestion.</span>
          </div>
        </div>
      </div>

      {mutation.isError && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-rose-900/60 bg-rose-950/20 p-3 text-[10px] text-rose-300 font-mono">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{mutation.error?.message ?? 'Erreur lors de l’ingestion du document.'}</span>
        </div>
      )}
    </div>
  );
};