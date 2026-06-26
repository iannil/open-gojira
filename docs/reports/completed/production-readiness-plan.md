# Gojira 生产化实施计划 (Production Readiness Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Gojira 从"业务闭环已通但数值飘"的状态,升级到"可在 A 股真实账户上跑、P&L 准确、风控自动、可回测验证"的生产级系统。

**Architecture:** 引入 `trades` 流水表作为唯一事件源,`Holding` 改为派生视图;双层强制 T+1;分层防御 Lixinger 失效;完整回测引擎验证策略;公司行为自动应用;Docker Compose 部署 + 多通道告警 + 实时行情补充。

**Tech Stack:** FastAPI / SQLAlchemy 2.0 / Pydantic v2 / APScheduler / Alembic / React 19 / Ant Design 6 / ECharts 6 / Docker Compose / 新浪财经实时报价 / Server酱 推送

---

## 上下文与共识(2026-06-12 grill-me 会话锁定)

本计划基于一次完整的 grill-me 决策会话,11 项核心决策已锁定:

| # | 决策点 | 选择 |
|---|---|---|
| Q1 | 成交回报 | 手动录入(用户填 trade,draft 不自动变 trade) |
| Q2 | 数据模型 | `trades` 流水表为事件源,`Holding` 派生,可红冲 |
| Q3 | T+1 | 双层强制(plan_runner 软校验 + trade 写入硬拒绝) |
| Q4 | 资金模型 | `cash_balance`(动态) + `total_capital`(静态) + `cash_adjustments` 流水 |
| Q5 | 成本 | 自动算 + 可覆盖,`broker_fee_configs` 历史化 |
| Q6 | 价格 / 涨跌停 / 停牌 | 三层校验,按 board/ST/停牌 跳过 |
| Q7 | Lixinger 失效 | 多层防御(HTTP 重试 + staleness + sanity check + system_alerts) |
| Q8 | 回测 | 完整引擎(5-10 年历史 + 真实约束 + point-in-time) |
| Q9 | 公司行为 | 自动同步 + 自动应用,配股人工 |
| Q10 | 盘中 / 告警 / 止损 | 监控 50-80 只关键股 + 多通道(server_chan)+ holding_risk_rules |
| Q11 | DR / 部署 | Docker Compose + restart=always + 每日备份 + healthcheck |
| Q12 | 税务 / 合规 | **不做** |
| Q13 | 初始化导入 | **用户手动添加**(不做交割单 CSV 导入) |

完整决策推理过程见对话历史。

---

## 关键假设(S0 Spike 必须先验证,任一失败则对应阶段降级)

| # | 假设 | 验证方式 | 失败降级方案 |
|---|---|---|---|
| A1 | Lixinger 提供送股/转增历史(不止现金分红) | 调 `/cn/company/dividend` 看 response 是否含送转字段 | 接东方财富 HTTP 接口做补充 |
| A2 | Lixinger 提供配股 / 退市 / 代码变更事件 | 查 Lixinger 文档 / 调试探针 | 接公告爬虫(巨潮资讯) |
| A3 | Lixinger 财报数据带 `publish_date` 字段 | 调 `/cn/company/fs/non_financial` 看 response schema | 用 `report_period + 90d` 估算发布日(粗糙但可用) |
| A4 | Lixinger 历史估值/PE 时序可拉 10 年 | 调 `/cn/company/fundamental/non_financial` 加 `startDate=2015-01-01` | 限制回测时间范围至 5 年 |
| A5 | 新浪 `hq.sinajs.cn` 实时报价稳定可用 | curl 测试 + 1 天稳定性观察 | 切腾讯 `qt.gtimg.cn` |
| A6 | SQLite WAL 在 5 分钟级写入 + 多读并发下不锁死 | 写并发压测脚本 | 引入 PostgreSQL(违反项目决策) |
| A7 | Lixinger 基础信息含 `trade_status` / `board` / `is_st` | 调 `/cn/company` 看 schema | 用股票代码前缀 + 名称含 ST 推断 |

---

## S0 Spike 结果(2026-06-12 完成)

完整报告:`docs/reports/spike-results-2026-06-12.md`

### 假设验证结果

| # | 假设 | 结果 | 关键修订 |
|---|---|---|---|
| A1 | 送股/转增 | ✅ | `bonusSharesFromProfit` / `bonusSharesFromCapitalReserve` 字段确认 |
| A2 | 配股/退市/并购独立端点 | ❌ | `/cn/company/allotment` 是僵尸端点(返回空);配股降级为手工录入 |
| A3 | publish_date | ✅ | `reportDate` 字段直接读取,S4B 简化 |
| A4 | 10 年历史 | ✅ + ⚠️ | 技术可行,但配额未知(5k/日悲观情景需 3-4 天首拉) |
| A5 | 新浪实时报价 | ✅ | 20/20 成功,延迟 44ms;盘中动态价格待 S5 开工前补测 |
| A6 | SQLite 并发 | ✅ | write p95=1.5ms,无需 PostgreSQL;**禁用 StaticPool** |
| A7 | company 字段 | ⚠️ | `listingStatus` + `exchange` 替代 `is_st`/`board`;`prev_close` 走 K 线;申万行业待 S2 排查 |

### 🚨 新增 P0 修复项(S1 之前必做)

**Bug 1**:`get_company_list(page_size=5000)` 被 Lixinger 静默截到 500 → 系统只看到 500/5625 股(8.9%)。
修复:改为分页拉取循环。

**Bug 2**:`get_dividend` 不处理 Lixinger 强制 ≤10 年时间窗,超期 403。
修复:封装 `get_dividend_full()` 自动分段。

**Gotcha**:`poolclass=pool.StaticPool`(conftest.py 用)绝不能用于生产代码 — 单连接跨线程共享破坏事务隔离。在 `app/db/engine.py` 加注释。

### 计划修订

- **S1 之前**:修 2 个 P0 bug + 加 StaticPool 注释
- **S1 范围**:新增任务 S1.0(`Stock` 表用 `listing_status` + `exchange` 替代 `is_st`/`board`);工作量 4-5 天 → **5-6 天**
- **S2 调整**:板块识别用 `exchange + code prefix`;ST 用 `listing_status in (...)`;`prev_close` 每日 K 线同步;新增调研任务"申万 industry_sw 数据源"
- **S4A 调整**:**删除配股自动 alert**(无数据源),新增"退市检测 daily sync"(company list diff + profile historyStockNames)
- **S4B 简化**:`publish_date_resolver` 从估算改为直接读 `reportDate`;首拉分批 + checkpoint
- **S5 调整**:新浪主 + 腾讯 fallback;字段索引已确认
- **S6 不变**:SQLite WAL 验证完毕

---

## 阶段总览

| 阶段 | 名称 | 关键产出 | 工作量 | 阻塞关系 |
|---|---|---|---|---|
| **S0** | Spike 验证 | 7 个假设的验证报告 | 2-3 天 | 阻塞 S1-S6 |
| **S1** | 数据模型与资金基础 | `trades` / `cash_balance` / `cash_adjustments` / `broker_fee_configs` 表 + Holding 派生 + 数据迁移 | 4-5 天 | 阻塞 S2-S5 |
| **S2** | 执行约束(T+1 + sizing + 价格校验) | `available_quantity_at` / `position_sizing_service` / `price_validator_service` + Trade 录入 UI | 3-4 天 | 阻塞 S3 |
| **S3** | Lixinger 多层防御 + system_alerts | retry / circuit_breaker / data_freshness / data_sanity / system_alerts 表 + Cockpit 红条 | 2-3 天 | 独立 |
| **S4** | 公司行为 + 回测引擎 | `corp_actions` 表 + 应用器 + `backtest/` 模块 + `/backtest` 页面 | 10-12 天 | 与 S5 并行 |
| **S5** | 盘中监控 + 告警 + 止损 | `intraday_price_poll` job + `notification_channels` + `holding_risk_rules` + 新浪接口 | 4-5 天 | 依赖 S3 |
| **S6** | Docker + DR + 运维 | docker-compose.prod.yml / backup 容器 / healthcheck-probe / scheduler 心跳 | 2-3 天 | 依赖 S3 |

**总工作量**:27-35 工作日(约 6-7 周单人专注)

---

## Minimum Viable Production (MVP) 切片定义

如果需要分批上线,推荐的最小可用切片:

**MVP-1 (S0+S1+S2+S6 部分)** = "数据准确的生产系统":
- trades 表 + cash_balance + T+1 + 价格校验 + Docker 部署 + 每日备份
- 此时系统已经能用作"准确账本",但缺少风控自动化与回测
- 约 12-15 工作日

**MVP-2 (+S3+S5)** = "有风控的生产系统":
- 加 Lixinger 防御 + 盘中告警 + 止损 + 多通道推送
- 约 6-8 工作日

**MVP-3 (+S4)** = "可验证策略的系统":
- 加公司行为自动化 + 回测引擎
- 约 10-12 工作日

---

## Stage 0: Spike 验证(必做,2-3 天)

### 文件结构

```
backend/spikes/
├── __init__.py
├── spike_lixinger_corp_actions.py     # A1+A2: 公司行为 API 验证
├── spike_lixinger_publish_date.py     # A3: 财报 publish_date 字段验证
├── spike_lixinger_history_range.py    # A4: 历史数据时间范围验证
├── spike_sina_realtime.py             # A5: 新浪实时报价稳定性
├── spike_sqlite_concurrency.py        # A6: SQLite 并发压测
└── spike_lixinger_company_fields.py   # A7: company 接口字段验证
docs/reports/
└── spike-results-2026-06-xx.md        # 汇总报告
```

### Tasks

#### Task S0.1: Lixinger 公司行为 API 探针(A1+A2)

**Files:**
- Create: `backend/spikes/spike_lixinger_corp_actions.py`
- Output: `docs/reports/spike-results-2026-06-xx.md`(追加)

- [ ] **Step 1: 写探针脚本**

```python
# backend/spikes/spike_lixinger_corp_actions.py
"""Spike: verify Lixinger covers corp actions beyond cash dividends.

Tests:
- A1: 送股/转增 history (10送5 etc.)
- A2: 配股 (rights issues)
- A2: 退市 (delistings)
- A2: 代码变更 / 重组 (code changes / mergers)
"""
from app.services.lixinger_client import get_lixinger_client

# 已知历史案例:
#   - 600519 贵州茅台:历年高分红
#   - 000651 格力电器:2017 年 10转5 派现
#   - 600999 招商证券:2014 年配股
#   - 600432 吉恩镍业:2018 年退市
#   - 600001 邯郸钢铁:2008 年被吸收合并退市

SAMPLE_CASES = {
    "high_dividend": "600519",
    "stock_dividend": "000651",
    "rights_issue": "600999",
    "delisted": "600432",
    "merged": "600001",
}

def main():
    client = get_lixinger_client()
    results = {}

    # 1. dividend endpoint 通常含送转
    for label, code in SAMPLE_CASES.items():
        try:
            divs = client.get_dividend(code, "2010-01-01")
            results[label] = {
                "code": code,
                "dividend_records_count": len(divs),
                "sample_record_keys": list(divs[0].keys()) if divs else [],
                "has_stock_dividend_field": any(
                    "send" in str(r).lower() or "transfer" in str(r).lower() or "split" in str(r).lower()
                    for r in divs
                ),
            }
        except Exception as e:
            results[label] = {"error": str(e)}

    return results

if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=2, ensure_ascii=False, default=str))
```

- [ ] **Step 2: 运行探针**

```bash
cd backend && source .venv/bin/activate
python -m spikes.spike_lixinger_corp_actions
```

Expected: JSON 输出,确认 `has_stock_dividend_field=True`。

- [ ] **Step 3: 探针配股 / 退市 / 代码变更(可能需要查 Lixinger 文档)**

去 https://www.lixinger.com/api-docs 查询是否有 `rights-issue` / `delisting` / `code-change` 接口,记录到 spike 报告。

- [ ] **Step 4: 写结论到 `docs/reports/spike-results-2026-06-xx.md`**

模板:
```markdown
# Spike 结果汇总 (2026-06-xx)

## A1 送股/转增覆盖
- 接口: `/cn/company/dividend`
- 字段: `sd` (送股 per 10) / `zzs` (转增 per 10) / `pd` (派现 per 10)
- 覆盖度: ✅/❌

## A2 配股/退市/代码变更
- 接口: ❌(如无,需补充源)
- 备选方案: ...
```

- [ ] **Step 5: 提交**

```bash
git add backend/spikes/ docs/reports/spike-results-2026-06-xx.md
git commit -m "chore(spike): verify Lixinger corp action coverage"
```

#### Task S0.2: 财报 publish_date 字段验证(A3)

**Files:**
- Create: `backend/spikes/spike_lixinger_publish_date.py`
- Output: 追加到 spike 报告

- [ ] **Step 1: 探针脚本**

```python
# backend/spikes/spike_lixinger_publish_date.py
"""Verify Lixinger financial data exposes publish_date.

Critical for backtest point-in-time correctness.
"""
from app.services.lixinger_client import get_lixinger_client

def main():
    client = get_lixinger_client()
    fs = client.get_financials("600519", start_date="2023-01-01", end_date="2024-12-31")
    if not fs:
        return {"error": "no data"}
    return {
        "record_count": len(fs),
        "first_record_keys": sorted(fs[0].keys()),
        "has_publish_date": any("publish" in k.lower() or "disclose" in k.lower() for k in fs[0].keys()),
        "has_report_period": any("report" in k.lower() or "period" in k.lower() or "end_date" in k.lower() for k in fs[0].keys()),
        "sample_first_3_periods": [r.get("end_date") or r.get("report_date") for r in fs[:3]],
    }

if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=2, ensure_ascii=False, default=str))
```

- [ ] **Step 2: 运行 + 记录结论**

如果没有 publish_date:用 `report_period + 90d` 估算发布日(粗糙方案),或找 Lixinger 的"财报披露日"独立接口。

#### Task S0.3: 历史数据时间范围(A4)

**Files:** `backend/spikes/spike_lixinger_history_range.py`

- [ ] 探针:拉 600519 自 2010-01-01 至今的 K 线 + fundamentals,记录返回记录数、最早日期、是否截断。

#### Task S0.4: 新浪实时报价稳定性(A5)

**Files:** `backend/spikes/spike_sina_realtime.py`

- [ ] **Step 1: 探针脚本**

```python
# backend/spikes/spike_sina_realtime.py
"""Sina realtime quote spike."""
import requests
import time

HEADERS = {"Referer": "https://finance.sina.com.cn"}

def fetch(codes: list[str]) -> dict[str, dict]:
    """Format: sh600519,sz000001."""
    sina_codes = []
    for code in codes:
        if code.startswith(("6", "5", "9")):
            sina_codes.append(f"sh{code}")
        else:
            sina_codes.append(f"sz{code}")
    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    r = requests.get(url, headers=HEADERS)
    r.encoding = "gbk"
    lines = r.text.strip().split("\n")
    out = {}
    for line in lines:
        if "=" not in line:
            continue
        var, data = line.split("=", 1)
        code = var.split("_")[-1].rstrip(";").strip('"').lower()
        # data format: 名称,昨收,今收,现价,最高,最低,...
        parts = data.strip('"').split(",")
        if len(parts) > 3:
            out[code[2:]] = {
                "name": parts[0],
                "prev_close": float(parts[2]),
                "current": float(parts[3]),
                "high": float(parts[4]),
                "low": float(parts[5]),
            }
    return out

if __name__ == "__main__":
    codes = ["600519", "000001", "300750", "688981"]
    for i in range(20):
        result = fetch(codes)
        print(f"[{i+1}/20]", result)
        time.sleep(15)  # 15秒一次,跑5分钟
```

- [ ] **Step 2: 跑 5 分钟,观察稳定性**

Expected: 20 次调用全部成功,无 429 / 无字段错位。

- [ ] **Step 3: 如果失败,切腾讯 `qt.gtimg.cn`,重跑**

#### Task S0.5: SQLite 并发压测(A6)

**Files:** `backend/spikes/spike_sqlite_concurrency.py`

- [ ] **Step 1: 压测脚本**

```python
# backend/spikes/spike_sqlite_concurrency.py
"""Simulate intraday polling write load: 1 writer + 5 readers, 5 min."""
import threading
import time
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_PATH = "/tmp/spike_concurrency.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

engine = create_engine(f"sqlite:///{DB_PATH}",
                      connect_args={"check_same_thread": False},
                      poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool)
# 启用 WAL
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.execute(text("PRAGMA busy_timeout=5000"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, val REAL, ts TEXT)"))

Session = sessionmaker(bind=engine)
errors = []
counts = {"writes": 0, "reads": 0}

def writer():
    from datetime import datetime
    for i in range(300):
        try:
            with Session() as s:
                s.execute(text("INSERT INTO test (val, ts) VALUES (:v, :t)"),
                         {"v": i * 0.1, "t": datetime.utcnow().isoformat()})
                s.commit()
            counts["writes"] += 1
        except Exception as e:
            errors.append(("write", str(e)))
        time.sleep(1)

def reader(idx: int):
    for i in range(600):
        try:
            with Session() as s:
                r = s.execute(text("SELECT COUNT(*) FROM test")).scalar()
            counts["reads"] += 1
        except Exception as e:
            errors.append((f"read{idx}", str(e)))
        time.sleep(0.5)

threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader, args=(i,)) for i in range(5)]
for t in threads: t.start()
for t in threads: t.join()

print(f"Result: writes={counts['writes']}, reads={counts['reads']}, errors={len(errors)}")
if errors:
    print(f"Sample errors: {errors[:5]}")
```

- [ ] **Step 2: 跑 5 分钟**

Expected: writes=300, reads=3000, errors=0。如果 errors > 0,WAL+busy_timeout 不够,需考虑 PostgreSQL。

#### Task S0.6: Lixinger company 接口字段(A7)

**Files:** `backend/spikes/spike_lixinger_company_fields.py`

- [ ] 探针:调 `/cn/company` 看 response 是否含 `trade_status` / `board` / `is_st` / `industry_sw`。

#### Task S0.7: 汇总报告

- [ ] **把 6 个探针结果汇总到 `docs/reports/spike-results-2026-06-xx.md`,每项给 ✅/⚠️/❌ 评级 + 影响 + 降级方案。**

- [ ] **若任一 ❌,先在文档里调整对应阶段的设计,再开始 S1。**

---

## Stage 1: trades 流水表 + 资金模型 + 成本计算(4-5 天)

### 文件结构

```
backend/app/models/
├── trade.py                    # 新增 — 成交流水事件源
├── cash_balance.py             # 新增 — 资金余额(单例)
├── cash_adjustment.py          # 新增 — 出入金流水
├── broker_fee_config.py        # 新增 — 券商费率配置
└── holding.py                  # 修改 — 改为派生视图字段
backend/app/services/
├── trade_service.py            # 新增 — 写入 trade + 现金更新原子
├── holding_view_service.py     # 新增 — 从 trades 派生 holding
├── fee_calculator_service.py   # 新增 — 佣金/印花税/过户费
└── capital_service.py          # 新增 — NAV 计算
backend/app/routers/
├── trades.py                   # 新增 — trades CRUD
├── cash.py                     # 新增 — cash_balance / adjustments
└── fee_configs.py              # 新增 — broker_fee_configs CRUD
backend/app/schemas/
├── trade.py
├── cash.py
└── fee_config.py
backend/alembic/versions/
├── o5p6q7r8s9t0_add_trades_table.py
├── p6q7r8s9t0u1_add_cash_balance_table.py
├── q7r8s9t0u1v2_add_broker_fee_configs.py
└── r8s9t0u1v2w3_migrate_holdings_to_trades.py
backend/app/services/
└── migrations/
    └── holding_to_trades_migrator.py   # 一次性迁移脚本
backend/tests/
├── test_trade_service.py
├── test_fee_calculator.py
├── test_holding_view.py
└── test_holding_migration.py
frontend/src/pages/
└── TradesPage.tsx              # 新增 — 成交流水 + 录入入口
frontend/src/components/
└── TradeEntryModal.tsx         # 新增 — 手动录入表单
```

### Tasks

#### Task S1.1: Trade 模型 + Alembic 迁移

**Files:**
- Create: `backend/app/models/trade.py`
- Create: `backend/alembic/versions/o5p6q7r8s9t0_add_trades_table.py`
- Test: `backend/tests/test_trade_model.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_trade_model.py
from datetime import datetime
from app.models.trade import Trade


def test_trade_create(db_session):
    t = Trade(
        stock_code="600519",
        side="BUY",
        price=1680.0,
        quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 30),
        commission=4.2,
        stamp_duty=0.0,
        transfer_fee=0.17,
        total_value=168004.37,
        source="manual",
    )
    db_session.add(t)
    db_session.commit()
    assert t.id is not None
    assert t.created_at is not None
    assert t.reversed_by_trade_id is None
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
pytest backend/tests/test_trade_model.py -v
```

Expected: ImportError,模块不存在。

- [ ] **Step 3: 实现 Trade 模型**

```python
# backend/app/models/trade.py
"""Trade model — immutable event source for all position changes.

A trade is a fact: at `filled_at`, N shares of `stock_code` were bought/sold
at `price`, incurring `commission + stamp_duty + transfer_fee`.

Trades are NEVER updated or deleted. To reverse a trade, create a new trade
of the opposite side with `reversed_by_trade_id` pointing back.
"""
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String, nullable=False, index=True)
    """BUY | SELL | DIVIDEND (cash inflow) | CORP_ACTION (quantity change)"""

    price: Mapped[float] = mapped_column(Float, nullable=False)
    """Per-share price. 0 for corp_action / dividend."""
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    """Signed: +N for incoming, -N for outgoing. BUY=+, SELL=-, DIVIDEND=0."""

    filled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    """Trade execution time, Asia/Shanghai (stored as naive datetime)."""

    commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stamp_duty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    transfer_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    """Net cash impact: BUY=+(price*qty + fees), SELL=-(price*qty - fees), DIVIDEND=-(cash)."""

    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    """manual | csv_import | broker_api | corp_action | migration | reversal"""
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    """Draft ID / corp_action ID / migration batch ID."""

    fee_source: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    """auto | manual_override"""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reversed_by_trade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trades.id"), nullable=True
    )
    """If set, this trade was reversed by the referenced trade."""

    __table_args__ = (
        Index("ix_trades_code_filled", "stock_code", "filled_at"),
        Index("ix_trades_source", "source"),
    )
```

- [ ] **Step 4: 写 Alembic 迁移**

```python
# backend/alembic/versions/o5p6q7r8s9t0_add_trades_table.py
"""add trades table

Revision ID: o5p6q7r8s9t0
Revises: 3c5b80889c29
Create Date: 2026-06-12 10:00:00
"""
revision = "o5p6q7r8s9t0"
down_revision = "3c5b80889c29"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stock_code", sa.String, sa.ForeignKey("stocks.code"), nullable=False),
        sa.Column("side", sa.String, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("filled_at", sa.DateTime, nullable=False),
        sa.Column("commission", sa.Float, nullable=False, server_default="0"),
        sa.Column("stamp_duty", sa.Float, nullable=False, server_default="0"),
        sa.Column("transfer_fee", sa.Float, nullable=False, server_default="0"),
        sa.Column("total_value", sa.Float, nullable=False),
        sa.Column("source", sa.String, nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String, nullable=True),
        sa.Column("fee_source", sa.String, nullable=False, server_default="auto"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("reversed_by_trade_id", sa.Integer,
                  sa.ForeignKey("trades.id"), nullable=True),
    )
    op.create_index("ix_trades_code_filled", "trades", ["stock_code", "filled_at"])
    op.create_index("ix_trades_source", "trades", ["source"])
    op.create_index("ix_trades_side", "trades", ["side"])


def downgrade():
    op.drop_table("trades")
```

- [ ] **Step 5: 跑测试**

```bash
pytest backend/tests/test_trade_model.py -v
```

Expected: PASS。

- [ ] **Step 6: 应用迁移**

```bash
cd backend && source .venv/bin/activate
alembic upgrade head
```

- [ ] **Step 7: 提交**

```bash
git add backend/app/models/trade.py backend/alembic/versions/o5p6q7r8s9t0_add_trades_table.py backend/tests/test_trade_model.py
git commit -m "feat(trades): add Trade model as event source"
```

#### Task S1.2: cash_balance + cash_adjustments 模型

**Files:**
- Create: `backend/app/models/cash_balance.py`
- Create: `backend/app/models/cash_adjustment.py`
- Create: `backend/alembic/versions/p6q7r8s9t0u1_add_cash_balance_table.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_cash_balance.py
from datetime import datetime
from app.models.cash_balance import CashBalance
from app.models.cash_adjustment import CashAdjustment


def test_cash_balance_singleton(db_session):
    cb = CashBalance(balance=100000.0)
    db_session.add(cb)
    db_session.commit()
    assert cb.id == 1
    assert cb.balance == 100000.0


def test_cash_adjustment_deposit(db_session):
    adj = CashAdjustment(
        amount=50000.0,
        happened_at=datetime(2026, 6, 12, 9, 0),
        reason="deposit",
        note="月度入金",
    )
    db_session.add(adj)
    db_session.commit()
    assert adj.id is not None
```

- [ ] **Step 2: 跑测试,确认失败**

- [ ] **Step 3: 实现两个模型**

```python
# backend/app/models/cash_balance.py
"""Cash balance — singleton row, updated atomically with each trade."""
from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CashBalance(Base):
    __tablename__ = "cash_balance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    as_of_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_trade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_adjustment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

```python
# backend/app/models/cash_adjustment.py
"""Cash adjustment — deposit / withdrawal / other non-trade cash flows."""
from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CashAdjustment(Base):
    __tablename__ = "cash_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    """+: deposit / dividend cash. -: withdrawal."""
    happened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    """deposit | withdrawal | dividend | other"""
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Alembic 迁移 + 跑测试 + 提交**(同 S1.1 模式)

#### Task S1.3: broker_fee_configs 模型 + seeder

**Files:**
- Create: `backend/app/models/broker_fee_config.py`
- Create: `backend/alembic/versions/q7r8s9t0u1v2_add_broker_fee_configs.py`
- Modify: `backend/app/services/builtin_seeder.py` — 启动时插入默认配置

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_broker_fee_config.py
from app.models.broker_fee_config import BrokerFeeConfig


def test_default_config(db_session):
    cfg = BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.00025,
        commission_min=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        effective_from="2023-10-23",
        is_active=True,
    )
    db_session.add(cfg)
    db_session.commit()
    assert cfg.id is not None
```

- [ ] **Step 2: 实现模型**

```python
# backend/app/models/broker_fee_config.py
"""Broker fee configuration — supports historical rate changes."""
from datetime import date
from sqlalchemy import Boolean, Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BrokerFeeConfig(Base):
    __tablename__ = "broker_fee_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    commission_rate: Mapped[float] = mapped_column(Float, nullable=False)
    commission_min: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    stamp_duty_rate: Mapped[float] = mapped_column(Float, nullable=False)
    transfer_fee_rate: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

- [ ] **Step 3: 在 builtin_seeder.py 添加默认配置**

```python
# backend/app/services/builtin_seeder.py(在 seed_builtin_strategies 之前添加)
from datetime import date
from app.models.broker_fee_config import BrokerFeeConfig

def seed_default_fee_config(db):
    existing = db.query(BrokerFeeConfig).filter_by(broker_name="default").first()
    if existing:
        return
    db.add(BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.00025,
        commission_min=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23),  # 现行印花税率生效日
        is_active=True,
    ))
    db.flush()
```

- [ ] **Step 4: 迁移 + seeder 接入 main.py + 测试 + 提交**

#### Task S1.4: fee_calculator_service

**Files:**
- Create: `backend/app/services/fee_calculator_service.py`
- Test: `backend/tests/test_fee_calculator.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_fee_calculator.py
from datetime import date
import pytest

from app.services.fee_calculator_service import compute_fees, FeeBreakdown
from app.models.broker_fee_config import BrokerFeeConfig


@pytest.fixture
def cfg(db_session):
    c = BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.00025,
        commission_min=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23),
        is_active=True,
    )
    db_session.add(c); db_session.flush()
    return c


def test_buy_fees(cfg):
    # 1680 元 × 100 股 = 168000 元
    # 佣金 = max(168000 × 0.00025, 5) = 42
    # 印花税 = 0(买方不收)
    # 过户费 = 168000 × 0.00001 = 1.68
    fees = compute_fees(side="BUY", price=1680.0, quantity=100, broker_config=cfg)
    assert fees.commission == 42.0
    assert fees.stamp_duty == 0.0
    assert fees.transfer_fee == pytest.approx(1.68, abs=0.01)


def test_sell_fees(cfg):
    # 卖出:佣金 + 印花税 + 过户费
    fees = compute_fees(side="SELL", price=1680.0, quantity=100, broker_config=cfg)
    assert fees.commission == 42.0
    assert fees.stamp_duty == pytest.approx(84.0, abs=0.01)  # 168000 × 0.0005
    assert fees.transfer_fee == pytest.approx(1.68, abs=0.01)


def test_min_commission_kicks_in(cfg):
    # 小单触发最低消费:1680 × 1 = 1680 元,佣金 = max(0.42, 5) = 5
    fees = compute_fees(side="BUY", price=1680.0, quantity=1, broker_config=cfg)
    assert fees.commission == 5.0


def test_total_value_buy(cfg):
    fees = compute_fees(side="BUY", price=1680.0, quantity=100, broker_config=cfg)
    # BUY: total_value = price*qty + commission + transfer_fee = 168000 + 42 + 1.68
    assert fees.total_value(side="BUY") == pytest.approx(168043.68, abs=0.01)


def test_total_value_sell(cfg):
    fees = compute_fees(side="SELL", price=1680.0, quantity=100, broker_config=cfg)
    # SELL: total_value = price*qty - commission - stamp_duty - transfer_fee
    assert fees.total_value(side="SELL") == pytest.approx(167872.32, abs=0.01)
```

- [ ] **Step 2: 实现**

```python
# backend/app/services/fee_calculator_service.py
"""Fee calculator — commission / stamp duty / transfer fee."""
from dataclasses import dataclass
from app.models.broker_fee_config import BrokerFeeConfig


@dataclass(frozen=True)
class FeeBreakdown:
    commission: float
    stamp_duty: float
    transfer_fee: float

    def total_value(self, side: str) -> float:
        """Net cash impact: BUY adds cost, SELL subtracts income."""
        notional_component = 0  # set by caller
        # Placeholder — actual price*qty computed in compute_fees and stored
        raise NotImplementedError  # replaced below


def compute_fees(
    side: str,
    price: float,
    quantity: int,
    broker_config: BrokerFeeConfig,
) -> "_FeeBreakdownWithNotional":
    notional = price * quantity
    commission = max(notional * broker_config.commission_rate,
                     broker_config.commission_min)
    stamp_duty = (notional * broker_config.stamp_duty_rate
                  if side == "SELL" else 0.0)
    transfer_fee = notional * broker_config.transfer_fee_rate
    return _FeeBreakdownWithNotional(
        commission=commission,
        stamp_duty=stamp_duty,
        transfer_fee=transfer_fee,
        notional=notional,
        side=side,
    )


@dataclass(frozen=True)
class _FeeBreakdownWithNotional:
    commission: float
    stamp_duty: float
    transfer_fee: float
    notional: float
    side: str

    def total_value(self, side: str | None = None) -> float:
        side = side or self.side
        fees = self.commission + self.stamp_duty + self.transfer_fee
        if side == "BUY":
            return self.notional + fees
        elif side == "SELL":
            return self.notional - fees
        elif side == "DIVIDEND":
            return -self.notional  # cash inflow
        else:
            return 0.0
```

(注:测试用 `FeeBreakdown`,实际实现返回带 notional 的子类。**让测试与实现匹配**:简化为单一类即可,见 step 3 修正)

- [ ] **Step 3: 修正实现(简化为单一 dataclass)**

```python
# backend/app/services/fee_calculator_service.py
from dataclasses import dataclass
from app.models.broker_fee_config import BrokerFeeConfig


@dataclass(frozen=True)
class FeeBreakdown:
    commission: float
    stamp_duty: float
    transfer_fee: float
    notional: float
    side: str

    def total_value(self, side: str | None = None) -> float:
        side = side or self.side
        fees = self.commission + self.stamp_duty + self.transfer_fee
        if side == "BUY":
            return self.notional + fees
        elif side == "SELL":
            return self.notional - fees
        elif side == "DIVIDEND":
            return -self.notional
        return 0.0


def compute_fees(side: str, price: float, quantity: int,
                 broker_config: BrokerFeeConfig) -> FeeBreakdown:
    notional = price * quantity
    return FeeBreakdown(
        commission=max(notional * broker_config.commission_rate,
                       broker_config.commission_min),
        stamp_duty=(notional * broker_config.stamp_duty_rate
                    if side == "SELL" else 0.0),
        transfer_fee=notional * broker_config.transfer_fee_rate,
        notional=notional,
        side=side,
    )
```

- [ ] **Step 4: 测试 + 提交**

#### Task S1.5: trade_service(原子写入 + cash 更新)

**Files:**
- Create: `backend/app/services/trade_service.py`
- Test: `backend/tests/test_trade_service.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_trade_service.py
from datetime import datetime
import pytest

from app.services.trade_service import record_trade, InsufficientBalanceError
from app.models.cash_balance import CashBalance
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.stock import Stock


@pytest.fixture
def setup_data(db_session):
    # 初始现金 20 万 + 一只股票 + 默认费率
    db_session.add(CashBalance(id=1, balance=200000.0))
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="SH"))
    from datetime import date
    cfg = BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    )
    db_session.add(cfg)
    db_session.flush()
    return cfg


def test_record_buy_updates_cash(db_session, setup_data):
    trade = record_trade(
        db_session,
        stock_code="600519",
        side="BUY",
        price=1680.0,
        quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 30),
        source="manual",
    )
    assert trade.id is not None
    assert trade.total_value == pytest.approx(168043.68, abs=0.01)
    cb = db_session.query(CashBalance).first()
    assert cb.balance == pytest.approx(200000 - 168043.68, abs=0.01)


def test_record_sell_updates_cash(db_session, setup_data):
    # 先买入建仓
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=1680.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 10, 30), source="manual")
    # 再卖出
    trade = record_trade(db_session, stock_code="600519", side="SELL",
                         price=1700.0, quantity=100,
                         filled_at=datetime(2026, 6, 12, 10, 30), source="manual")
    cb = db_session.query(CashBalance).first()
    # 200000 - 168043.68 (buy) + 169828.32 (sell after fees)
    assert cb.balance == pytest.approx(200000 - 168043.68 + 169828.32, abs=0.5)


def test_buy_exceeding_cash_raises(db_session, setup_data):
    # 现金 20 万,试图买 200 股 × 1680 = 33.6 万
    with pytest.raises(InsufficientBalanceError):
        record_trade(db_session, stock_code="600519", side="BUY",
                     price=1680.0, quantity=200,
                     filled_at=datetime(2026, 6, 12, 10, 30), source="manual")
```

- [ ] **Step 2: 实现**

```python
# backend/app/services/trade_service.py
"""Trade service — atomic write + cash balance update."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.trade import Trade
from app.services.fee_calculator_service import compute_fees


class InsufficientBalanceError(HTTPException):
    def __init__(self, required: float, available: float):
        super().__init__(status_code=400,
                        detail=f"Insufficient cash: need {required}, have {available}")


def _get_active_fee_config(db: Session, filled_at: datetime) -> BrokerFeeConfig:
    cfg = db.execute(
        select(BrokerFeeConfig)
        .where(BrokerFeeConfig.is_active == True,
               BrokerFeeConfig.effective_from <= filled_at.date())
        .order_by(BrokerFeeConfig.effective_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not cfg:
        raise HTTPException(500, "No active broker fee config")
    return cfg


def _ensure_cash_balance_row(db: Session) -> CashBalance:
    cb = db.query(CashBalance).first()
    if not cb:
        cb = CashBalance(id=1, balance=0.0)
        db.add(cb)
        db.flush()
    return cb


def record_trade(
    db: Session,
    *,
    stock_code: str,
    side: str,
    price: float,
    quantity: int,
    filled_at: datetime,
    source: str = "manual",
    source_ref: str | None = None,
    fee_config: BrokerFeeConfig | None = None,
    commission_override: float | None = None,
    note: str | None = None,
) -> Trade:
    """Atomically write a trade and update cash balance.

    For BUY: checks cash sufficient before writing.
    For SELL: T+1 check happens in S2 (Task S2.1).
    """
    cfg = fee_config or _get_active_fee_config(db, filled_at)
    fees = compute_fees(side=side, price=price, quantity=quantity, broker_config=cfg)
    commission = commission_override if commission_override is not None else fees.commission
    total_value = fees.notional + commission + fees.stamp_duty + fees.transfer_fee
    if side == "SELL":
        total_value = fees.notional - commission - fees.stamp_duty - fees.transfer_fee
    elif side == "DIVIDEND":
        total_value = -fees.notional

    cb = _ensure_cash_balance_row(db)

    if side == "BUY":
        if cb.balance < total_value:
            raise InsufficientBalanceError(required=total_value, available=cb.balance)

    signed_qty = quantity if side in ("BUY", "CORP_ACTION_ADD") else (-quantity if side == "SELL" else 0)

    trade = Trade(
        stock_code=stock_code,
        side=side,
        price=price,
        quantity=signed_qty,
        filled_at=filled_at,
        commission=commission,
        stamp_duty=fees.stamp_duty,
        transfer_fee=fees.transfer_fee,
        total_value=total_value,
        source=source,
        source_ref=source_ref,
        fee_source="manual_override" if commission_override is not None else "auto",
        note=note,
    )
    db.add(trade)
    db.flush()

    if side == "BUY":
        cb.balance -= total_value
    elif side == "SELL":
        cb.balance += total_value
    elif side == "DIVIDEND":
        cb.balance += -total_value  # total_value is negative for DIVIDEND
    cb.last_trade_id = trade.id
    cb.as_of_at = datetime.utcnow()
    db.flush()
    return trade
```

- [ ] **Step 3: 测试 + 提交**

#### Task S1.6: holding_view_service(从 trades 派生)

**Files:**
- Create: `backend/app/services/holding_view_service.py`
- Test: `backend/tests/test_holding_view.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_holding_view.py
from datetime import datetime
from app.services.trade_service import record_trade
from app.services.holding_view_service import get_holding_view


def test_empty(db_session):
    holdings = get_holding_view(db_session)
    assert holdings == []


def test_single_buy(db_session, setup_stock_and_cash):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=200,
                 filled_at=datetime(2026, 6, 11, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    assert len(holdings) == 1
    h = holdings[0]
    assert h["stock_code"] == "600519"
    assert h["total_quantity"] == 200
    assert h["avg_cost_basis"] == pytest.approx(100.0, abs=0.01)


def test_avg_cost_after_multiple_buys(db_session, setup_stock_and_cash):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=120.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    h = holdings[0]
    assert h["total_quantity"] == 200
    # 加权平均 = (100*100 + 120*100 + fees) / 200
    # 简化:用 total_value / qty
    assert 100 < h["avg_cost_basis"] < 120


def test_partial_sell(db_session, setup_stock_and_cash):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=200,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="SELL",
                 price=110.0, quantity=100,
                 filled_at=datetime(2026, 6, 12, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    assert holdings[0]["total_quantity"] == 100
```

- [ ] **Step 2: 实现**

```python
# backend/app/services/holding_view_service.py
"""Holding view — derived from trades (single source of truth)."""
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.trade import Trade


def get_holding_view(db: Session, as_of: datetime | None = None) -> list[dict]:
    """Return current open positions aggregated from trades."""
    q = (
        select(
            Trade.stock_code,
            func.sum(Trade.quantity).label("total_quantity"),
            func.sum(Trade.total_value).label("total_cost"),
            func.min(Trade.filled_at).label("first_buy_at"),
            func.max(Trade.filled_at).label("last_trade_at"),
        )
        .where(Trade.reversed_by_trade_id.is_(None))
        .group_by(Trade.stock_code)
    )
    if as_of:
        q = q.where(Trade.filled_at <= as_of)

    rows = db.execute(q).all()
    result = []
    for r in rows:
        qty = r.total_quantity or 0
        if qty <= 0:
            continue  # closed position
        total_cost = r.total_cost or 0
        # For DIVIDEND trades, quantity=0 but total_value is negative (cash inflow).
        # We want avg_cost_basis = (cash spent on buys) / quantity.
        # Sells reduce quantity but their total_value is positive cash (income).
        # Simplified: avg_cost_basis = sum(total_value of BUY trades) / total_buy_qty
        # For now, use a rough approximation:
        buy_only_q = (
            select(func.sum(Trade.total_value), func.sum(Trade.quantity))
            .where(Trade.stock_code == r.stock_code,
                   Trade.side == "BUY",
                   Trade.reversed_by_trade_id.is_(None))
        )
        if as_of:
            buy_only_q = buy_only_q.where(Trade.filled_at <= as_of)
        buy_row = db.execute(buy_only_q).one()
        buy_cost = buy_row[0] or 0
        buy_qty = buy_row[1] or 0
        avg_cost = buy_cost / buy_qty if buy_qty > 0 else 0
        result.append({
            "stock_code": r.stock_code,
            "total_quantity": qty,
            "avg_cost_basis": avg_cost,
            "first_buy_at": r.first_buy_at,
            "last_trade_at": r.last_trade_at,
        })
    return result


def available_quantity_at(db: Session, stock_code: str, moment: datetime) -> int:
    """T+1: shares bought on `moment.date()` are frozen until next day."""
    today = moment.date()
    buys_before = db.execute(
        select(func.sum(Trade.quantity))
        .where(Trade.stock_code == stock_code,
               Trade.side == "BUY",
               Trade.filled_at < datetime.combine(today, datetime.min.time()),
               Trade.reversed_by_trade_id.is_(None))
    ).scalar() or 0
    sells_before = db.execute(
        select(func.sum(Trade.quantity))  # quantity is negative for SELL
        .where(Trade.stock_code == stock_code,
               Trade.side == "SELL",
               Trade.filled_at < datetime.combine(today, datetime.min.time()),
               Trade.reversed_by_trade_id.is_(None))
    ).scalar() or 0
    # sells_before is negative, so subtract to reduce
    return buys_before + sells_before  # since SELL quantity is negative
```

- [ ] **Step 3: 测试 + 提交**

#### Task S1.7: 数据迁移脚本(现有 Holding → trades)

**Files:**
- Create: `backend/app/services/migrations/holding_to_trades_migrator.py`
- Create: `backend/alembic/versions/r8s9t0u1v2w3_migrate_holdings_to_trades.py`
- Test: `backend/tests/test_holding_migration.py`

- [ ] **Step 1: 写迁移逻辑测试**

```python
# backend/tests/test_holding_migration.py
from datetime import date
from app.models.holding import Holding
from app.models.stock import Stock
from app.services.migrations.holding_to_trades_migrator import migrate_holdings_to_trades
from app.services.holding_view_service import get_holding_view


def test_migration_creates_trades(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="SH"))
    db_session.add(Holding(
        stock_code="600519",
        buy_date=date(2026, 1, 15),
        buy_price=1680.0,
        quantity=100,
        stop_profit_price=2184.0,
    ))
    db_session.flush()

    migrate_holdings_to_trades(db_session)

    holdings = get_holding_view(db_session)
    assert len(holdings) == 1
    assert holdings[0]["stock_code"] == "600519"
    assert holdings[0]["total_quantity"] == 100
    assert holdings[0]["avg_cost_basis"] == 1680.0
```

- [ ] **Step 2: 实现迁移器**

```python
# backend/app/services/migrations/__init__.py
# (空)
```

```python
# backend/app/services/migrations/holding_to_trades_migrator.py
"""One-shot migrator: existing Holding rows → opening Trade events."""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.trade import Trade


def migrate_holdings_to_trades(db: Session, batch_id: str = "migration_2026_06_12") -> int:
    """Convert each open Holding to a Trade(source='migration').

    Only open positions (sell_date IS NULL) are migrated. Closed historical
    holdings are skipped — they were already P&L realized.
    """
    open_holdings = db.execute(
        select(Holding).where(Holding.sell_date.is_(None))
    ).scalars().all()

    count = 0
    for h in open_holdings:
        existing = db.execute(
            select(Trade).where(
                Trade.stock_code == h.stock_code,
                Trade.source == "migration",
                Trade.source_ref == f"{batch_id}:{h.id}",
            )
        ).scalar_one_or_none()
        if existing:
            continue  # idempotent

        trade = Trade(
            stock_code=h.stock_code,
            side="BUY",
            price=h.buy_price,
            quantity=h.quantity,
            filled_at=datetime.combine(h.buy_date, datetime.min.time()),
            commission=0.0,
            stamp_duty=0.0,
            transfer_fee=0.0,
            total_value=h.buy_price * h.quantity,
            source="migration",
            source_ref=f"{batch_id}:{h.id}",
            note=f"Migrated from Holding#{h.id}",
        )
        db.add(trade)
        count += 1

    db.flush()
    return count
```

- [ ] **Step 3: Alembic data migration(在 schema migration 后跑数据迁移)**

```python
# backend/alembic/versions/r8s9t0u1v2w3_migrate_holdings_to_trades.py
"""migrate existing holdings to trades

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
"""
revision = "r8s9t0u1v2w3"
down_revision = "q7r8s9t0u1v2"

from alembic import op


def upgrade():
    from app.db.session import SessionLocal
    from app.services.migrations.holding_to_trades_migrator import migrate_holdings_to_trades
    db = SessionLocal()
    try:
        count = migrate_holdings_to_trades(db)
        print(f"Migrated {count} open holdings to trades")
        db.commit()
    finally:
        db.close()


def downgrade():
    # 不可逆数据迁移
    pass
```

- [ ] **Step 4: 在本地 dev DB 跑迁移 + 验证 + 提交**

```bash
cd backend && source .venv/bin/activate
alembic upgrade head
# 启动应用确认 Cockpit 仍显示持仓
./dev.sh  # 手动验证
```

#### Task S1.8: API 路由(trades / cash / fee_configs)

**Files:**
- Create: `backend/app/routers/trades.py`
- Create: `backend/app/routers/cash.py`
- Create: `backend/app/routers/fee_configs.py`
- Create: `backend/app/schemas/trade.py` / `cash.py` / `fee_config.py`
- Modify: `backend/app/main.py` 注册新路由

- [ ] **Step 1: 写 schemas**

(参考现有 `backend/app/schemas/plan.py` 的风格,实现 TradeCreate / TradeResponse / CashBalanceResponse / CashAdjustmentCreate / BrokerFeeConfigCreate / BrokerFeeConfigResponse)

- [ ] **Step 2: 写 routers(标准 CRUD + record_trade 端点)**

```python
# backend/app/routers/trades.py 关键端点:
POST   /api/trades                 # 手动录入成交
GET    /api/trades                 # 流水列表(过滤 code/side/source/date_range)
GET    /api/trades/{id}            # 详情
POST   /api/trades/{id}/reverse    # 红冲(生成反向 trade)
```

- [ ] **Step 3: 测试 API + 提交**

#### Task S1.9: 前端 TradeEntryModal + TradesPage

**Files:**
- Create: `frontend/src/components/TradeEntryModal.tsx`
- Create: `frontend/src/pages/TradesPage.tsx`
- Modify: `frontend/src/api/client.ts` 添加 trade API 函数
- Modify: `frontend/src/App.tsx` 添加路由 `/trades`
- Modify: `frontend/src/components/Layout.tsx` 添加菜单项

- [ ] **Step 1: 在 client.ts 添加 API 函数**

```typescript
// frontend/src/api/client.ts 追加
export const tradesApi = {
  list: (params?: { code?: string; side?: string; limit?: number }) =>
    client.get('/trades', { params }).then(r => r.data),
  create: (data: TradeCreate) => client.post('/trades', data).then(r => r.data),
  reverse: (id: number) => client.post(`/trades/${id}/reverse`).then(r => r.data),
};

export const cashApi = {
  getBalance: () => client.get('/cash/balance').then(r => r.data),
  listAdjustments: () => client.get('/cash/adjustments').then(r => r.data),
  createAdjustment: (data: CashAdjustmentCreate) =>
    client.post('/cash/adjustments', data).then(r => r.data),
};
```

- [ ] **Step 2: 实现 TradeEntryModal**

(参考现有 `frontend/src/components/QiuScorerWizard.tsx` 的表单风格。表单字段顺序:`filled_at → stock_code → side → price → quantity → [auto-computed: commission/stamp_duty/transfer_fee/total_value] → [可改: commission_override] → note`)

- [ ] **Step 3: 实现 TradesPage**

(Ant Design Table + 顶部"录入成交"按钮 + 时间倒序 + 过滤器)

- [ ] **Step 4: 浏览器手测 + 提交**

```bash
./dev.sh
# 浏览器打开 http://localhost:3000/trades
# 录入 1 笔 BUY + 1 笔 SELL
# 验证 Cockpit 的现金余额正确变化
```

#### Task S1.10: position_advisor 切换到 holding_view_service

**Files:**
- Modify: `backend/app/services/position_advisor_service.py`

- [ ] **Step 1: 改 `_open_holdings` / `_industry_weights` 用 `holding_view_service.get_holding_view`**

- [ ] **Step 2: 跑全部测试 + 提交**

---

## Stage 2: 执行约束(T+1 + sizing + 价格校验)(3-4 天)

### 文件结构

```
backend/app/models/
└── stock.py                          # 修改 — 加 board / is_st / is_suspended / prev_close / suspended_until
backend/app/services/
├── position_sizing_service.py        # 新增
├── price_validator_service.py        # 新增
└── plan_runner.py                    # 修改 — SELL 评估加 T+1 检查 + 跳过停牌
backend/alembic/versions/
└── s9t0u1v2w3x4_add_stock_trading_fields.py
frontend/src/components/
└── TradeEntryModal.tsx               # 修改 — 加价格校验显示
```

### Tasks(任务清单,每个 TDD 详细度参考 S1)

#### Task S2.1: Stock 表加交易字段

字段:`board`(main/chinext/star/bjse) / `is_st`(bool) / `is_suspended`(bool) / `suspended_until`(date) / `prev_close`(float)

- 写测试 → 改 model → Alembic 迁移 → stocks_sync_service 同步时解析这些字段 → 提交

#### Task S2.2: price_validator_service

```python
def price_band(stock: Stock) -> tuple[float, float]:
    """Return (lower_limit, upper_limit) based on board + ST."""
    limit = 0.05 if stock.is_st else {
        "main": 0.10, "chinext": 0.20, "star": 0.20, "bjse": 0.30
    }.get(stock.board, 0.10)
    return (stock.prev_close * (1 - limit), stock.prev_close * (1 + limit))

def assert_tradable(stock: Stock, price: float, filled_at: date) -> None:
    """Raise if suspended or price out of band (unless new listing)."""
    ...
```

测试覆盖:主板 ±10%、ST ±5%、创业板 ±20%、停牌拒绝、新股首日跳过、新股次日恢复。

#### Task S2.3: trade_service 接入 T+1 + 价格校验

在 `record_trade` 中:
- SELL:调 `available_quantity_at(filled_at)` 校验
- BUY/SELL:调 `assert_tradable` 校验价格(可被 `force=True` 覆盖,记 audit)

#### Task S2.4: position_sizing_service

```python
def compute_buy_quantity(
    capital_base: float, target_pct: float, current_price: float,
    available_cash: float, lot_size: int = 100,
) -> BuyQuantityResult:
    raw_cash = capital_base * target_pct
    raw_qty = int(raw_cash // current_price)
    rounded = (raw_qty // lot_size) * lot_size
    # 二次校验:加完佣金不超现金
    commission = max(rounded * current_price * 0.00025, 5.0)
    if rounded * current_price + commission > available_cash:
        rounded -= lot_size
    return BuyQuantityResult(quantity=max(0, rounded), estimated_cost=..., ...)
```

#### Task S2.5: plan_runner 改造

- 评估 SELL 规则前先查 `available_quantity_at(now)`,为 0 跳过该股
- 扫描时跳过 `is_suspended=True`
- 生成 draft 时填 `suggested_quantity`(新字段)

#### Task S2.6: 前端 TradeEntryModal 加价格校验

输入 price 时实时调 `/api/stocks/{code}/price-band` 获取区间,超出红字提示 + 阻断提交(可勾选 override)。

#### Task S2.7: SELL draft 详情页显示可用份额

展示「可用 N 股 / 共 M 股(M-N 是今日买入冻结)」。

**Stage 2 验收**:
- 录入超出涨跌停的价格 → 系统拒绝
- 录入今日买入的股票的 SELL → 系统拒绝
- 停牌股票不进 plan_runner 扫描
- BUY draft 显示建议股数

---

## Stage 3: Lixinger 多层防御 + system_alerts(2-3 天)

### 文件结构

```
backend/app/models/
└── system_alert.py                  # 新增
backend/app/services/
├── circuit_breaker.py               # 新增
├── data_freshness_service.py        # 新增
├── data_sanity_service.py           # 新增
└── system_alert_service.py          # 新增
backend/app/services/lixinger_client.py  # 修改 — 加 tenacity 重试 + 断路器
backend/app/routers/
└── system_alerts.py                 # 新增
frontend/src/components/
└── SystemAlertBanner.tsx            # 新增 — Cockpit 顶部红条
```

### Tasks

#### Task S3.1: system_alerts 表 + CRUD

字段:id / severity(info/warning/critical)/ category(data/scheduler/api/db/token)/ message / detail_json / created_at / resolved_at / resolved_by

#### Task S3.2: data_freshness 表 + service

记录每个数据类别(category: stocks/valuation/kline/financial/dividend)的 last_synced_at / last_success_at / record_count。`plan_runner` 启动时调 `assert_fresh_enough(category, max_age_hours=24)`,过期抛 `DataStaleError`。

#### Task S3.3: data_sanity_service

```python
SANITY_RULES = {
    "pe_ttm": lambda v: 0 < v < 1000,
    "pb": lambda v: 0 < v < 100,
    "dyr": lambda v: 0 <= v < 0.30,
    "sp": lambda v: v > 0,
    "mc": lambda v: v > 0,
}

def validate_record(record: dict) -> list[str]:
    """Return list of violation messages."""
    ...
```

Pipeline 同步时调用,违规记录进 dead_letter,不写主表。

#### Task S3.4: lixinger_client 加 tenacity + 断路器

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=10),
       retry=retry_if_exception_type((httpx.RequestError,)),
       reraise=True)
def _post_with_retry(...): ...

# 断路器:连续 5 次失败 → 5 分钟拒绝 + emit critical system_alert
```

#### Task S3.5: scheduler job 失败捕获

```python
# scheduler.py 每个 job 包一层 try/except
def with_alerting(job_id: str, fn):
    def wrapped():
        try:
            fn()
            record_heartbeat(job_id, status="ok")
        except Exception as e:
            system_alert_service.create(
                severity="critical",
                category="scheduler",
                message=f"Job {job_id} failed: {e}",
                detail_json={"traceback": traceback.format_exc()},
            )
            record_heartbeat(job_id, status="error")
            raise
    return wrapped
```

#### Task S3.6: 前端 SystemAlertBanner

Cockpit 顶部固定区域,有 unresolved critical 时红条 + 警告图标。点击展开详情。

**Stage 3 验收**:
- 关掉 Lixinger token → Cockpit 红条出现
- 数据 24 小时未同步 → plan_runner 拒绝运行 + 红条
- Lixinger 返回 dyr=NaN → 进 dead_letter 不写主表

---

## Stage 4: 公司行为 + 回测引擎(10-12 天)

### 子阶段 4A:公司行为(3-4 天)

#### 文件结构

```
backend/app/models/
└── corp_action.py
backend/app/services/
├── corp_action_sync_service.py
└── corp_action_processor_service.py
backend/alembic/versions/
└── t0u1v2w3x4y5_add_corp_actions.py
```

#### Tasks

- **Task S4A.1**: corp_actions 表(id / stock_code / ex_date / action_type / params_json / source / processed_at / applied_trade_id)
- **Task S4A.2**: corp_action_sync_service — Lixinger 每日同步(扩展 lixinger_client 加 `get_corp_actions` / `get_rights_issues` / `get_delistings`)
- **Task S4A.3**: corp_action_processor_service — 按 action_type 分派处理:
  - cash_dividend → 写 DIVIDEND trade(加 cash)
  - stock_dividend / capitalization → 写 CORP_ACTION trade(增数量,price=0)
  - rights_issue → **不自动**,触发 system_alert(warning)+ Cockpit 提示决策
  - delist → 持仓标记 is_delisted,market_value 归零
  - merger / code_change → 旧股 SELL trade + 新股 BUY trade(按 ratio)
- **Task S4A.4**: scheduler 任务 `corp_action_apply_daily` (交易日 9:00 应用当日 ex_date 的 actions)

### 子阶段 4B:回测数据基础设施(2-3 天)

#### 文件结构

```
backend/app/models/
├── historical_valuation.py
├── historical_kline.py
└── historical_financial.py
backend/app/services/pipelines/
├── historical_data_pipeline.py
└── publish_date_resolver.py   # A3 假设的兜底
backend/alembic/versions/
└── u1v2w3x4y5z6_add_historical_tables.py
```

#### Tasks

- **Task S4B.1**: 三张历史数据表 schema
- **Task S4B.2**: historical_data_pipeline — 首次全量拉取(分批避免 quota)+ 增量同步
- **Task S4B.3**: publish_date_resolver — 财报的发布日解析(若 Lixinger 不直接给,用 `report_period + 90d` 估算,标记 `publish_date_estimated=True`)

### 子阶段 4C:回测引擎核心(3-4 天)

#### 文件结构

```
backend/app/services/backtest/
├── __init__.py
├── engine.py            # 主循环
├── point_in_time.py     # 上下文构建(不能用未来数据)
├── simulator.py         # 撮合(T+1/lot/涨跌停/费用/滑点)
├── metrics.py           # CAGR/Sharpe/MaxDD/命中率
└── reporter.py          # 生成 BacktestResult
backend/app/models/
└── backtest_run.py
backend/app/routers/
└── backtests.py
```

#### Tasks

- **Task S4C.1**: BacktestRun 表(id / config_json / started_at / completed_at / status / result_json)
- **Task S4C.2**: point_in_time context builder — 给定 day,返回当日可用的全市场数据(财报只能用 publish_date ≤ day 的)
- **Task S4C.3**: simulator — 实现 T+1、100 股最小、涨跌停拒绝、佣金/印花税、滑点(默认 0.1%)
- **Task S4C.4**: metrics — CAGR / Sharpe / MaxDD / 胜率 / 与沪深300对比
- **Task S4C.5**: engine 主循环
- **Task S4C.6**: API `POST /api/backtests` 提交 + `GET /api/backtests/{id}` 查询 + 异步执行

### 子阶段 4D:回测可视化(2 天)

#### 文件结构

```
frontend/src/pages/BacktestPage.tsx
frontend/src/components/backtest/
├── BacktestConfigForm.tsx
├── EquityCurveChart.tsx       # ECharts 净值曲线 vs benchmark
├── MetricsCards.tsx
├── MonthlyHeatmap.tsx
└── SignalList.tsx
```

#### Tasks

- **Task S4D.1**: 配置表单(策略选择 / 时间范围 / 初始资金 / 滑点假设)
- **Task S4D.2**: 净值曲线 + benchmark 对比
- **Task S4D.3**: 关键指标卡片
- **Task S4D.4**: 月度收益热力图
- **Task S4D.5**: 信号明细表

**Stage 4 验收**:
- 内置策略跑 2019-2024 回测,净值曲线显示
- 与沪深 300 对比,Sharpe / MaxDD 数字合理
- 公司行为自动应用后,持仓数量正确

---

## Stage 5: 盘中监控 + 多通道告警 + 止损(4-5 天)

### 文件结构

```
backend/app/models/
├── notification_channel.py
├── holding_risk_rule.py
└── trading_calendar.py
backend/app/services/
├── realtime_quote_service.py        # 新浪接口封装
├── notification_service.py
├── intraday_monitor_service.py
└── stop_loss_service.py
backend/app/scheduler.py             # 修改 — 加 intraday_price_poll job
backend/app/routers/
├── notifications.py
└── trading_calendar.py
```

### Tasks

#### Task S5.1: trading_calendar 表 + seeder

预填 2025-2027 节假日(国务院放假安排)。`is_trading_day(date)` 工具函数。每年初手动更新。

#### Task S5.2: notification_channels 表 + service

```python
# dispatch(alert: SystemAlert)
# 按 severity_filter 过滤通道,逐个发送
# 失败的通道标记 + fallback 到 in_app
```

支持通道:in_app(必)/ server_chan(推荐)/ email / dingtalk_webhook

#### Task S5.3: realtime_quote_service

```python
def get_realtime_prices(codes: list[str]) -> dict[str, RealtimeQuote]:
    """Sina hq.sinajs.cn, return current/prev_close/high/low."""
```

加 1 分钟内存缓存避免高频调用。

#### Task S5.4: holding_risk_rules 表

```python
holding_id / stop_loss_pct / stop_loss_type(pct_from_cost|fixed_price|trailing)
/ take_profit_pct / take_profit_type / enabled / triggered_at
```

#### Task S5.5: stop_loss_service

```python
def check_holding(holding, current_price: float) -> StopLossEvent | None:
    """Return event if stop-loss or take-profit triggered."""
```

触发后:
- 自动生成强烈推荐的 SELL draft(reason="止损触发")
- 写 system_alert(critical)
- 推所有通道

#### Task S5.6: intraday_monitor_service

```python
def intraday_watch_list(db) -> set[str]:
    """持仓 + 自选 + 待执行草稿 + 论点股"""
    ...

def poll_once(db):
    codes = intraday_watch_list(db)
    quotes = realtime_quote_service.get_realtime_prices(list(codes))
    for code, q in quotes.items():
        intraday_price_cache.set(code, q.current)
        check_alert_rules(code, q.current)
        for h in holdings_of(code):
            check_stop_loss(h, q.current)
        refresh_pending_drafts(code, q.current)
```

#### Task S5.7: scheduler 接入

```python
@scheduler.scheduled_job("cron", day_of_week="mon-fri",
                         hour="9-14", minute="*/5",
                         timezone="Asia/Shanghai", id="intraday_poll")
def intraday_poll_job():
    if not is_trading_day(today()):
        return
    with SessionLocal() as db:
        intraday_monitor_service.poll_once(db)
```

#### Task S5.8: 前端 — 通知配置 UI + 止损规则 UI

Cockpit 持仓行加"止损规则"按钮(弹窗设置)。Settings 加"通知通道"配置。

**Stage 5 验收**:
- 配置 server_chan → 触发止损 → 微信收到推送
- 盘中 9:30-15:00 每 5 分钟拉价,Cockpit 显示实时
- 持仓股跌 8% → 自动生成 SELL draft + 推送

---

## Stage 6: Docker + DR + 运维(2-3 天)

### 文件结构

```
/Dockerfile.backend
/Dockerfile.frontend
/docker-compose.prod.yml
/docker-compose.dev.yml
/docker/backup/
├── Dockerfile
└── backup.sh
/docker/healthcheck-probe/
├── Dockerfile
└── probe.sh
backend/app/models/
└── system_health.py        # 心跳记录
backend/app/routers/
└── health.py               # 修改 — 扩展 deep 探针
backend/app/services/
└── scheduler_heartbeat_service.py
.env.example
```

### Tasks

#### Task S6.1: Dockerfile.backend + Dockerfile.frontend

后端:`python:3.14-slim` + venv + uvicorn。前端:`node:20` build + `nginx:alpine` serve。

#### Task S6.2: docker-compose.prod.yml

```yaml
services:
  backend:
    build: ./backend
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:3001/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    volumes:
      - ./backend/data:/app/data
      - ./backups:/backups
    env_file: .env
  frontend:
    build: ./frontend
    restart: always
    ports: ["80:80", "443:443"]
    depends_on:
      backend:
        condition: service_healthy
  backup:
    build: ./docker/backup
    restart: always
    volumes:
      - ./backend/data:/data:ro
      - ./backups:/backups
  healthcheck-probe:
    build: ./docker/healthcheck-probe
    restart: always
    env_file: .env
```

#### Task S6.3: backup 容器

每日 02:00 用 sqlite3 `.backup` 命令导出,保留 7 日,加密压缩。

#### Task S6.4: healthcheck-probe 容器

每 5 分钟 curl `/api/health/deep`,失败 3 次调 notification_service 推送 critical 告警。

#### Task S6.5: system_health 表 + scheduler 心跳

每个 job 完成后写心跳。`detect_missed_jobs` 检测超 1.5 倍间隔未心跳的 job → 告警。

#### Task S6.6: /api/health/deep 扩展

返回完整体检:database / lixinger / scheduler / data_freshness / disk_usage / token_expiry / recent_errors。

#### Task S6.7: 时区统一改造

CLAUDE.md 的 P3 项"datetime.utcnow() 迁移"在此**升级为 P0**:
- 业务时间(filled_at / ex_date)全部 Asia/Shanghai 存储(naive datetime)
- 元数据时间(created_at)UTC
- 写工具函数 `to_shanghai_naive(dt)` 强制入库前转换

#### Task S6.8: 备份恢复演练

每月一次 cron:从 7 天前备份恢复到临时 DB,跑 schema 校验 + 抽样查询,失败告警。

**Stage 6 验收**:
- `docker compose up -d` 起来,Cockpit 可访问
- 杀掉 backend 容器 → 自动重启 → 30 秒内恢复
- 跑 backup 容器 1 次 → 备份文件存在
- 关掉 Lixinger token → healthcheck-probe 推送告警

---

## 实施记录(执行时填写)

| 阶段 | 开始日期 | 完成日期 | 实际工时 | 备注 |
|---|---|---|---|---|
| S0 | | | | |
| S1 | | | | |
| S2 | | | | |
| S3 | | | | |
| S4 | | | | |
| S5 | | | | |
| S6 | | | | |

---

## 不在范围(明确不做)

- Q12: 税务 / 合规导出(用户决策跳过)
- Q13: 交割单 CSV 自动导入(用户选择手动录入)
- 策略版本化(`strategy_versions` 表,等首个真实需求出现再加)
- 多账户支持(单券商账户假设)
- 历史数据完整回填自动化(分批手动控制)
- audit_log 长期归档机制(等表超过 10 万行再考虑)
- 移动端 App(Web 响应式已够)
- 用户认证(个人工具,无)
- PostgreSQL 迁移(SQLite WAL 已够,除非 S0 Spike 6 失败)

---

## Self-Review

### Spec coverage 检查

| 决策点 | 实现位置 | 状态 |
|---|---|---|
| Q1 手动录入 | S1.5 trade_service + S1.9 TradeEntryModal | ✅ |
| Q2 trades 流水表 | S1.1 Trade model + S1.7 迁移 | ✅ |
| Q3 T+1 双层 | S1.6 available_quantity_at + S2.3 trade_service 校验 + S2.5 plan_runner 软校验 | ✅ |
| Q4 资金模型 | S1.2 cash_balance/adjustments + S1.5 现金更新 | ✅ |
| Q5 成本 | S1.3 broker_fee_configs + S1.4 fee_calculator | ✅ |
| Q6 价格 / 涨跌停 / 停牌 | S2.1 Stock 字段 + S2.2 price_validator + S2.3 校验 | ✅ |
| Q7 Lixinger 防御 | S3.2 freshness + S3.3 sanity + S3.4 retry/breaker + S3.5 scheduler 捕获 | ✅ |
| Q8 回测 | S4B 数据基础设施 + S4C 引擎 + S4D 可视化 | ✅ |
| Q9 公司行为 | S4A sync + processor | ✅ |
| Q10 盘中 / 告警 / 止损 | S5.1-5.8 | ✅ |
| Q11 Docker / DR | S6.1-6.8 | ✅ |

### Placeholder 扫描

✅ S0/S1 全部步骤含完整代码
⚠️ S2-S6 任务为"结构化清单"+ 关键代码片段,执行时按 TDD 展开为 step-by-step。这是显式选择——多周项目无法一次写完所有 step,且执行时可能根据 Spike 结果调整。

### 类型一致性

- `Trade` 字段在 S1.1 定义,S1.5/S1.6/S1.7 引用一致(`stock_code / side / price / quantity / filled_at / commission / stamp_duty / transfer_fee / total_value / source / source_ref / fee_source / reversed_by_trade_id`)
- `available_quantity_at(db, stock_code, moment)` 签名在 S1.6 / S2.3 / S2.5 一致
- `compute_fees(side, price, quantity, broker_config)` 在 S1.4 / S1.5 一致
- `FeeBreakdown.total_value(side)` 在 S1.4 / S1.5 一致

### 已知风险

1. **Lixinger 数据覆盖度未验证** — S0 Spike 1-2 是阻断点,可能需要找补充数据源
2. **新浪接口稳定性** — S0 Spike 4,失败需切腾讯
3. **SQLite 并发** — S0 Spike 5,失败需 PostgreSQL
4. **历史数据量** — 10 年 × 5000 股 × 日级 ≈ 1200 万行,SQLite 单表可能撑不住,需分表或归档
5. **回测引擎复杂度** — point-in-time 实现易出 bug,S4C 需要专门 code review

---

## 执行交接

Plan saved to: `docs/active/production-readiness-plan.md`

**两种执行方式:**

**1. Subagent-Driven(推荐)** — 每个 task 派遣新 subagent,任务间 review,快速迭代。适合本计划这种"任务边界清晰、互不依赖代码上下文"的场景。

**2. Inline Execution** — 当前会话内执行,批量任务 + checkpoint review。适合需要保留对话上下文的场景。

**推荐路径**:
- **S0 Spike** 用 Inline(需要边跑边判断,结果影响后续设计)
- **S1-S6** 用 Subagent-Driven(任务清晰,可并行)

**Which approach?**
