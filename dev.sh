#!/usr/bin/env bash
# Gojira 开发环境一键启动
# Usage: ./dev.sh
#
# 同时启动:
#   - Backend (uvicorn --reload, 端口 3001)
#   - Frontend (Vite dev server, 端口 3000)
#
# 要求:
#   - .env 文件在项目根目录 (复制 .env.example 并填入 API keys)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Gojira Dev ==="

# ── 检查 .env ───────────────────────────────────────────────────────────
if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "[WARN] .env 不存在！复制 .env.example 并填入 LIXINGER_TOKEN / ZHIPU_API_KEY:"
  echo "  cp .env.example .env"
  echo ""
fi

# ── 启动 backend (后台) ─────────────────────────────────────────────────
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
uvicorn app.main:app --reload --host 0.0.0.0 --port 3001 &
BACKEND_PID=$!

# ── 启动 frontend (后台) ─────────────────────────────────────────────────
echo "[Frontend] 启动 Vite dev server (端口 3000)..."
cd "$ROOT_DIR/frontend"
npm run dev -- --host 0.0.0.0 --port 3000 &
FRONTEND_PID=$!

# ── 清理 ────────────────────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "=== 关闭服务 ==="
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  wait
}
trap cleanup EXIT INT TERM

echo ""
echo "=== 启动完成 ==="
echo "  Backend:  http://localhost:3001"
echo "  Frontend: http://localhost:3000"
echo "  /api/health → http://localhost:3001/api/health"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待任一进程退出
wait
