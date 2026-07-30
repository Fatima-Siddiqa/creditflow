#!/usr/bin/env bash
# One-time setup: creates a venv per service, installs deps, runs migrations.
# Run from the repo root:  bash scripts/setup_venvs.sh
#
# Assumes Postgres/Redis/RabbitMQ/MongoDB are already running natively and
# reachable on the ports each service's app/config.py already defaults to
# (see LOCAL_DEV.md step 2) and that scripts/init_schemas.sql has been run.

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

# Find a Python 3.12 interpreter. On Windows/Git Bash it's usually just
# `python` (via the official installer) or available through the `py`
# launcher; on macOS/Linux it's usually `python3.12` or `python3`.
PY=${PYTHON_BIN:-}
if [ -z "$PY" ]; then
  for candidate in python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY=$candidate; break; fi
  done
  if [ -z "$PY" ] && command -v py >/dev/null 2>&1; then PY="py -3.12"; fi
fi
[ -n "$PY" ] || { echo "No Python interpreter found on PATH."; exit 1; }

# venv layout differs: POSIX -> .venv/bin, Windows -> .venv/Scripts
venv_bin() { [ -d "$1/Scripts" ] && echo "$1/Scripts" || echo "$1/bin"; }

SERVICES=(
  api-gateway
  auth-service
  user-service
  billing-service
  credits-service
  usage-service
  ai-generation-service
  content-service
  scheduler-service
  social-publishing-service
  scraper-service
  notification-service
  admin-service
)

for svc in "${SERVICES[@]}"; do
  dir="services/$svc"
  echo "=== $svc ==="
  $PY -m venv "$dir/.venv"
  bin="$(venv_bin "$dir/.venv")"
  "$bin/python" -m pip install --upgrade pip -q
  "$bin/pip" install -r "$dir/requirements.txt" -q

  # Every service except api-gateway and scraper-service has Alembic
  # migrations against its own Postgres schema.
  if [ -f "$dir/alembic.ini" ]; then
    (cd "$dir" && "./$(venv_bin .venv)/alembic" upgrade head)
  fi
done

echo
echo "All venvs created and migrations applied. Next: bash scripts/start_all.sh"
