# SQLite → PostgreSQL 迁移完成报告

**日期**: 2026-06-27  
**状态**: 全部完成

## 决策回顾（grill-me 会话确认）

| # | 主题 | 决定 |
|---|------|------|
| 1 | 测试策略 | 测试继续用 SQLite 内存，零改动 |
| 2 | PG 实例 | Docker Compose 加 `postgres:16-alpine`，也支持 `.env` 覆盖外部 PG |
| 3 | 数据迁移 | 写一次性迁移脚本 `backend/scripts/migrate_sqlite_to_pg.py`，保留所有数据 |
| 4 | `beijing_now_sql()` | 删除——0 调用死代码 |
| 5 | Alembic 历史 | 保留现有迁移，`env.py` 去掉 `render_as_batch=True` |
| 6 | 类型兼容 | 无需改动——全部标准类型 |
| 7 | psycopg2 | 切到非 binary 版本，Dockerfile 安装 `libpq-dev`+`libpq5` |
| 8 | dev.sh | 自动管理 Docker PG 容器 |

## 改动的 11 个文件

| # | 文件 | 改动 |
|---|------|------|
| 1 | `backend/requirements.txt` | `psycopg2-binary` → `psycopg2` |
| 2 | `backend/Dockerfile` | 加 `libpq-dev`（构建阶段）+ `libpq5`（运行时阶段） |
| 3 | `backend/app/config.py` | 默认 `DATABASE_URL` → `postgresql://gojira:gojira@localhost:5432/gojira` |
| 4 | `backend/alembic/env.py` | 删除 `render_as_batch=True` |
| 5 | `backend/app/core/datetime_utils.py` | 删除 `beijing_now_sql()` / `beijing_now_minus_sql()` 死代码 |
| 6 | `docker-compose.yml` | 新增 `postgres:16-alpine` 服务，更新 backend `DATABASE_URL`，db-backup 用 `pg_dump` |
| 7 | `docker-compose.local.yml` | 新增 postgres 端口映射 `5432:5432` |
| 8 | `dev.sh` | 新增 `_ensure_postgres()` 自动管理 Docker PG 容器，status 显示 PG 状态 |
| 9 | `.env` | 新增 DATABASE_URL 注释说明 |
| 10 | `backend/scripts/migrate_sqlite_to_pg.py` | **新文件**：一次性迁移脚本 |
| 11 | `scripts/backup.sh` | 已支持 PG（无需改动） |

## 验证结果

- **720 测试通过**，0 失败（排除 1 个预存测试不相关问题）
- 迁移脚本 `migrate_sqlite_to_pg.py`：FK 拓扑排序 → 批量读取 SQLite → 批量写入 PG → 重置序列，幂等设计

## 迁移到 PG 的步骤

```bash
# 1. 启动 PostgreSQL（Docker）
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d postgres

# 2. （可选）保留现有 SQLite 数据作为备份
cp backend/data/gojira.db backend/data/gojira.db.bak

# 3. 安装后端依赖（如果有新的 psycopg2）
cd backend && source .venv/bin/activate && pip install -r requirements.txt

# 4. 运行数据迁移脚本（从 SQLite → PG）
python backend/scripts/migrate_sqlite_to_pg.py

# 5. 启动完整服务
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d

# 或使用 dev.sh 本地开发
./dev.sh start
```

## 回退方案

如需回退到 SQLite，只需：
1. 在 `.env` 设置 `DATABASE_URL=sqlite:///data/gojira.db`
2. 确保 `backend/data/gojira.db` 存在
3. `alembic/env.py` 恢复 `render_as_batch=True`
