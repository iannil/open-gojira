#!/usr/bin/env bash
# Gojira 开发环境一键管理
# Usage:
#   ./dev.sh             启动所有服务（等同于 start，兼容旧用法）
#   ./dev.sh start       启动所有服务
#   ./dev.sh stop        停止所有服务
#   ./dev.sh restart     重启所有服务
#   ./dev.sh status      查看服务状态
#   ./dev.sh logs        查看日志（tail -f）
#
# 启动的服务:
#   - Backend (uvicorn --reload, 端口 3001)
#   - Frontend (Vite dev server, 端口 3000)
#
# 要求:
#   - .env 文件在项目根目录 (复制 .env.example 并填入 API keys)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT_DIR/.dev"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_LOG="$PID_DIR/backend.log"
FRONTEND_LOG="$PID_DIR/frontend.log"

# ── 辅助函数 ────────────────────────────────────────────────────────────

ensure_pid_dir() {
  mkdir -p "$PID_DIR"
}

cleanup_on_exit() {
  # trap 清理：只在没有子命令执行时使用（兼容旧用法 Ctrl+C）
  if [ -f "$BACKEND_PID_FILE" ]; then
    local pid
    pid=$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$BACKEND_PID_FILE"
  fi
  if [ -f "$FRONTEND_PID_FILE" ]; then
    local pid
    pid=$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi
}

# ── 启动 ────────────────────────────────────────────────────────────────

cmd_start() {
  ensure_pid_dir

  # ── 检查 .env ─────────────────────────────────────────────────────────
  if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "[WARN] .env 不存在！复制 .env.example 并填入 LIXINGER_TOKEN / ZHIPU_API_KEY:"
    echo "  cp .env.example .env"
    echo ""
  fi

  # ── 启动 backend ──────────────────────────────────────────────────────
  echo "[Backend] 启动 uvicorn (端口 3001)..."
  cd "$ROOT_DIR/backend"
  if [ ! -d ".venv" ]; then
    echo "[Backend] 首次运行：创建虚拟环境..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
  else
    source .venv/bin/activate
  fi
  nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 3001 \
    > "$BACKEND_LOG" 2>&1 &
  echo $! > "$BACKEND_PID_FILE"
  echo "[Backend] PID $(cat "$BACKEND_PID_FILE")"

  # ── 启动 frontend ─────────────────────────────────────────────────────
  echo "[Frontend] 启动 Vite dev server (端口 3000)..."
  cd "$ROOT_DIR/frontend"
  nohup npm run dev -- --host 0.0.0.0 --port 3000 \
    > "$FRONTEND_LOG" 2>&1 &
  echo $! > "$FRONTEND_PID_FILE"
  echo "[Frontend] PID $(cat "$FRONTEND_PID_FILE")"

  echo ""
  echo "=== 启动完成 ==="
  echo "  Backend:  http://localhost:3001"
  echo "  Frontend: http://localhost:3000"
  echo "  /api/health → http://localhost:3001/api/health"
  echo ""
  echo "查看日志: ./dev.sh logs"
  echo "停止服务: ./dev.sh stop"
}

# ── 停止 ────────────────────────────────────────────────────────────────

cmd_stop() {
  local any=false

  if [ -f "$BACKEND_PID_FILE" ]; then
    local pid
    pid=$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)
    if [ -n "$pid" ] && kill "$pid" 2>/dev/null; then
      echo "[Backend] 已停止 PID $pid"
      any=true
    else
      echo "[Backend] 未运行 (PID $pid 不存在)"
    fi
    rm -f "$BACKEND_PID_FILE"
  else
    # 尝试按端口查找（兜底）
    local pid
    pid=$(lsof -ti:3001 2>/dev/null || true)
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
      echo "[Backend] 已停止端口 3001 上的进程 PID $pid"
      any=true
    fi
  fi

  if [ -f "$FRONTEND_PID_FILE" ]; then
    local pid
    pid=$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)
    if [ -n "$pid" ] && kill "$pid" 2>/dev/null; then
      echo "[Frontend] 已停止 PID $pid"
      any=true
    else
      echo "[Frontend] 未运行 (PID $pid 不存在)"
    fi
    rm -f "$FRONTEND_PID_FILE"
  else
    local pid
    pid=$(lsof -ti:3000 2>/dev/null || true)
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
      echo "[Frontend] 已停止端口 3000 上的进程 PID $pid"
      any=true
    fi
  fi

  if [ "$any" = false ]; then
    echo "没有运行中的服务。"
  fi
}

# ── 状态 ────────────────────────────────────────────────────────────────

# _pids_on_port 返回端口上所有 PID（空格分隔）
_pids_on_port() {
  lsof -ti:"$1" 2>/dev/null | tr '\n' ' ' | sed 's/ $//' || true
}

# _pid_display 取第一个 PID 用于显示，附加计数
_pid_display() {
  local pids="$1"
  local first
  first="${pids%% *}"
  if [ -z "$first" ]; then
    echo ""
  elif [ "$pids" = "$first" ]; then
    echo "$first"
  else
    echo "${first} (+$(echo "$pids" | wc -w | tr -d ' ')个子进程)"
  fi
}

cmd_status() {
  local backend_pid=""
  local frontend_pid=""
  local backend_running=false
  local frontend_running=false

  if [ -f "$BACKEND_PID_FILE" ]; then
    backend_pid=$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)
    if [ -n "$backend_pid" ] && kill -0 "$backend_pid" 2>/dev/null; then
      backend_running=true
    fi
  fi
  # 兜底：按端口查找
  if [ "$backend_running" = false ]; then
    local all_pids
    all_pids=$(_pids_on_port 3001)
    if [ -n "$all_pids" ]; then
      backend_running=true
      backend_pid="$all_pids"
    fi
  fi

  if [ -f "$FRONTEND_PID_FILE" ]; then
    frontend_pid=$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)
    if [ -n "$frontend_pid" ] && kill -0 "$frontend_pid" 2>/dev/null; then
      frontend_running=true
    fi
  fi
  if [ "$frontend_running" = false ]; then
    local all_pids
    all_pids=$(_pids_on_port 3000)
    if [ -n "$all_pids" ]; then
      frontend_running=true
      frontend_pid="$all_pids"
    fi
  fi

  echo "=== 服务状态 ==="
  if [ "$backend_running" = true ]; then
    echo "  Backend  [运行中]  PID $(_pid_display "$backend_pid")  http://localhost:3001"
  else
    echo "  Backend  [已停止]"
  fi
  if [ "$frontend_running" = true ]; then
    echo "  Frontend [运行中]  PID $(_pid_display "$frontend_pid")  http://localhost:3000"
  else
    echo "  Frontend [已停止]"
  fi
}

# ── 日志 ────────────────────────────────────────────────────────────────

cmd_logs() {
  if [ ! -d "$PID_DIR" ]; then
    echo "没有日志文件（服务尚未启动过）。"
    exit 1
  fi

  local files=()
  [ -f "$BACKEND_LOG" ] && files+=("$BACKEND_LOG")
  [ -f "$FRONTEND_LOG" ] && files+=("$FRONTEND_LOG")

  if [ ${#files[@]} -eq 0 ]; then
    echo "没有日志文件。"
    exit 1
  fi

  tail -f "${files[@]}"
}

# ── 主命令路由 ──────────────────────────────────────────────────────────

usage() {
  echo "用法: $0 {start|stop|restart|status|logs}"
  echo ""
  echo "  start    启动所有服务"
  echo "  stop     停止所有服务"
  echo "  restart  重启所有服务"
  echo "  status   查看服务状态"
  echo "  logs     查看日志 (tail -f)"
  exit 0
}

case "${1:-}" in
  start|"")
    # trap 保证前台 Ctrl+C 时也清理
    trap cleanup_on_exit EXIT INT TERM
    cmd_start
    # 保持前台运行，Ctrl+C 触发清理
    wait
    ;;
  stop)
    cmd_stop
    ;;
  restart)
    cmd_stop
    echo "---"
    cmd_start
    # 保持前台运行
    wait
    ;;
  status)
    cmd_status
    ;;
  logs)
    cmd_logs
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "错误: 未知命令 '$1'"
    usage
    ;;
esac
