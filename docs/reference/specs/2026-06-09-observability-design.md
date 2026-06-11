# 全链路可观测系统设计

**日期**: 2026-06-09
**状态**: 已确认
**方案**: A — 装饰器驱动 + 模块级批量注入

## Context

Gojira 项目现有 `app/core/observability.py` 提供 structlog + LifecycleTracker 装饰器，但仅被 1 个 service 使用。278 个 service 函数、131 个 API 端点、10 个定时任务缺乏结构化观测。前端无任何观测基础设施。

本设计建立一个以 LLM 为主要消费者的全链路可观测体系，使 AI 工具能精准快速定位和解决问题。

## 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 消费者 | LLM 为主 | JSON 结构化日志，机器可解析 |
| 范围 | 前后端独立体系 | 各自独立运行，互不依赖 |
| 粒度 | 全量记录 | 参数 + 返回值 + 调用链 + 耗时 |
| 存储 | 文件日志 | 按日期轮转，LLM 直接读取 |
| 注入方式 | 模块级批量装饰 | 零侵入、可控、不使用 import hook |

## 一、后端观测核心架构

### 1.1 升级 LifecycleTracker

文件：`app/core/observability.py`

现有 `LifecycleTracker` 升级为支持：

**嵌套 Span 树**
- 每个 `@track_lifecycle` 自动生成 span_id
- 通过 `contextvars` 维护 `parent_span_id` 链
- 输出包含 `parent_span_id` 字段，LLM 可重建完整调用树

**参数/返回值序列化**
- `_safe_serialize()` 函数处理策略：
  - 基本类型（str/int/float/bool/None）直接序列化
  - dict/list 递归序列化，限制深度=4、单字段长度=500字符
  - SQLAlchemy Session → `"<Session>"`，ORM 对象 → `"<Model:Stock:600519>"`
  - 其他不可序列化对象 → `"<type:ClassName>"`
- `@track_lifecycle(compact=True)` 只记录参数计数和返回值类型

**分层控制**
- `OBSERVABILITY_LEVEL` 环境变量：
  - `full`（默认）：全量记录参数 + 返回值
  - `compact`：只记录参数计数 + 返回值类型
  - `off`：关闭观测
- `OBSERVABILITY_EXCLUDE` 环境变量：排除模块 glob 列表

**文件日志轮转**
- 使用 `logging.handlers.TimedRotatingFileHandler`
- 目录：`backend/logs/observability/`
- 文件名：`obs-YYYY-MM-DD.jsonl`
- 每天轮转，保留 30 天
- 同时输出到 stdout

### 1.2 日志输出格式

每行一条 JSON，格式如下：

```json
{
  "ts": "2026-06-09T14:30:00.123Z",
  "trace_id": "a1b2c3d4e5f6",
  "span_id": "x1y2z3",
  "parent_span_id": "p1q2r3",
  "event": "Function_Start",
  "function": "cockpit_service.build_cockpit",
  "args": {"db": "<Session>", "codes": ["600519", "000858"]},
  "kwargs": {}
}
```

```json
{
  "ts": "2026-06-09T14:30:00.456Z",
  "trace_id": "a1b2c3d4e5f6",
  "span_id": "x1y2z3",
  "parent_span_id": "p1q2r3",
  "event": "Function_End",
  "function": "cockpit_service.build_cockpit",
  "duration_ms": 333.21,
  "return_type": "dict",
  "return_summary": "{keys: [portfolio, benchmark, alerts], len: 3}"
}
```

```json
{
  "ts": "2026-06-09T14:30:00.456Z",
  "trace_id": "a1b2c3d4e5f6",
  "span_id": "x1y2z3",
  "parent_span_id": "p1q2r3",
  "event": "Error",
  "function": "cockpit_service.build_cockpit",
  "duration_ms": 333.21,
  "error_type": "LixingerError",
  "error_message": "API rate limit exceeded",
  "stack_trace": "Traceback (most recent call last):\n  ..."
}
```

## 二、自动注入机制

### 2.1 模块级批量装饰

文件：`app/core/observability_instrument.py`

`instrument_module(package_path, exclude=None)` 函数：

1. 扫描指定包下所有 `.py` 文件
2. 对每个模块中不以 `_` 开头的公共函数自动包装 `track_lifecycle`
3. 支持排除列表：`exclude=["seed_*", "*_helper"]`
4. 使用 `wrapt.wrap_function_wrapper` 保持原始函数签名

使用方式（在 `app/services/__init__.py` 中）：

```python
from app.core.observability_instrument import instrument_module
instrument_module("app.services", exclude=["seed_*", "builtin_seeder"])
```

### 2.2 Router 层 — FastAPI 中间件

在 `app/main.py` 中升级现有 `request_tracing_middleware`：

- 记录每个 HTTP 请求的 method + path + query_params + request_body（截断 1KB）
- 记录 response_status + response_body_summary + duration_ms + trace_id
- 自动生成 trace_id 并传播到所有下游 span

### 2.3 Scheduler 层

升级 `app/scheduler.py` 的 `_with_tracking()`：

- 每个 job 自动获得独立 trace_id
- 内部调用自动获得嵌套 span
- 与 service 层的 span 树无缝衔接

### 2.4 控制开关

- `instrument_module()` 检查 `OBSERVABILITY_LEVEL`，`off` 时完全跳过
- `OBSERVABILITY_MODULES` 环境变量：只观测指定模块（逗号分隔）
- 不使用 import hook，避免模块加载时序问题

## 三、前端独立观测体系

### 3.1 核心模块

```
src/observability/
  logger.ts       — 结构化 JSON logger
  tracer.ts       — API 调用链追踪器（trace_id + span_id）
  serializer.ts   — 参数/返回值安全序列化
  types.ts        — 类型定义
```

### 3.2 API 拦截器

在 `src/api/client.ts` 中添加 Axios request/response 拦截器：

- 每个请求自动记录 trace_id、method、url、params、request_body
- 响应记录 status、response_data_summary、duration_ms
- 错误记录完整 error 堆栈
- 输出到 `console.log(JSON.stringify({...}))`

### 3.3 组件级观测（可选）

关键页面组件包裹 HOC，记录组件挂载/卸载和关键 state 变更。

### 3.4 前端日志格式

```json
{
  "ts": "2026-06-09T14:30:00.123Z",
  "trace_id": "fe-a1b2c3d4",
  "span_id": "fe-x1y2z3",
  "source": "frontend",
  "event": "API_Call",
  "method": "GET",
  "url": "/api/cockpit",
  "status": 200,
  "duration_ms": 45.2,
  "response_summary": "{keys: [portfolio, benchmark], len: 2}"
}
```

## 四、LLM 消费接口

### 4.1 执行轨迹报告生成器

文件：`app/core/observability_report.py`

CLI 工具：

```bash
# 查看指定 trace 的调用树
python -m app.core.observability report --trace a1b2c3d4

# 查看最近 N 分钟的错误
python -m app.core.observability errors --minutes 30

# 查看慢调用
python -m app.core.observability slow --threshold_ms 1000 --minutes 60
```

输出格式（调用树）：

```
[trace: a1b2c3d4] GET /api/cockpit (342ms)
  ├── cockpit_service.build_cockpit (320ms)
  │   ├── holding_service.get_holdings (45ms) → 12 items
  │   ├── valuation_service.get_valuations (180ms) → 12 items
  │   │   └── lixinger_client.get_fundamentals (165ms)
  │   └── alert_service.evaluate_alerts (85ms) → 3 alerts
  └── theme_service.get_themes (15ms) → 5 themes
```

### 4.2 API 查询端点

文件：`app/routers/observability.py`

- `GET /api/observability/trace/{trace_id}` — 查询完整调用链
- `GET /api/observability/recent-errors?minutes=30` — 最近错误
- `GET /api/observability/slow-spans?threshold_ms=1000&minutes=60` — 慢调用

### 4.3 错误诊断报告

异常发生时自动生成：

- 完整调用栈（带参数值）
- 每一层 span 的耗时
- 失败的 SQL 查询（如有）
- 外部 API 调用的请求/响应（如有）

### 4.4 日志文件直接读取

LLM 通过 Read/grep 工具直接读取 `logs/observability/obs-*.jsonl`：
- 每行独立 JSON，支持流式读取
- 按 trace_id 过滤：`grep "a1b2c3d4" logs/observability/obs-2026-06-09.jsonl`
- 按 event 过滤：`grep '"Error"' logs/observability/obs-2026-06-09.jsonl`

## 五、实现计划

### 后端文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/core/observability.py` | 重写 | 嵌套 span + 参数序列化 + 文件输出 + 分层控制 |
| `app/core/observability_instrument.py` | 新建 | `instrument_module()` 自动注入引擎 |
| `app/core/observability_report.py` | 新建 | 执行轨迹报告生成器 + CLI |
| `app/services/__init__.py` | 修改 | 添加批量注入调用 |
| `app/scheduler.py` | 修改 | 升级 `_with_tracking()` |
| `app/main.py` | 修改 | 升级中间件 + 添加观测路由 |
| `app/routers/observability.py` | 新建 | 查询端点 |
| `app/schemas/observability.py` | 新建 | Pydantic schemas |
| `backend/logs/observability/.gitkeep` | 新建 | 日志目录 |
| `requirements.txt` | 修改 | 添加 `wrapt` |

### 前端文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/observability/logger.ts` | 新建 | 结构化 JSON logger |
| `src/observability/tracer.ts` | 新建 | API 调用链追踪器 |
| `src/observability/serializer.ts` | 新建 | 安全序列化 |
| `src/observability/types.ts` | 新建 | 类型定义 |
| `src/api/client.ts` | 修改 | 添加拦截器 |

### 实现顺序

1. 后端 `observability.py` 核心升级
2. 后端 `observability_instrument.py` 自动注入引擎
3. 后端 service 批量注入 + router 中间件升级
4. 后端 scheduler 升级 + observability router + CLI 报告工具
5. 后端测试
6. 前端 `src/observability/` 核心模块
7. 前端 API 拦截器集成
8. 端到端验证

## 六、验证方式

1. 启动后端，触发任意 API 请求，检查 `logs/observability/obs-*.jsonl` 包含完整调用链
2. 故意触发错误，验证错误诊断报告包含完整调用栈
3. 运行 `python -m app.core.observability report --trace <id>` 验证报告输出
4. 前端打开 DevTools console，验证 API 调用有 JSON 结构化输出
5. 设置 `OBSERVABILITY_LEVEL=off`，确认零开销
