#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root

if [ ! -d run ] || [ -z "$(ls -A run 2>/dev/null)" ]; then
  echo "Nothing to stop (no run/*.pid files)."
  exit 0
fi

for pidfile in run/*.pid; do
  name=$(basename "$pidfile" .pid)
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" && echo "stopped $name (pid $pid)"
  else
    echo "$name (pid $pid) already stopped"
  fi
  rm -f "$pidfile"
done
