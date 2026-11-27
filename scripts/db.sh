#!/usr/bin/env bash
# Local PostgreSQL for development — no root, no Docker.
# Uses PostgreSQL from PATH, or a micromamba env (conda-forge) called "amina-pg".
#
#   scripts/db.sh install   # one-off: micromamba create -n amina-pg postgresql=18
#   scripts/db.sh init      # create the cluster in .data/postgres + role/db "amina"
#   scripts/db.sh start | stop | status | psql | reset
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGDATA="${PGDATA:-$ROOT/.data/postgres}"
PGPORT="${PGPORT:-5432}"
PG_ENV="${PG_ENV:-amina-pg}"
DB_NAME="${DB_NAME:-amina}"
DB_USER="${DB_USER:-amina}"
DB_PASSWORD="${DB_PASSWORD:-amina}"

find_pgbin() {
  if command -v pg_ctl >/dev/null 2>&1; then dirname "$(command -v pg_ctl)"; return; fi
  for d in "${MAMBA_ROOT_PREFIX:-$HOME/.local/share/mamba}/envs/$PG_ENV/bin" "$HOME/micromamba/envs/$PG_ENV/bin" "$HOME/.conda/envs/$PG_ENV/bin"; do
    [ -x "$d/pg_ctl" ] && { echo "$d"; return; }
  done
  echo ""
}

PGBIN="${PGBIN:-$(find_pgbin)}"
need_bin() {
  if [ -z "$PGBIN" ]; then
    echo "PostgreSQL binaries not found. Run: scripts/db.sh install  (needs micromamba), or install PostgreSQL 16+." >&2
    exit 1
  fi
}

start() {
  need_bin
  if "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then echo "PostgreSQL already running on port $PGPORT"; return; fi
  "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/server.log" -o "-p $PGPORT -k /tmp -c listen_addresses=localhost" -w start >/dev/null
  echo "PostgreSQL running on localhost:$PGPORT (data: $PGDATA)"
}

case "${1:-start}" in
  install)
    command -v micromamba >/dev/null || { echo "micromamba not found — install PostgreSQL another way" >&2; exit 1; }
    micromamba create -y -n "$PG_ENV" -c conda-forge "postgresql=18"
    ;;
  init)
    need_bin
    if [ -f "$PGDATA/PG_VERSION" ]; then echo "Cluster already exists at $PGDATA"; else
      mkdir -p "$PGDATA"
      "$PGBIN/initdb" -D "$PGDATA" -U postgres --auth-local=trust --auth-host=scram-sha-256 -E UTF8 --locale=C.UTF-8 >/dev/null
      echo "Initialised cluster at $PGDATA"
    fi
    start
    "$PGBIN/psql" -h /tmp -p "$PGPORT" -U postgres -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
    CREATE ROLE $DB_USER LOGIN CREATEDB PASSWORD '$DB_PASSWORD';
  END IF;
END \$\$;
SQL
    if ! "$PGBIN/psql" -h /tmp -p "$PGPORT" -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
      "$PGBIN/createdb" -h /tmp -p "$PGPORT" -U postgres -O "$DB_USER" "$DB_NAME"
    fi
    echo "Database ready: postgres://$DB_USER:$DB_PASSWORD@localhost:$PGPORT/$DB_NAME"
    ;;
  start) start ;;
  stop) need_bin; "$PGBIN/pg_ctl" -D "$PGDATA" -m fast stop ;;
  status) need_bin; "$PGBIN/pg_ctl" -D "$PGDATA" status ;;
  psql) need_bin; shift; PGPASSWORD="$DB_PASSWORD" "$PGBIN/psql" -h localhost -p "$PGPORT" -U "$DB_USER" "$DB_NAME" "$@" ;;
  reset)
    need_bin
    "$PGBIN/psql" -h /tmp -p "$PGPORT" -U postgres -q -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE)" -c "CREATE DATABASE $DB_NAME OWNER $DB_USER"
    echo "Database $DB_NAME recreated (run: cd backend && uv run python manage.py migrate && uv run python manage.py seed_demo)"
    ;;
  *) echo "usage: $0 {install|init|start|stop|status|psql|reset}" >&2; exit 2 ;;
esac
