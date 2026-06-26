# Gojira 部署 Runbook & 运维手册

> **版本**: 1.0 (2026-06-26)
> **适用**: 单用户生产部署 (SQLite WAL, Docker Compose)
> **前置**: Git, Docker 24+, 64-bit Linux/macOS

---

## 目录

1. [部署前检查清单](#1-部署前检查清单)
2. [生产部署步骤](#2-生产部署步骤)
3. [首次启动配置](#3-首次启动配置)
4. [日常运维检查清单](#4-日常运维检查清单)
5. [备份与恢复](#5-备份与恢复)
6. [故障排除指南](#6-故障排除指南)
7. [升级指南](#7-升级指南)
8. [参考命令速查](#8-参考命令速查)

---

## 1. 部署前检查清单

### 1.1 服务器最低要求

| 项目 | 最低 | 推荐 |
|:---|:---:|:---:|
| CPU | 2 cores | 4 cores |
| RAM | 2 GB | 4 GB |
| 磁盘 | 10 GB | 50 GB (含历史数据) |
| OS | Ubuntu 22.04+ / Debian 12+ | 同左 |
| Docker | 24.0+ | 27.0+ |
| 网络 | 出站访问 lixinger.com, bigmodel.cn | — |

### 1.2 软件依赖

```bash
# 安装 Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录使组生效

# 验证
docker --version && docker compose version
```

### 1.3 域名与 DNS（可选）

如果提供 HTTPS 访问:
- 准备域名 (如 `gojira.example.com`)
- DNS A 记录指向服务器 IP
- 开放 80 (HTTP 重定向) + 443 (HTTPS) 端口

---

## 2. 生产部署步骤

### 2.1 克隆代码

```bash
git clone <your-repo-url> /opt/gojira
cd /opt/gojira
```

### 2.2 配置环境变量

```bash
cp .env.example .env
# 务必修改以下值:
vim .env
```

**必须配置的项**:

```ini
# ── 数据库 ──
DATABASE_URL=sqlite:///data/gojira.db

# ── API 密钥 ──
LIXINGER_TOKEN=your_lixinger_token_here
ZHIPU_API_KEY=your_zhipu_api_key_here

# ── CORS ──
CORS_ORIGINS=["http://localhost:80","https://gojira.example.com"]
```

> ⚠️ **安全提醒**: `.env` 包含 API 密钥，确保 `.gitignore` 已排除，切勿提交到 git。

### 2.3 启动服务

```bash
# 启动全部服务 (backend + frontend + caddy)
docker compose up -d

# 确认健康状态
docker compose ps

# 查看启动日志
docker compose logs backend --tail=50
```

### 2.4 初次数据同步

首次部署后，数据库为空。需要通过 API 或 UI 触发数据同步:

```bash
# 1. 同步全市场股票列表
curl -X POST http://localhost:80/api/stocks/sync

# 2. 启动 valuations pipeline（全市场估值数据）
curl -X POST http://localhost:80/api/data-management/pipeline/valuations/start

# 3. 运行 quality_screen（LLM 初筛）
curl -X POST http://localhost:3001/api/scheduler/jobs/v2_quality_screen_weekly/run

# 4. 运行 deep_research（LLM 深度研究）
curl -X POST http://localhost:3001/api/scheduler/jobs/v2_deep_research_weekly/run
```

> ⚠️ valuations pipeline 同步全市场（~5600 只股票）可能需要 **5-10 分钟**。

### 2.5 验证安装

```bash
# 健康检查
curl http://localhost:80/api/health

# 查看 scheduler job 列表
curl http://localhost:80/api/scheduler/jobs | python3 -m json.tool

# 前端访问
open http://localhost:80
```

---

## 3. 首次启动配置

### 3.1 初始现金设置

通过 UI 或 API 设置初始资金:

```bash
curl -X POST http://localhost:80/api/cash/adjustments \
  -H "Content-Type: application/json" \
  -d '{"amount": 1000000, "happened_at": "'$(date -Iseconds)'", "reason": "deposit", "note": "初始入金"}'
```

### 3.2 券商费率配置

创建默认券商费率（卖出时用于计算印花税/佣金）:

```bash
curl -X POST http://localhost:80/api/fee-configs \
  -H "Content-Type: application/json" \
  -d '{
    "broker_name": "default",
    "commission_rate": 0.00025,
    "commission_min": 5.0,
    "stamp_duty_rate": 0.0005,
    "transfer_fee_rate": 0.00001,
    "effective_from": "2026-01-01",
    "is_active": true
  }'
```

### 3.3 冷启动流程

如果已有持仓需要初始化:

```bash
# 1. 建仓：逐笔录入已有交易
# 通过 UI / DraftsPage → ExecuteModal 或 API
curl -X POST http://localhost:80/api/trades \
  -H "Content-Type: application/json" \
  -d '{
    "stock_code": "600519", "side": "BUY",
    "price": 1500.0, "quantity": 100,
    "filled_at": "2026-06-01T10:30:00",
    "source": "csv_import"
  }'
```

> 如持仓较多，可批量调用或通过 `/api/trades` 逐一录入。

---

## 4. 日常运维检查清单

### 4.1 每日检查（开盘前 09:00）

```bash
# 1. 确认所有服务运行
docker compose ps

# 2. 确认 scheduler 正常运行
curl http://localhost:80/api/scheduler/jobs | python3 -c "
import sys,json
data = json.load(sys.stdin)
for j in data:
    if j['enabled']:
        print(f\"  {j['job_id']:35s} next_run={j['next_run_time'] or 'N/A':25s} last={j['last_run_status'] or 'never':10s}\")
"

# 3. 检查 cash balance
curl http://localhost:80/api/cash/balance

# 4. 检查 portfolio 持仓
curl http://localhost:80/api/portfolio/summary | python3 -m json.tool

# 5. 检查未处理的 drafts（应买/应卖信号）
curl 'http://localhost:80/api/drafts?status=pending' | python3 -c "
import sys,json
data = json.load(sys.stdin)
print(f'待处理 drafts: {len(data)} 条')
"
```

### 4.2 每周检查

```bash
# 1. 检查 LLM 月度成本
#   → 在 UI Cockpit 页查看 LLM Cost 告警
#   → 或直接查询数据库
sqlite3 backend/data/gojira.db \
  "SELECT strftime('%Y-%m', created_at) as month, 
          ROUND(SUM(cost_cny), 2) as total_cost,
          COUNT(*) as call_count
   FROM llm_call_log 
   GROUP BY month 
   ORDER BY month DESC
   LIMIT 3;"

# 2. 检查磁盘使用
df -h /var/lib/docker/volumes/gojira_backend_data/
du -sh backend/data/

# 3. 检查 pipeline 健康度
curl http://localhost:80/api/data-management/pipeline/runs | python3 -c "
import sys,json
data = json.load(sys.stdin)
by_status = {}
for r in data:
    s = r.get('status','unknown')
    by_status[s] = by_status.get(s,0) + 1
for s,c in sorted(by_status.items()):
    print(f'  {s:15s}: {c}')
"
```

### 4.3 每月检查

```bash
# 1. 审计日志归档
sqlite3 backend/data/gojira.db "SELECT COUNT(*) FROM audit_log;"

# 2. 检查 scheduler 执行历史失败率
curl http://localhost:80/api/scheduler/jobs | python3 -c "
import sys,json
data = json.load(sys.stdin)
failed = [j for j in data if j.get('last_run_status') == 'failed']
if failed:
    print('以下 job 上次执行失败:')
    for j in failed:
        print(f'  {j[\"job_id\"]}: last={j.get(\"last_run_at\",\"?\")}')
else:
    print('所有 job 上次执行正常')
"

# 3. 检查 LLM 月度预算（$150 硬熔断）
#   → 在 UI Cockpit 页查看
#   → 如需重置计数器，重启 backend 服务
```

---

## 5. 备份与恢复

### 5.1 自动备份

docker-compose 包含 `db-backup` 服务，使用 `scripts/backup.sh`：

```bash
# 手动触发备份
docker compose run --rm db-backup

# 备份文件位置
ls -la /var/lib/docker/volumes/gojira_backup_data/_data/
```

备份默认保留最近 **30 份**，按文件名时间戳轮转。

### 5.2 手动备份

```bash
# 停止 backend 确保数据一致性（可选）
docker compose stop backend

# 备份 SQLite 数据库
docker run --rm -v gojira_backend_data:/data:ro -v $(pwd)/backups:/backups \
  alpine:3.19 sh -c "apk add --no-cache sqlite > /dev/null && \
  sqlite3 /data/gojira.db '.backup /backups/gojira_manual_$(date +%Y%m%d_%H%M%S).db'"

# 重新启动 backend
docker compose start backend
```

### 5.3 恢复

```bash
# 停止服务
docker compose down

# 替换数据库文件
docker run --rm -v gojira_backend_data:/data -v $(pwd)/backups:/backups \
  alpine:3.19 sh -c "cp /backups/gojira_20260626_120000.db /data/gojira.db"

# 重新启动
docker compose up -d

# 验证数据
curl http://localhost:80/api/portfolio/summary | python3 -m json.tool
```

### 5.4 冷备份策略建议

| 频率 | 方式 | 保留 |
|:---|:---|---:|
| 每日 | docker-compose db-backup 自动 | 30 天 |
| 每周 | 手动 scp 备份到另一台机器 | 3 个月 |
| 每月 | 冷备份 + 归档 | 12 个月 |

---

## 6. 故障排除指南

### 6.1 服务无法启动

```bash
# 查看所有容器日志
docker compose logs --tail=50

# 检查端口冲突
sudo lsof -i :3001  # backend
sudo lsof -i :80    # caddy

# 重建镜像
docker compose build --no-cache
docker compose up -d
```

### 6.2 Backend 健康检查失败

```bash
# 查看 backend 日志
docker compose logs backend --tail=100

# 检查数据库文件
docker compose exec backend ls -la /app/data/

# 检查环境变量
docker compose exec backend env | grep -E "DATABASE|LIXINGER|ZHIPU"
```

### 6.3 数据库损坏

SQLite WAL 模式非常稳定，但如果遇到异常关机:

```bash
# 1. 停止 backend
docker compose stop backend

# 2. 运行完整性检查
docker compose run --rm -v gojira_backend_data:/data:ro \
  alpine:3.19 sh -c "apk add --no-cache sqlite > /dev/null && \
  sqlite3 /data/gojira.db 'PRAGMA integrity_check;'"

# 3. 如果检查失败，从最近的备份恢复
#   → 参见 5.3 恢复章节
```

### 6.4 Lixinger API 限流

```bash
# 查看最近 lixinger 调用错误
docker compose logs backend --tail=200 | grep -i lixinger | grep -i error

# 症状: pipelinerun 状态=failed, error_message 含"rate limit"
# 缓解: pipelinerun 有自动重试(tenacity 3次),等待即可
# 长时间限流: 检查 Lixinger 账户配额
```

### 6.5 LLM 调用超时

```bash
# 查看 LLM 调用日志
docker compose logs backend --tail=200 | grep -i "glm\|zhipu\|llm" | grep -i error

# 常见原因:
# - GLM API 网络不稳定（含 SSL hang）
# - 月度预算超限（$150 硬熔断）
# - API Key 过期

# 缓解:
# - research_stale_sweep 自动清理超时 run（15/30 分钟）
# - 如预算超限，在 .env 中提高 SERENITY_MONTHLY_BUDGET_CNY
#   然后重启: docker compose restart backend
```

### 6.6 磁盘空间不足

```bash
# 查看各 volume 使用
docker system df

# 清理无用数据
# 1. 旧的 pipeline run 日志（保留最近 100 条）
# 2. 旧的 LLM call dump（backend/data/llm_logs/）
# 3. Docker build 缓存
docker builder prune -f
docker image prune -f

# 监控 volume 大小
docker run --rm -v gojira_backend_data:/data alpine du -sh /data/
```

### 6.7 Scheduler Job 手动触发

```bash
# 查看所有 job
curl http://localhost:80/api/scheduler/jobs | python3 -m json.tool

# 手动触发某个 job
curl -X POST http://localhost:80/api/scheduler/jobs/daily_base_sync/run

# 强制重新调度某个 job
curl -X POST http://localhost:80/api/scheduler/jobs/v2_quality_screen_weekly/run
```

### 6.8 Pipeline Stuck 处理

如果 pipeline 状态卡在 `running` 超过 8 小时:

```bash
# 1. 手动修复
sqlite3 backend/data/gojira.db \
  "UPDATE pipeline_runs SET status='failed', finished_at=datetime('now')
   WHERE status='running' AND started_at < datetime('now', '-8 hours');"

# 2. pipeline_stale_sweep job 每 15 分钟自动清理
# 3. 可临时触发手动清理
curl -X POST http://localhost:80/api/scheduler/jobs/pipeline_stale_sweep/run
```

---

## 7. 升级指南

### 7.1 标准升级

```bash
# 1. 拉取最新代码
cd /opt/gojira
git pull origin main

# 2. 备份数据库
docker compose run --rm db-backup

# 3. 重新构建并启动
docker compose build
docker compose up -d

# 4. 验证
curl http://localhost:80/api/health
docker compose ps
```

### 7.2 Alembic 数据库迁移

Gojira 使用 Alembic 管理数据库 schema 变更:

```bash
# 查看迁移历史
docker compose exec backend alembic history

# 执行待处理的迁移
docker compose exec backend alembic upgrade head

# 创建新的迁移（开发时需要）
# docker compose exec backend alembic revision --autogenerate -m "description"
```

### 7.3 版本回退

```bash
# 1. 从备份恢复数据库（→ 5.3）
# 2. 回退代码
git checkout <previous-tag-or-commit>

# 3. 重建并启动
docker compose build
docker compose up -d
```

---

## 8. 参考命令速查

### 8.1 Docker

```bash
docker compose up -d              # 启动所有服务
docker compose down               # 停止并移除容器
docker compose restart backend    # 重启 backend
docker compose logs backend -f    # 实时跟踪 backend 日志
docker compose exec backend sh    # 进入 backend 容器
docker compose build              # 重建所有镜像
docker compose pull               # 拉取最新镜像（CI/CD 后）
```

### 8.2 API 健康检查

```bash
# 基础健康
curl http://localhost:80/api/health
# 预期: {"status":"ok","version":"..."}

# 完整健康
curl http://localhost:80/api/health/full
# 预期: {"database":"connected","lixinger":"configured","llm":"configured",...}
```

### 8.3 数据库

```bash
# 直接查询（仅开发/排障时）
sqlite3 backend/data/gojira.db ".tables"
sqlite3 backend/data/gojira.db "SELECT code, current_state FROM stock_lifecycle;"
sqlite3 backend/data/gojira.db "SELECT COUNT(*) FROM trades;"
```

### 8.4 数据管理

```bash
# 清空使用数据（保留市场数据，重置投资记录）
python scripts/wipe_usage_data.py --dry-run  # 预演
python scripts/wipe_usage_data.py             # 执行

# Pipeline 状态查询
curl http://localhost:80/api/data-management/pipeline/runs | python3 -m json.tool
```

---

> **文档维护**: 此 Runbook 应与代码同步更新。如有部署流程变更，请同时更新此文档。
