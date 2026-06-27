# 统一任务调度层 — 架构设计与实施计划

> **设计决策来源**：`/grill-me 深度讨论`（2026-06-26）
> **文档状态**：已确认设计，等待 Phase 1 实施
> **关联**：`docs/active/redesign-decisions-v2.md` · `docs/active/v2-implementation-plan.md`

---

## 一、设计总览

### 问题陈述

当前系统有两层分离的任务抽象：
- **APScheduler**（上层）— 17 个 cron job，通过 `JOB_REGISTRY` 映射到纯函数
- **PipelineManager**（下层）— 数据管道框架（Extract→Transform→Validate→Load→Verify），带检查点/死信/重试
- 两者通过 `pipeline_stale_sweep` 等桥接 job 连接，**没有统一的调度抽象**
- 缺少超时控制、任务间依赖、统一重试策略、事件驱动触发等关键能力

### 设计原则

1. **统一抽象** — 所有异步/定时任务统一为 `Task` 概念
2. **渐进迁移** — 现有代码零改动进入 Phase 1，逐个替换进入 Phase 2
3. **轻量无依赖** — 不引入 Celery/Temporal/Redis Queue，保持 SQLite 原生
4. **可观测优先** — 每个 Task 的执行全程可追踪（复用 `@tracked` 装饰器）

### 已确认的决策矩阵

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 架构范围 | 统一任务抽象层（不替换底层引擎） |
| 2 | 执行模型 | 混合模式：同步(ThreadPool) + async 双后端 |
| 3 | 任务依赖 | 简单依赖链（`depends_on`） |
| 4 | 状态机 | 详细：pending→queued→running→paused→cancelled→success/failed |
| 5 | 重试策略 | 统一：自动(配置次数+指数退避)+手动(UI/API) |
| 6 | 触发方式 | cron + 事件驱动 |
| 7 | 并发控制 | 互斥锁（同一 task 同时只有一个实例） |
| 8 | 数据层 | 统一 `tasks` + `task_runs` 两表 |
| 9 | 超时 | Task 级别 timeout，超时标记 failed(timeout) |
| 10 | EventBus 关系 | 作为触发前端，Task 层保证可靠执行 |
| 11 | 前端 | 增强现有 SchedulerPage，新增 Task 标签页 |
| 12 | 治理告警 | 全面治理（超时预警+堆积+调度延迟+依赖超时） |

---

## 二、3-Phase 迁移路径

```
Phase 1 (核心抽象) ◀━━ 你现在在这里
  └── 建表 + 核心引擎 + @task 装饰器 + 兼容层
       → APScheduler 降级为物理时间触发器

Phase 2 (逐步包装)
  └── 17 个 job 逐一迁移 + PipelineTask 适配器
       → 依赖链 + 互斥锁 + 超时 watchdog + 重试管理器

Phase 3 (事件集成)
  └── EventBus → Task 触发 + Task 完成 → EventBus
       → 全面治理告警 + 旧代码清理 + 前端全面支持
```

---

## 三、Phase 1 详细实施计划

### Phase 1 目标

> **"搭好骨架"**：建表、核心引擎、@task 装饰器、兼容层。现有 17 个 job 和所有 pipeline **零改动**，通过兼容层在统一调度器下正常运行。

### 预估工期：1 周

### 任务清单

#### Step 1.1 — 数据模型与迁移（1 天）

**新表：`tasks`**
```sql
CREATE TABLE tasks (
    task_id          VARCHAR(128) PRIMARY KEY,      -- 唯一标识，如 "daily_kline_sync"
    type             VARCHAR(32) NOT NULL DEFAULT 'job',  -- job / pipeline / event
    status           VARCHAR(16) NOT NULL DEFAULT 'pending', -- pending|active|paused|retired
    trigger_type     VARCHAR(16) NOT NULL DEFAULT 'cron', -- cron|event|api|chain
    cron_expr        VARCHAR(64),                   -- cron 表达式（trigger_type=cron）
    event_source     VARCHAR(64),                   -- 触发事件名（trigger_type=event）
    depends_on       TEXT,                          -- JSON: ["task_a", "task_b"]
    retry_config     TEXT,                          -- JSON: {"max_retries":3, "backoff":"exponential", "max_delay_seconds":300}
    timeout_seconds  INTEGER DEFAULT 300,
    mutex_enabled    BOOLEAN DEFAULT TRUE,          -- 互斥锁
    enabled          BOOLEAN DEFAULT TRUE,
    tags             TEXT,                          -- JSON: ["data","kline"]
    description      TEXT,
    created_at       DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at       DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

**新表：`task_runs`**
```sql
CREATE TABLE task_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id          VARCHAR(128) NOT NULL REFERENCES tasks(task_id),
    status           VARCHAR(16) NOT NULL DEFAULT 'queued',
        -- queued → running → success
        --         → running → failed
        --         → running → retrying → running → ...
        --         → cancelled
        --         → paused
    progress         REAL DEFAULT 0.0,              -- 0.0 ~ 1.0
    progress_message TEXT,                          -- "正在处理第 45/120 只股票"
    started_at       DATETIME,
    finished_at      DATETIME,
    duration_ms      INTEGER,
    retry_count      INTEGER DEFAULT 0,
    max_retries      INTEGER DEFAULT 0,
    last_error       TEXT,
    result_summary   TEXT,
    worker_id        VARCHAR(64),                   -- 哪个 worker 在执行
    triggered_by     VARCHAR(32) DEFAULT 'cron',    -- cron|api|event|chain|retry
    trace_id         VARCHAR(64),                   -- 全链路追踪 ID
    created_at       DATETIME NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_task_runs_task_id ON task_runs(task_id);
CREATE INDEX idx_task_runs_status ON task_runs(status);
CREATE INDEX idx_task_runs_created ON task_runs(created_at);
```

**迁移策略**：
- 新建 2 张表（`tasks` + `task_runs`）
- 从现有 `scheduler_jobs` 表数据 seed 初始化 `tasks` 表
- 现有 `scheduler_jobs` + `job_executions` 表**暂时保留**（Phase 3 清理）
- 新建 Alembic migration 文件

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/models/task.py` | 新增 | ORM 模型：Task, TaskRun |
| `backend/app/models/__init__.py` | 修改 | 导出新模型 |
| `backend/app/schemas/task.py` | 新增 | Pydantic schemas: TaskCreate, TaskResponse, TaskRunResponse, TaskListParams |
| `backend/app/schemas/__init__.py` | 修改 | 导出新 schema |
| `backend/alembic/versions/xxxx_add_tasks_and_task_runs.py` | 新增 | 建表 migration + seed 数据 |

#### Step 1.2 — TaskRegistry（任务注册中心）（1 天）

核心能力：
- `@task()` 装饰器，声明式注册 task
- 启动时自动扫描 `app.tasks/` 包
- 自动将注册的 task 同步到 `tasks` 表
- 运行时通过 `task_id` 获取 `TaskDefinition` 对象

```python
# 使用示例
@task(
    name="daily_kline_sync",
    cron="0 18 * * 1-5",
    retry=3,
    backoff="exponential",
    timeout=600,
    mutex=True,
    tags=["data", "kline"],
)
def daily_kline_sync(ctx: TaskContext) -> dict:
    """执行 K 线同步"""
    ...
```

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/services/task/__init__.py` | 新增 | 包初始化 |
| `backend/app/services/task/registry.py` | 新增 | TaskRegistry + @task 装饰器 |
| `backend/app/services/task/context.py` | 新增 | TaskContext（进度上报/日志/取消信号） |
| `backend/app/tasks/__init__.py` | 新增 | 任务定义包（初始为空，Phase 2 填充） |
| `backend/app/tasks/_compat.py` | 新增 | 兼容层：将现有 17 个 job 函数包装为 Task |

#### Step 1.3 — TaskEngine（调度核心）（1.5 天）

核心能力：
- **cron 触发器**：替代 APScheduler 的 `add_job()`，改为每秒 tick 检查到期任务
- **互斥锁**：`SELECT ... FOR UPDATE` 或 `UPDATE tasks SET status='running' WHERE status='queued'` 原子操作
- **依赖检查器**：运行前检查所有 `depends_on` 任务的最新 run 是否为 success
- **超时 watchdog**：后台线程定期检查 running 任务是否超时，超时则标记 `failed(timeout)`
- **重试管理器**：失败后按配置进行指数退避重试
- **生命周期**：start/shutdown 挂载在 FastAPI lifespan 中

```python
class TaskEngine:
    def start(self):
        """启动调度循环（每秒 tick）"""
    
    def shutdown(self, wait: bool = True):
        """优雅关闭：等待当前任务完成或超时后强制取消"""
    
    def trigger_task(self, task_id: str, trigger_type: str = "api") -> TaskRun:
        """手动触发任务"""
    
    def cancel_task(self, run_id: int) -> bool:
        """取消正在执行的任务"""
    
    def pause_task(self, task_id: str) -> bool:
        """暂停定时任务"""
    
    def resume_task(self, task_id: str) -> bool:
        """恢复定时任务"""
    
    def list_runs(self, task_id: str | None, status: str | None, limit: int) -> list[TaskRun]:
        """查询执行历史"""
    
    def get_health(self) -> dict:
        """健康检查：排队深度、worker 数量、最近错误"""
```

**与 APScheduler 的关系**：
- TaskEngine 启动后，会扫描所有 `tasks` 表中 `trigger_type=cron` & `enabled=true` 的任务
- **APScheduler 降级**：只作为 TaskEngine 的"物理时间触发后端"保留
  - APScheduler 注册一个每秒 tick 的 job：`_task_engine_tick`
  - 或者直接移除 APScheduler，TaskEngine 自己用 `time.sleep(1)` 循环
- **选择方案**：初期保留 APScheduler 作为 tick 触发，但将 job 调度逻辑全部移到 TaskEngine

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/services/task/engine.py` | 新增 | TaskEngine 核心 |
| `backend/app/services/task/dependency.py` | 新增 | 依赖检查器 |
| `backend/app/services/task/timeout_watchdog.py` | 新增 | 超时 watchdog |
| `backend/app/services/task/retry_manager.py` | 新增 | 重试管理器 |
| `backend/app/services/task/mutex.py` | 新增 | 互斥锁实现 |

#### Step 1.4 — TaskExecutor（双后端执行器）（1 天）

核心能力：
- **同步执行器**：`ThreadPoolExecutor(max_workers=8)` 执行现有的同步 job/pipeline 函数
- **异步执行器**：`asyncio.create_task()` 执行 `async def` 的新任务
- **worker_id** 分配，便于追踪
- **取消信号传播**：通过 `TaskContext.cancelled` 标记让任务优雅退出

```python
class TaskExecutor:
    def __init__(self, max_sync_workers: int = 8):
        self._sync_pool = ThreadPoolExecutor(max_sync_workers)
        self._async_tasks: dict[int, asyncio.Task] = {}
    
    async def execute_sync(self, run_id: int, fn: Callable, ctx: TaskContext) -> dict:
        """在 ThreadPool 中执行同步函数"""
    
    async def execute_async(self, run_id: int, fn: Callable, ctx: TaskContext) -> dict:
        """在 event loop 中执行异步函数"""
    
    async def cancel_run(self, run_id: int):
        """取消指定 run_id 的执行"""
    
    def shutdown(self, wait: bool = True):
        """关闭线程池"""
```

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/services/task/executor.py` | 新增 | TaskExecutor |
| `backend/app/services/task/worker.py` | 新增 | Worker 管理（worker_id 分配/心跳） |

#### Step 1.5 — 兼容层：包装现有 17 个 Job（0.5 天）

现有 `scheduler.py` 中的 17 个 job 函数（`daily_kline_sync_job` 等）全部保持不动。在 `tasks/_compat.py` 中：

```python
# _compat.py — 将现有 job 函数包装为 Task
from app.services.task.registry import task
from app.scheduler import daily_kline_sync_job, ...

@task(
    name="daily_kline_sync",
    cron="0 18 * * 1-5",
    retry=3,
    timeout=600,
    mutex=True,
    tags=["data", "kline"],
    **_job_config  # 从 JOB_REGISTRY 提取
)
def _daily_kline_sync_wrapper(ctx: TaskContext) -> dict:
    """兼容包装：调用现有 job 函数"""
    return daily_kline_sync_job()
```

**关键原则**：17 个 job 函数**不修改**，只在兼容层中引用。Phase 2 逐个迁移时才真正重写。

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/tasks/_compat.py` | 新增 | 17 个 Task 包装器（与 Step 1.2 合并） |

#### Step 1.6 — 集成到 FastAPI 生命周期（0.5 天）

- `app/main.py` lifespan 中注册 TaskEngine 启动/关闭
- 新增 TaskEngine 启动时自动扫描 `app.tasks` 包
- 新增 `task_registry.sync_to_db()` 将注册的 task 同步到 `tasks` 表
- 新增 `task_engine.start()` 开始调度循环

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/main.py` | 修改 | lifespan 事件中集成 TaskEngine |
| `backend/app/services/task/__init__.py` | 修改 | 包初始化时自动 import tasks |

#### Step 1.7 — 后端 REST API（0.5 天）

新增 router `/api/tasks/*`：

| 端点 | 方法 | 说明 |
|---|---|---|
| `GET  /api/tasks` | list | 列出所有 Task（含状态/下次运行时间） |
| `GET  /api/tasks/{id}` | detail | 单个 Task 详情 + 最近 runs |
| `PUT  /api/tasks/{id}` | update | 更新 cron/retry/timeout/enabled |
| `POST /api/tasks/{id}/trigger` | trigger | 手动触发 |
| `POST /api/tasks/{id}/pause` | pause | 暂停 |
| `POST /api/tasks/{id}/resume` | resume | 恢复 |
| `GET  /api/tasks/runs` | runs | 查询执行历史（分页/过滤） |
| `POST /api/tasks/runs/{run_id}/cancel` | cancel | 取消运行 |
| `POST /api/tasks/runs/{run_id}/retry` | retry | 手动重试 |

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/app/routers/task.py` | 新增 | Task REST API |
| `backend/app/routers/__init__.py` | 修改 | 注册新 router |
| `backend/app/main.py` | 修改 | 注册路由 |

#### Step 1.8 — 前端 SchedulerPage 增强（1 天）

在现有 SchedulerPage 中新增 **Task 管理标签页**：

- **Task 列表**：显示所有注册的 task（table: 名称/类型/触发方式/cron/状态/上次运行/下次运行/操作）
- **Task 详情弹窗**：运行历史、重试配置、依赖关系
- **手动操作按钮**：触发/暂停/恢复/取消
- **实时状态指示**：当前 running 任务显示进度条
- 复用现有 Ant Design Table 和 Modal 组件

**API 客户端新增**：
```typescript
// src/api/client.ts 新增
listTasks(): Promise<TaskInfo[]>
getTask(id: string): Promise<TaskDetail>
updateTask(id: string, data: Partial<TaskUpdate>): Promise<void>
triggerTask(id: string): Promise<void>
pauseTask(id: string): Promise<void>
resumeTask(id: string): Promise<void>
listTaskRuns(params: TaskRunParams): Promise<TaskRun[]>
cancelTaskRun(runId: number): Promise<void>
retryTaskRun(runId: number): Promise<void>
```

**文件清单**：
| 文件 | 操作 | 说明 |
|---|---|---|
| `frontend/src/api/client.ts` | 修改 | 新增 Task API 函数 |
| `frontend/src/api/types.ts` | 修改 | 新增 Task / TaskRun 类型 |
| `frontend/src/features/scheduler/components/TaskListTab.tsx` | 新增 | Task 列表标签页 |
| `frontend/src/features/scheduler/components/TaskDetailModal.tsx` | 新增 | Task 详情弹窗 |
| `frontend/src/features/scheduler/SchedulerPage.tsx` | 修改 | 新增 Task 标签页 |
| `frontend/src/features/scheduler/useTaskQueries.ts` | 新增 | React Query hooks |
| `frontend/src/features/scheduler/useTaskMutations.ts` | 新增 | Mutation hooks + toast |

---

## 四、Phase 1 完整文件清单

| # | 文件 | 操作 | 预估行数 |
|---|---|---|---|
| 1 | `backend/app/models/task.py` | 新增 | 80 |
| 2 | `backend/app/models/__init__.py` | 修改 | +2 |
| 3 | `backend/app/schemas/task.py` | 新增 | 120 |
| 4 | `backend/app/schemas/__init__.py` | 修改 | +2 |
| 5 | `backend/alembic/versions/xxxx_add_tasks_and_task_runs.py` | 新增 | 100 |
| 6 | `backend/app/services/task/__init__.py` | 新增 | 20 |
| 7 | `backend/app/services/task/registry.py` | 新增 | 150 |
| 8 | `backend/app/services/task/context.py` | 新增 | 60 |
| 9 | `backend/app/services/task/engine.py` | 新增 | 350 |
| 10 | `backend/app/services/task/executor.py` | 新增 | 120 |
| 11 | `backend/app/services/task/dependency.py` | 新增 | 60 |
| 12 | `backend/app/services/task/mutex.py` | 新增 | 40 |
| 13 | `backend/app/services/task/retry_manager.py` | 新增 | 80 |
| 14 | `backend/app/services/task/timeout_watchdog.py` | 新增 | 100 |
| 15 | `backend/app/services/task/worker.py` | 新增 | 50 |
| 16 | `backend/app/tasks/__init__.py` | 新增 | 10 |
| 17 | `backend/app/tasks/_compat.py` | 新增 | 200 |
| 18 | `backend/app/main.py` | 修改 | +30 |
| 19 | `backend/app/routers/task.py` | 新增 | 200 |
| 20 | `backend/app/routers/__init__.py` | 修改 | +2 |
| 21 | `frontend/src/api/client.ts` | 修改 | +80 |
| 22 | `frontend/src/api/types.ts` | 修改 | +40 |
| 23 | `frontend/src/features/scheduler/SchedulerPage.tsx` | 修改 | +50 |
| 24 | `frontend/src/features/scheduler/components/TaskListTab.tsx` | 新增 | 200 |
| 25 | `frontend/src/features/scheduler/components/TaskDetailModal.tsx` | 新增 | 150 |
| 26 | `frontend/src/features/scheduler/useTaskQueries.ts` | 新增 | 50 |
| 27 | `frontend/src/features/scheduler/useTaskMutations.ts` | 新增 | 80 |

**总计**：约 **2,500 行新增代码**

---

## 五、架构图（Phase 1 完成后的状态）

```
┌────────────────────────────────────────────────────────────────┐
│  Frontend (SchedulerPage 增强)                                  │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐ │
│  │  Jobs Tab (保留)     │  │  Tasks Tab (新增)                │ │
│  │  17 cron jobs 列表   │  │  21 tasks 列表                   │ │
│  │  cron 编辑/启用/触发  │  │  状态/进度/依赖/操作              │ │
│  └─────────────────────┘  └──────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────┤
│  REST API: /api/scheduler/* (保留) + /api/tasks/* (新增)        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────────────────────────────────────────┐       │
│  │             TaskEngine (新增)                         │       │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ │       │
│  │  │ Cron     │ │ Event    │ │ Dep    │ │ Mutex    │ │       │
│  │  │ Trigger  │ │ Listener │ │ Checker│ │ Lock     │ │       │
│  │  └──────────┘ └──────────┘ └────────┘ └──────────┘ │       │
│  │  ┌──────────┐ ┌────────────┐ ┌──────────┐          │       │
│  │  │ Timeout  │ │ Retry      │ │ Worker   │          │       │
│  │  │ Watchdog │ │ Manager    │ │ Manager  │          │       │
│  │  └──────────┘ └────────────┘ └──────────┘          │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                │
│  ┌─────────────────────────────────────────────────────┐       │
│  │            TaskRegistry (新增)                        │       │
│  │  自动扫描 app.tasks → 注册 @task 装饰器 → DB 同步      │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                │
│  ┌─────────────────────────────────────────────────────┐       │
│  │            TaskExecutor (新增)                        │       │
│  │  ┌──────────────────┐  ┌────────────────────────┐   │       │
│  │  │ SyncExecutor     │  │ AsyncExecutor          │   │       │
│  │  │ ThreadPool(8)    │  │ asyncio.create_task()  │   │       │
│  │  └──────────────────┘  └────────────────────────┘   │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                │
│  ┌──────────────┐  ┌────────────────────┐  ┌──────────────┐   │
│  │ APScheduler   │  │ PipelineManager    │  │ EventBus     │   │
│  │ (降级为 tick) │  │ (保留,被Task包装)   │  │ (保留,触发前端)│   │
│  └──────────────┘  └────────────────────┘  └──────────────┘   │
│                                                                │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  DB: tasks + task_runs (新增)                        │       │
│  │      scheduler_jobs + job_executions (保留,过渡期)    │       │
│  └─────────────────────────────────────────────────────┘       │
└────────────────────────────────────────────────────────────────┘
```

---

## 六、Phase 1 验证清单

- [ ] `TaskRegistry` 启动时自动注册 17+ tasks
- [ ] `TaskEngine` 启动后 cron 任务按时触发
- [ ] 互斥锁正常工作（同一 task 并发触发只有一个执行）
- [ ] 超时 watchdog 正确拦截超时任务
- [ ] 失败后重试按指数退避执行（最多 N 次）
- [ ] REST API 所有端点返回正确
- [ ] 前端 Task 列表展示所有 task 及其状态
- [ ] 手动触发/暂停/恢复/取消操作正常工作
- [ ] 现有 17 个 cron job 的行为与迁移前完全一致
- [ ] 所有 pipeline 行为完全一致
- [ ] 服务重启后恢复运行中的任务状态
- [ ] `pytest tests/` 全部通过
- [ ] 前端 `npm run build` 通过

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| TaskEngine tick 循环阻塞 FastAPI | 低 | 高 | 用独立线程 + asyncio 事件循环 |
| 超时 watchdog kill 任务时数据不一致 | 中 | 中 | 超时不强制 kill，设 cancelled 标记让任务自查 |
| 互斥锁在 SQLite 下性能问题 | 低 | 中 | SQLite WAL 模式下 `UPDATE ... WHERE status='queued'` 原子操作 |
| 与现有 APScheduler 调度冲突 | 中 | 高 | Phase 1 保留 APScheduler，但将 TaskEngine cron 设为权威源 |
| 迁移过程长，功能阻塞 | 中 | 中 | 3-Phase 策略，每 Phase 独立可发布 |
