#!/usr/bin/env bash
# Démarre les 3 services de PE Tracker (FastAPI :8000, Express :3001, Vite :3000)
# d'une seule commande, avec logs préfixés par service et arrêt propre au Ctrl+C.
#
# Usage: ./start.sh

set -uo pipefail
set -m  # monitor mode : chaque job `&` reçoit son propre groupe de processus,
        # nécessaire pour pouvoir tout tuer proprement (y compris les petits-
        # enfants npm → tsx / vite) avec un seul kill -- -<pid> par job.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# --- Vérifications préalables (voir RUNBOOK.md pour l'installation initiale) ---
if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "❌ .venv introuvable. Installation initiale requise :"
  echo "   python3 -m venv .venv && source .venv/bin/activate && pip install -r api/requirements.txt"
  exit 1
fi

if [ ! -d "$ROOT_DIR/backend/node_modules" ]; then
  echo "❌ backend/node_modules introuvable. Lance d'abord: cd backend && npm install"
  exit 1
fi

if [ ! -d "$ROOT_DIR/pe-market-intelligence-terminal/node_modules" ]; then
  echo "❌ pe-market-intelligence-terminal/node_modules introuvable. Lance d'abord: cd pe-market-intelligence-terminal && npm install"
  exit 1
fi

if [ ! -f "$ROOT_DIR/api/.env" ]; then
  echo "⚠️  api/.env introuvable — copie api/.env.example vers api/.env et renseigne tes clés (voir RUNBOOK.md)."
fi

JOB_PIDS=()

cleanup() {
  echo ""
  echo "Arrêt des 3 services..."
  for pid in "${JOB_PIDS[@]}"; do
    kill -- "-$pid" 2>/dev/null
  done
  sleep 1
  for pid in "${JOB_PIDS[@]}"; do
    kill -9 -- "-$pid" 2>/dev/null
  done
  exit 0
}
trap cleanup INT TERM

echo "🚀 Démarrage : FastAPI (:8000) · Express (:3001) · Vite (:3000)"
echo "   Ctrl+C pour tout arrêter proprement."
echo ""

( "$ROOT_DIR/.venv/bin/python" -m uvicorn api.main:app --reload --reload-dir "$ROOT_DIR/api" --reload-exclude "$ROOT_DIR/.venv" --port 8000 2>&1 | sed -u 's/^/[fastapi] /' ) &
JOB_PIDS+=("$!")
( cd "$ROOT_DIR/backend" && npm run dev 2>&1 | sed -u 's/^/[express] /' ) &
JOB_PIDS+=("$!")
( cd "$ROOT_DIR/pe-market-intelligence-terminal" && npm run dev 2>&1 | sed -u 's/^/[vite   ] /' ) &
JOB_PIDS+=("$!")

wait
