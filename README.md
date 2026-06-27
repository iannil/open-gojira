# Gojira — 个人股票自动驾驶舱

> 你个人的 A 股自动驾驶舱 — 选股、深研、草稿、跟踪，全部自动。

**Gojira** 是一台面向**中国 A 股市场**的个人投资自动化系统。它把「选股 → 深研 → 买卖草稿 → 持仓审计 → 论点跟踪」这一整条流程，变成机器自动跑。

**只缺一件事：不在券商真实下单。** 所有交易以 paper draft 形式生成，你需要手动到券商 APP 复刻。

---

## 目录

1. [项目是什么](#1-项目是什么)
2. [启动与首次配置](#2-启动与首次配置)
3. [首次数据同步](#3-首次数据同步)
4. [看懂 Cockpit（主面板）](#4-看懂-cockpit主面板)
5. [双引擎选股 + 自动草稿](#5-双引擎选股--自动草稿)
6. [理解 TaskEngine（统一任务调度）](#6-理解-taskengine统一任务调度)
7. [故障排查](#7-故障排查)

---

## 1. 项目是什么

### 1.1 一句话定位

**如果你每天花大量时间翻股票、看财报、盯行情、纠结买卖点——Gojira 替你做完这些重复劳动。**

它从两个独立的角度自动扫描全市场：

1. **价值复利引擎** — 学习巴菲特、芒格、段永平、李录四位大师的选股逻辑，通过 LLM 深度研究，寻找长期持有的优质公司
2. **产业链卡点引擎** — 通过行业链分析，找到那些卡住产业链咽喉、不可替代的公司

两条引擎独立产出候选股，**互不裁决**，给你两个不同的视角做决策。

### 1.2 它能做什么

| 能力 | 说明 |
|---|---|
| 📡 **自动扫描** | 每天自动跑全市场 5600+ 只股票，按规则筛选 + LLM 深度研究 |
| 📝 **自动出草稿** | 发现符合条件的买入/卖出机会，自动生成带价格和仓位的草稿 |
| 🔍 **深度研究** | 对候选股进行 4 位大师思维的并行分析，输出结构化研究报告 |
| 📊 **持仓审计** | 自动监测持仓论点是否被证伪、估值是否越界、行业集中度是否超标 |
| 🚨 **智能告警** | 发现红旗信号、逻辑破裂、仓位超标时自动推送告警 |
| 📅 **自动调度** | 周一到周五，按交易日历自动运行数据同步和策略评估 |

### 1.3 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI (Python 3.14) + SQLAlchemy 2 + Pydantic v2 |
| 前端 | React 19 + TypeScript + Vite + Ant Design 6 + ECharts 6 |
| 数据库 | PostgreSQL 16（通过 Docker 运行，端口 7155） |
| 数据源 | [Lixinger 理杏仁](https://www.lixinger.com) — 唯一 A 股数据源 |
| LLM | 智谱 GLM（默认 glm-4.7） — 用于深度研究与智能筛选 |
| 调度 | TaskEngine（统一任务抽象层） — cron + 依赖 + 重试 + 超时看门狗 |

### 1.4 设计原则

1. **除真实券商下单外全自动化** — 筛选 / 研究 / 草稿 / 审计 / 告警都自动
2. **架构清晰可维护** — PostgreSQL（Docker 单容器）、无 Redis / CI 等额外基础设施
3. **交易思想可追溯** — 每一条规则和逻辑都有投资理论原文支撑

项目完整架构详见 [`docs/progress/STATUS.md`](docs/progress/STATUS.md) 与 [`docs/active/redesign-decisions-v2.md`](docs/active/redesign-decisions-v2.md)。

---

## 2. 启动与首次配置

### 2.1 环境要求

| 依赖 | 最低版本 | 验证命令 |
|---|---|---|
| Python | 3.14 | `python3 --version` |
| Node.js | 20 | `node --version` |
| npm | 10 | `npm --version` |
| Docker | 24+ | `docker --version` |

PostgreSQL 通过 Docker 容器运行（`docker compose up postgres`），开发环境不需要手动安装 PG。

### 2.2 克隆 + 安装依赖

```bash
git clone <repo-url> gojira
cd gojira

# 后端依赖
cd backend
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 前端依赖
cd ../frontend
npm install

# 启动 PostgreSQL（Docker）
cd ..
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d postgres
```

### 2.3 配置 .env（必填 Lixinger token）

```bash
cp .env.example .env
```

编辑 `.env`，填入真实 token：

| 字段 | 必填 | 说明 |
|---|---|---|
| `LIXINGER_TOKEN` | ✅ **必填** | [理杏仁官网](https://www.lixinger.com) → 用户中心 → API Token |
| `ZHIPU_API_KEY` | 🔶 可选（LLM 研究用） | [智谱开放平台](https://open.bigmodel.cn/usercenter/apikeys) |
| `DATABASE_URL` | 默认 PostgreSQL | 参考 `.env.example`，默认 `postgresql://gojira:gojira@localhost:7155/gojira` |

验证 token 有效：

```bash
cd backend && source .venv/bin/activate
python -c "from app.config import settings; print('LIXINGER_TOKEN:', 'set' if settings.LIXINGER_TOKEN else 'MISSING'); print('ZHIPU_API_KEY:', 'set' if settings.ZHIPU_API_KEY else 'MISSING')"
```

### 2.4 启动开发服务器

```bash
cd /path/to/gojira
./dev.sh
```

`dev.sh` 会：
1. 自动启动 PostgreSQL Docker 容器（端口 7155）
2. 运行数据库迁移（确保表结构最新）
3. 启动后端（`http://localhost:7150`）
4. 启动前端（`http://localhost:7149`）

预期看到：

```
Starting Gojira development environment...
[PostgreSQL] 启动 docker-compose postgres 服务...
[Backend]    启动 uvicorn (端口 7150)
[Frontend]   启动 Vite dev server (端口 7149)
```

打开浏览器 **http://localhost:7149** — 看到 Cockpit 主面板即成功。

### 2.5 验证健康状态

```bash
curl http://localhost:7150/api/health
# 预期: {"status":"ok","checks":{"database":"ok","lixinger_token":"configured","zhipu_api_key":"configured"}}
```

三个 `ok` = 完全就绪。

### 2.6 常用命令速查

```bash
./dev.sh                  # 启动前后端（自动启动 PG Docker）
./dev.sh status           # 查看服务状态
./dev.sh stop             # 停止所有服务

# 仅后端
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 7150

# 仅前端
cd frontend && npm run dev

# 跑测试（后端目录下）
cd backend && source .venv/bin/activate
pytest                     # 723 测试全跑
pytest -k "test_xxx"       # 单个测试
```

### 2.7 启动后第一件事

打开 **http://localhost:7149/data-management**，确认数据是否已同步。如果还没同步，跳到 [第 3 章](#3-首次数据同步)。

---

## 3. 首次数据同步

### 3.1 同步流程

```mermaid
flowchart TD
    A[DataManagement 页面] --> B[universe_bootstrap]
    B -->|全市场 5600+ 股| C[stocks 表]
    C --> D[valuations 同步]
    D -->|PE/PB/DYR| E[valuations 表]
    C --> F[financials 同步]
    F -->|5 年财报| G[financial_statements 表]
    C --> H[klines 同步]
    H -->|5 年日 K| I[price_klines 表]
    C --> J[dividends 同步]
    J -->|10 年分红| K[dividends 表]
```

### 3.2 用 API 启动（推荐）

最简单的全市场初始化方式：

```bash
# 1. 全市场股票列表
curl -X POST 'http://localhost:7150/api/data-management/pipeline/universe_bootstrap/start' \
  -H 'Content-Type: application/json' \
  -d '{"stock_codes": null}'
# 预期: ~5s, 返回 {"stock_count": 5626}

# 2. 估值快照（全市场 PE/PB/DYR）
curl -X POST 'http://localhost:7150/api/data-management/pipeline/valuations/start' \
  -H 'Content-Type: application/json' -d '{}'
# 预期: ~60s

# 3. 财报数据（可选粒度）
curl -X POST 'http://localhost:7150/api/data-management/pipeline/financials/start' \
  -H 'Content-Type: application/json' \
  -d '{"granularity": "q", "years": 5}'
# 预期: ~90 min

# 4. K 线（日 K）
curl -X POST 'http://localhost:7150/api/data-management/pipeline/klines/start' \
  -H 'Content-Type: application/json' \
  -d '{"years": 5}'
# 预期: ~3 hours

# 5. 分红（高股息策略需要）
curl -X POST 'http://localhost:7150/api/data-management/pipeline/dividends/start' \
  -H 'Content-Type: application/json' \
  -d '{"years": 10}'
# 预期: ~3 hours
```

### 3.3 用 UI 启动

打开 **http://localhost:7149/data-management**，在「Pipeline 控制」Tab 中：
1. 选择 pipeline 类型
2. 点「启动」
3. 在「运行历史」看进度

---

## 4. 看懂 Cockpit（主面板）

打开浏览器看到 Cockpit 后，你会看到几个核心区域：

### 4.1 信号区（顶部）

显示当前最重要的**系统信号**：
- 📌 **新候选股** — 双引擎新筛选出的值得关注的公司
- 🚨 **持仓告警** — 持仓股触发的卖出信号（论点证伪 / 估值越界 / 仓位超标）
- 📋 **待执行草稿** — 等待你确认的买卖草稿

### 4.2 持仓概览

你的持仓全貌：总市值、盈亏、行业分布、集中度检查。**持仓数据全部从 Trade 账本派生，是唯一真相源。**

### 4.3 研究动态

最近完成的 LLM 深度研究报告和产业链扫描结果，点击可查看完整内容。

### 4.4 系统健康

数据新鲜度、Pipeline 状态、LLM 调用量等信息。如果哪个数据源过期了，这里会标红。

---

## 5. 双引擎选股 + 自动草稿

这是 Gojira v2 最核心的能力——**两条独立的选股引擎，并行工作，互不干扰。**

### 5.1 价值复利引擎（ai-berkshire）

模拟四位投资大师的思维方式，对候选股进行深度研究：

| 大师 | 关注维度 |
|---|---|
| 🏛️ **巴菲特** | 护城河、ROE 持续性、自由现金流质量 |
| 🧠 **芒格** | 商业模式可理解性、心理模型、逆向思维 |
| 📐 **段永平** | 企业文化、本分、用户导向、定价权 |
| 📊 **李录** | 文明演进视角、结构性增长、能力圈边界 |

每位大师独立输出分析报告，最后合成综合评分。

### 5.2 产业链卡点引擎（serenity）

从产业链视角扫描：哪些公司卡住了不可替代的咽喉位置？哪些行业环节最难被绕过？

引擎输出：主题扫描报告 + 公司排序 + 证据链追踪。

### 5.3 自动草稿生成

当某个股票满足条件时，系统自动生成草稿：

**买入条件**：
- 双引擎之一筛选出该股票
- 估值处于合理或偏低位置
- 满足仓位管理规则（不超行业上限）

**卖出条件（4 种）**：
1. **论据证伪** — 当初买入的逻辑不成立了
2. **估值过热** — 价格超过合理估值 1.3 倍
3. **仓位超标** — 单股超 15% 仓位
4. **基本面恶化** — 核心财务指标显著变差

> ⚠️ 没有止损卖出。Gojira 只做基于逻辑的卖出，不做基于价格的止损。

### 5.4 三层 LLM 防御

为了防止 LLM 产生幻觉或错误判断，系统内置了三层防护：

1. **Prompt 约束** — 研究 prompt 严格限定输出格式和范围
2. **后验校验** — 单股评分偏差超过 5% 自动标记
3. **Pipeline 熔断** — 冲突率超 20% 自动暂停整个 pipeline

同时，每月 LLM 调用预算设有 **$150 硬熔断**，超支自动停用。

---

## 6. 理解 TaskEngine（统一任务调度）

Gojira 使用**统一的 TaskEngine 调度系统**来管理所有后台任务。TaskEngine 以 `@task` 装饰器声明式定义任务，支持：

- **Cron 触发** — 按标准 cron 表达式定时执行
- **依赖解析** — 任务可声明依赖上游任务，自动按序执行
- **互斥锁** — 同一时刻每个任务只有一个实例运行
- **超时看门狗** — 超过时间限制的任务自动终止
- **自动重试** — 失败任务按指数退避自动重试
- **执行历史** — 每次运行记录完整状态，页面可追溯

所有任务使用 Asia/Shanghai 时区，自动识别 A 股交易日。

### 6.1 数据同步任务

| 频次（CST） | 任务 | 说明 |
|---|---|---|
| 每交易日 15:00 | 全量数据同步 | 基础行情 + 增量的批量拉取 |
| 每交易日 15:15 | 估值更新 | 拉取最新 PE/PB/DYR |
| 每交易日 17:00 | 股息同步 | 检查新增股息数据 |
| 每交易日 17:15 | 公司行动同步 | 检查增发/回购/配股等事件 |
| 每交易日 17:20 | K 线增量同步 | 补全最近交易日 K 线 |
| 每日 全天（每15分钟） | 交易日历检查 | 确认当天是否开市 |
| 每交易日 09:00 | 数据新鲜度检查 | 标记过期数据的告警状态 |

### 6.2 LLM Pipeline 任务

| 频次（CST） | 任务 | 说明 |
|---|---|---|
| 周六 17:00 | 质量筛选 | LLM 对全市场做第一道质量过滤 |
| 周六 17:30 | 深度研究 | 对通过质量筛选的股票进行四位大师深度分析 |
| 周六 18:00 | 产业链扫描 | 扫描产业链卡点变化 |
| 每交易日 09:00 | 卖出触发检查 | 检查持仓是否触发出卖信号（估值/仓位/基本面） |
| 每交易日 18:30 | 论点评分 | 跟踪持仓论点，检查是否被证伪 |

### 6.3 任务管理

- **TaskCenter 页面** — 查看所有任务定义、状态、运行历史：`http://localhost:7149/task-center`
- **Scheduler 页面** — 查看传统调度视图：`http://localhost:7149/scheduler`
- **手动触发** — 在 TaskCenter 页面点击「触发」立即运行任务
- **暂停/恢复** — 支持按任务暂停，方便开发和排查

---

## 7. 故障排查

### 7.1 服务起不来

```bash
./dev.sh stop
lsof -ti :7149 -ti :7150 | xargs kill -9  # 强制清理端口
docker compose -f docker-compose.yml -f docker-compose.local.yml restart postgres
./dev.sh
```

### 7.2 数据库问题

```bash
# 确认 PostgreSQL 容器运行中
docker compose -f docker-compose.yml -f docker-compose.local.yml ps

# 查看 PG 日志
docker compose logs postgres

# 查看当前 schema 版本
cd backend && source .venv/bin/activate
alembic current

# 升级到最新
alembic upgrade head
```

### 7.3 数据显示「数据过期」

说明数据同步失败。检查：
- Lixinger token 是否有效（`python -c "from app.config import settings; print(settings.LIXINGER_TOKEN[:8] if settings.LIXINGER_TOKEN else 'MISSING')"`）
- 网络是否可达
- PostgreSQL 容器是否在运行
- 到 **http://localhost:7149/data-management** 手动触发同步

### 7.4 TaskEngine 未启动

```bash
# 检查 TaskEngine 健康状态
curl http://localhost:7150/api/tasks/health

# 查看任务运行历史
curl http://localhost:7150/api/tasks/runs?limit=10
```

完整故障排查指南见 [`docs/active/v2-implementation-plan.md`](docs/active/v2-implementation-plan.md)。

---

## 了解更多

| 文档 | 说明 |
|---|---|
| [`docs/progress/STATUS.md`](docs/progress/STATUS.md) | 项目当前状态快照（AI 首读） |
| [`docs/progress/2026-06-26-v2-architecture-and-progress.md`](docs/progress/2026-06-26-v2-architecture-and-progress.md) | v2 完整架构与进展 |
| [`docs/active/redesign-decisions-v2.md`](docs/active/redesign-decisions-v2.md) | v2 架构设计决策（26 项） |
| [`docs/active/v2-implementation-plan.md`](docs/active/v2-implementation-plan.md) | 8-Phase 完整蓝图 |
| [`docs/active/roadmap.md`](docs/active/roadmap.md) | 近期开发优先级 |
| [`docs/standards/trading-philosophy.md`](docs/standards/trading-philosophy.md) | 交易思想权威说明 |
| [`docs/standards/serialization.md`](docs/standards/serialization.md) | 序列化标准 |
| [`memory/MEMORY.md`](memory/MEMORY.md) | 项目长期记忆（沉积层） |

---

🟢 **v2 全链路闭环** · 25 路由 · 19 前端页面 · 29 ORM 模型 · 723 测试通过 · Alembic head: `v2_4_drop_holdings_table`
