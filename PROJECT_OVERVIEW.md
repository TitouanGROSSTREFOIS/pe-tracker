# PE Tracker

PE Tracker est un terminal opérationnel pour l'analyse de deals M&A / Private
Equity mid-market, du premier repérage d'une cible jusqu'au mémo de comité
d'investissement.

## Le problème adressé

Une petite équipe d'investissement (PE, corporate development) qui prospecte
le mid-market n'a en général ni Bloomberg, ni Capital IQ, ni une base de
comparables privée déjà constituée. PE Tracker reconstitue ce flux de travail
à partir de sources publiques et gratuites, sur une thèse sectorielle
volontairement précise : le **TIC** (Test, Inspection, Certification) et
l'ingénierie technique.

## Ce qu'il fait, de bout en bout

1. **Sourcing** — identifie des cibles réelles par code NAF et taille dans le
   registre officiel des entreprises françaises (pas de recherche par
   mots-clés comme point d'entrée).
2. **Qualification** — filtre et note les cibles par pertinence sectorielle
   et taille de chiffre d'affaires.
3. **Spreading assisté par IA** — extrait automatiquement les données
   financières d'un teaser ou d'un rapport PDF, avec relecture humaine
   obligatoire avant tout enregistrement.
4. **Valorisation calibrée** — construit un univers de comparables cotés
   (Europe/US) à partir de données de marché réelles et en dérive un multiple
   d'entrée sectoriel, plutôt qu'un multiple fixé arbitrairement.
5. **Modélisation LBO** — moteur multi-tranches (dette senior/mezzanine,
   cash-sweep, waterfall), scénarios sauvegardables, export Excel à formules
   vivantes.
6. **Mémo IC** — génère un mémo de comité d'investissement rédigé, citant les
   chiffres du deal avec leur origine.

Le pipeline complet (deals, portefeuille, comparables, LBO, mémos) reste
piloté depuis un tableau de bord unique.

## Le principe différenciant

**100 % de sources de données publiques et gratuites** (registre officiel,
Sirene, dépôts réglementaires XBRL, API de marché à quota gratuit) — aucun
abonnement Bloomberg/Capital IQ requis. En contrepartie, chaque donnée
affichée porte sa **provenance** (registre officiel, document fourni, marché,
estimation, saisie manuelle) : rien n'est présenté comme un fait établi sans
pouvoir dire d'où il vient, et aucune donnée simulée n'est jamais affichée
sans étiquette.

## Stack

FastAPI (Python) pour le domaine métier M&A, Express (Node/TypeScript) pour
la couche marché/macro/news, React/Vite pour l'interface.

---

Pour le détail des modules, des sources de données et des limites assumées :
voir [README.md](README.md). Pour l'installation et le démarrage : voir
[RUNBOOK.md](RUNBOOK.md).
