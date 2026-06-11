#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PID_DIR="$ROOT_DIR/.dev-pids"

SCHEDULER_ENABLED="${SCHEDULER_ENABLED:-true}"
SKIP_MIGRATE="${SKIP_MIGRATE:-false}"

# ── Helpers ───────────────────────────────────────────────────────────────

ensure_pid_dir() { mkdir -p "$PID_DIR"; }
backend_pidfile()  { echo "$PID_DIR/backend.pid"; }
frontend_pidfile() { echo "$PID_DIR/frontend.pid"; }

is_alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }
read_pid() { [[ -f "$1" ]] && cat "$1" || true; }

stop_service() {
  local name="$1" pidfile="$2" port="${3:-}" pid
  pid=$(read_pid "$pidfile")
  if is_alive "$pid"; then
    echo "[Stop] $name (PID $pid)"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do is_alive "$pid" || break; sleep 0.5; done
    is_alive "$pid" && { echo "[Stop] $name: force kill"; kill -9 "$pid" 2>/dev/null || true; }
  else
    echo "[Stop] $name: not running"
  fi
  rm -f "$pidfile"
  # Fallback: kill any leftover process on the port
  if [[ -n "$port" ]]; then
    local leftover
    leftover=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$leftover" ]]; then
      echo "[Stop] $name: cleaning leftover on port $port"
      echo "$leftover" | xargs kill -9 2>/dev/null || true
    fi
  fi
}

stop_all() {
  echo "Stopping all services..."
  stop_service "Backend" "$(backend_pidfile)" 3001
  stop_service "Frontend" "$(frontend_pidfile)" 3000
  echo "Done."
}

status_all() {
  local bpid fpid running=0
  bpid=$(read_pid "$(backend_pidfile)")
  fpid=$(read_pid "$(frontend_pidfile)")
  is_alive "$bpid" && { echo "[Backend]  running (PID $bpid) → http://localhost:3001"; running=$((running+1)); } || echo "[Backend]  stopped"
  is_alive "$fpid" && { echo "[Frontend] running (PID $fpid) → http://localhost:3000"; running=$((running+1)); } || echo "[Frontend] stopped"
  [[ $running -eq 0 ]] && echo "No services running." || true
}

run_migrate() {
  if [[ "$SKIP_MIGRATE" != "true" ]]; then
    echo "[Migrate] Ensuring DB schema..."
    ( cd "$BACKEND_DIR" && source .venv/bin/activate && python -c "
from app.models import *  # noqa: F401,F403
from app.db.base import Base
from app.db.engine import engine
from app.config import settings
from pathlib import Path
from alembic import command
from alembic.config import Config
Base.metadata.create_all(bind=engine)
project_root = Path('.').resolve()
cfg = Config(str(project_root / 'alembic.ini'))
cfg.set_main_option('script_location', str(project_root / 'alembic'))
cfg.set_main_option('sqlalchemy.url', settings.DATABASE_URL)
command.stamp(cfg, 'head')
print('Schema ready.')
" )
    echo ""
  fi
}

start_all() {
  ensure_pid_dir
  local bpid fpid
  bpid=$(read_pid "$(backend_pidfile)")
  fpid=$(read_pid "$(frontend_pidfile)")
  if is_alive "$bpid" || is_alive "$fpid"; then
    echo "Stopping existing services..."
    stop_all
    sleep 1
  fi

  echo "Starting Gojira development environment..."
  echo ""
  run_migrate

  local LOG_DIR="$ROOT_DIR/.dev-logs"
  mkdir -p "$LOG_DIR"

  cleanup() { echo ""; stop_all; }
  trap cleanup EXIT INT TERM

  echo "[Backend] Starting on :3001 (SCHEDULER_ENABLED=$SCHEDULER_ENABLED)"
  ( cd "$BACKEND_DIR" && source .venv/bin/activate && export SCHEDULER_ENABLED && exec uvicorn app.main:app --reload --host 0.0.0.0 --port 3001 ) > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$(backend_pidfile)"

  echo "[Frontend] Starting on :3000"
  ( cd "$FRONTEND_DIR" && exec npm run dev ) > "$LOG_DIR/frontend.log" 2>&1 &
  echo $! > "$(frontend_pidfile)"

  sleep 3
  echo ""
  status_all
  echo ""
  cat <<EOF
  Cockpit           →  http://localhost:3001/api/cockpit
  Plans             →  http://localhost:3001/api/plans
  Themes            →  http://localhost:3001/api/themes
  Scheduler status  →  http://localhost:3001/api/scheduler/jobs

  Logs:
    tail -f $LOG_DIR/backend.log
    tail -f $LOG_DIR/frontend.log

  Manual triggers:
    curl -X POST http://localhost:3001/api/scheduler/jobs/daily_snapshot/run
    curl -X POST http://localhost:3001/api/scheduler/jobs/daily_plan_evaluation/run

Press Ctrl+C to stop all services.
EOF

  # Monitor loop with exit diagnostics
  while true; do
    bpid=$(read_pid "$(backend_pidfile)")
    fpid=$(read_pid "$(frontend_pidfile)")
    if ! is_alive "$bpid"; then
      echo ""
      echo "[EXIT] Backend (PID $bpid) died. Last 30 lines:"
      echo "-------------------------------------------"
      tail -30 "$LOG_DIR/backend.log"
      echo "-------------------------------------------"
      break
    fi
    if ! is_alive "$fpid"; then
      echo ""
      echo "[EXIT] Frontend (PID $fpid) died. Last 30 lines:"
      echo "-------------------------------------------"
      tail -30 "$LOG_DIR/frontend.log"
      echo "-------------------------------------------"
      break
    fi
    sleep 2
  done
  stop_all
}

start_foreground() {
  ensure_pid_dir
  cleanup() { echo ""; stop_all; }
  trap cleanup EXIT INT TERM

  echo "Starting Gojira development environment..."
  echo ""
  run_migrate

  echo "[Backend] Starting on :3001 (SCHEDULER_ENABLED=$SCHEDULER_ENABLED)"
  ( cd "$BACKEND_DIR" && source .venv/bin/activate && export SCHEDULER_ENABLED && exec uvicorn app.main:app --reload --host 0.0.0.0 --port 3001 ) &

  echo "[Frontend] Starting on :3000"
  ( cd "$FRONTEND_DIR" && exec npm run dev ) &

  cat <<EOF

  Frontend          →  http://localhost:3000
  Backend           →  http://localhost:3001
  ────────────────────
  Cockpit           →  http://localhost:3001/api/cockpit
  Plans             →  http://localhost:3001/api/plans
  Themes            →  http://localhost:3001/api/themes
  Scheduler status  →  http://localhost:3001/api/scheduler/jobs

  Manual triggers:
    curl -X POST http://localhost:3001/api/scheduler/jobs/daily_snapshot/run
    curl -X POST http://localhost:3001/api/scheduler/jobs/daily_plan_evaluation/run

Press Ctrl+C to stop all services.
EOF
  wait
}

usage() {
  cat <<EOF
Usage: ./dev.sh <command> [options]

Commands:
  start     Start all services in background
  stop      Stop all services
  restart   Stop then start all services
  status    Show running services
  fg        Start all services in foreground (Ctrl+C to stop, original behavior)

Options (for start/restart/fg):
  --no-scheduler   Run backend with SCHEDULER_ENABLED=false
  --skip-migrate   Don't run alembic upgrade head before starting

Env overrides:
  SCHEDULER_ENABLED=true|false  (default: true)
  SKIP_MIGRATE=true|false       (default: false)
EOF
}

# ── Main ─────────────────────────────────────────────────────────────────

COMMAND="${1:-fg}"
shift || true

for arg in "$@"; do
  case "$arg" in
    --no-scheduler) SCHEDULER_ENABLED=false ;;
    --skip-migrate) SKIP_MIGRATE=true ;;
  esac
done

case "$COMMAND" in
  start)    start_all ;;
  stop)     stop_all ;;
  restart)  stop_all; sleep 1; start_all ;;
  status)   ensure_pid_dir; status_all ;;
  fg)       start_foreground ;;
  -h|--help) usage ;;
  *)        echo "Unknown command: $COMMAND"; usage; exit 1 ;;
esac
