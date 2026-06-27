# 2026-06-27: theme_scan / deep_research 进度卡住修复

## 现象

TaskCenter 页面上 `theme_scan_on_demand` / `deep_research_on_demand` 任务进度卡在 10%，实时日志无更新。

## 根因分析

`theme_scan_pipeline.run()` 只在 5 个 LLM step 之间汇报进度，每个 LLM step（尤其第一个 `system_change` + web_search）会阻塞 1-5 分钟。期间：
1. 无 `on_progress` 调用，`TaskRun.progress_message` 不更新
2. 无 `on_log` 调用，日志面板无新条目
3. 前端每 5 秒轮询看到的是静止状态 → 用户认为任务已死

## 修复

### theme_scan_pipeline

在 `backend/app/services/pipelines/llm/theme_scan_pipeline.py` 中：

1. **新增 `_heartbeat_while` 上下文管理器**：LLM step 阻塞期间启动守护线程，每 10 秒：
   - 调用 `on_progress(p, f"{label} — 已等待 {elapsed}s")`
   - progress 值从 step_base 向 step_ceiling 每次 +1%（制造视觉移动）
   - 线程在 `with` 块退出时自动 `stop.set()` + join(2)

2. **覆盖全部 5 个 step**：
   - Step 1 (system_change): 10% → 28%
   - Step 2 (value_chain): 30% → 48%
   - Step 3 (scarce_layer): 50% → 63%
   - Step 4 (company_universe): 65% → 78%
   - Step 5 (candidate_rank): 85% → 98%

### deep_research_pipeline

在 `backend/app/services/pipelines/llm/deep_research_pipeline.py` 中：

1. **新增相同 `_heartbeat_while` 上下文管理器**
2. **添加 `on_progress` 参数**到 `run()` 签名
3. **覆盖全部 3 个阻塞 step**：
   - Step 1 (data_collection): 10% → 35%
   - Steps 2-5 (4 masters parallel): 40% → 70%
   - Step 6 (synthesis): 75% → 88%

同时更新 `backend/app/tasks/llm_pipelines.py` 中 `deep_research_on_demand` 任务函数，传递 `on_progress=lambda p, m: ctx.report_progress(p, m)`。

## 验证

- 语法检查 OK (ast.parse) — 两个文件
- 模块导入 OK
- 测试：722 passed, 1 failed（预存的 API 200→202 问题，与本修改无关）

## 文件变更

### `backend/app/services/pipelines/llm/theme_scan_pipeline.py`
- 新增 imports: `threading`, `time`, `contextmanager`, `Iterator`
- 新增 `_heartbeat_while()` 上下文管理器
- 修改 `run()` 中 5 个 `_step()` 调用，每个用 `with _heartbeat_while(...):` 包裹

### `backend/app/services/pipelines/llm/deep_research_pipeline.py`
- 新增 imports: `threading`, `time`, `Callable`, `contextmanager`, `Iterator`
- 新增 `_heartbeat_while()` 上下文管理器
- 新增 `on_progress` 参数到 `run()` 签名
- `run()` 体中插入进度调用 + heartbeat 包裹 3 个阻塞 step

### `backend/app/tasks/llm_pipelines.py`
- `deep_research_on_demand` 调用 `deep_research_pipeline.run()` 时传入 `on_progress`
