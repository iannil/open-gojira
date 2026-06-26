# 代码库清理审计 (2026-06-26)

> **背景**：v2 大重写(2026-06-24 起)删除了 v1 规则策略引擎,但遗留了少量死代码/孤儿文件/配置不一致,且文档(STATUS/CLAUDE/roadmap)长期描述已删的 v1 架构。本报告梳理全部冗余/过期/失效项,并记录本轮已执行的安全清理。
> **配套**：文档治理见 `docs/progress/STATUS.md` 重写 + `docs/progress/2026-06-26-v2-architecture-and-progress.md`。

---

## A. 安全清理项（处置状态）

| # | 项 | 文件 | 处置 | 状态 |
|---|---|---|---|---|
| A1 | 空 package | `backend/app/services/migrations/`（仅 `__init__.py`） | 删除 | ⏳ 待执行(环境 Bash 分类器降级,`rm` 受阻) |
| A2 | ~~0-caller 弃用函数~~ | `backend/app/core/datetime_utils.py::utcnow()` | **取消删除** | ✅ 已核实:**并非死代码** — `events.py:17/59` 仍用作 Event timestamp `default_factory`。docstring 的 "0 callers" 不可信,保留 |
| A3 | 孤儿前端组件(grep 确认无 importer) | `frontend/src/components/PendingCorpActionsCard.tsx`、`DraftAvailableCell.tsx`、`components/stock/KlineChart.tsx`(连带空目录) | 删除 | ⏳ 待执行(已 grep 确认 NO_EXTERNAL_REFS;`rm` 受阻) |
| A4 | 未声明依赖 | `frontend/package.json` 缺 `dayjs`(经 antd 传递解析,脆弱) | 补 `^1.11.21` | ✅ 已执行 |
| A5 | 配置不一致 | `docker-compose.yml` `db-backup` 默认密码 `gojira` ≠ postgres/.env.example 的 `gojira_secret` | 统一为 `gojira_secret` | ✅ 已执行 |
| A6 | 过时注释 | `backend/app/main.py:80` "Seed built-in strategies and plans"(seeding 已随 builtin_seeder 删除) | 删注释 | ✅ 已执行 |

> **A1/A3 待执行原因**：本轮会话期间环境的 Bash 安全分类器持续降级,只读命令(grep/find)间歇可用,但 `rm`/`mv` 等改动命令被阻断。删除目标已用 grep 确认安全(A3 = NO_EXTERNAL_REFS),待分类器恢复后执行:
> ```sh
> rm -f frontend/src/components/PendingCorpActionsCard.tsx \
>       frontend/src/components/DraftAvailableCell.tsx \
>       frontend/src/components/stock/KlineChart.tsx && rmdir frontend/src/components/stock
> rm -rf backend/app/services/migrations
> ```

## B. 文档失实（本轮已重写，记录在案）

- `docs/progress/STATUS.md`：原描述 v1(1187 测试/22 routers/50 alembic),引用已不存在的 `docs/reference/specs/`、`invest{1,2,3}.md` 死链接。→ 已整文重写为 v2 真相。
- `CLAUDE.md`：原列已删的 routers/services/models/pages,计数错误(21/42/17/402)。→ 已重写架构段。
- `docs/active/roadmap.md`：原 v1 P0/P1(plan_runner/watchlist/PROMOTE)。→ 已重写为 v2 近期优先级。
- docs/ 归位(⏳ 待执行,同受 Bash `mv`/`rm` 受阻)：`docs/active/production-readiness-plan.md` → `docs/reports/completed/`；`docs/active/project-state.md` → `docs/archive/v1/`；v1 progress 日志(`2026-06-13-*`、`2026-06-18-*` 5 篇)→ `docs/archive/v1/progress/`；round6 三件套去重;删 `docs/reports/screenshots/`(thesis-monitor-v2 孤儿)与空目录 `docs/screenshots/lifecycle/`。`docs/progress/2026-06-26-paper-trading-loop-design.md` 留在 progress/(进行中)。

## C. 真实隐患（记录，需后续决策/单独修，本轮不动）

### C1. scheduler.py v1 孤儿 job + latent NameError（P3，优先级最高的隐患）
`backend/app/scheduler.py` 是 v1/v2 混合：
- **纯死函数**(不在 JOB_REGISTRY,引用已删模块,调用即崩)：`daily_plan_evaluation_job`(import `plan_runner`)、`thesis_evaluation_job`(import `thesis_monitor_service`)、`weekly_rebalancing_review_job`(import `rebalance_service`)、`daily_cycle_assessment_job`、`_monthly_thesis_variable_sync_job`、`_weekly_research_refresh_job`、`weekly_business_pattern_inference_job`(import `business_pattern_service`)、`research_stale_sweep_job`(import `ResearchRun` model)、`daily_snapshot_job`。
- **latent NameError(registry 内,危险)**：`_watched_and_held_codes`(scheduler.py:295) 调用 `watchlist_service.all_watched_codes` 但 `watchlist_service` **从未 import**(v1 已删)。被 registry 内的 `daily_kline_sync`/`daily_prev_close_sync`/`monthly_dividend_sync`/`quarterly_financials_refresh`/`quarterly_shareholders_refresh`/`weekly_dividend_sync` 间接调用 → 一旦 `SCHEDULER_ENABLED=true` 且这些 job 触发即 NameError。
- 因 scheduler 默认关闭(`SCHEDULER_ENABLED=false`)未在生产暴露。**修复建议**：删全部死函数;registry 内 job 的 code 列表改用 `position_service.held_stock_codes` + lifecycle 派生(去掉 watchlist 依赖)。

### C2. `/drafts` 前端 stub
`frontend/src/features/drafts/DraftsPage.tsx` 是占位("v2 待重建"),但 `/drafts` 导航项可达 → 非功能页面。属 roadmap P0(纸面交易前端 UI)范畴,届时重建。

### C3. 两套 research API 命名并存
`src/api/client.ts`(serenity `/research/themes...`)与 `src/api/research.ts`(v2 pipeline `/research/{code}`)两套 research 模型/类型并存,易混淆。建议合并或明确文档边界。

### C4. 疑似重叠服务（待确认边界，非确认重复）
- 四个数据校验服务：`data_quality_service`(253L)/`data_sanity_service`(153L)/`data_freshness_service`(116L)/`price_validator_service`。职责可能重叠,需确认。
- `historical_data_pipeline.py`(319L,service 层)vs `pipelines/` 子系统 — 可能被 PipelineManager 取代,确认是否 legacy。
- 两个 corp-action 服务(`processor`+`sync`)疑为合理的 sync/process 拆分,非重复。

### C5. 前端弃用类型
`frontend/src/api/types.ts:586` `ThemeExposure` 标 `@deprecated`(改用 `ThemeExposureAnalysis`)。确认无消费者后删。

### C6. quality_screen TODO
`backend/app/services/pipelines/llm/quality_screen_pipeline.py:101` `TODO: when full market cap data available`。功能性 TODO,记录。

### C7. deep_research stub helper
`backend/app/services/pipelines/llm/deep_research_pipeline.py:572` 自述 stub 的中间结果提取 helper;主路径走 `existing_report_id` 异步流(:615)。非主链路,记录。

## D. 大体积/运行时产物（gitignored，仅记录，未删）

- `backend/data/backups/pre-usage-wipe-2026-06-18.db`(~185MB,v0.1 paper artifact)
- 根 `README.md`(~74KB,疑似累积设计笔记,可考虑迁入 docs/ 或精简)
- `.dev-logs/backend.log`(~1.15MB)、`.DS_Store` 等

## E. 验证基线

- 后端测试：MEMORY 记录 555 passed。清理后须 `cd backend && source .venv/bin/activate && pytest -q` 复核不减（本轮因 Bash 分类器降级**未能复跑**,待执行）。
- 前端：删孤儿组件 + 补 dayjs 后 `cd frontend && npm run build && npm run lint` 通过（待执行）。
- `grep -rn "PendingCorpActionsCard\|DraftAvailableCell\|stock/KlineChart" frontend/src` 已确认 NO_EXTERNAL_REFS（删除前提成立）。
- A2 注意:`utcnow` 仍被 `events.py` 引用,**不删**。
