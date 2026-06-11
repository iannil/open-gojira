# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Gojira 是一个面向中国 A 股市场的全栈投资分析系统，提供个股分析、估值工具、投资组合管理、分红追踪和交易纪律等功能。

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

- `app/main.py` — FastAPI 应用入口，配置 CORS、生命周期（自动建表）及所有路由注册
- `app/config.py` — Pydantic Settings，读取 `.env` 配置；默认使用 SQLite，路径为 `data/gojira.db`
- `app/routers/` — 按业务域划分的 API 端点：health, stocks, valuation, portfolio, dividend, market, financial, watchlist, alerts, scheduler, cashflow_goal, audit_log, plans, drafts, plan_templates, cockpit, review, theme
- `app/services/` — 业务逻辑层；通过依赖注入接收 SQLAlchemy `Session`
- `app/schemas/` — Pydantic v2 模型，用于请求/响应数据校验
- `app/models/` — SQLAlchemy ORM 模型（Stock, Holding, Plan, Draft, ValuationSnapshot, FinancialStatement, DividendRecord, AlertRule, AuditLog, CashflowGoal, Theme, WatchlistItem, PlanTemplate）
- `app/db/` — 数据库引擎（SQLite）、会话管理（`get_db` 依赖）、声明式基类
- `app/services/lixinger_client.py` — Lixinger (理杏仁) API 客户端，唯一的 A 股数据源
- `app/scheduler.py` — APScheduler 后台调度（每日快照、K线、警报评估、Plan 评估、周度再平衡、月度论点同步）
- `app/services/plan_evaluator.py` — Plan DSL 纯函数评估器
- `app/services/thesis_variable_sync_service.py` — 论点变量行业模板 + 自动同步

### 前端 (React 19 / TypeScript / Vite)

- `src/App.tsx` — Ant Design ConfigProvider + React Router，嵌套路由挂载在 Layout 下
- `src/api/client.ts` — Axios 客户端，baseURL 为 `/api`；所有 API 函数集中定义在此
- `src/api/types.ts` — TypeScript 类型定义，与后端 schemas 一一对应
- `src/pages/` — 路由级页面组件（Cockpit, Universe, Plans, PlanEditor, Review, StockDetail）
- `src/components/` — 按功能组织的组件：QiuScorerWizard, DisciplineChecklistModal, KlineChart 等
- `src/styles/theme.css` — 全局 CSS 自定义属性主题（"墨韵金阁"风格）
- `src/components/Layout.tsx` — 应用外壳，包含导航栏

### 测试

后端测试使用内存 SQLite（`conftest.py` 通过测试会话覆盖 `get_db` 依赖）。每个测试通过 `autouse` fixture 获得全新的数据库 schema。测试使用 `fastapi.testclient.TestClient`。

## 关键模式

- 所有路由端点通过 `Depends(get_db)` 获取数据库会话，再委托给 service 层处理
- 前端 API 客户端集中在 `src/api/client.ts`，新增接口在此添加函数
- Pydantic schemas 与 ORM models 分离，由 service 层负责转换
- 行业分析模板从 `backend/app/templates/industries/` 下的 JSON 文件加载
- UI 组件库使用 Ant Design；图表使用 ECharts（通过 echarts-for-react）

## 文档索引

- `docs/progress/STATUS.md` — 项目进展真相（AI 首先阅读此文件）
- `docs/archive/2026-06-04-investment-system-design.md` — 原始设计稿（归档）
- `docs/active/roadmap.md` — 下一步优先级计划
- `docs/active/code-audit.md` — 代码审计发现
- `docs/reference/investment-theory-source.md` — 投资理论原文
