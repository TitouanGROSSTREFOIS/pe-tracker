# PE Tracker — Script de démonstration (2-3 min, live)

> Principe : tout est pré-chargé avant l'entretien. Tu ne cliques en direct que
> 3 moments. Le reste, tu le racontes. Ne jamais attendre un chargement à l'écran
> devant le recruteur.

---

## 0. Le crochet — une phrase, avant même de cliquer

> « J'ai construit un outil qui reproduit le cycle d'analyse d'un fonds mid-market
> sur un secteur précis — le contrôle et l'ingénierie technique — entièrement à
> partir de données publiques gratuites. Il source des cibles réelles, les
> valorise, modélise le LBO et rédige la note de comité. Je vous montre la chaîne
> en deux minutes. »

Puis tu enchaînes directement. Pas de préambule technique, pas de « alors voilà, j'ai utilisé FastAPI et React ». La stack, tu la donnes seulement si on te la demande.

---

## 1. La séquence — 3 temps forts

### Temps 1 — L'origination (~30 s) · écran : Deal Sourcing

**Ce que tu montres :** la liste des cibles réelles, badges TARGET / PLATFORM, CA réels.

**Ce que tu dis :**
> « Le point de départ n'est pas Google, c'est le registre officiel. Je filtre
> l'univers français par code d'activité — le contrôle et l'ingénierie technique
> — et par taille. Ça donne environ 2 500 sociétés, dont 70 % publient un chiffre
> d'affaires exploitable. L'outil a trouvé et qualifié seul des acteurs comme
> Dekra ou Artelia, sans que je les cherche. »

**Le geste :** tu pointes une cible, tu cliques « Promouvoir en deal ».

**Phrase de bascule :**
> « Je distingue les cibles d'acquisition, sous 100 M€, des plateformes de
> consolidation au-dessus — c'est la logique d'un buy-and-build. »

---

### Temps 2 — La valorisation traçable (~45 s) · écran : LBO Calculator (deal pré-rempli)

**Ce que tu montres :** le bloc de calibrage du multiple d'entrée, déjà affiché.

**Ce que tu dis — c'est ICI que tu gagnes des points :**
> « Le multiple d'entrée n'est pas posé au doigt mouillé. Je pars de la médiane
> des comparables cotés du secteur — Bureau Veritas, SGS, Intertek, Eurofins —
> soit 12,5 fois l'EBITDA. J'applique une décote de taille et d'illiquidité de
> 35 %, parce qu'on ne paie pas une PME non cotée comme un leader mondial coté.
> J'entre donc à 8,2 fois. Et chaque chiffre affiche sa source. »

**Le geste :** tu survoles un multiple → le badge de provenance apparaît (MARCHÉ / ESEF, exercice).

> « Ça, c'est extrait des dépôts financiers officiels européens, en données
> structurées. Gratuit, vérifiable. »

---

### Temps 3 — Le livrable (~45 s) · écrans : Excel puis IC memo

**Ce que tu montres d'abord :** l'export Excel déjà ouvert dans un onglet.

**Ce que tu dis :**
> « Le LBO s'exporte en modèle Excel entièrement recalculable. Si vous changez le
> multiple de sortie ici… » — tu modifies une cellule bleue — « …le TRI et le
> MOIC se recalculent, sans repasser par l'application. C'est un vrai modèle, pas
> une capture. »

**Puis :** l'IC memo généré.

> « Et l'outil rédige la note de comité en anglais, en citant ses propres
> sources — y compris ses limites. Là, il signale de lui-même que l'EBITDA d'une
> cible non cotée est difficile à obtenir en due diligence. Il ne cache pas ce
> qu'il ne sait pas. »

**Clôture :**
> « De la donnée publique à la note de comité, traçable de bout en bout. »

---

## 2. Les 4 phrases clés à ancrer (si tu ne retiens que ça)

1. « Je pars du registre officiel, pas de Google — d'où un univers exhaustif et zéro faux positif. »
2. « 12,5x coté, moins 35 % de décote taille/illiquidité, égale 8,2x sur le non coté. »
3. « Chaque chiffre affiche sa source. »
4. « L'outil signale lui-même les limites de ses données. »

---

## 3. Les parades — questions pièges

### ⚠️ SECTION DETTE (ton point à blinder — apprends-la par cœur)

**« Explique-moi comment tu structures la dette. »**
> « L'acquisition se finance en deux blocs : de la dette et des fonds propres.
> Je cale la dette à 4 fois l'EBITDA — un levier standard sur le mid-market. Sur
> une cible à 8,4 M€ d'EBITDA, ça fait environ 34 M€ de dette. Le reste du prix
> d'achat, c'est l'apport en fonds propres du fonds. »

**« Et comment tu gagnes de l'argent, alors ? »** — LA question centrale du LBO
> « Par trois leviers. Un : le désendettement — chaque année, le cash généré par
> la société rembourse la dette, donc la part de valeur qui revient aux fonds
> propres augmente mécaniquement, même sans rien faire d'autre. Deux : la
> croissance de l'EBITDA. Trois : l'expansion du multiple à la sortie, que je ne
> suppose pas ici — je sors au même multiple qu'à l'entrée, par prudence. »

**« Décris-moi le remboursement de la dette. »**
> « Il y a une tranche senior amortissable : elle se rembourse chaque année, mais
> plafonnée par le cash réellement disponible — si le cash-flow baisse, le
> remboursement baisse d'autant. Le modèle gère ça en cascade, la dette senior se
> sert avant la mezzanine. C'est un cash sweep : l'excédent de trésorerie va
> prioritairement à la dette. »

**« Comment tu passes de l'entrée à la sortie ? »**
> « À la sortie, à 5 ans : je reprends l'EBITDA de sortie, je le multiplie par le
> multiple de sortie pour obtenir la valeur d'entreprise. J'en retire la dette qui
> reste à ce moment-là, et ce qui reste, c'est la valeur des fonds propres. Le
> MOIC, c'est cette valeur de sortie divisée par l'apport de départ ; le TRI, c'est
> le même rapport annualisé sur 5 ans. »

**Le réflexe si on te pousse et que tu doutes :**
> « Le modèle Excel est ouvert, je peux vous dérouler la mécanique cellule par
> cellule. » → tu montres, tu ne bluffes pas. Un LBO qui se lit dans un tableur
> est plus convaincant qu'une récitation.

**Chiffres à connaître par cœur (cible BTP Consultants) :**
- CA ≈ 61 M€ · EBITDA ≈ 8,4 M€ (marge ~13,75 %)
- Multiple d'entrée 8,2x · levier 4x EBITDA · dette ≈ 34 M€
- Horizon 5 ans · sortie au même multiple · TRI ~15 % · MOIC ~2,0x
- *(Retiens l'ordre de grandeur, pas la décimale. « Autour de 15 % » suffit.)*

---

### Autres parades

**« D'où sort l'EBITDA si les comptes publics ne le donnent pas ? »**
> « Bonne remarque — les comptes français publics donnent le CA et le résultat
> net, pas l'EBITDA. Ici il vient du teaser. Quand la donnée manque, l'outil
> l'estime à partir de la marge sectorielle, mais il le marque explicitement comme
> estimé. La vraie source d'EBITDA réel sur du non coté, c'est la liasse détaillée
> de l'INPI, que j'intègre. »

**« Pourquoi EV/EBITDA et pas un autre multiple ? »**
> « Parce que sur des services techniques capitalistiquement légers, l'EBITDA est
> le meilleur proxy de la capacité à rembourser la dette — c'est ce qui compte en
> LBO. Le PER serait faussé par les structures de dette différentes ; EV/EBITDA
> neutralise ça. »

**« Pourquoi 35 % de décote, et pas 30 ou 40 ? »**
> « C'est un paramètre, pas un dogme — je peux le bouger en direct. 35 % est un
> point médian pour la décote taille + illiquidité sur le mid-market français.
> L'important n'est pas le chiffre exact, c'est que le raisonnement soit explicite
> et ajustable. »

**« En quoi c'est mieux qu'un stagiaire avec Excel ? »**
> « Le stagiaire met deux heures à retraiter un teaser et à monter la table de
> comps. L'outil le fait en trente secondes, avec la source de chaque chiffre
> tracée. Il ne remplace pas le jugement — il supprime le travail à faible valeur
> pour qu'on passe direct à l'analyse. »

**« C'est toi qui as tout codé ? »** — réponds franchement
> « J'ai piloté la conception et l'architecture, et une partie du code a été
> générée sous ma direction. Le vrai travail a été de traquer ce qui ne marchait
> pas vraiment — j'ai trouvé plusieurs fonctionnalités qui semblaient marcher et
> ne tournaient pas. C'est ça, le métier : ne pas croire un résultat sur parole. »

---

## 4. Checklist AVANT l'entretien (5 min de setup)

- [ ] Les 3 services lancés (`start.sh`), testés 10 min avant.
- [ ] Onglets pré-ouverts dans l'ordre : Deal Sourcing · LBO (deal #2 pré-rempli) · Excel export · IC memo.
- [ ] Le deal BTP Consultants est bien en base, calibrage affiché.
- [ ] L'Excel est déjà téléchargé et ouvert (ne pas le générer en live).
- [ ] Un mémo déjà généré et visible (pour ne pas dépendre d'OpenAI en direct).
- [ ] Connexion de secours prête (partage 4G du téléphone) au cas où le wifi lâche.
- [ ] **Ne pas ouvrir Deal Pipeline en démo** tant que le cache Adzuna n'est pas corrigé (29 appels externes au chargement).
- [ ] Zoom navigateur à ~110 % pour la lisibilité si écran partagé.

---

## 5. La version 30 secondes (si on ne te donne pas le temps de montrer)

> « J'ai construit un outil d'analyse pour un fonds mid-market, sur le secteur du
> contrôle technique. Il part du registre officiel pour sourcer des cibles réelles,
> les valorise par comparaison avec les leaders cotés en appliquant une décote
> d'illiquidité, modélise le rachat par effet de levier avec un export Excel
> recalculable, et rédige la note de comité. Tout ça sur de la donnée publique
> gratuite, avec la source de chaque chiffre tracée. Ce qui m'a le plus appris,
> c'est de débusquer ce qui ne marchait pas vraiment sous les apparences. »
