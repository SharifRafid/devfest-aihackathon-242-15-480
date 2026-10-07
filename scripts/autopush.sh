#!/usr/bin/env bash
# Background loop: run scripts/push.sh every N minutes (default 15).
# usage: ./scripts/autopush.sh start [minutes] | stop | status | log
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
pid=".git/autopush.pid"; log=".git/autopush.log"
case "${1:-status}" in
  start)
    if [ -f "$pid" ] && kill -0 "$(cat "$pid")" 2>/dev/null; then echo "[autopush] already running (pid $(cat "$pid"))"; exit 0; fi
    mins="${2:-15}"
    nohup bash -c "while true; do sleep $((mins*60)); ./scripts/push.sh; done" >>"$log" 2>&1 &
    echo $! > "$pid"; echo "[autopush] started, every ${mins} min (pid $!). log: $log"
    ;;
  stop)
    if [ -f "$pid" ]; then kill "$(cat "$pid")" 2>/dev/null && echo "[autopush] stopped" || echo "[autopush] not running"; rm -f "$pid"; else echo "[autopush] not running"; fi
    ;;
  status)
    if [ -f "$pid" ] && kill -0 "$(cat "$pid")" 2>/dev/null; then echo "[autopush] running (pid $(cat "$pid"))"; else echo "[autopush] not running"; fi
    ;;
  log) tail -n 30 "$log" 2>/dev/null || echo "(no log yet)" ;;
  *) echo "usage: $0 start [minutes] | stop | status | log"; exit 1 ;;
esac
