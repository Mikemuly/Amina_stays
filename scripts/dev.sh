#!/usr/bin/env bash
# One command for local development: PostgreSQL + Django API + scheduler + Next.js.
#
#   scripts/dev.sh            # start everything (first run installs deps, migrates and seeds the demo)
#   scripts/dev.sh --reseed   # also reset the demo data
#
# Uses Docker for PostgreSQL if scripts/db.sh can't find local binaries and Docker is available.
# Stop with Ctrl-C (PostgreSQL keeps running: scripts/db.sh stop).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
# Demo mode by default for a fresh clone. A DEBUG or DEMO set in the shell, .env or backend/.env wins: Django only
# reads .env for variables that aren't already in the environment, so exporting a default here would hide it.
in_env_file() { grep -qsE "^[[:space:]]*(export[[:space:]]+)?$1=" .env backend/.env; }
in_env_file DEBUG || export DEBUG="${DEBUG:-1}"
in_env_file DEMO || export DEMO="${DEMO:-1}"

say() { printf '\033[1;35m▸ %s\033[0m\n' "$*"; }

# 1. Database
if [ -n "${DATABASE_URL:-}" ]; then
  say "Using DATABASE_URL"
elif bash scripts/db.sh start 2>/dev/null || bash scripts/db.sh init; then
  say "Local PostgreSQL is up"
elif command -v docker >/dev/null 2>&1; then
  say "Starting PostgreSQL in Docker"
  docker compose up -d db
  until docker compose exec -T db pg_isready -U amina >/dev/null 2>&1; do sleep 1; done
else
  echo "No PostgreSQL available: run scripts/db.sh install && scripts/db.sh init, or install Docker." >&2
  exit 1
fi

# 2. Backend
say "Backend dependencies"
(cd backend && "$UV" sync -q)
say "Migrations"
(cd backend && "$UV" run python manage.py migrate --noinput -v 0)
if [ "${1:-}" = "--reseed" ] || ! (cd backend && "$UV" run python manage.py shell -c "from apps.properties.models import Unit; import sys; sys.exit(0 if Unit.objects.exists() else 1)" >/dev/null 2>&1); then
  say "Seeding demo data"
  (cd backend && "$UV" run python manage.py seed_demo --reset)
fi

# 3. Frontend
if [ ! -d frontend/node_modules ]; then
  say "Frontend dependencies"
  (cd frontend && npm install --no-audit --no-fund)
fi

# 4. Run
pids=()
cleanup() { trap - INT TERM EXIT; for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup INT TERM EXIT

(cd backend && exec "$UV" run python manage.py runserver 127.0.0.1:8000) & pids+=($!)
(cd backend && exec "$UV" run python manage.py run_scheduler) & pids+=($!)
(cd frontend && exec node_modules/.bin/next dev --port 3000) & pids+=($!)

say "Guest site  http://localhost:3000"
say "Demo Lab    http://localhost:3000/demo"
say "Host        http://localhost:3000/host   (log in as AMINA_PHONE: with DEMO=1 the code shows on screen, otherwise it comes by SMS - in the Africa's Talking simulator with sandbox keys)"
say "API docs    http://localhost:8000/api/docs"
wait -n
