# RUNBOOK — Démarrage de PE Tracker

> Guide de lancement uniquement (installation, démarrage, variables
> d'environnement, erreurs fréquentes). Pour la présentation du projet et le
> détail de l'architecture des deux backends, voir [README.md](README.md) et
> [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).
>
> Mis à jour le 2026-07-22. Chaque commande ci-dessous a été exécutée
> réellement et a fonctionné, y compris le script `start.sh` et son arrêt
> propre au Ctrl+C.

## Services et ports

| Service | Port |
|---|---|
| API FastAPI (`api/`) | 8000 |
| Backend Express (`backend/`) | 3001 |
| Frontend Vite (`pe-market-intelligence-terminal/`) | 3000 |

Sans le serveur Express, les pages Market Intelligence (bandeau macro),
Credit & Macro et Money Market resteront incomplètes.

---

## 1. Prérequis (versions exactement testées)

| Outil | Version testée | Vérifier avec |
|---|---|---|
| Python | 3.13.1 | `python3 --version` |
| Node.js | v24.11.1 | `node --version` |
| npm | 11.6.2 | `npm --version` |

Le projet fournit déjà un environnement virtuel Python (`.venv/`) et les
`node_modules/` des deux projets Node. Si tu pars d'une machine neuve (pas
celle-ci), suis la section 2. Si `.venv/` et `node_modules/` existent déjà,
tu peux sauter directement à la section 3 (démarrage quotidien).

---

## 2. Installation initiale (one-shot, machine neuve)

### 2.1 — API Python (FastAPI)

Depuis la racine du projet :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
```

### 2.2 — Backend Node (Express)

```bash
cd backend
npm install
cd ..
```

### 2.3 — Frontend (React / Vite)

```bash
cd pe-market-intelligence-terminal
npm install
cd ..
```

### 2.4 — Variables d'environnement

Voir le tableau complet en section 4. Deux fichiers `.env` à créer :

```bash
cp api/.env.example api/.env
# puis éditer api/.env et coller les clés
```

`backend/.env` existe déjà avec un exemple dans `backend/.env.example`
(à dupliquer/adapter de la même façon si tu repars de zéro).

---

## 3. Démarrage quotidien

### Méthode principale — une seule commande

Depuis la racine du projet :

```bash
./start.sh
```

Lance les 3 services (FastAPI, Express, Vite) dans un seul terminal, avec les
logs de chacun préfixés (`[fastapi]`, `[express]`, `[vite   ]`) pour rester
lisibles. **Ctrl+C arrête proprement les 3 services** (y compris le
sous-processus `--reload` de uvicorn, qui échappe à un simple `kill` mal
ciblé — testé explicitement).

Si `start.sh` refuse de démarrer, il te dira précisément ce qui manque
(`.venv`, `node_modules`, `api/.env`) — reviens à la section 2.

### Méthode de repli — 3 terminaux séparés

Utile pour voir les logs de chaque service dans sa propre fenêtre, ou si
`start.sh` pose un souci non prévu.

**Terminal 1 — API FastAPI (port 8000)**

```bash
cd "pe_tracker"
source .venv/bin/activate
python -m uvicorn api.main:app --reload --reload-dir "$PWD/api" --reload-exclude "$PWD/.venv" --port 8000
```

⚠️ Utilise bien `python -m uvicorn` (voir "Erreurs fréquentes" ci-dessous) —
ne lance jamais juste `uvicorn ...` sans avoir vérifié quel `uvicorn` est
utilisé. Utilise bien `--reload-dir`/`--reload-exclude` comme ci-dessus —
sans `--reload-exclude` pointé sur `.venv`, iCloud Drive déclenche une
boucle de rechargement infinie (voir "Erreurs fréquentes").

**Terminal 2 — Backend Express (port 3001)**

```bash
cd "pe_tracker/backend"
npm run dev
```

**Terminal 3 — Frontend Vite (port 3000)**

```bash
cd "pe_tracker/pe-market-intelligence-terminal"
npm run dev
```

---

## 4. Variables d'environnement

> ⚠️ **Avant toute publication éventuelle de ce dépôt** (même sur un remote
> privé partagé, et a fortiori public) : les clés `FRED_API_KEY` et
> `NEWS_API_KEY` ont été codées en dur dans `api/config.py` à un moment de
> l'historique Git (commit `a21bf3b`, confirmé par `git log -S`). Elles ont
> depuis été retirées du code source, mais restent lisibles dans l'historique
> tant qu'il n'est pas réécrit. **Tourne ces deux clés côté FRED/NewsAPI
> avant toute publication.** Le dépôt reste privé pour l'instant — aucune
> réécriture d'historique n'a été effectuée (opération destructive, hors
> périmètre sans validation explicite).

### `api/.env` (backend FastAPI, préfixe `PE_`)

> **Convention de nommage** : `api/config.py` utilise pydantic-settings avec
> `env_prefix="PE_"`. Chaque variable d'environnement `PE_XXX_YYY` doit avoir
> un champ correspondant `xxx_yyy` (snake_case, préfixe retiré) déclaré dans
> la classe `Settings`. **Si le champ n'existe pas dans `Settings`, la
> variable est silencieusement ignorée** (`extra="ignore"`) — aucune erreur,
> aucun avertissement, la clé semble "configurée" dans `.env` mais n'est
> jamais lue par le code. Toute nouvelle clé doit donc être ajoutée aux DEUX
> endroits : `.env` (la valeur) ET `api/config.py` (le champ `Settings`) —
> sinon elle est un no-op silencieux.

| Variable | Obligatoire | Rôle | Où l'obtenir |
|---|---|---|---|
| `PE_OPENAI_API_KEY` | **Oui** | Mémo IC, extraction de documents, scoring OSINT du sourcing | https://platform.openai.com/api-keys |
| `PE_SERPER_API_KEY` | Non (dégradé si absent) | Recherche Google pour le Radar concurrentiel et un fallback d'estimation financière | https://serper.dev |
| `PE_BUILTWITH_API_KEY` | Non (toujours "mock" si absent) | Stack technique (Digital DD) d'une cible sourcée | https://api.builtwith.com |
| `PE_PAPPERS_API_KEY` | Non — **obsolète**, crédits gratuits épuisés, aucun budget alloué. Le code appelant Pappers n'a pas été supprimé (ne pas casser les moteurs qui le référencent) mais ne doit plus être compté comme une source active. | Historique légal/corporate (France) d'une cible | https://www.pappers.fr/api |
| `PE_ADZUNA_APP_ID` + `PE_ADZUNA_APP_KEY` | Non (toujours "mock" si absent — les deux sont requises ensemble) | Signaux RH/recrutement d'une cible | https://developer.adzuna.com |
| `PE_FMP_API_KEY` | Non (repli yfinance si absent) | Profil `Company` du Comps Engine (prix, market cap, secteur). Ne fournit pas les états financiers sur le plan gratuit constaté. | https://site.financialmodelingprep.com |
| `PE_FINNHUB_API_KEY` | Non (repli) | `enterprise_value` + EBITDA du Comps Engine — plan gratuit strictement limité aux tickers cotés US (403 sur tout le reste) | https://finnhub.io |
| `PE_ALPHAVANTAGE_API_KEY` | Non (repli) | Chiffre d'affaires (`revenue`) du Comps Engine — même limitation US-only, et quota de 25 requêtes/jour | https://www.alphavantage.co/support/#api-key |
| `PE_DATABASE_URL` | Non (défaut = SQLite local `pe_intelligence.db`) | Bascule vers PostgreSQL en prod | — |

### `backend/.env` (backend Express, sans préfixe)

| Variable | Obligatoire | Rôle | Où l'obtenir |
|---|---|---|---|
| `FRED_API_KEY` | Non (fallback statique si absent) | Taux banques centrales, courbe des taux, spreads de crédit, Euribor | https://fred.stlouisfed.org/docs/api/api_key.html |
| `NEWS_API_KEY` | Non (retourne une liste vide + message si absent) | Fil d'actualités PE réel (page News & Signals) | https://newsapi.org/register |
| `API_NINJAS_KEY` | Non, legacy | Taux banques centrales, ancien fournisseur — non utilisé activement | https://api-ninjas.com/api/interestrate |

### `pe-market-intelligence-terminal/.env.local` (frontend)

| Variable | Obligatoire | Rôle |
|---|---|---|
| `VITE_API_URL` | Non (défaut `http://localhost:3001/api`) | Change l'URL du backend Express si tu changes son port |
| `VITE_FASTAPI_URL` | Non (défaut `http://localhost:8000`) | Change l'URL de l'API FastAPI si tu changes son port |
| `GEMINI_API_KEY` | Constaté présent mais inutilisé | Aucun code du frontend ne le lit — vestige à ignorer ou supprimer |

Aucune valeur secrète réelle n'a été écrite dans ce document ni dans les
fichiers `.env.example`.

---

## 5. Vérifier que ça marche

1. Avec `./start.sh` : le terminal unique doit afficher `[fastapi] Uvicorn
   running on http://127.0.0.1:8000`, `[express] 🚀 PE Tracker Backend
   (Market/Macro/News) running at http://localhost:3001` et `[vite   ] ➜
   Local:   http://localhost:3000/`. Avec la méthode 3 terminaux, chacun
   affiche sa propre ligne équivalente.
2. Ouvrir http://localhost:8000/health → doit renvoyer
   `{"status":"ok","version":"1.0.0"}`.
3. Ouvrir http://localhost:8000/docs → documentation interactive Swagger de
   toute l'API FastAPI (utile pour tester un endpoint à la main).
4. Ouvrir http://localhost:3001/api/test → doit renvoyer
   `{"message":"Success: Backend is connected!"}`.
5. Ouvrir http://localhost:3000/ dans le navigateur → l'application doit
   s'afficher avec des données dans les tuiles (deals réels FastAPI, cours de
   marché).

---

## 6. Erreurs fréquentes

**`ModuleNotFoundError: No module named 'cachetools'` au démarrage de
l'API, alors que `pip install` a bien été fait**
Cause : il existe plusieurs `uvicorn` installés sur cette machine (un dans
`.venv/`, un autre lié à une installation Python 3.12 globale). Si tu lances
juste `uvicorn api.main:app`, le shell peut résoudre vers le **mauvais**
`uvicorn` (celui qui n'a pas accès aux paquets de `.venv`), même après
`source .venv/bin/activate`.
Solution : lance toujours `python -m uvicorn api.main:app --reload --port 8000`
avec le `python` du venv actif (jamais `uvicorn` tout court). Pour vérifier
lequel est utilisé : `which -a uvicorn` doit lister celui de `.venv/bin/`
en premier.

**Le frontend affiche des tuiles vides ou des erreurs réseau sur certaines
pages (bandeau macro de Market Intelligence, News & Signals, Credit & Macro,
Money Market)**
Cause la plus probable : le backend Express n'est pas lancé (Terminal 2, ou
absent des logs de `start.sh`). Ces pages/sections dépendent d'Express pour
les données marché/macro/news ; tout le reste (deals, sourcing, portefeuille,
LBO) dépend uniquement de FastAPI.

**Le port 8000 ou 3001 ou 3000 est déjà utilisé**
Un ancien processus tourne encore. Trouver le PID avec
`lsof -i :8000` (remplacer le port) puis `kill <PID>`.

**Un `pip install -r api/requirements.txt` propre pourrait installer des
versions différentes de `numpy` et `openai` que celles réellement testées**
Constaté : l'environnement `.venv` actuel tourne avec `numpy==1.26.4` et
`openai==2.21.0`, alors que `api/requirements.txt` déclare `numpy==2.2.1`
et `openai==1.59.6`. Tout fonctionne dans la configuration actuelle
(testée), mais une réinstallation stricte depuis `requirements.txt` sur une
machine neuve utiliserait des versions non testées ensemble.

**uvicorn recharge en boucle infinie, logs remplis de
`WatchFiles detected changes in '.venv/lib/.../xxx.py'. Reloading...`**
Cause confirmée (Tâche Finalisation, Partie B) : ce projet vit dans un
dossier synchronisé par **iCloud Drive**, qui re-matérialise en continu des
fichiers sous `.venv/` (paquets pip) — chaque re-matérialisation déclenche
`--reload`. Deux pièges pour qui voudrait corriger ça vite :
1. `uvicorn --reload-dir api` seul ne suffit PAS : le reloader `WatchFiles`
   d'uvicorn (`uvicorn/supervisors/watchfilesreload.py`) réintroduit
   silencieusement le `cwd` dans les dossiers surveillés dès que celui-ci
   n'est pas déjà littéralement dans `reload_dirs` — donc `.venv` reste
   surveillé même avec `--reload-dir` pointé ailleurs.
2. Le correctif fiable est `--reload-exclude` pointé sur le **chemin absolu**
   de `.venv` (pas un motif glob type `.venv/*`, qui ne matche pas les
   fichiers profondément imbriqués) — `FileFilter` d'uvicorn détecte alors
   que c'est un vrai dossier et exclut tous ses descendants via
   `path.parents`, quelle que soit la profondeur.
`start.sh` lance désormais FastAPI avec
`--reload --reload-dir "$ROOT_DIR/api" --reload-exclude "$ROOT_DIR/.venv"`.
Vérifié : toucher un fichier sous `.venv/` ne déclenche plus de rechargement ;
toucher un fichier sous `api/` recharge toujours normalement. Si ce projet
est un jour déplacé hors d'iCloud Drive (ou avec le dossier `.venv` exclu de
la synchronisation via les réglages iCloud), ce risque disparaît à la
source — la parade ci-dessus reste nécessaire tant que ce n'est pas fait.

**`.venv/bin/pip` échoue avec `bad interpreter: .../pe_tracker/.venv/bin/python3.13: no such file or directory`**
Constaté pendant cette tâche. Le shebang de `.venv/bin/pip` contient un
chemin absolu figé au moment de la création du venv — si le dossier du
projet a été renommé/déplacé depuis (ex. l'ancien chemin ne contenait pas
« Documents - MacBook Air de Titouan (2) »), ce script cassé, même si
`.venv/bin/python` fonctionne toujours. Contournement : utiliser
`.venv/bin/python -m pip ...` au lieu de `.venv/bin/pip ...` (n'utilise pas
le shebang, résout l'interpréteur correctement). Non corrigé dans cette
tâche (recréer le venv est plus risqué que de contourner) — à recréer
(`python3 -m venv .venv --clear` puis réinstaller) si ce script doit être
utilisé directement un jour.
