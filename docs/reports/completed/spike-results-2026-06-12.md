# Spike 结果汇总 (2026-06-12)

> **范围**: 生产化计划 S0 阶段的 6 个验证探针
> **目的**: 在投入 4-5 天的 S1 数据模型工作前,锁定或调整 7 个关键假设
> **执行**: worktree `production-readiness-s0`,6 个探针在 `backend/spikes/`(未提交)

---

## 速览:7 个假设的结果

| # | 假设 | 结果 | 对原计划的影响 |
|---|---|---|---|
| A1 | Lixinger 提供送股/转增 | ✅ 已确认 | S4A corp_action 处理器直接读 `bonusSharesFromProfit` / `bonusSharesFromCapitalReserve` |
| A2 | Lixinger 提供配股/退市/并购独立端点 | ❌ 失败 | S4A 配股降级(手工录入或弃做),退市用启发式(股票从 company list 消失 + profile `historyStockNames`) |
| A3 | 财报带 publish_date | ✅ 强确认 | S4B `publish_date_resolver` 简化为字段读取 `reportDate`,无需估算 |
| A4 | 5-10 年历史数据可拉 | ✅ 技术 + ⚠️ 配额 | S4 回测用 10 年,但首拉 5625 股可能需 3-4 天(悲观 5k/日配额),建议优先 Plan 涉及股票 |
| A5 | 新浪实时报价稳定 | ✅ 已确认 | S5 实时层用新浪;腾讯做 fallback;盘中验证待补 |
| A6 | SQLite 并发不锁死 | ✅ 已确认 | 不切 PostgreSQL;**禁用 StaticPool**(陷阱) |
| A7 | Lixinger company 接口字段 | ⚠️ 部分 | 用 `listingStatus` + `exchange` 替代 `is_st` / `board`;`prev_close` 走 K 线;申万行业待 S2 排查 |

**总结**:7 个假设中 4 个 ✅、2 个 ⚠️、1 个 ❌。整体计划**可行**,但 S4A 公司行为模块要降级配股处理,S2 要新增"申万行业数据源"调研。

---

## 关键发现(原计划未覆盖,需新增 P0 修复)

### 🚨 生产 bug 1:`get_company_list` pageSize 被静默截断

**现状**(`backend/app/services/lixinger_client.py:120-127`):

```python
def get_company_list(self, page: int = 0, page_size: int = 5000) -> list[dict]:
    data = self._post("/cn/company", {"pageIndex": page, "pageSize": page_size}, ...)
```

**问题**:Lixinger 实测**静默把 pageSize 截到 500**,即使传 5000 也只返回 500 条。当前调用方传 `page_size=5000`,以为拉到全市场,实际只拿到 **500/5625 = 8.9%**。

**影响**:
- `universe_service` / `stocks_sync_service` 同步不全
- `plan_runner` 扫描的"全市场"实际只是 500 股子集
- 候选池 / 策略评估覆盖率严重失真
- 回测 universe 不完整

**修复**:改为分页拉取,直到累计 < page_size:

```python
def get_company_list_all(self) -> list[dict]:
    all_records = []
    page = 0
    while True:
        batch = self._post("/cn/company", {"pageIndex": page, "pageSize": 500}, cache_ttl=86400)
        if not batch:
            break
        all_records.extend(batch)
        if len(batch) < 500:
            break
        page += 1
    return all_records
```

**优先级**:P0,要在 S1 之前修(否则 S1 的数据迁移会基于错误的全市场假设)。

### 🚨 生产 bug 2:`get_dividend` 不处理 10 年时间窗限制

**现状**:

```python
def get_dividend(self, stock_code: str, start_date: str, end_date: Optional[str] = None) -> list[dict]:
    payload = {"stockCode": stock_code, "startDate": start_date}
    if end_date:
        payload["endDate"] = end_date
    return self._post("/cn/company/dividend", payload, cache_ttl=3600) or []
```

**问题**:Lixinger **强制 dividend 查询时间跨度 ≤ 10 年**,否则返回 403 `时间跨度不能超过10年`。S0.1 测试 `2010-01-01` 到现在(~16 年)直接 403。

**影响**:
- 用户拉 10+ 年历史分红会失败,但 `dividend_service` 没有兜底
- S4 回测引擎拉历史 corp_actions 时会爆

**修复**:封装一个分段版本:

```python
def get_dividend_full(self, stock_code: str, start_date: str, end_date: str) -> list[dict]:
    """Auto-segment queries > 10 years."""
    from datetime import datetime, timedelta
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    results = []
    cursor = start
    while cursor < end:
        seg_end = min(cursor + timedelta(days=3650), end)  # ~10 years
        seg = self._post("/cn/company/dividend",
                         {"stockCode": stock_code,
                          "startDate": cursor.strftime("%Y-%m-%d"),
                          "endDate": seg_end.strftime("%Y-%m-%d")},
                         cache_ttl=3600) or []
        results.extend(seg)
        cursor = seg_end + timedelta(days=1)
    return results
```

**优先级**:P0,同上。

### ⚠️ StaticPool 陷阱(已在 S0.5 验证)

**问题**:`backend/tests/conftest.py` 用 `poolclass=pool.StaticPool` 是为测试隔离,但**绝不能用于生产**。StaticPool 单连接跨线程共享,会破坏事务隔离、产生假性数据错乱。

**现状**:`backend/app/db/engine.py` 用默认 QueuePool — 正确。但要防止未来有人误抄。

**建议**:在 `app/db/engine.py` 顶部加注释 + link 到本 spike 报告,说明为何不能用 StaticPool。

---

## 各假设详细结论

### A1: 送股 / 转增 ✅

**端点**:`/cn/company/dividend`
**字段**:
- `bonusSharesFromProfit` — 送股(每 10 股)
- `bonusSharesFromCapitalReserve` — 转增(每 10 股)
- `dividend` / `dividendAmount` — 现金分红(每股 / 总额)
- `exDate` / `registerDate` / `paymentDate` — 除权除息日 / 股权登记日 / 派息日
- `fsEndDate` — 对应财报期

**样本**:
- 600519 茅台:37 条历史(2010-2024 分段)
- 000651 格力:34 条,2017 年 10转5 派现可见

**对 S4A 的影响**:`corp_action_processor_service` 处理 `cash_dividend` / `stock_dividend` / `capitalization` 三类,直接读这些字段即可。

---

### A2: 配股 / 退市 / 并购独立端点 ❌

**测试 11 个候选端点**:
- `/cn/company/allotment` — **返回 200 但永远空数据**(僵尸端点,3 个已知配股案例都返回 [])
- `/cn/company/delisting` / `/delist` / `/corp-action` / `/capital-change` / `/merger` / `/code-change` — 全部 404

**退市的启发式检测**(可用但需工程化):
1. 每日全量同步 `/cn/company`,记录 stock_code 集合
2. 昨日有今日无 → 标记 `delisted`,触发 `/cn/company/profile` 拉 `historyStockNames`
3. profile 含 `退市XX` / `*ST` 的更名记录 → 提取退市日期

**配股处理(降级方案)**:
- **不做自动检测**,改为用户手动录入配股决策
- 触发条件:`cash_adjustments` 表中 `reason="rights_issue_subscription"` 由用户填,或弃做这部分

**对 S4A 的影响**:
- 删除原计划的"配股触发 alert + Cockpit 提示决策"功能
- 新增"退市检测 daily sync job"(基于 company list diff)
- 在文档中标注"配股无自动覆盖,用户自行关注公告"

---

### A3: publish_date ✅

**端点**:`/cn/company/fs/non_financial`
**字段**:`reportDate`(就是披露日)+ `reportType`(`annual_report` / `interim_report` / `first_quarterly_report` / `third_quarterly_report`)

**验证**:20 条茅台财报样本全部在 CSRC 法定披露窗口内:
- 年报 90-94 天(法定上限 120 天)
- 半年报 29-40 天(上限 61)
- 一季报 26-28 天(上限 30)
- 三季报 17-26 天(上限 31)

**对 S4B 的影响**:
- `publish_date_resolver` 简化为:`return record["reportDate"]`
- 删除原计划的估算逻辑(或保留为兜底:`if reportDate is None: use reportType 法定上限`)
- 回测引擎的 point-in-time 过滤:`where reportDate <= backtest_day`

**bonus**:`accountant` / `accountingFirm` / `auditOpinionType` 字段可作未来"审计意见异常"过滤。

---

### A4: 5-10 年历史覆盖 ✅ + ⚠️

**测试结果**(600519 茅台 2015-2024):
- K 线 (`/candlestick`):**2431 条**(10 年 × ~243 交易日,完整)
- 估值 (`/fundamental/non_financial`):**2431 条**(与 K 线 1:1 对齐)
- 财报-年 (`/fs/non_financial` granularity=y):**10 条**(2015-2024 全年报)
- 财报-季 (granularity=q):**40 条**(10 年 × 4 季)

**数据质量**:早期数据完整,无"延后开始"现象,OHLCV 全非零。K 线和估值可同一 API 拉到(简化数据流)。

**配额估算**(全市场 5625 股 × 10 年):

| 数据类型 | 调用次数(10y 单窗口) |
|---|---|
| K 线 (1 股/次) | 5,625 |
| 估值 (10 股/次) | 563 |
| 财报 (1 股/次 × 2 粒度) | 11,250 |
| **合计** | **~17,500** |

| Lixinger 配额 | 完成时间 |
|---|---|
| 50k/日(乐观) | ~1 小时 |
| 5k/日(悲观) | 3-4 天 |

**对 S4 的影响**:
- 10 年回测**技术可行**,无需缩到 5 年
- 全量首拉要分批 + checkpoint(复用 `pipelines/checkpoint.py`)
- **建议优先拉当前 Plan 涉及股票**(持仓 + 自选 + 候选),不是全市场
- 配额监控在 S3 的 `data_freshness` 之外,新增 `quota_usage` 跟踪

**bonus**:`turnover` 字段恒为 null,用 `to_r`(换手率)替代。数据按日期**倒序**返回。

---

### A5: 新浪实时报价 ✅

**端点**:`https://hq.sinajs.cn/list=sh600519,sz000001`
**关键约束**:
- 必须 `Referer: https://finance.sina.com.cn`,否则 403
- 编码 GBK(`r.encoding = "gbk"`)
- 字段索引:`[0]`名称 / `[2]`昨收 / `[3]`现价 / `[4]`最高 / `[5]`最低 / `[30]`日期 / `[31]`时间

**稳定性测试**(20 次 × 15s 间隔):
- 成功率 20/20
- 延迟 min=35ms / avg=44ms / max=57ms / stdev=6ms
- 零 429 / 零 5xx / 零解析失败
- 响应无任何 rate-limit header

**板块覆盖**:主板 / 创业板 / 科创板 / 北交所都返回正常(`688xxx` 走 `sh` 前缀已验证)

**待补**:盘中(工作日 9:30-15:00)再跑一次,确认价格真在动(本次测试已收盘 4 小时,价格静止)。

**对 S5 的影响**:
- `realtime_quote_service` 用新浪为主,腾讯 `qt.gtimg.cn`(免 Referer)做 fallback
- 1 分钟内存缓存避免高频
- timeout 5s + retry 2 次 + 指数退避
- 实时性满足长线投资体系要求(15 秒级足够)

---

### A6: SQLite 并发 ✅

**测试**:1 写线程(每秒 1 笔 trade + cash 更新,事务原子)+ 5 读线程(每 0.5s 聚合查询)× 3 分钟。

**结果**:
- 写入 180 / 读取 1785 / 错误 **0**
- 写延迟 p50=0.9ms / p95=1.5ms / p99=2.6ms / max=5.5ms
- 读延迟 p50=0.5ms / p95=1.2ms / p99=1.5ms / max=2.3ms
- 数据一致性 ¥0 偏差(`1000000 - Σ trades.total_value == cash_balance.balance`)
- 无 lock contention,距 5s busy_timeout 还有 1000 倍余量

**关键 gotcha**:
- **绝不能用 `poolclass=pool.StaticPool`**(虽然 `conftest.py` 用了,但那是测试隔离用的)
- StaticPool 单连接跨线程共享 → 事务隔离失效 → 假性数据错乱
- 生产 `app/db/engine.py` 默认 QueuePool(每线程独立连接),已正确
- **建议**:`engine.py` 顶部加注释,链接本报告

**对 S1/S5 的影响**:
- SQLite WAL 完全够,无需 PostgreSQL
- 真实生产写入速率(每天 ~10 笔 trade)远低于压测负载
- 即使盘中 5 分钟监控 + 多用户读,也在容量内

---

### A7: company 接口字段 ⚠️

**端点 1**:`/cn/company`(返回 9 字段)
- `stockCode` / `name` / `exchange`(sh/sz/bj)
- `listingStatus`(7 个枚举值,见下)
- `fsTableType`(`non_financial` / `bank` / `security` / `insurance` / `other_financial`)
- `ipoDate` / `mutualMarketFlag` / `mutualMarkets` / `areaCode`

**`listingStatus` 枚举分布**(5625 股全样本):
| 状态 | 数量 | 含义 |
|---|---|---|
| `normally_listed` | 5364 | 正常 |
| `delisting_risk_warning` | 125 | *ST |
| `special_treatment` | 110 | ST |
| `delisting_transitional_period` | 8 | 退市整理期 |
| `ipo_suspension` | 8 | 暂停上市 |
| `issued_but_not_listed` | 4 | 已发行未上市 |
| `issue_failure` | 1 | 发行失败 |
| `unauthorized` | 1 | 未批准 |

**端点 2**:`/cn/company/profile`(公司基本面,无交易状态字段)

**缺失的关键字段**:
- `prev_close` — company / profile / fundamentals 都没有,要 `/candlestick` kline 拉
- 申万 `industry_sw` — profile 完全无行业字段,`/cn/industry/constituents/sw_2021/{code}` 对样本返回空,**需 S2 排查正确代码格式**
- 停牌状态 — Lixinger 静态数据不覆盖,要从新浪实时行情或交易所公告判断

**板块识别方案**(替代 board 字段):
```python
def detect_board(exchange: str, code: str) -> str:
    if exchange == "bj" or code.startswith("920"):
        return "bjse"
    if code.startswith("688"):
        return "star"
    if code.startswith(("300", "301")):
        return "chinext"
    return "main"
```

**ST 识别方案**(替代 is_st 字段):
```python
def is_st(listing_status: str) -> bool:
    return listing_status in ("special_treatment", "delisting_risk_warning",
                              "delisting_transitional_period")
```

**验证**:110 只 `special_treatment` 全部以 `ST` 开头;125 只 `delisting_risk_warning` 全部以 `*ST` 开头。**有 2 只异常**:名称 `*ST` 但 `listingStatus=normally_listed`(可能是 Lixinger 数据延迟或刚摘帽),**以 `listingStatus` 为准**。

**对 S2 的影响**:
- `Stock` 表新增字段:`exchange`(已有?) / `listing_status` / `fs_table_type` / `ipo_date`
- 不再加 `board` / `is_st` / `is_suspended`(都是派生属性)
- `prev_close` 每日同步任务从 K 线拉,存到 Stock 或独立表
- `industry_sw` 待 S2 阶段调研补充(可能要从外部源)

---

## 对原计划的修订项

### S1 之前必须修(P0)

1. **修 `get_company_list` 分页 bug** — 否则 S1 数据迁移基于错误的全市场假设
2. **修 `get_dividend` 时间窗 bug** — S4 依赖

### S1 范围调整

- 新增任务 S1.0:`Stock` 表字段调整(用 `listing_status` + `exchange` 替代 `is_st` / `board`),原计划 S2.1 的部分前移到 S1
- 新增任务 S1.X:`StaticPool` 警示注释

### S2 调整

- 板块识别用 `exchange + code prefix`,不用 Lixinger `board` 字段
- ST 识别用 `listing_status in (...)`,不用名称匹配
- 涨跌停的 `prev_close` 每日 K 线同步,不存 Lixinger company
- **新增调研任务**:申万行业数据源(`/cn/industry/constituents/sw_2021/{code}` 返回空的原因)

### S4A 调整(公司行为)

- **删除"配股触发 alert + 决策"功能**,改为文档说明"配股无自动覆盖,用户自行关注公告"
- **新增"退市检测 daily sync"任务**:基于 company list diff + profile `historyStockNames`
- `corp_action_processor_service` 处理 `cash_dividend` / `stock_dividend` / `capitalization` 三类,直接读 dividend 端点字段

### S4B 调整(回测)

- `publish_date_resolver` 简化为读 `reportDate`
- 历史数据首拉分批 + checkpoint
- 优先 Plan 涉及股票(不是全市场)
- 新增 `quota_usage` 监控(S3 扩展)

### S5 调整(盘中监控)

- 新浪为主 + 腾讯 fallback
- 盘中验证脚本待写(S5 开工前)
- 字段索引已确认

### S6 不变

- SQLite WAL 配置验证完毕,不需要 PostgreSQL
- Docker 备份方案不变

---

## 下一步

S0 完成。所有假设已验证或降级方案明确。两个 P0 bug 待修。**S1 可启动**,但需在 S1.0 先修 2 个 bug + 调整 Stock schema。

预计 S1 工作量从原计划的 4-5 天 → **5-6 天**(加 bug 修复 + schema 调整)。

---

## Spike 文件清单(未 git commit)

```
backend/spikes/
├── __init__.py
├── spike_lixinger_corp_actions.py     # A1 + A2
├── spike_lixinger_publish_date.py     # A3
├── spike_lixinger_history_range.py    # A4
├── spike_sina_realtime.py             # A5
├── spike_sqlite_concurrency.py        # A6
└── spike_lixinger_company_fields.py   # A7
```

是否提交?推荐:**spike 脚本不提交**(一次性验证用),**汇总报告提交**(长期参考价值)。后续可放到 `docs/reports/completed/`。
