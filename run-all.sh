#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/services"

declare -A PORTS=(
  [api-gateway]=8000 [auth-service]=8001 [user-service]=8002 [billing-service]=8003
  [credits-service]=8004 [usage-service]=8005 [ai-generation-service]=8006
  [content-service]=8007 [scheduler-service]=8008 [social-publishing-service]=8009
  [scraper-service]=8010 [notification-service]=8011 [admin-service]=8012
)

mkdir -p ../logs
PIDS=()

for svc in "${!PORTS[@]}"; do
  port=${PORTS[$svc]}
  (
    cd "$svc"
    [ -d venv ] || python -m venv venv
    source venv/Scripts/activate
    pip install -q -r requirements.txt
    alembic upgrade head
    uvicorn app.main:app --host 0.0.0.0 --port "$port"
  ) > "../logs/$svc.log" 2>&1 &
  PIDS+=($!)
  echo "started $svc on :$port (pid $!)"
done

# scheduler-service needs a SECOND process for Celery worker+beat --
# just uvicorn isn't enough for it. Run only this combined command --
# don't also run docker-compose.yml's separate scheduler-celery-beat
# container's `celery beat` on its own, or you'll get two beat
# schedulers racing against the same broker.
(
  cd scheduler-service
  source venv/Scripts/activate
  celery -A app.celery_app worker --beat --loglevel=info -c 1
) > ../logs/scheduler-celery.log 2>&1 &
PIDS+=($!)
echo "started scheduler celery worker+beat (pid $!)"

trap 'echo "stopping everything..."; kill "${PIDS[@]}" 2>/dev/null' EXIT
echo "all services launching -- tail -f logs/*.log to watch. Ctrl+C stops everything."
wait