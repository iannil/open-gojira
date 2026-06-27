#!/usr/bin/env bash
# Gojira Docker 本地长期运行管理脚本
# =====================================
# 将项目打包为 Docker 镜像并在本地持续运行（生产模式，无 Caddy/HTTPS 等本地不必要的组件）
#
# 用法:
#   ./docker-local.sh              启动所有容器（等同于 up）
#   ./docker-local.sh up           构建并启动所有容器（后台）
#   ./docker-local.sh up-front     仅构建并启动前端（后台）
#   ./docker-local.sh stop         停止所有容器
#   ./docker-local.sh down         停止并删除所有容器
#   ./docker-local.sh restart      重启所有容器
#   ./docker-local.sh logs         查看日志（tail -f）
#   ./docker-local.sh rebuild      重新构建镜像并启动（代码更新后执行）
#   ./docker-local.sh rebuild-backend  仅重新构建后端
#   ./docker-local.sh rebuild-frontend 仅重新构建前端
#   ./docker-local.sh status       查看容器状态
#   ./docker-local.sh shell        进入后端容器内的 bash
#   ./docker-local.sh db-shell     进入后端容器查看数据库
#
# 启动后访问:
#   Frontend: http://localhost:7149
#   Backend:   http://localhost:7150
#
# 前提条件:
#   - Docker 已安装并运行（推荐 OrbStack 或 Docker Desktop）
#   - .env 文件在项目根目录（复制 .env.example 并填入 API keys）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_ARGS="-f docker-compose.yml -f docker-compose.local.yml"
PID_DIR="$ROOT_DIR/.dev"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── 检查 .env ─────────────────────────────────────────────────────────
check_env() {
  if [ ! -f "$ROOT_DIR/.env" ]; then
    if [ -f "$ROOT_DIR/.env.example" ]; then
      warn ".env 不存在！正在从 .env.example 复制..."
      cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
      info "请编辑 .env 填入 LIXINGER_TOKEN 和 ZHIPU_API_KEY，然后重新运行本脚本。"
    else
      warn ".env 不存在！请创建 .env 文件并填入以下内容:"
      echo ""
      echo "  LIXINGER_TOKEN=<你的理杏仁Token>"
      echo "  ZHIPU_API_KEY=<你的智谱API Key>"
      echo ""
    fi
  fi
}

# ── 修复 Docker buildx activity 文件权限（OrbStack 兼容） ──────────
fix_buildx_activity() {
  local activity_dir="$HOME/.docker/buildx/activity"
  if [ -d "$activity_dir" ]; then
    local tmpfiles
    tmpfiles=$(find "$activity_dir" -name '.tmp-*' 2>/dev/null || true)
    if [ -n "$tmpfiles" ]; then
      rm -f "$tmpfiles" 2>/dev/null || true
    fi
  fi
}

# ── 命令实现 ──────────────────────────────────────────────────────────

cmd_up() {
  check_env
  fix_buildx_activity
  info "构建并启动所有容器..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS up -d --build
  info "启动完成！"
  echo ""
  echo "  Frontend: http://localhost:7149"
  echo "  Backend:   http://localhost:7150"
  echo ""
  echo "查看状态:  ./docker-local.sh status"
  echo "查看日志:  ./docker-local.sh logs"
  echo "停止容器:  ./docker-local.sh stop"
}

cmd_up_front() {
  check_env
  fix_buildx_activity
  info "构建并启动前端（后台模式）..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS up -d --build frontend
  info "前端启动完成！http://localhost:7149"
}

cmd_stop() {
  info "停止所有容器..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS stop
  info "已停止。"
}

cmd_down() {
  info "停止并删除所有容器..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS down
  info "已清理。"
}

cmd_restart() {
  cmd_stop
  echo "---"
  cmd_up
}

cmd_logs() {
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS logs -f
}

cmd_rebuild() {
  check_env
  fix_buildx_activity
  info "重新构建镜像（代码更新后执行）..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS up -d --build --force-recreate
  info "重建完成！"
  echo ""
  docker compose $COMPOSE_ARGS ps
}

cmd_rebuild_backend() {
  check_env
  fix_buildx_activity
  info "重新构建后端镜像..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS build --no-cache backend
  docker compose $COMPOSE_ARGS up -d --force-recreate backend
  info "后端重建完成！"
}

cmd_rebuild_frontend() {
  check_env
  fix_buildx_activity
  info "重新构建前端镜像..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS build --no-cache frontend
  docker compose $COMPOSE_ARGS up -d --force-recreate frontend
  info "前端重建完成！"
}

cmd_status() {
  cd "$ROOT_DIR"
  echo "=== 容器状态 ==="
  docker compose $COMPOSE_ARGS ps
  echo ""
  echo "=== 资源使用 ==="
  docker compose $COMPOSE_ARGS stats --no-stream 2>/dev/null || echo "(stats 不可用)"
}

cmd_shell() {
  info "进入后端容器..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS exec backend /bin/bash
}

cmd_db_shell() {
  info "进入数据库 CLI（PostgreSQL）..."
  cd "$ROOT_DIR"
  docker compose $COMPOSE_ARGS exec -e PGPASSWORD="${POSTGRES_PASSWORD:-gojira}" backend psql \
    -h "${PGHOST:-postgres}" \
    -p "${PGPORT:-5432}" \
    -U "${POSTGRES_USER:-gojira}" \
    -d "${POSTGRES_DB:-gojira}"
}
}

# ── 主命令路由 ──────────────────────────────────────────────────────────

usage() {
  echo "Gojira Docker 本地长期运行管理脚本"
  echo ""
  echo "用法: $0 {up|stop|down|restart|logs|rebuild|status|shell|db-shell}"
  echo ""
  echo "  up              构建并启动所有容器（后台）"
  echo "  up-front        仅构建并启动前端"
  echo "  stop            停止所有容器"
  echo "  down            停止并删除所有容器"
  echo "  restart         重启所有容器"
  echo "  logs            查看日志 (tail -f)"
  echo "  rebuild         重新构建所有镜像并启动（代码更新后执行）"
  echo "  rebuild-backend 仅重新构建后端"
  echo "  rebuild-frontend仅重新构建前端"
  echo "  status          查看容器状态"
  echo "  shell           进入后端容器内的 bash"
  echo "  db-shell        查看数据库信息"
  echo ""
  echo "端口映射:"
  echo "  Frontend → http://localhost:7149"
  echo "  Backend  → http://localhost:7150"
  exit 0
}

case "${1:-}" in
  up|"")
    cmd_up
    ;;
  up-front)
    cmd_up_front
    ;;
  stop)
    cmd_stop
    ;;
  down)
    cmd_down
    ;;
  restart)
    cmd_restart
    ;;
  logs)
    cmd_logs
    ;;
  rebuild)
    cmd_rebuild
    ;;
  rebuild-backend)
    cmd_rebuild_backend
    ;;
  rebuild-frontend)
    cmd_rebuild_frontend
    ;;
  status)
    cmd_status
    ;;
  shell)
    cmd_shell
    ;;
  db-shell)
    cmd_db_shell
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    error "未知命令: '$1'"
    usage
    ;;
esac
