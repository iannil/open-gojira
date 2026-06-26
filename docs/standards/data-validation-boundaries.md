# 数据校验服务边界说明

> 2026-06-26 — 分析四个名称相似的数据校验服务，澄清职责边界。

## 总览

| 服务 | 职责 | 调用时机 | 产出 |
|:---|:---|---|---|
| **data_quality** | 数据质量总评分 | UI 请求 / 审计 | DataQualityResponse |
| **data_sanity** | 单条记录字段校验 | Pipeline 写入前 | 有效/无效记录拆分 |
| **data_freshness** | 同步状态追踪 + 过期门禁 | Pipeline 开始/结束 + 读取前 | freshness_report / DataStaleError |
| **price_validator** | 交易价格合规校验 | Trade 创建前 | 断言通过 / StockSuspendedError 等 |

---

## 1. data_quality_service → `compute_quality(db)`

**职责**: 计算全市场数据质量的**聚合指标**。

- 覆盖 valuations / klines / financials / dividends
- 检查: 新鲜度 / 连续数据缺口 / 异常计数 / Pipeline 通过率
- 面向**审计和监控**，由前端 DataManagementPage 调用

**不负责**:
- 单条记录的字段校验 → data_sanity
- 实时同步追踪 → data_freshness  
- 交易价格约束 → price_validator

---

## 2. data_sanity_service → `validate_record` / `validate_batch`

**职责**: 对 Pipeline 写入前的**单条数据记录**做字段级校验。

- 执行 `SANITY_RULES` 中的断言 (例如 PE 不能为负, PE/PB 比例合理)
- 将批量数据拆分为 `(valid, invalid)` 两组
- 超标时触发系统告警

**不负责**:
- 跨记录的质量聚合 → data_quality
- 数据新鲜度判断 → data_freshness
- 价格涨跌停检查 → price_validator

---

## 3. data_freshness_service → `record_sync_*` / `assert_fresh_enough`

**职责**: 追踪各类数据的**同步状态**，在依赖过期数据前**阻断流程**。

- 每个 Pipeline 完成后调用 `record_sync_success` 记录最新同步时间
- `assert_fresh_enough` 在 plan_runner / trade_service 读取数据前检查
- 数据超过 `max_age_hours` → 抛 `DataStaleError` (503)

**不负责**:
- 数据本身的正确性 → data_sanity / price_validator
- 长期质量趋势 → data_quality

---

## 4. price_validator_service → `assert_tradable` / `price_band`

**职责**: 确保**单笔交易**价格在合规范围内。

- 检查: 是否停牌 / 是否 ST / 价格是否在涨跌停板内 → `assert_tradable`
- 根据交易所 + 代码前缀 + 上市状态动态计算板幅 → `price_band`
- 由 `trade_service.record_trade` 在写入 Trade 前调用

**不负责**:
- 数据质量 / 新鲜度 → data_quality / data_freshness
- 通用的字段校验 → data_sanity

---

## 结论

四个服务**边界清晰，无重叠**，不需要合并。

| 服务 | 是否保留 | 理由 |
|:---|:---:|:---|
| data_quality | ✅ 保留 | UI 数据管理页唯一依赖 |
| data_sanity | ✅ 保留 | Pipeline 写入前置过滤 |
| data_freshness | ✅ 保留 | 防 stale 读取，与 Pipeline 紧耦合 |
| price_validator | ✅ 保留 | 交易模块核心依赖，独立职责 |

唯一的建议：未来如发现 `data_quality` 和 `data_sanity` 共用某些规则定义，可考虑将共享常量提取到 `core/constants.py`，但**不合并服务**。
