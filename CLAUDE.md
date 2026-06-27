# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Open Gojira 是一台 **「个人股票自动驾驶舱」**：面向中国 A 股市场,采用**规则筛选 + LLM 深度研究 + 规则/人工审批**的混合架构,实现「选股 → 深研 → 买卖草稿 → 持仓审计 → 论点跟踪」全流程自动化。除了在券商真实下单外,全部自动。

**双引擎选股**(两条独立来源,不互相裁决)：价值复利(ai-berkshire 四大师 段/巴/芒/李)+ 产业链卡点(serenity)。交易思想权威见 `docs/standards/trading-philosophy.md`,工程决策见 `docs/active/redesign-decisions-v2.md`(26 决策)。

技术栈: FastAPI (Python 3.14) + React 19 (TypeScript) + PostgreSQL + Ant Design 6 + ECharts 6。Lixinger (理杏仁) 是唯一外部 A 股数据源,Zhipu GLM 提供 LLM + web_search。

当前状态: **v2 大重写**(2026-06-24 起),纸面交易后端闭环完成(2026-06-26,555 测试记录值)。详见 `docs/progress/STATUS.md` + `docs/progress/2026-06-26-v2-architecture-and-progress.md`。

> ⚠️ **v1→v2**：v2 删除了 v1 规则策略引擎(Strategy/Plan/Candidate/Watchlist/Holding/builtin_seeder/strategy_engine/plan_runner)。遇到这些名字或 `docs/reference/invest{1,2,3}.md`/`docs/reference/specs/` 一律视为已删除历史。

## 项目指南

- 目标：以强类型、可测试、分层解耦为核心，保证项目健壮性与可扩展性；以清晰可读、模式统一为核心，使大模型易于理解与改写。
- 语言约定：交流与文档使用中文；生成的代码使用英文；文档放在 `docs` 且使用 Markdown。
- 发布约定：
  - 发布的成果物必须且始终以生产环境为标准，要包含所有发布生产所应该包含的文件或数据（包含全量发布与增量发布，首次发布与非首次发布）。
- 环境约定：
  - 对于数据库、消息队列、缓存等，尽量使用docker部署环境
  - 如果是Python项目，尽可能使用venv虚拟环境
  - 尽量为项目配置独立的网络，避免与其他项目网络冲突
- 文档约定：
  - 每次修改都必须延续上一次的进展，每次修改的进展都必须保存在对应的 `docs` 文件夹下的文档中。
  - 执行修改过程中，进展随时保存文档，带上实际修改的时间，便于追溯修改历史。
  - 未完成的修改，文档保存在 `/docs/progress` 文件夹下。
  - 已完成的修改，文档保存在 `/docs/reports/completed` 文件夹下。
  - 对修改进行验收，文档保存在 `/docs/reports` 文件夹下。
  - 对重复的、冗余的、不能体现实际情况的文档或文档内容，要保持更新和调整。
  - 文档模板和命名规范可以参考 `/docs/standards` 和 `docs/templates` 文件夹下的内容。

### 面向大模型的可改写性（LLM Friendly）

- 一致的分层与目录：相同功能在各应用/包中遵循相同结构与命名，使检索与大范围重构更可控。
- 明确边界与单一职责：函数/类保持单一职责；公共模块暴露极少稳定接口；避免隐式全局状态。
- 显式类型与契约优先：导出 API 均有显式类型；运行时与编译时契约一致（zod schema 即类型源）。
- 声明式配置：将重要行为转为数据驱动（配置对象 + `as const`/`satisfies`），减少分支与条件散落。
- 可搜索性：统一命名（如 `parseXxx`、`assertNever`、`safeJsonParse`、`createXxxService`），降低 LLM 与人类的检索成本。
- 小步提交与计划：通过 `IMPLEMENTATION_PLAN.md` 和小步提交让模型理解上下文、意图与边界。
- 变更安全策略：批量程序性改动前先将原文件备份至 `/backup` 相对路径；若错误数异常上升，立即回滚备份。

### 可观测性开发（Observability Driven Development）

- 为了能够完整追踪代码的执行流，请你遵循 "全链路可观测性 (Full-Lifecycle Observability)" 模式编写代码；
- 结构化日志： 所有的日志输出必须是 JSON 格式，包含字段：timestamp, trace_id (全链路唯一ID), span_id (当前步骤ID), event_type (Function_Start/End, Branch, Error), payload (变量状态)；
- 装饰器/切面模式： 请定义一个 LifecycleTracker 装饰器或上下文管理器；
- 在函数进入时：记录输入参数 (Args/Kwargs)；
- 在函数退出时：记录返回值 (Return Value) 和耗时 (Duration)；
- 在函数异常时：记录完整的堆栈信息 (Stack Trace)；
- 关键节点埋点： 在复杂的 if/else 分支、for/while 循环内部、以及外部 API 调用前后，必须手动添加埋点（Point）；
- 执行摘要： 代码运行结束时，必须能够生成一份“执行轨迹报告 (Execution Trace Report)”；
- 请确保埋点代码与业务逻辑解耦（尽量使用装饰器），不要让日志代码淹没业务逻辑；

### 记忆系统

本项目采用基于Markdown文件的透明双层记忆架构。禁止使用复杂的嵌入检索。 所有记忆操作必须对人类可读且对Git友好。

#### 存储结构

记忆分为两个独立的层："流"（日常）层和"沉积"（长期）层。

- 第一层：每日笔记（流）
  - 路径： `./memory/daily/{YYYY-MM-DD}.md`
  - 类型： 仅追加日志。
  - 目的： 记录上下文的"流动"。今天所说的一切、做出的决定以及完成的任务。
  - 格式： 按时间顺序排列的Markdown条目。

- 第二层：长期记忆（沉积）
  - 路径： `./memory/MEMORY.md`
  - 类型： 经过整理、结构化的知识。
  - 目的： 记录上下文的"沉积"。用户偏好、关键上下文、重要决策以及"经验教训"（避免过去的错误）。
  - 格式： 分类的Markdown（例如 `## 用户偏好`、`## 项目上下文`、`## 关键决策`）。

#### 操作规则

##### 上下文加载（读取）

当初始化会话或生成响应时，通过组合以下内容来构建系统提示：

1. 长期上下文： 读取 `MEMORY.md` 的全部内容。
2. 近期上下文： 读取当前（以及可选的之前）一天的每日笔记内容。

##### 记忆持久化（写入）

- 即时操作（日常）：
  - 每一次交互都需要确认当日的记忆存在，如果不存在，应先初始化当日记忆
  - 将每一次重要的交互、工具输出或决策追加到当天的每日笔记中。
  - 不要覆盖或删除每日笔记中的内容；将其视为不可变的日志。
- 整合操作（长期）：
  - 触发条件： 当检测到有意义的信息时（例如，用户陈述了偏好、发现了特定的错误修复模式、建立了项目规则）。
  - 操作： 更新 `MEMORY.md`。
  - 方法： 智能地将新信息合并到现有类别中。如果信息已过时，则移除或更新它。此文件代表*当前*的真实状态。

#### 维护与调试

- 透明度： 所有记忆文件都是标准的Markdown文件。如果代理因错误的上下文而行为异常，修复方法是手动编辑 `.md` 文件。
- 版本控制： 所有记忆文件都受Git跟踪。

## 开发命令

```bash
# 同时启动前后端（推荐）
./dev.sh

# 仅启动后端（在 backend/ 目录下）
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 3001

# 仅启动前端（在 frontend/ 目录下）
npm run dev

# 运行全部后端测试（在 backend/ 目录下）
source .venv/bin/activate
pytest

# 运行单个测试文件
pytest tests/test_models.py

# 前端构建与检查（在 frontend/ 目录下）
npm run build
npm run lint
```

后端运行在 3001 端口，前端运行在 3000 端口。Vite 通过代理将 `/api` 请求转发到后端。

## 架构

### 后端 (Python / FastAPI)

分层架构：**Routers → Services → Models**，使用 **Schemas** 进行请求/响应校验。

实测计数(2026-06-26)：**25 routers · 36 services + llm(10) + pipelines(11 + pipelines/llm 6) · 27 models · 21 schemas · core(14) · 3 alembic 迁移**。

- `app/main.py` — FastAPI 应用入口，配置 CORS、生命周期（建表 + alembic upgrade）及 22 路由注册
- `app/config.py` — Pydantic Settings，读取 `.env`；默认 PostgreSQL,路径 `data/gojira.db`
- `app/routers/` — 22 个业务模块：health, stocks, valuation, financial, dividend, portfolio, market, trades, cash, fee_configs, corp_actions, drafts, cockpit, **research_v2**, **theme_scan**, alerts, system_alerts, notifications, scheduler, data_management, audit_log, observability
- `app/services/` — 业务逻辑层(顶层 36)；依赖注入接收 SQLAlchemy `Session`
- `app/services/llm/` — LLM 层(10)：`client`(GLM/Anthropic 抽象 + 缓存/重试/watchdog)、`cost_tracker`($150 硬熔断)、`conflict_validator`(5% 后验)、`red_line_checker`(8 红线)、`scoring`、`prompt_loader`、`deep_research_schema`、`theme_scan_schema`
- `app/services/pipelines/` — Pipeline 框架(11)：manager 编排 + base/checkpoint/dead_letter/metrics/throttler + 5 数据 Pipeline(dividend/financial/kline/valuation/universe_bootstrap)
- `app/services/pipelines/llm/` — 6 个 LLM Pipeline：quality_screen / deep_research(4 大师并行 + 综合) / thesis_tracker / news_pulse / earnings_review / theme_scan
- `app/schemas/` — Pydantic v2 请求/响应校验(21)
- `app/models/` — SQLAlchemy ORM(27)：Stock, Trade, CashBalance, Draft, ResearchReport, ThemeScanReport, StockLifecycle, DecisionAudit, LLMCallLog, RedLineEvent, Valuation, Financial, PriceKline, Dividend, CorpAction, SystemAlert, AuditLog, ...（**无 Holding/Plan/Candidate/Strategy/Watchlist** — v2 已删）
- `app/services/position_service.py` — **持仓/盈亏唯一真相源**(Trade 账本派生：移动加权 / 已实现+浮动盈亏 / T+1 冻结)。`holdings` 表已删(migration `v2_4`)
- `app/services/trade_service.py` — `record_trade` 唯一写持仓入口
- `app/services/draft_generator.py` — BUY 草稿生成(触发条件 D + 仓位 10/30/20 + TTL 7 天)
- `app/services/lifecycle_service.py` — StockLifecycle 状态机(30 天 re-research 缓存)
- `app/services/lixinger_client.py` — Lixinger API 客户端,唯一 A 股数据源
- `app/scheduler.py` — APScheduler 后台调度。JOB_REGISTRY 含 19 个 job(数据同步 + 股息 + 公司行动 + v2 LLM Pipeline)，无 v1 残留引用。
- `app/prompts/` — 外部 prompt 目录(按 pipeline 分)
- `app/core/observability*.py` — 全链路可观测系统(`@tracked` 装饰器 + 模块级批量注入)
- `app/core/events.py` + `event_handlers.py` — 进程内 EventBus(异步非阻塞)
- `app/core/scoring_config.py` — 双引擎评分 profile 权重(PROFILE_WEIGHTS)

### 前端 (React 19 / TypeScript / Vite)

**feature-based 架构**：`src/pages/*` 是 1 行 re-export shim,真实实现在 `src/features/`。

- `src/App.tsx` — ConfigProvider + React Router + TanStack Query，路由挂在 Layout 下
- `src/api/client.ts` — API 函数集中定义(含 serenity research 块);`src/api/research.ts` — v2 research 客户端(5 函数)
- `src/api/types.ts` — TypeScript 类型,与后端 schemas 对应
- `src/features/` — 路由级功能模块(17)：`cockpit`(信号优先 dashboard) / `universe` / `reports`(研究报告) / `stock-detail`(研究触发+K线) / `trades`(账本+出入金) / `drafts`(草稿审批) / `portfolio`(持仓组合) / `dividend`(股息红利) / `fee-configs`(券商费率) / `audit-log`(审计日志) / `market`(市场指数) / `corp-actions`(公司行动) / `valuation`(估值分析) / `data-management` / `scheduler` / `monitoring`(通知+风控,内嵌 alerts) / `eval`
- `src/components/` — 共享组件：`Layout`(导航壳) / `ErrorBoundary` / `QueryBoundary` / `SystemAlertBanner` / `TradeEntryModal` / `CashAdjustmentModal` / `primitives/`
- `src/styles/theme.css` — 全局 CSS 主题（"墨韵金阁"风格）

### 测试

后端测试使用内存 SQLite（`conftest.py` 通过测试会话覆盖 `get_db` 依赖）。每个测试通过 `autouse` fixture 获得全新的数据库 schema。测试使用 `fastapi.testclient.TestClient`。

## 关键模式

- 所有路由端点通过 `Depends(get_db)` 获取数据库会话，再委托给 service 层处理
- 前端 API 客户端集中在 `src/api/client.ts` / `src/api/research.ts`，新增接口在此添加函数
- Pydantic schemas 与 ORM models 分离，由 service 层负责转换；序列化标准见 `docs/standards/serialization.md`
- **双引擎评分 hybrid**：LLM 算分=advisory,Python 按 source profile(`scoring_config.PROFILE_WEIGHTS`)复核为权威分
- **LLM 防御三层**：Prompt 约束 + 代码后验(单股 ≤5% `conflict_validator`)+ Pipeline 熔断(冲突率 >20%)+ 8 红线否决(`red_line_checker`);成本 `cost_tracker` $150/月硬熔断
- **持仓真相源唯一**：一切持仓/盈亏经 `position_service` 从 Trade 账本派生,写交易走 `trade_service.record_trade`,勿直接建持仓
- LLM prompt 走 `app/prompts/{pipeline}/` 外部文件,不硬编码在 py
- UI 组件库 Ant Design；图表 ECharts(echarts-for-react)
- 可观测性：`@tracked` 装饰器 + 模块级批量注入,trace_id 全链路唯一
- EventBus 异步非阻塞：数据/论点/审计的自动响应链；新买卖 draft → in-app `system_alert(category=signal)`

## 文档索引

- `docs/progress/STATUS.md` — **项目当前状态快照**（AI 首先阅读此文件）
- `docs/progress/2026-06-26-v2-architecture-and-progress.md` — **v2 完整架构与进展**(迭代必读)
- `docs/standards/trading-philosophy.md` — **交易思想权威**(双引擎/评分/去重/弃用清单)
- `docs/active/redesign-decisions-v2.md` — **工程决策锚点**(26 决策,AI 首读)
- `docs/active/v2-implementation-plan.md` — 8-Phase 完整蓝图
- `docs/active/roadmap.md` — 近期优先级 (P0/P1/P2/P3)
- `docs/standards/serialization.md` — 序列化标准（持续生效）
- `docs/templates/` — 文档骨架模板（progress-entry / completed-report / acceptance-report）
- `docs/reports/` — 验收报告 + 代码库审计；`docs/reports/completed/` — 已完成的修改记录
- `docs/reference/ai-berkshire/` · `serenity-skill/` — 双引擎方法论参考（gitignored）
- `docs/archive/v1/` — v1 废弃文档（redesign-decisions-v1 / ADRs / 审计）；`docs/archive/` — 早期设计稿
- `memory/MEMORY.md` · `memory/daily/` — 项目记忆（沉积层 + 流层）

**文档规范**（详见项目指南）：
- 未完成的修改 → `docs/progress/`
- 已完成的修改 → `docs/reports/completed/`
- 对修改进行验收 → `docs/reports/`
- 持续生效的标准 → `docs/standards/`
- 文档骨架模板 → `docs/templates/`
