# 2026-06-27: TaskCenter 执行日志 + 细粒度进度

## 修改时间

2026-06-27 08:59 CST

## 内容

针对 TaskCenter 页面(http://localhost:7149/task-center)改造，实现更细粒度的进度状态更新和执行日志查看。

## 修改清单

### 后端

1. **新增 `TaskRunLog` 模型** (`backend/app/models/task.py`)
   - 新增 `task_run_logs` 表，存储每步执行日志
   - 字段: `id`, `run_id` (FK → `task_runs.id`, CASCADE), `timestamp`, `level` (info/warning/error/progress), `message`, `progress` (可选)
   - `TaskRun.logs` relationship

2. **新增 alembic 迁移** (`backend/alembic/versions/v2_7_add_task_run_logs.py`)
   - 创建 `task_run_logs` 表 + 索引

3. **更新 `TaskContext`** (`backend/app/services/task/context.py`)
   - 新增 `on_log` 回调参数
   - 新增 `log(message, level)` 方法 — 任务可随时输出日志
   - `report_progress()` 自动以 `progress` 级别写入日志

4. **更新 `TaskEngine`** (`backend/app/services/task/engine.py`)
   - `_dispatch_run()` 中向 TaskContext 传入 `on_log` 回调
   - 新增 `_append_log()` 方法写入 DB
   - `run_to_dict()` 返回 `log_count` 字段

5. **新增 API 端点** (`backend/app/routers/task.py`)
   - `GET /api/tasks/runs/{run_id}/logs` — 返回时间序的执行日志列表
   - 支持 `limit` 参数 (默认500, 最大2000)

6. **更新 Schema** (`backend/app/schemas/task.py`)
   - 新增 `TaskRunLogResponse` Pydantic schema
   - `TaskRunDetailResponse` 增加 `log_count` 字段

### 前端

7. **新增类型** (`frontend/src/api/types.ts`)
   - `TaskRunLogResponse` 接口
   - `TaskRunDetailResponse` 增加 `log_count`

8. **新增 API 函数** (`frontend/src/api/client.ts`)
   - `fetchTaskRunLogs(runId, limit?)` → GET `/tasks/runs/{runId}/logs`

9. **重构 TaskCenterPage** (`frontend/src/features/task-center/TaskCenterPage.tsx`)
   - **进度条**: 用 Ant Design `<Progress>` 组件替代纯文本百分数，支持 success/exception/active 状态
   - **进度消息**: 进度条下方显示 `progress_message`，超长时 Tooltip
   - **日志 Drawer**: 每行运行记录有「查看/实时」按钮，点击打开右侧 Drawer
   - **Timeline 展示**: Drawer 内使用 Ant Design `<Timeline>`，每条日志含 level Tag + 时间戳 + 消息 + 可选子进度条
   - **自动刷新**: 打开日志 Drawer 时每 5s 自动轮询最新日志（运行中任务可实时追踪）

## 验证

- Backend: 722 passed, 0 failed (排除已知 theme_scan 异步问题)
- Backend task tests: 37 passed
- Frontend: TypeScript `tsc --noEmit` 零错误
- Frontend: ESLint 零新增错误
