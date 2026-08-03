#!/usr/bin/env bash
# Starts all 13 services + the scheduler's Celery worker/beat.
# Run from the repo root, after scripts/setup_venvs.sh:  bash scripts/start_all.sh
# Stop everything with:                                   bash scripts/stop_all.sh

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root
mkdir -p logs run services/content-service/uploads

# venv layout differs: POSIX -> .venv/bin, Windows -> .venv/Scripts
venv_bin() { [ -d "$1/Scripts" ] && echo "$1/Scripts" || echo "$1/bin"; }

declare -A PORTS=(
  [api-gateway]=8000
  [auth-service]=8001
  [user-service]=8002
  [billing-service]=8003
  [credits-service]=8004
  [usage-service]=8005
  [ai-generation-service]=8006
  [content-service]=8007
  [scheduler-service]=8008
  [social-publishing-service]=8009
  [scraper-service]=8010
  [notification-service]=8011
  [admin-service]=8012
)

start_service() {
  local svc=$1 port=$2
  echo "starting $svc on :$port"
  (
    cd "services/$svc"
    export UPLOAD_DIR="$(pwd)/uploads"   # only content-service reads this; harmless elsewhere
    bin="$(venv_bin .venv)"
    nohup "$bin/uvicorn" app.main:app --reload --port "$port" \
      > "../../logs/$svc.log" 2>&1 &
    echo $! > "../../run/$svc.pid"
  )
}

for svc in "${!PORTS[@]}"; do
  start_service "$svc" "${PORTS[$svc]}"
done

echo "starting scheduler-service celery worker+beat"
CELERY_POOL_ARGS=(-c 1)
case "$(uname -s)" in MINGW*|MSYS*) CELERY_POOL_ARGS=(--pool=solo) ;; esac  # Windows has no fork()
(
  cd services/scheduler-service
  bin="$(venv_bin .venv)"
  nohup "$bin/celery" -A app.celery_app worker --loglevel=info "${CELERY_POOL_ARGS[@]}" \
    > ../../logs/scheduler-celery-worker.log 2>&1 &
  echo $! > ../../run/scheduler-celery-worker.pid
)
(
  cd services/scheduler-service
  bin="$(venv_bin .venv)"
  nohup "$bin/celery" -A app.celery_app beat --loglevel=info \
    > ../../logs/scheduler-celery-beat.log 2>&1 &
  echo $! > ../../run/scheduler-celery-beat.pid
)

sleep 2
echo
echo "Done. Health check all services:"
for svc in "${!PORTS[@]}"; do
  printf "  %-28s http://localhost:%s/healthz\n" "$svc" "${PORTS[$svc]}"
done
echo
echo "Logs:  tail -f logs/<service>.log"
echo "Stop:  bash scripts/stop_all.sh"
