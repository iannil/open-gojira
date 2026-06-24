# ADR-0004: 进程模型——拆 API + Worker

2026-06-24 决定:Gojira 的 backend 拆成两个进程。**API 进程**(`uvicorn --reload`)只管 HTTP,不跑 scheduler/pipeline/plan_runner。**Worker 进程**(production,无 reload)跑 APScheduler + pipeline manager + plan_runner + EventBus。两进程共享同一 SQLite(WAL 模式支持多连接)。API→worker 的手动触发通过 `job_queue` 表 IPC,不上 Celery/Redis。

## Context

决策 6 选了「全量 maximal 数据」,意味着 backfill 是常态(2-3 小时/run)。现状是 backend 单进程 `uvicorn --reload`,APScheduler + pipeline daemon thread 都活在同一进程——改代码触发 reload → daemon thread 死 → 跑到 25% 的 financials backfill 永远 `running`(README L9 已知限制)。在 maximal 数据策略下,L9 从「cosmetic 已知限制」升级为「核心阻塞」,必须从根上解决。

四个候选方案的取舍是「dev 热重载 / backfill 不中断 / 复杂度」三角:单进程方案(A/C/D)要么牺牲 dev 体验要么牺牲 backfill 完整性,只有拆进程(B)同时满足「改 API 代码不中断 backfill」+「dev 热重载保留」。

## Considered Options

- **单进程 + 模式切换(dev 用 reload / backfill 用 production)**:被拒。靠你记着切模式是脆弱的,一次忘记就丢 backfill
- **单进程 production 永远不开 reload**:被拒。dev 体验差(每次代码改动手动重启),且单用户开发频率高
- **单进程 + 强 checkpoint resume**:被拒。resume 逻辑必须极致可靠(测试覆盖 95%+),否则 reload 后从断点续跑有 bug 是隐性灾难;且 reload 期间 daemon thread 还是死,只是能恢复
- **拆进程 + Celery/Redis 任务队列**:被拒。Redis 违反目标 #2「不引入基础设施」,单用户没必要

## Consequences

### 新增

- `backend/app/worker_main.py`:worker 进程入口,启动 APScheduler + pipeline manager daemon + EventBus
- `backend/app/job_queue/` 模块(或 service):API→worker IPC
  - `job_queue` 表:`{id, job_type, payload_json, status: pending/running/done/failed, created_at, started_at, finished_at, result_json, error_message}`
  - API endpoint(如 `POST /plans/3/run`)→ INSERT job_queue → 立即返回 job_id
  - worker 轮询 job_queue(每 N 秒)→ 执行 → UPDATE status
- `dev.sh` 改成起 2 进程,`.dev-pids/{api,worker}.pid`
- `dev.sh status` 显示双进程状态
- worker heartbeat:每 60s 写 `worker_heartbeat` 表(或 data_freshness 复用)→ Cockpit `WorkerHeartbeatCard` 显示「最后心跳 / 是否存活」

### 移动(从 API 到 worker)

- `app/scheduler.py` 整个移到 worker_main.py 启动
- `app/services/pipelines/manager.py` 的 daemon thread 启动逻辑移到 worker
- `app/services/plan_runner.py` 的 cron 触发链路在 worker 内闭环
- EventBus(`app/core/events.py`)限 worker 进程内;API 进程不发事件(若需,通过 job_queue 传递)

### 保留

- 共享同一 SQLite 文件(`backend/data/gojira.db`)
- WAL 模式(已开)支持多连接并发读 + 单写
- API 进程仍能直接读写 DB(HTTP 请求处理)
- manual execute 路径在 API(用户点击 → API 直接处理,不需要 worker)

### 风险

- SQLite 单写:API 写 + worker 写可能偶发 lock contention。WAL 下概率低,但 high-frequency 写入场景需观察。若问题严重,后续考虑「API 只读,所有写通过 job_queue 给 worker」
- job_queue 轮询延迟:默认 N 秒(建议 5s),手动触发会比同步慢 5s。可接受(决策 4 是 weekly review,不要求实时)

## 关联

- 决策来源:`docs/active/redesign-decisions.md` 决策 7
- 数据策略(依赖此架构):决策 6
- 手动运维(无 launchd,worker 挂了手动重启):ADR-0006
