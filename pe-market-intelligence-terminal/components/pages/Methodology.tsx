import React from 'react';
import { Card } from '../ui/Card';
import {
  BookOpen, Radar, Brain, TrendingUp, Network, Landmark,
  ArrowRight, ChevronRight, Globe, Search, BarChart3,
  Calculator, Zap, FileText, Database, Shield, Layers,
  PlayCircle, FileSearch, Building2, GitBranch, MessageSquare,
  AlertTriangle, CheckCircle2, Link2, Scale, Filter, Users,
  FileSpreadsheet,
} from 'lucide-react';

// ============================================
// Reusable sub-components
// ============================================

/** Math block — monospace equation on dark bg */
const Eq: React.FC<{ children: React.ReactNode; label?: string }> = ({ children, label }) => (
  <div className="my-3 bg-slate-950 border border-slate-800 rounded-lg px-5 py-3 font-mono text-sm text-cyan-300 overflow-x-auto whitespace-pre-line">
    {label && <span className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">{label}</span>}
    {children}
  </div>
);

/** Section header within a card */
const SectionH3: React.FC<{ icon: React.ReactNode; children: React.ReactNode }> = ({ icon, children }) => (
  <h3 className="flex items-center gap-2 text-sm font-bold text-slate-200 uppercase tracking-wider mt-6 mb-3">
    <span className="text-cyan-500">{icon}</span>
    {children}
  </h3>
);

/** Paragraph */
const P: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-xs text-slate-400 leading-relaxed mb-3">{children}</p>
);

/** Inline code */
const C: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <code className="text-cyan-400 bg-slate-900 px-1.5 py-0.5 rounded text-[11px] font-mono">{children}</code>
);

/** Pipeline step badge */
const Step: React.FC<{ n: number; label: string; desc: string }> = ({ n, label, desc }) => (
  <div className="flex items-start gap-3 mb-3">
    <div className="w-7 h-7 rounded-full bg-cyan-950/50 border border-cyan-800 flex items-center justify-center text-xs font-bold text-cyan-400 shrink-0 mt-0.5">
      {n}
    </div>
    <div>
      <div className="text-xs font-bold text-slate-200">{label}</div>
      <div className="text-[11px] text-slate-500 leading-relaxed">{desc}</div>
    </div>
  </div>
);

// ============================================
// Main Component
// ============================================

export const Methodology: React.FC = () => {
  return (
    <div className="h-full w-full flex flex-col space-y-8 max-w-5xl">

      {/* ── Header ── */}
      <div>
        <h2 className="text-lg font-bold text-white uppercase tracking-tight flex items-center gap-2 mb-2">
          <span className="text-cyan-500">///</span> Méthodologie &amp; Formules
          <span className="text-[10px] text-slate-500 font-mono border border-slate-800 rounded px-1.5 py-0.5 ml-2">WHITEPAPER</span>
        </h2>
        <p className="text-xs text-slate-500 font-mono">
          Documentation complète du projet — de la source de donnée brute jusqu'au chiffre affiché à l'écran,
          pour chaque module. Fidèle au code réel (vérifié, pas supposé) ; toute incertitude est signalée
          explicitement plutôt qu'inventée.
        </p>
      </div>

      {/* ── P2 (Partie E) : positionnement honnête — ce que l'outil EST et
          n'est PAS, pour qu'un lecteur ne prenne jamais un livrable généré ici
          pour un dossier d'IC prêt à voter. ── */}
      <div className="bg-amber-950/20 border border-amber-800/60 rounded-lg px-5 py-4">
        <h3 className="text-[10px] text-amber-400 uppercase tracking-wider font-bold mb-2 flex items-center gap-2">
          <AlertTriangle size={13} /> Positionnement — à lire avant tout
        </h3>
        <p className="text-xs text-slate-300 leading-relaxed mb-2">
          Cet outil est un moteur de <b>sourcing</b> et de <b>pré-screening</b> pour des cibles PME françaises,
          typiquement en dessous de 10 M€ de chiffre d'affaires, avec traçabilité systématique de la provenance
          de chaque donnée (réelle vs estimée). Les livrables générés (mémo IC, deck, modèle Excel) sont un{' '}
          <b>point de départ documenté pour l'analyste</b> — pas un dossier d'investment committee prêt à être
          voté en l'état.
        </p>
        <p className="text-xs text-slate-300 leading-relaxed mb-2">
          En particulier : (1) sous 10 M€ de CA, un LBO standalone est indicatif — la structure réaliste à cette
          taille est un bolt-on adossé à une plateforme (voir Buy &amp; Build), financé en dette bancaire, pas un
          LBO mezzanine autonome ; (2) tout mémo doit présenter au moins un scénario base et un scénario baissier,
          jamais un chiffre unique présenté comme certain ; (3) les comparables cotés utilisés pour calibrer un
          multiple sont des ancrages de marché — leur médiane n'est jamais directement applicable à une cible de
          quelques M€ sans décote de taille/illiquidité substantielle ; (4) toute donnée estimée reste estimée
          jusqu'à confirmation en diligence — jamais présentée avec la certitude d'un chiffre audité.
        </p>
        <p className="text-xs text-slate-400 leading-relaxed">
          Utiliser ces livrables comme point de départ pour la diligence, la modélisation et la discussion en
          comité — jamais comme substitut à la diligence elle-même.
        </p>
      </div>

      {/* Table of Contents */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-lg px-5 py-4">
        <h3 className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-3">Sommaire</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            { n: 1, label: 'Sourcing', icon: <Radar size={14} />, anchor: '#sourcing' },
            { n: 2, label: 'Qualification & Scoring', icon: <Scale size={14} />, anchor: '#scoring' },
            { n: 3, label: 'Spreading IA', icon: <FileSearch size={14} />, anchor: '#spreading' },
            { n: 4, label: 'Comparables & Valorisation', icon: <Building2 size={14} />, anchor: '#comparables' },
            { n: 5, label: 'Moteur LBO', icon: <Calculator size={14} />, anchor: '#lbo' },
            { n: 6, label: 'Buy & Build', icon: <Network size={14} />, anchor: '#buildup' },
            { n: 7, label: 'IC Memo & Exports', icon: <MessageSquare size={14} />, anchor: '#memo' },
            { n: 8, label: 'Macro & Crédit', icon: <TrendingUp size={14} />, anchor: '#macro' },
            { n: 9, label: 'Traçabilité', icon: <Shield size={14} />, anchor: '#tracabilite' },
            { n: 10, label: 'Architecture', icon: <Layers size={14} />, anchor: '#architecture' },
            { n: 11, label: 'La démo expliquée', icon: <PlayCircle size={14} />, anchor: '#demo' },
          ].map(s => (
            <a
              key={s.n}
              href={s.anchor}
              className="flex items-center gap-3 px-3 py-2.5 rounded border border-slate-800 bg-slate-950/50 hover:border-cyan-800 hover:bg-cyan-950/20 transition-all group"
            >
              <div className="text-cyan-500 group-hover:text-cyan-400 transition-colors">{s.icon}</div>
              <div>
                <div className="text-[10px] text-slate-500 font-mono">SECTION {s.n}</div>
                <div className="text-xs text-slate-300 font-bold">{s.label}</div>
              </div>
              <ChevronRight size={14} className="ml-auto text-slate-700 group-hover:text-cyan-500 transition-colors" />
            </a>
          ))}
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 1 — Sourcing
         ══════════════════════════════════════════════════════ */}
      <div id="sourcing">
        <Card title="1. Sourcing" subtitle="Deux voies indépendantes : registre officiel (déterministe) et Google Radar (exploratoire)">
          <div className="p-5 space-y-1">
            <P>
              Le sourcing alimente la base de cibles (<C>SourcedTarget</C>) par <strong className="text-cyan-400">deux voies
              distinctes</strong>, qui ne partagent ni la même source de données ni la même logique de filtrage
              par la taille. C'est une source de confusion possible si on les confond : la voie registre est
              un filtrage déterministe sur données officielles, la voie Radar est une découverte exploratoire
              sur le web.
            </P>

            <SectionH3 icon={<Building2 size={14} />}>1.1 — Voie registre (Sirene)</SectionH3>
            <P>
              Source : <C>recherche-entreprises.api.gouv.fr</C> (DINUM), gratuite, sans clé — un miroir public des
              données Sirene/INSEE. Le périmètre est fixé par code NAF :
            </P>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              <div className="bg-slate-950 border border-cyan-900/40 rounded-lg p-3">
                <div className="text-[10px] font-bold text-cyan-400 uppercase mb-1 font-mono">71.20B</div>
                <div className="text-[11px] text-slate-400">Analyses, essais et inspections techniques</div>
              </div>
              <div className="bg-slate-950 border border-cyan-900/40 rounded-lg p-3">
                <div className="text-[10px] font-bold text-cyan-400 uppercase mb-1 font-mono">71.12B</div>
                <div className="text-[11px] text-slate-400">Ingénierie, études techniques</div>
              </div>
            </div>
            <P>
              (Deux codes voisins existent mais sont volontairement <strong className="text-slate-500">exclus</strong> du
              périmètre par défaut : <C>71.20A</C> « Contrôle technique automobile » et <C>71.12A</C> « Activités des
              géomètres » — hors thèse TIC.) Filtres supplémentaires : entreprise active uniquement, catégorie
              PME/ETI (grandes entreprises exclues), effectif ≥ 20 salariés.
            </P>
            <P>
              La taille détermine ensuite le <strong className="text-violet-300">target_type</strong>, à partir du <strong className="text-slate-300">CA réel du
              registre</strong> (jamais réestimé) :
            </P>
            <Eq label="Typologie par taille (D11)">
              CA {'<'} 10 M€  → rejetée (hors thèse){'\n'}
              10 M€ ≤ CA ≤ 100 M€ → target_type = "target"{'\n'}
              CA {'>'} 100 M€ → target_type = "platform"
            </Eq>
            <P>
              Le pays est fixé à « France » pour ces cibles : la source elle-même le garantit (Sirene est un
              registre exclusivement français). <C>revenue_estimate</C> est le CA réel du registre — pas une
              estimation. À ce stade, <strong className="text-amber-400">EBITDA et EV ne sont pas renseignés</strong> (le quick-screen
              LBO n'intervient que sur la voie Radar, voir 1.2, ou lors de la promotion en deal, §5).
            </P>

            <SectionH3 icon={<Search size={14} />}>1.2 — Voie Google Radar</SectionH3>
            <P>
              Source : Serper.dev (API Google Search), requêtes combinatoires de mots-clés sectoriels (≤5),
              paramètres <C>gl=fr</C> / <C>hl=fr</C> — un <strong className="text-amber-400">biais géographique doux</strong> (préférence de
              résultats, pas un filtre dur), contrairement à la voie registre où le France-only est garanti par
              construction de la donnée source. Un filtre de domaines exclut réseaux sociaux, annuaires et presse.
            </P>
            <P>
              Sur cette voie, <C>ebitda_estimate</C>/<C>enterprise_value</C> sont calculés dès le sourcing via le
              quick-screen (profil sectoriel générique — voir §5 pour <C>LBO_PROFILES</C>, marge/multiple par
              défaut 12 %/6.0x si le secteur n'est pas résolu), provenance <strong className="text-amber-400">ESTIMATE</strong> — jamais
              présenté comme un état financier réel. <C>target_type</C> n'est <strong className="text-rose-400">jamais calculé</strong> sur cette
              voie (reste <C>null</C>) : la classification taille/plateforme (§1.1) est une logique propre à la
              voie registre, pas encore étendue à Radar.
            </P>

            <SectionH3 icon={<FileText size={14} />}>1.3 — Persistance</SectionH3>
            <P>
              Chaque cible est persistée en base SQLite (SQLAlchemy async) avec l'ensemble des champs extraits
              et sa provenance par champ. Le pipeline de scan tourne en tâche de fond (BackgroundTasks FastAPI) ;
              un scan par lot (upload CSV d'URLs) est également disponible.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 2 — Qualification & Scoring
         ══════════════════════════════════════════════════════ */}
      <div id="scoring">
        <Card title="2. Qualification & Scoring" subtitle="Deux formules distinctes, une pour chaque voie de sourcing">
          <div className="p-5 space-y-1">
            <P>
              Comme le sourcing (§1), la qualification suit une logique différente selon la voie d'origine —
              la pertinence sectorielle n'est pas évaluée de la même façon selon qu'elle est déjà acquise
              (registre, filtrage NAF) ou reste à établir (Radar, texte libre).
            </P>

            <SectionH3 icon={<Filter size={14} />}>2.1 — Voie registre</SectionH3>
            <Step n={1} label="Pertinence sectorielle" desc="Acquise par construction — le filtrage NAF (§1.1) est déjà déterministe, aucun recalcul ici (l'ancien scoring TF-IDF sur un texte de thèse synthétique produisait des faux négatifs sur des acteurs sectoriels évidents comme DEKRA ou Qualiconsult — abandonné pour cette voie)." />
            <Step n={2} label="Taille" desc="Le CA réel doit résoudre en target_type 'target' ou 'platform' (§1.1). CA absent ou < 10 M€ → rejet immédiat, AVANT tout appel LLM (économie de budget)." />
            <Step n={3} label="Note LLM" desc="Site scrapé (crawl multi-pages) puis évalué par LLM (voir prompt commun ci-dessous). Score < 20/100 → rejet." />
            <Eq label="Score final — voie registre">
              Score = 0.75 × Score_LLM + 0.25 × Score_taille{'\n'}
              Score_taille = 100 si target_type="target" (cœur de thèse) ; 70 si "platform" (plateforme de consolidation, pas une cible)
            </Eq>

            <SectionH3 icon={<Scale size={14} />}>2.2 — Voie Radar</SectionH3>
            <Step n={1} label="TF-IDF" desc="Similarité textuelle (scikit-learn, n-grammes 1-2) entre le profil de la plateforme et le texte scrapé de la cible. Score < 10/100 → rejet immédiat, avant tout appel LLM." />
            <Step n={2} label="Filtre de taille LBO" desc="CA compatible avec un LBO mid-market : entre 1 M€ et 50 M€ (fourchette différente des 10-100 M€ de la voie registre — les cibles Radar visent un univers plus large et moins qualifié en amont). CA inconnu (absent) : laissé passer, pas rejeté." />
            <Step n={3} label="Note LLM" desc="Même prompt que la voie registre. Contrairement au registre, un score LLM de 0 ne rejette PAS la cible ici — elle est conservée mais pondérée très bas dans le score composite." />
            <Eq label="Score final — voie Radar">
              Score = 0.4 × Score_TF-IDF + 0.6 × Score_LLM
            </Eq>

            <SectionH3 icon={<MessageSquare size={14} />}>2.3 — Prompt LLM (commun aux deux voies)</SectionH3>
            <P>
              Modèle <C>gpt-4o-mini</C>, température 0.3, réponse JSON forcée. Rôle système : « analyste M&A senior
              dans un fonds de Buy & Build ». Instruction explicite : <strong className="text-rose-400">score 0</strong> si la cible est un
              média, un blog, un comparateur ou un annuaire — un garde-fou anti-bruit avant même la note
              qualitative. Sortie structurée : <C>llm_score</C> (0-100), <C>strategic_fit</C> (2 phrases),
              <C>growth_signals</C>, <C>red_flags</C>, <C>competitors</C>.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 3 — Spreading IA
         ══════════════════════════════════════════════════════ */}
      <div id="spreading">
        <Card title="3. Spreading IA" subtitle="Extraction de documents (teasers, comptes) — jamais appliquée automatiquement">
          <div className="p-5 space-y-1">
            <P>
              Le spreading IA extrait des chiffres clés d'un document uploadé (teaser, rapport annuel) pour
              accélérer la saisie d'un analyste — il ne remplace jamais sa validation.
            </P>

            <SectionH3 icon={<FileSearch size={14} />}>3.1 — Extraction</SectionH3>
            <Step n={1} label="Lecture PDF" desc="pdfplumber, 5 premières pages seulement. Texte plafonné à 12 000 caractères avant envoi au LLM." />
            <Step n={2} label="LLM d'extraction" desc="gpt-4o-mini, réponse JSON forcée. Extrait 4 champs : company_name, business_summary, estimated_revenue, estimated_ebitda — unités forcées en millions d'euros (correction apportée après un bug réel : un même PDF donnait tantôt une marge de 15 %, tantôt de 0,015 % selon la façon dont l'unité était lue)." />
            <Step n={3} label="Interdiction d'inférence" desc="Le prompt interdit explicitement de déduire un EBITDA à partir d'une marge sectorielle ou d'un benchmark si aucun chiffre absolu n'est écrit dans le document — dans ce cas, le champ doit rester vide (null), jamais complété par une hypothèse." />

            <SectionH3 icon={<AlertTriangle size={14} />}>3.2 — Garde-fous serveur (jamais correctifs automatiques)</SectionH3>
            <P>
              Après extraction, un contrôle de vraisemblance serveur signale (sans jamais corriger) les valeurs
              suspectes :
            </P>
            <Eq label="Bornes de plausibilité (marge EBITDA/CA)">
              Marge {'<'} -20% ou {'>'} 60% → signalée (hors bornes plausibles){'\n'}
              0% ≤ Marge {'<'} 2% → test de facteur d'erreur d'unité (×10, ×100, ×1e3, ×1e4, ×1e5, ×1e6)
            </Eq>
            <P>
              Ce deuxième test recherche spécifiquement l'erreur de conversion d'unité qui a motivé la
              contrainte du prompt ci-dessus (§3.1, étape 2) — un garde-fou serveur en plus du garde-fou prompt,
              pas une redite : le premier réduit la fréquence de l'erreur, le second la détecte si elle survient
              quand même.
            </P>

            <SectionH3 icon={<CheckCircle2 size={14} />}>3.3 — Validation humaine obligatoire</SectionH3>
            <P>
              L'extraction retourne les valeurs, les signaux d'alerte (<C>ExtractionFlag</C>, avec sévérité) et
              des propositions de rapprochement avec des cibles déjà en base (nom similaire, seuil de similarité
              ≥ 0.6) — <strong className="text-emerald-400">rien n'est enregistré automatiquement</strong>. L'analyste voit les valeurs et
              flags dans une fenêtre de revue et valide (ou corrige) manuellement avant toute écriture en base.
            </P>
            <div className="bg-amber-950/20 border border-amber-900/40 rounded-lg p-3 mt-2">
              <p className="text-[11px] text-amber-300">
                <strong>Limite connue :</strong> la provenance <C>DOCUMENT</C> (§9) est prévue dans le modèle de
                données et affichée dans l'interface, mais le flux d'upload actuel ne l'attache pas encore
                automatiquement à un champ lors de la validation — elle n'est aujourd'hui utilisée que par un
                script de chargement manuel ponctuel. Signalé ici plutôt que passé sous silence.
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 4 — Comparables & Valorisation
         ══════════════════════════════════════════════════════ */}
      <div id="comparables">
        <Card title="4. Comparables & Valorisation de marché" subtitle="D'un ticker coté à une médiane de marché exploitable">
          <div className="p-5 space-y-1">
            <P>
              Le CompSet TIC ("TIC & Ingénierie technique") réunit des leaders cotés du secteur (Bureau Veritas,
              SGS, Eurofins, Intertek…) — voir page Comparables. Chaque société est enrichie depuis plusieurs
              sources de marché réelles, avec repli en cascade documenté :
            </P>
            <Step n={1} label="Profil (identité, EV)" desc="FMP (Financial Modeling Prep) en priorité. Si le plan gratuit ne couvre pas un champ, repli sur yfinance ; si yfinance est bloqué, Finnhub comble les champs manquants." />
            <Step n={2} label="États financiers (EBITDA, revenue)" desc="FMP en priorité. Repli en cascade : Finnhub (EBITDA, enterprise value), puis Alpha Vantage (revenue) — utilisé avec parcimonie, quota de 25 requêtes/jour constaté sur le plan gratuit." />
            <Step n={3} label="ESEF/XBRL (filings.xbrl.org)" desc="Connecteur dédié pour reconstruire un EBITDA depuis les dépôts réglementaires IFRS des émetteurs européens quand un concept de D&A propre existe (Bureau Veritas, Eurofins). Chez d'autres émetteurs (Alten, SPIE), la D&A est mélangée à des provisions dans une extension propriétaire — jamais isolée par approximation : le champ reste vide plutôt que reconstruit avec une hypothèse hasardeuse. Assystem publie un EBITDA déclaré directement (balisé explicitement), utilisé tel quel et distingué d'un EBITDA reconstruit." />
            <P>
              Chaque valeur du tableau de comparables porte sa provenance exacte (§9) — jamais une seule
              provenance générique pour toute la ligne.
            </P>

            <SectionH3 icon={<Link2 size={14} />}>4.1 — Chaîne de calibrage (D22)</SectionH3>
            <P>
              La médiane du CompSet (membres avec EBITDA réel exploitable uniquement, minimum 3) nourrit
              directement le multiple d'entrée utilisé pour valoriser une cible non cotée :
            </P>
            <Eq label="Multiple d'entrée calibré">
              Multiple_d'Entrée = Médiane(EV/EBITDA du CompSet) × (1 − Décote_taille_illiquidité)
            </Eq>
            <P>
              Décote par défaut 35 % (modifiable), matérialisant l'écart entre une valorisation de marché coté
              et une transaction mid-market non cotée. Cette chaîne — et ses conditions d'applicabilité — est
              détaillée en §5.2 (Moteur LBO), qui en est le principal consommateur.
            </P>

            <SectionH3 icon={<Users size={14} />}>4.2 — Comparables par cible (onglet « Market Comps », Deal Sourcing)</SectionH3>
            <P>
              <strong className="text-emerald-400">D49 (Tâche Finalisation) — système unifié.</strong> Depuis la vue
              détail d'une cible sourcée (onglet « Market Comps »), ce panel n'est plus un mécanisme séparé : il
              réutilise directement <strong className="text-cyan-400">le même CompSet TIC réel et la même chaîne de
              calibrage sectoriel qu'en §4.1</strong> (GET /lbo/calibration, GET /comps/{'{comp_set_id}'}) — un seul
              système de valorisation dans tout l'outil, pas deux.
            </P>
            <Step
              n={1}
              label="Résolution du secteur"
              desc="Le premier mot-clé de qualification de la cible (target.keywords[0]) est utilisé comme sector_or_naf — exactement la même dérivation que sourcing_service.py::promote_target_to_deal (Deal.sector au moment de la promotion). Le multiple affiché ici en vue détail est donc, par construction, identique à celui que le scénario LBO base-case calculera après promotion de la même cible."
            />
            <Step
              n={2}
              label="Calibrage ou message honnête"
              desc="Si le secteur résolu correspond au CompSet TIC calibré : médiane des comparables cotés réels − décote taille/illiquidité (§4.1), avec la chaîne de calcul affichée et la provenance ESTIMATE du multiple dérivé (D46 — jamais DOCUMENT ni MARKET pour une valeur dérivée, même sur des comparables MARKET). Sinon : le même message qu'au LBO (§5.2), « calibrage non applicable / échantillon insuffisant », jamais un multiple inventé pour combler l'absence."
            />
            <P>
              <strong className="text-rose-400">Retiré par cette tâche</strong> : l'ancien mécanisme "Comparable
              Intelligence" par cible (public peers proposés par GPT-4o-mini en texte libre sans score de
              similarité, et private peers cherchés via Pappers — abandonné, crédits épuisés — retombant
              systématiquement sur 3 sociétés PLACEHOLDER fabriquées, SIREN factice inclus) a été supprimé du code
              (api/services/comps_service.py, endpoint GET /sourcing/{'{id}'}/comps). Ce n'était pas une donnée
              dégradée occasionnelle : c'était, en pratique, toujours une donnée inventée. Le badge « EXEMPLE (non
              réel) » qui la signalait n'a plus lieu d'être — la donnée qu'il signalait n'existe plus.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 5 — LBO Engine
         ══════════════════════════════════════════════════════ */}
      <div id="lbo">
        <Card title="5. Moteur LBO (Paper LBO V3)" subtitle="Entrée → détention (dette multi-tranches, cash sweep) → sortie (waterfall fund/management)">
          <div className="p-5 space-y-1">
            <P>
              Le moteur LBO modélise une acquisition à effet de levier sur un horizon de détention
              (5 ans par défaut, réglable de 3 à 7 ans). Il combine trois blocs : une structure d'entrée
              (Sources &amp; Uses), une simulation annuelle de la dette (multi-tranches avec cash sweep),
              et une répartition des produits de sortie entre le fonds et le management (waterfall).
              Le multiple d'entrée peut être fixé par un profil sectoriel générique <em>ou</em> dérivé
              d'un panel réel de comparables cotés (chaîne de calibrage, D22 — voir ci-dessous).
            </P>

            <SectionH3 icon={<Landmark size={14} />}>5.1 — Sources &amp; Uses (Année 0)</SectionH3>
            <Eq label="EBITDA d'entrée">
              EBITDA₀ = CA₀ × Marge_EBITDA_secteur
            </Eq>
            <Eq label="Enterprise Value d'entrée">
              EV₀ = EBITDA₀ × Multiple_d'Entrée
            </Eq>
            <Eq label="Financement">
              Dette₀ = Σ(tranches) — plafonnée à 60 % de l'EV₀ (si dépassement, toutes les tranches sont réduites au prorata){'\n'}
              Equity₀ = EV₀ − Dette₀
            </Eq>
            <P>
              La marge EBITDA et le multiple d'entrée viennent soit du profil sectoriel générique
              résolu pour le secteur saisi, soit — si le calibrage sectoriel est activé et applicable —
              de la chaîne de calibrage ci-dessous. Le multiple de sortie est égal au multiple d'entrée
              par défaut, mais reste modifiable indépendamment.
            </P>
            <P>
              <strong className="text-amber-400">Routage par taille (sous 10 M€ de CA)</strong> — un LBO
              standalone à effet de levier mid-market (mezzanine incluse) n'est pas finançable en pratique
              à cette taille sur le marché bancaire français. En dessous de ce seuil, le scénario de base
              généré automatiquement utilise un levier réaliste de dette bancaire senior seule (2,0-2,5x
              EBITDA, pas de mezzanine) et est étiqueté <em>indicatif</em> dans le mémo, le deck et le
              modèle Excel, avec un renvoi explicite vers le module Buy &amp; Build — la structure
              réaliste à cette taille est un bolt-on adossé à une plateforme existante, pas un LBO autonome.
            </P>
            <P>
              <strong className="text-amber-400">Scénario baissier</strong> — chaque deal promu génère
              désormais, en plus du scénario de base, un cas <em>Downside</em> (CA d'entrée -10 %, multiple
              de sortie -1,0x, même secteur/levier/calibrage) via le même moteur. Le mémo et le deck
              présentent systématiquement les deux côte à côte en Section VII — un mémo d'IC à scénario
              unique n'est pas jugé acceptable.
            </P>

            <SectionH3 icon={<Search size={14} />}>5.2 — Chaîne de calibrage sectoriel (D22)</SectionH3>
            <P>
              Plutôt qu'un multiple fixé arbitrairement, le multiple d'entrée peut être <strong className="text-cyan-400">dérivé
              d'un panel réel</strong> de comparables cotés du secteur TIC (Test, Inspection, Certification
              &amp; ingénierie technique) — le seul CompSet actuellement calibré sur ce terminal (voir
              page Comparables). La chaîne de calcul, affichée telle quelle dans l'interface :
            </P>
            <Eq label="Multiple d'entrée calibré">
              Multiple_d'Entrée = Médiane(EV/EBITDA du CompSet) × (1 − Décote_taille_illiquidité)
            </Eq>
            <P>
              La décote (35 % par défaut, modifiable) matérialise l'écart entre une valorisation de
              marché coté (comparables) et une transaction mid-market non cotée, structurellement moins
              liquide. Le calibrage n'est <strong className="text-amber-400">applicable</strong> que si le secteur résolu pour la
              cible correspond au CompSet calibré, et <strong className="text-amber-400">suffisant</strong> que si ce CompSet
              compte au moins 3 comparables avec un EBITDA réel exploitable — dans tous les autres cas,
              le calculateur explique pourquoi et retombe sur le profil générique du secteur résolu
              (jamais silencieusement, voir le message affiché dans l'interface).
            </P>

            <SectionH3 icon={<Landmark size={14} />}>5.3 — Structure de dette multi-tranches</SectionH3>
            <P>
              Chaque tranche est définie par un nombre de « turns » d'EBITDA (taille), un taux d'intérêt
              et un profil de remboursement :
            </P>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              <div className="bg-slate-950 border border-slate-800 rounded-lg p-3">
                <div className="text-[10px] font-bold text-cyan-400 uppercase mb-1">Amortissable</div>
                <div className="text-[11px] text-slate-400">Remboursement fixe chaque année = montant initial ÷ durée de détention, plafonné par le solde restant et le cash disponible.</div>
              </div>
              <div className="bg-slate-950 border border-slate-800 rounded-lg p-3">
                <div className="text-[10px] font-bold text-amber-400 uppercase mb-1">Bullet (in fine)</div>
                <div className="text-[11px] text-slate-400">Aucun remboursement de principal avant la sortie — remboursée en une fois par l'Equity de sortie.</div>
              </div>
            </div>
            <P>
              <strong className="text-rose-400">Point de mécanique important, vérifié dans le code</strong> : le cash sweep
              (affectation du cash excédentaire, au-delà de l'amortissement programmé, au désendettement
              anticipé) ne s'exécute qu'en mode simple à une seule tranche (V2 legacy). En structure
              multi-tranches (V3, dès qu'au moins une tranche personnalisée est définie), <strong className="text-rose-400">il
              n'y a pas de cash sweep additionnel</strong> — seul l'amortissement programmé des tranches
              amortissables s'applique. Une tranche bullet ne rembourse donc jamais de principal avant
              l'année de sortie, même si l'entreprise génère beaucoup de cash disponible.
            </P>

            <SectionH3 icon={<TrendingUp size={14} />}>5.4 — Cash-flow annuel (Années 1 → N)</SectionH3>
            <Eq label="Croissance & EBITDA">
              CA(t) = CA(t-1) × (1 + croissance){'\n'}
              EBITDA(t) = CA(t) × Marge_EBITDA
            </Eq>
            <Eq label="Intérêts (par tranche, cumulés)">
              Intérêts(t) = Σ [ Solde_tranche(t-1) × Taux_tranche ]
            </Eq>
            <Eq label="Impôts — assiette = EBITDA − Intérêts uniquement">
              Résultat_imposable = EBITDA(t) − Intérêts(t){'\n'}
              Impôts(t) = max(0, Résultat_imposable) × 25 % (IS France)
            </Eq>
            <Eq label="Free Cash Flow">
              Capex(t) = CA(t) × taux_capex_secteur{'\n'}
              ΔBFR(t) = max(0, ΔCA(t)) × taux_bfr_secteur — jamais négatif : pas de libération de BFR modélisée en cas de baisse de CA{'\n'}
              FCF(t) = EBITDA(t) − Intérêts(t) − Impôts(t) − Capex(t) − ΔBFR(t)
            </Eq>
            <P>
              Le Capex n'est <strong className="text-amber-400">pas</strong> déduit de l'assiette imposable dans ce modèle
              simplifié (contrairement à un compte de résultat complet où l'amortissement, pas le Capex
              brut, viendrait réduire le résultat fiscal) — une simplification volontaire du « Paper LBO »,
              pas une approximation comptable complète.
            </P>

            <SectionH3 icon={<BarChart3 size={14} />}>5.5 — Sortie, IRR &amp; MOIC</SectionH3>
            <Eq label="Valorisation de sortie (année N)">
              EV_exit = EBITDA(N) × Multiple_de_Sortie{'\n'}
              Equity_exit = EV_exit − Dette(N) [somme des soldes finaux de toutes les tranches]
            </Eq>
            <Eq label="MOIC">
              MOIC = Equity_exit / Equity₀
            </Eq>
            <Eq label="IRR">
              IRR = MOIC^(1/N) − 1
            </Eq>
            <P>
              Cette formule d'IRR est exacte (pas une approximation) pour la forme de flux modélisée ici :
              un seul décaissement à l'entrée (Equity₀) et un seul encaissement à la sortie (Equity_exit),
              sans dividende ni flux intermédiaire distribué au fonds pendant la détention. Un IRR {'>'} 20%
              est généralement considéré comme attractif en PE mid-market.
            </P>

            <SectionH3 icon={<Zap size={14} />}>5.6 — Waterfall (Management Package)</SectionH3>
            <P>
              Si un management package est configuré, l'Equity de sortie est partagé entre le fonds et le
              management :
            </P>
            <Eq label="Part management">
              Part_mgmt = Sweet_Equity_% + (Bonus_Ratchet_% si IRR_brut ≥ Seuil_Ratchet, sinon 0){'\n'}
              Part_mgmt plafonnée à 50 %
            </Eq>
            <Eq label="Répartition">
              Produits_management = Equity_exit × Part_mgmt{'\n'}
              Produits_fonds = Equity_exit − Produits_management
            </Eq>
            <P>
              Le ratchet se déclenche sur l'IRR brut du deal (avant partage) : s'il atteint le seuil défini
              (25 % par défaut), la part du management passe du seul sweet equity à sweet equity + bonus.
              L'IRR et le MOIC du fonds affichés dans le panneau Waterfall sont recalculés sur les
              produits nets de la dilution management, pas sur l'IRR brut du deal.
            </P>

            <div className="mt-4 bg-slate-950 border border-slate-800 rounded-lg p-4">
              <h4 className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">Profils Sectoriels par Défaut</h4>
              <p className="text-[10px] text-slate-600 mb-3">
                22 profils au total, résolus par code NAF ou mots-clés (voir <C>resolve_profile_key</C>).
                Seul « Conseil, Juridique &amp; Ingénierie » est actuellement calibrable via un CompSet réel
                (§2.2) — tous les autres profils restent des valeurs de marché génériques, éditables via
                les curseurs mais non dérivées de comparables. Aucun profil n'inclut de levier ni de coût
                de la dette par défaut : ces deux paramètres viennent exclusivement de la structure de
                dette configurée (§2.3), pas du secteur.
              </p>
              <div className="overflow-x-auto max-h-80 overflow-y-auto">
                <table className="w-full text-left border-collapse text-[11px] font-mono">
                  <thead>
                    <tr className="text-[10px] text-slate-500 border-b border-slate-800 uppercase sticky top-0 bg-slate-950">
                      <th className="py-2 px-3">Secteur</th>
                      <th className="py-2 px-3 text-right">Marge EBITDA</th>
                      <th className="py-2 px-3 text-right">Multiple</th>
                      <th className="py-2 px-3 text-right">Croissance</th>
                      <th className="py-2 px-3 text-right">Capex</th>
                      <th className="py-2 px-3 text-right">BFR</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    {[
                      ['Conseil, Juridique & Ingénierie', '15%', '7.0x', '4%', '2%', '15%', true],
                      ['Logiciel & Services IT', '20%', '10.0x', '8%', '3%', '10%', false],
                      ['Services Financiers & Assurance', '25%', '8.5x', '4%', '2%', '5%', false],
                      ['Activités Immobilières', '30%', '8.0x', '2%', '3%', '5%', false],
                      ['Pharmacie & Biotechnologie', '20%', '9.0x', '6%', '8%', '15%', false],
                      ['Santé & Action Sociale', '14%', '8.0x', '5%', '5%', '12%', false],
                      ['Énergie & Environnement', '15%', '7.0x', '2%', '8%', '10%', false],
                      ['Médias & Télécommunications', '15%', '7.5x', '4%', '5%', '12%', false],
                      ['Électronique & Équip. high-tech', '13%', '7.0x', '4%', '5%', '18%', false],
                      ['Enseignement & Formation', '12%', '7.0x', '4%', '4%', '10%', false],
                      ['Transport & Logistique', '9%', '6.0x', '3%', '7%', '15%', false],
                      ['Hôtellerie & Restauration', '12%', '6.5x', '3%', '6%', '8%', false],
                      ['Services aux Entreprises', '12%', '6.5x', '4%', '3%', '15%', false],
                      ['Loisirs, Sport & Culture', '10%', '6.0x', '3%', '5%', '10%', false],
                      ['Agroalimentaire & Boissons', '9%', '6.5x', '3%', '5%', '18%', false],
                      ['Textile, Habillement & Cuir', '10%', '5.5x', '2%', '4%', '22%', false],
                      ['Industrie & Manufacture', '10%', '5.5x', '2%', '6%', '20%', false],
                      ['Commerce & Distribution', '6%', '5.5x', '2%', '3%', '22%', false],
                      ['BTP & Construction', '8%', '5.0x', '2%', '4%', '25%', false],
                      ['Agriculture, Sylviculture & Pêche', '8%', '5.0x', '2%', '6%', '20%', false],
                      ['Autres Services', '10%', '5.5x', '2%', '3%', '12%', false],
                      ['Généraliste Mid-Market (défaut)', '12%', '6.0x', '3%', '4%', '15%', false],
                    ].map(([s, m, mult, g, cx, wcr, calibrated]) => (
                      <tr key={s as string} className={`border-b border-slate-800/50 hover:bg-slate-800/30 ${calibrated ? 'bg-cyan-950/20' : ''}`}>
                        <td className="py-2 px-3 text-cyan-400 font-bold">
                          {s}{calibrated && <span className="ml-2 text-[8px] text-cyan-300 border border-cyan-800 rounded px-1 py-0.5">CALIBRABLE</span>}
                        </td>
                        <td className="py-2 px-3 text-right">{m}</td>
                        <td className="py-2 px-3 text-right">{mult}</td>
                        <td className="py-2 px-3 text-right">{g}</td>
                        <td className="py-2 px-3 text-right">{cx}</td>
                        <td className="py-2 px-3 text-right">{wcr}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <SectionH3 icon={<FileText size={14} />}>5.7 — Ce qui est modifiable vs fixe</SectionH3>
            <P>
              <strong className="text-emerald-400">Modifiable</strong> depuis l'interface : CA d'entrée, secteur (donc profil),
              multiples d'entrée/sortie (override manuel), structure de dette complète (nombre de
              tranches, taille, taux, profil amortissable/bullet), management package (sweet equity,
              seuil et bonus de ratchet), décote taille/illiquidité du calibrage, horizon de détention
              (3 à 7 ans).
            </P>
            <P>
              <strong className="text-slate-500">Fixe (constantes du moteur)</strong> : taux d'IS France (25 %), plafond de
              dette totale (60 % de l'EV), garde-fou de croissance (± 50 %/an), et — en mode simple
              (V2, sans tranche personnalisée) uniquement — le levier senior par défaut (4,0x EBITDA)
              et son taux (7 %).
            </P>

            <SectionH3 icon={<FileSpreadsheet size={14} />}>5.8 — Export Excel : modèle vivant à 8 onglets</SectionH3>
            <P>
              L'export <C>.xlsx</C> (calculateur : <C>POST /lbo/export-excel</C> ; deal promu :{' '}
              <C>GET /deals/{'{id}'}/export-lbo-excel</C>, qui lit le scénario LBO de référence déjà
              sauvegardé) reproduit un modèle de fonds professionnel — <strong className="text-emerald-400">toute
              hypothèse est une cellule d'entrée, toute valeur dérivée est une formule Excel native</strong> :
              flexer une hypothèse (multiple de sortie, croissance, taux…) recalcule tout le classeur,
              retours compris, sans rouvrir l'application. Convention de couleur : <span className="text-blue-400 font-mono">bleu</span> = saisie,{' '}
              <span className="font-mono">noir</span> = formule calculée, <span className="text-emerald-500 font-mono">vert</span> = lien pur vers un
              autre onglet.
            </P>
            <P>8 onglets, dans cet ordre :</P>
            <ol className="list-decimal list-inside space-y-1 text-[13px] text-slate-300 ml-2">
              <li><strong className="text-cyan-400">Cover & Assumptions</strong> — en-tête cible/secteur/pays/scénario (deals promus uniquement), provenance réel vs estimé de chaque chiffre clé (§9), puis toutes les hypothèses.</li>
              <li><strong className="text-cyan-400">Sources & Uses</strong> — emplois (EV) vs sources (dette + equity sponsor), entièrement par liens vers l'onglet 1 (aucune hypothèse dupliquée), avec contrôle dur Sources = Emplois.</li>
              <li><strong className="text-cyan-400">Operating Model</strong> — Revenue → EBITDA → EBT → impôt → FCF. Le moteur ne modélise pas de D&A distinct de l'EBITDA : la base imposable est EBITDA − intérêts, jamais un poste EBIT fabriqué.</li>
              <li><strong className="text-cyan-400">Debt Schedule</strong> — par tranche en mode V3 (multi-tranche : annuité fixe pour l'amortissable, jamais de remboursement anticipé pour le bullet), ou tranche unique à cash-sweep intégral en mode V2 legacy (le mode réellement utilisé par tous les deals promus du produit aujourd'hui) — deux mécaniques distinctes, chacune reflétée exactement.</li>
              <li><strong className="text-cyan-400">Returns & Waterfall</strong> — Exit EV, Exit Equity, MoIC, IRR natif (<C>=IRR()</C>) et le waterfall Fund/Management si le scénario en a un.</li>
              <li><strong className="text-cyan-400">Sensitivity</strong> — grilles IRR/MOIC (entrée×sortie, levier×sortie), réutilisant la sensibilité déjà bâtie pour le mémo IC (§7.4). Ce sont des <strong className="text-amber-400">snapshots calculés par le moteur Python à l'export</strong>, explicitement étiquetés comme tels : reconstruire 25+ cellules de simulation multi-année en formules Excel natives sans macro n'est pas praticable — limite honnête, documentée dans l'onglet lui-même plutôt que masquée derrière une fausse formule "vivante".</li>
              <li><strong className="text-cyan-400">Credit Metrics</strong> — Dette/EBITDA, EBITDA/Intérêts, FCF/Dette, DSCR — combinaisons de cellules déjà présentes sur Operating Model/Debt Schedule, aucune nouvelle donnée moteur. Le DSCR vaut trivialement 1,00x tant que le cash-sweep est intégral (V2) : c'est la conséquence mathématique honnête d'un modèle qui alloue 100 % du cash disponible au service de la dette, pas un défaut.</li>
              <li><strong className="text-cyan-400">Checks</strong> — Sources = Emplois, cohérence du roll-forward de dette (par tranche), cohérence des retours (recalcul indépendant Exit Equity et MOIC×Entry Equity), cohérence de l'EBITDA entre onglets, absence de solde de dette négatif, et IRR vs sa forme fermée MOIC^(1/n)−1. Chaque ligne est <strong className="text-emerald-400">PASS/FAIL par formule</strong> (mise en forme conditionnelle verte/rouge) — jamais une valeur écrite en dur.
              </li>
            </ol>
            <P>
              Vérifié à la génération (BTP Consultants, deal réel) : classeur recalculé sous LibreOffice,
              concordance à l'euro/au centime près avec la sortie du moteur sur les 6 années de
              projection et tous les indicateurs de retour ; flexer le multiple de sortie dans le classeur
              fait bouger IRR/MOIC de façon cohérente, sans aucun appel Python ; onglet Checks entièrement
              au vert.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 6 — Buy & Build Engine
         ══════════════════════════════════════════════════════ */}
      <div id="buildup">
        <Card title="6. Buy & Build (roll-up)" subtitle="Multiple arbitrage — hypothèses sourcées sur le profil sectoriel TIC, toutes modifiables">
          <div className="p-5 space-y-1">
            <P>
              Simule une stratégie de <strong className="text-cyan-400">consolidation</strong> : une plateforme acquiert des
              add-ons, consolide CA/EBITDA avec des synergies d'échelle, puis sort au multiple de la plateforme
              plutôt qu'au multiple (souvent plus faible) auquel chaque add-on a été acheté — <strong className="text-cyan-400">l'arbitrage
              de multiple</strong>. C'est une surcouche : elle réutilise les constantes du LBO standalone (§5) sans
              dupliquer ni modifier son moteur de calcul.
            </P>

            <SectionH3 icon={<Zap size={14} />}>6.1 — Théorie du multiple arbitrage</SectionH3>
            <Eq label="Multiple mixte à l'achat">
              Blended_Multiple = Σ(EV_i) / Σ(EBITDA_i), i ∈ {'{'} Plateforme, Add-ons {'}'} (EBITDA avant synergies)
            </Eq>
            <P>
              La création de valeur par arbitrage vient de l'écart entre ce multiple mixte payé à l'achat et le
              multiple de sortie retenu (celui de la plateforme) — appliqué à un EBITDA consolidé plus gros et
              (si les synergies se matérialisent) plus élevé que la somme des parties.
            </P>

            <SectionH3 icon={<Network size={14} />}>6.2 — Hypothèses par défaut : sourcées, pas arbitraires</SectionH3>
            <P>
              Avant correction, les hypothèses de croissance (3 %), Capex (4 % du CA) et BFR (15 % de ΔCA)
              étaient des constantes codées en dur, sans lien avec le reste du projet. Elles ont été remplacées
              par les valeurs du profil sectoriel <strong className="text-cyan-400">« Conseil, Juridique &amp; Ingénierie »</strong>{' '}
              (<C>professional_svc</C>, §5.7) — pas un choix arbitraire : c'est le secteur réel de <em>toutes</em> les
              cibles sourcées par ce projet (périmètre NAF 71.20B/71.12B, §1.1), et le seul profil calibré sur un
              CompSet réel (§4.1).
            </P>
            <div className="overflow-x-auto mb-3">
              <table className="w-full text-left border-collapse text-[11px] font-mono">
                <thead>
                  <tr className="text-[10px] text-slate-500 border-b border-slate-800 uppercase">
                    <th className="py-2 px-3">Hypothèse</th>
                    <th className="py-2 px-3 text-right">Défaut (profil TIC)</th>
                    <th className="py-2 px-3">Modifiable</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  <tr className="border-b border-slate-800/50"><td className="py-2 px-3">Croissance CA consolidé</td><td className="py-2 px-3 text-right">4 %/an (ou inférée des projections LBO réelles des cibles si disponibles)</td><td className="py-2 px-3 text-emerald-400">Oui</td></tr>
                  <tr className="border-b border-slate-800/50"><td className="py-2 px-3">Capex</td><td className="py-2 px-3 text-right">2 % du CA</td><td className="py-2 px-3 text-emerald-400">Oui</td></tr>
                  <tr className="border-b border-slate-800/50"><td className="py-2 px-3">BFR</td><td className="py-2 px-3 text-right">15 % de ΔCA</td><td className="py-2 px-3 text-emerald-400">Oui</td></tr>
                  <tr className="border-b border-slate-800/50"><td className="py-2 px-3">Levier d'entrée</td><td className="py-2 px-3 text-right">4.0x EBITDA (partagé avec le LBO standalone, §5.7)</td><td className="py-2 px-3 text-emerald-400">Oui</td></tr>
                  <tr><td className="py-2 px-3">Synergies</td><td className="py-2 px-3 text-right">5 % du CA consolidé (fourchette usuelle 3-8 % pour un roll-up de services professionnels)</td><td className="py-2 px-3 text-emerald-400">Oui</td></tr>
                </tbody>
              </table>
            </div>
            <P>
              Chaque hypothèse est éditable dans le panneau « Hypothèses avancées » de la page Buy &amp; Build, avec
              une courte explication de ce qu'elle représente — jamais un curseur nu sans contexte.
            </P>

            <SectionH3 icon={<Building2 size={14} />}>6.3 — Lien au pipeline réel</SectionH3>
            <P>
              La plateforme se sélectionne parmi les cibles sourcées réelles (idéalement <C>target_type=platform</C>,
              §1.1 — ex. Artelia, Dekra) et les add-ons parmi les cibles <C>target</C>. Certaines plateformes réelles
              n'ont pas de quick-screen financier propre (sourcées via la voie « grands groupes » plutôt que le
              quick-screen OSINT, §1.2) : dans ce cas, EBITDA et EV sont estimés avec le même profil sectoriel TIC
              (marge 15 %, multiple 7.0x) que celui déjà utilisé pour le quick-screen des autres cibles — et la
              simulation le signale explicitement (badge « estimé »), jamais présenté comme une donnée propre à
              la cible.
            </P>

            <SectionH3 icon={<BarChart3 size={14} />}>6.4 — Comparaison des rendements</SectionH3>
            <Eq label="Delta IRR">
              ΔIRR = IRR_buildup − IRR_standalone
            </Eq>
            <P>
              <C>IRR_standalone</C>/<C>MOIC_standalone</C> viennent du quick-screen de la plateforme seule (s'il
              existe) — un ΔIRR positif indique que la consolidation crée de la valeur par rapport à un scénario
              où la plateforme resterait seule.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 7 — IC Memo & Exports
         ══════════════════════════════════════════════════════ */}
      <div id="memo">
        <Card title="7. IC Memo & Exports" subtitle="Format IC professionnel 9 sections, narration LLM sur données réelles, contexte partagé mémo/deck">
          <div className="p-5 space-y-1">
            <SectionH3 icon={<MessageSquare size={14} />}>7.1 — Format 9 sections</SectionH3>
            <P>
              Le mémo suit désormais une structure IC professionnelle à <strong className="text-cyan-400">9 sections fixes</strong> (gpt-4o-mini,
              température 0.2), toujours rédigées en anglais quelle que soit la langue des données sous-jacentes
              (choix délibéré, cohérence d'un run à l'autre) : <C>I. Executive Summary</C>, <C>II. Company Overview</C>,{' '}
              <C>III. Industry &amp; Market</C>, <C>IV. Financial Analysis</C>, <C>V. Investment Thesis</C>,{' '}
              <C>VI. Deal Terms &amp; Structure</C>, <C>VII. Returns Analysis</C>, <C>VIII. Risk Factors</C>,{' '}
              <C>IX. Recommendation</C>. Le LLM ne calcule et n'invente aucun chiffre — il ne fait que citer, avec leur
              provenance, les valeurs déjà calculées par le moteur LBO / le calibrage / le CompSet, et rédiger
              l'analyse (thèse, risques, recommandation) autour. Tout point de donnée que l'outil n'a pas
              (management, headcount, quality of earnings, BFR, capex détaillé…) reçoit le marqueur standard{' '}
              <C>[To be completed in due diligence — data not available from automated analysis]</C> — jamais une
              valeur devinée pour combler le vide.
            </P>

            <SectionH3 icon={<Shield size={14} />}>7.2 — Un contexte unique, partagé mémo + deck</SectionH3>
            <P>
              <C>ic_context.build_ic_context()</C> assemble un seul dictionnaire structuré — chiffres qualifiés de
              leur provenance (§9), tableau Sources &amp; Uses, scénario LBO de référence, comparables — et c'est ce
              MÊME objet qui alimente le prompt du LLM, l'export Word et l'export PPTX. Les trois ne peuvent donc
              jamais diverger sur un chiffre : il n'existe qu'un seul endroit où un montant est qualifié ou un
              tableau assemblé. Le multiple d'entrée cité suit la chaîne de calibrage (§4.1) si applicable, sinon la
              mention explicite d'un profil sectoriel générique ; le scénario LBO n'est cité que s'il existe
              réellement (jamais un IRR/MOIC inventé).
            </P>

            <SectionH3 icon={<AlertTriangle size={14} />}>7.3 — Self-check obligatoire (cohérence des tableaux)</SectionH3>
            <P>
              Avant génération, un contrôle programmatique vérifie que les tableaux financiers du mémo/deck se
              tiennent : (1) <strong className="text-emerald-400">Sources = Uses</strong> (dette + equity = enterprise value, à l'euro
              près) ; (2) <strong className="text-emerald-400">cohérence des retours</strong> (exit equity / entry equity recalculé vs MOIC
              stocké) ; (3) <strong className="text-amber-400">cohérence de l'EBITDA</strong> entre le chiffre posé sur le deal et l'EBITDA
              d'entrée du scénario LBO. Ce 3ᵉ contrôle échoue en pratique sur les deals antérieurs au calibrage
              sectoriel (§4.1) : le deal porte l'EBITDA du profil sectoriel générique (marge par défaut), le scénario
              LBO porte l'EBITDA calibré sur la médiane du CompSet réel — deux méthodes d'estimation légitimes mais
              distinctes, calculées à des moments différents. Le mémo/deck ne force jamais l'un à correspondre à
              l'autre : les deux chiffres sont cités avec leur provenance propre, et l'écart est expliqué en toutes
              lettres dans la Section IV/VI plutôt que masqué.
            </P>

            <SectionH3 icon={<Calculator size={14} />}>7.4 — Sensibilité des retours (Section VII)</SectionH3>
            <P>
              Quand un scénario LBO de référence existe, la Section VII inclut une grille de sensibilité{' '}
              <strong className="text-cyan-400">IRR/MOIC par multiple de sortie × levier d'entrée</strong> — reconstruite en appelant le
              moteur LBO existant (<C>run_lbo_model</C>) avec le profil sectoriel exact figé du scénario sauvegardé
              (marge EBITDA, croissance, capex, BFR repris tels quels depuis <C>result_json</C>), en ne faisant varier
              que le multiple de sortie et le levier. Aucune nouvelle formule : la cellule centrale de la grille
              reproduit exactement l'IRR/MOIC du scénario de base, preuve que le calcul reste fidèle au modèle réel.
            </P>

            <SectionH3 icon={<GitBranch size={14} />}>7.5 — Effet de bord</SectionH3>
            <P>
              Générer un mémo fait passer le statut du deal de <C>Screening</C> à <C>IC Review</C> — une seule fois,
              jamais si le statut a déjà été avancé manuellement au-delà (voir Deal Pipeline).
            </P>

            <SectionH3 icon={<FileText size={14} />}>7.6 — Exports Word (.docx) et PPTX</SectionH3>
            <P>
              <strong className="text-emerald-400">Export Word</strong> : 9 sections, tableaux calculés indépendamment du LLM (chiffres
              clés, analyse financière, Sources &amp; Uses, grille de sensibilité, tableau de self-check) interleavés
              avec la narration extraite verbatim du markdown généré — les tableaux s'affichent même si le mémo n'a
              pas encore été généré.
            </P>
            <P>
              <strong className="text-amber-400">Export PPTX</strong> : même structure 9 sections en 12 diapositives (couverture +
              une ou deux diapositives par section), consommant le même <C>ic_context</C> que le Word — couverture,
              synthèse, profil société, marché &amp; comparables, analyse financière, thèse, valorisation, structure
              du capital, retours &amp; sensibilité, risques (avec les limites de self-check affichées si un contrôle
              échoue), recommandation. Dégrade proprement (section marquée indisponible) plutôt que d'échouer si le
              scénario LBO ou les comparables manquent.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 8 — Macro & Crédit
         ══════════════════════════════════════════════════════ */}
      <div id="macro">
        <Card title="8. Macro & Crédit" subtitle="Credit & Macro Dashboard + Money Market & Rates — sources FRED, verdicts calculés">
          <div className="p-5 space-y-1">
            <P>
              Ces deux pages sont servies par le backend Express (marché/macro), pas par FastAPI — source unique :
              l'API <strong className="text-cyan-400">FRED</strong> (Federal Reserve Economic Data). Aucune donnée simulée n'est
              affichée comme réelle : quand FRED est indisponible, un badge de repli honnête remplace le badge
              « live » (jamais silencieusement).
            </P>

            <SectionH3 icon={<Database size={14} />}>8.1 — Fraîcheur</SectionH3>
            <P>
              Credit &amp; Macro : aucun cache serveur — chaque chargement de page interroge FRED en direct
              (rafraîchissement client fixé à 10 min). Money Market : cache serveur 60 minutes (footer affiche
              l'heure exacte du dernier rafraîchissement). Chaque indicateur affiche sa propre date de dernière
              valeur publiée — pas une date globale supposée, car les séries FRED combinées n'ont pas toutes la
              même fréquence de publication (quotidienne pour les taux, mensuelle pour certains indices).
            </P>

            <SectionH3 icon={<Scale size={14} />}>8.2 — Logique des verdicts qualitatifs</SectionH3>
            <P>
              Chaque étiquette qualitative est <strong className="text-emerald-400">recalculée depuis une variation réelle</strong>{' '}
              (dernière valeur FRED vs dernière valeur distincte précédente) — jamais une constante :
            </P>
            <Eq label="Banques centrales — Hawkish / Dovish / Hold">
              Variation ≥ +5 points de base → Hawkish{'\n'}
              Variation ≤ −5 points de base → Dovish{'\n'}
              Sinon → Hold
            </Eq>
            <Eq label="Stress crédit — niveau">
              ratio = valeur / seuil{'\n'}
              ratio ≥ 85% → High · ratio ≥ 50% → Medium · sinon → Low
            </Eq>
            <Eq label="Stress crédit — tendance">
              Baisse (spread, VIX, taux directeur) → improving (détente){'\n'}
              Hausse → deteriorating (tension){'\n'}
              |variation| non significative → stable
            </Eq>
            <P>
              Exception documentée : le taux directeur BoJ n'a aucune série FRED fiable et à jour identifiée
              (la série candidate testée s'est arrêtée en 2023) — reste une valeur statique, explicitement
              signalée <C>STATIQUE</C> dans l'interface plutôt que présentée comme « live » par commodité.
            </P>

            <SectionH3 icon={<TrendingUp size={14} />}>8.3 — Money Market : honnêteté sur les taux dérivés</SectionH3>
            <P>
              Euribor 3M vient d'une série FRED réelle (taux interbancaire zone euro, proxy mensuel). Euribor 6M
              et 12M n'ont pas de série FRED directe fiable identifiée : ils sont <strong className="text-amber-400">dérivés</strong> du 3M
              réel via un spread de marché constant documenté (+5bps, +10bps) — étiquetés <C>FRED (dérivé)</C>,
              jamais confondus avec une observation FRED brute (<C>FRED</C> tout court) dans le badge source.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 9 — Traçabilité
         ══════════════════════════════════════════════════════ */}
      <div id="tracabilite">
        <Card title="9. Traçabilité" subtitle="Chaque chiffre sait d'où il vient — 6 provenances, jamais devinées">
          <div className="p-5 space-y-1">
            <P>
              Principe transversal du projet : toute valeur financière porte une provenance explicite
              (<C>DataProvenance</C>), un des 6 statuts suivants — jamais un septième deviné à la volée :
            </P>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              {[
                { name: 'REGISTRY', desc: 'Comptes officiels déposés (registre, greffe, INPI)', cls: 'border-emerald-900/40 text-emerald-400' },
                { name: 'MARKET', desc: 'Fournisseur de données de marché (FMP, Finnhub, ESEF)', cls: 'border-sky-900/40 text-sky-400' },
                { name: 'DOCUMENT', desc: "Extrait d'un document fourni (teaser, rapport annuel)", cls: 'border-cyan-900/40 text-cyan-400' },
                { name: 'MANUAL', desc: "Saisi ou corrigé par l'utilisateur", cls: 'border-violet-900/40 text-violet-400' },
                { name: 'ESTIMATE', desc: "Dérivé d'une hypothèse ou d'une règle de calcul", cls: 'border-amber-900/40 text-amber-400' },
                { name: 'UNKNOWN', desc: 'Origine indéterminable — jamais devinée', cls: 'border-rose-900/40 text-rose-400' },
              ].map(prov => (
                <div key={prov.name} className={`bg-slate-950 border rounded-lg p-3 ${prov.cls.split(' ')[0]}`}>
                  <div className={`text-[10px] font-bold uppercase mb-1 font-mono ${prov.cls.split(' ')[1]}`}>{prov.name}</div>
                  <div className="text-[11px] text-slate-400">{prov.desc}</div>
                </div>
              ))}
            </div>

            <SectionH3 icon={<Link2 size={14} />}>9.1 — Provenance d'une valeur dérivée</SectionH3>
            <P>
              Quand une valeur est calculée à partir de plusieurs champs (ex. EV/EBITDA), elle hérite de la
              provenance la plus <strong className="text-rose-400">faible</strong> de ses composants — jamais celle du composant
              le plus solide :
            </P>
            <Eq label="Ordre de robustesse (du plus faible au plus fort)">
              UNKNOWN {'<'} ESTIMATE {'<'} MANUAL {'<'} DOCUMENT {'<'} MARKET {'<'} REGISTRY
            </Eq>
            <P>
              Exemple : un multiple EV/EBITDA calculé sur un EBITDA <C>ESTIMATE</C> reste <C>ESTIMATE</C>, même si
              l'EV utilisée venait d'un registre officiel (<C>REGISTRY</C>) — le maillon le plus faible détermine
              la fiabilité globale.
            </P>

            <SectionH3 icon={<AlertTriangle size={14} />}>9.2 — Correction d'une affirmation précédente de cette page</SectionH3>
            <P>
              Une version antérieure de cette section affirmait que <C>DOCUMENT</C> et <C>MANUAL</C> n'étaient
              jamais posés par le flux d'upload live — c'était <strong className="text-rose-400">inexact</strong> : l'investigation qui a
              suivi (recherche limitée à tort au code Python d'<C>api/</C>) avait manqué la logique, bien réelle,
              construite côté client dans <C>DocumentReviewModal.tsx</C> (<C>buildFieldProvenance</C>) — DOCUMENT si
              le champ n'a pas été modifié après extraction, MANUAL s'il a été corrigé, décidé à la soumission en
              comparant la valeur finale à la valeur extraite d'origine. Vérifié en base sur un upload réel :
              un champ non modifié est bien tagué <C>DOCUMENT</C> avec le nom du fichier en référence, un champ
              corrigé est bien tagué <C>MANUAL</C>.
            </P>
            <P>
              La vraie rupture trouvée en creusant plus loin était ailleurs : l'extraction renvoie les montants en{' '}
              <strong className="text-amber-400">millions d'euros</strong> (contrat explicite du prompt LLM), mais la modale les
              envoyait tels quels dans un champ stocké en euros absolus partout ailleurs dans l'app — un facteur
              ×1 000 000 manquant qui aurait fait persister un CA réel de 61,1 M€ comme <C>61.1</C> en base. Corrigée
              (conversion à la soumission, libellés clarifiés « M€ » / « € »). Ce type d'erreur — une provenance
              honnête pointant vers une valeur fausse — est plus trompeur qu'une provenance manquante : signalé ici
              en toute transparence plutôt que corrigé silencieusement.
            </P>
            <P>
              Ce système est <strong className="text-slate-500">distinct</strong> des badges « MOCK DATA » ponctuels visibles ailleurs
              dans l'app (ex. certaines intégrations OSINT, ou le repli statique du backend marché/macro,
              §8) : ceux-ci signalent une source de données entière non branchée, pas la provenance d'un champ
              individuel.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 10 — Architecture
         ══════════════════════════════════════════════════════ */}
      <div id="architecture">
        <Card title="10. Architecture" subtitle="Deux backends, un frontend — séparation stricte des domaines">
          <div className="p-5 space-y-1">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
              <div className="bg-slate-950 border border-cyan-900/40 rounded-lg p-3">
                <div className="text-[10px] font-bold text-cyan-400 uppercase mb-1 font-mono">FastAPI :8000</div>
                <div className="text-[11px] text-slate-400">
                  Source de vérité du domaine M&amp;A : sourcing, scoring, comparables, calibrage, moteur LBO,
                  Buy &amp; Build, deals, mémos IC. Base SQLite (SQLAlchemy async). Sections 1 à 7, 9 de cette page.
                </div>
              </div>
              <div className="bg-slate-950 border border-emerald-900/40 rounded-lg p-3">
                <div className="text-[10px] font-bold text-emerald-400 uppercase mb-1 font-mono">Express :3001</div>
                <div className="text-[11px] text-slate-400">
                  Couche marché/macro/news uniquement : FRED (taux, crédit, money market), NewsAPI (actualités
                  thématiques), indices boursiers. Pas de base de données — cache fichier local (money market,
                  news). Section 8 de cette page.
                </div>
              </div>
              <div className="bg-slate-950 border border-amber-900/40 rounded-lg p-3">
                <div className="text-[10px] font-bold text-amber-400 uppercase mb-1 font-mono">React :3000</div>
                <div className="text-[11px] text-slate-400">
                  Frontend Vite/React/TypeScript. Consomme les deux backends directement (pas de proxy/agrégation
                  côté client) — chaque page sait explicitement de quel backend elle dépend.
                </div>
              </div>
            </div>
            <P>
              Cette séparation stricte est délibérée : le domaine M&amp;A (données d'entreprises, deals, modèles
              financiers) ne doit jamais dépendre de la disponibilité de la couche marché/macro, et
              réciproquement — une panne FRED ne bloque jamais le sourcing ou le calcul d'un LBO.
            </P>
          </div>
        </Card>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 11 — La démo expliquée
         ══════════════════════════════════════════════════════ */}
      <div id="demo">
        <Card title="11. La démo expliquée" subtitle="Le parcours de bout en bout, et ce que chaque étape démontre">
          <div className="p-5 space-y-1">
            <P>
              Le parcours suivant illustre la chaîne complète du projet, d'une cible brute à un mémo
              d'investissement exportable — chaque étape mobilise un module documenté ci-dessus.
            </P>
            <Step n={1} label="Sourcing d'une cible" desc="Un scan (registre ou Radar, §1) ramène une cible réelle avec son score de qualification (§2) — démontre le filtrage NAF déterministe et la note LLM." />
            <Step n={2} label="Promotion en deal (LBO base-case auto)" desc="La cible devient un Deal ; un scénario LBO 'Base Case' est calculé et sauvegardé automatiquement à la promotion (§5) — démontre que le pipeline sourcing → valorisation ne nécessite aucune ressaisie manuelle." />
            <Step n={3} label="Spreading d'un teaser" desc="Upload d'un document (§3) : extraction, garde-fous de vraisemblance, revue humaine avant toute sauvegarde — démontre que l'IA assiste la saisie sans jamais s'y substituer." />
            <Step n={4} label="Valorisation calibrée" desc="Le multiple d'entrée est recalculé depuis le CompSet réel (§4.1) si le secteur de la cible correspond au CompSet calibré — démontre la chaîne médiane comparables → décote → multiple." />
            <Step n={5} label="LBO complet" desc="Structure de dette multi-tranches, cash-flows, IRR/MOIC (§5) — démontre le moteur complet, du Sources & Uses à la sortie." />
            <Step n={6} label="Mémo IC" desc="Génération LLM avec chaque chiffre pré-qualifié par sa provenance (§7) — démontre la traçabilité (§9) appliquée à un livrable final." />
            <Step n={7} label="Exports Word / PPTX" desc="Le mémo devient un document Word et un deck IC complet (§7.4) — démontre que le pipeline produit un livrable utilisable hors de l'application, pas seulement un écran." />
          </div>
        </Card>
      </div>

      {/* ── Footer / Disclaimer ── */}
      <div className="bg-slate-900/30 border border-slate-800 rounded-lg px-5 py-4 text-[10px] text-slate-600 font-mono leading-relaxed">
        <strong className="text-slate-500">Disclaimer :</strong> Ce terminal est un outil d'aide à la décision. 
        Les modèles financiers présentés sont des approximations (« Paper LBO ») et ne constituent pas un conseil en investissement. 
        Les données OSINT sont extraites automatiquement et peuvent contenir des erreurs. Les estimations de CA/EBITDA sont indicatives 
        et doivent être validées en due diligence. Les profils sectoriels sont des moyennes de marché — chaque transaction doit être 
        modélisée individuellement. © PE Terminal — Confidentiel &amp; Propriétaire.
      </div>
    </div>
  );
};
