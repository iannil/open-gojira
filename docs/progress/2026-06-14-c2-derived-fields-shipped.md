# C.2.1 + C.2.2 完成 — derived 字段计算 (2026-06-14)

> **状态**: ✅ C.2.1 + C.2.2 完成
> **commit**: `25ed0e2` (financials nested fix) + `482b786` (derived fields)
> **关联**: `docs/reference/specs/2026-06-14-comprehensive-audit.md`
> **下一步**: C.2.3 dividend_sustainability(可选) 或 C.2.4 full backfill

## 摘要

C.2.1 修复了 Lixinger financials 字段全部 None 的 bug(嵌套响应解析错误)。
C.2.2 实现了 derived 字段计算,让 build_stock_context_at 能 populate 策略依赖的
窗口字段。

## C.2.1: Lixinger nested response bug

**根因**: `historical_data_pipeline.fetch_and_upsert_financials` 用 `r.get("ps.toi.t")`
等扁平键读数据,但 Lixinger 实际返回**嵌套结构** `record[q][section][field][t]`。

```python
# 实际响应(record 0):
{
  "q": {
    "ps": {"toi": {"t": 70987206095}, "np": {"t": 37331971189}},
    "m": {"wroe": {"t": 0.167}, "ncffoa_np_r": {"t": 0.814}},
    ...
  }
}
```

**修复**: 新增 `_nested_financial_value(record, granularity, section, field)` 辅助函数,
逐层走 `record[g][section][field][t]`。

**测试**:
- `test_fetch_and_upsert_financials` 改用真实嵌套 fixture
- `test_nested_financial_value_helper` 直接测 walker(7 个 case)

**实测 600519 × 2023 H1**:
```
period=2023-06-30 revenue=70987206095 net_profit=37331971189
roe=0.167 ocf_to_np_ratio=0.814 gross_margin=0.918
```

## C.2.2: 派生字段计算

**新增辅助函数**:

```python
def _compute_percentile_at(db, code, day, field, years=10, min_samples=30) -> float | None:
    """Percentile rank (0-1) of current field within [day-years, day] window.
    Returns None if window < min_samples (statistically unstable)."""

def _compute_price_drop_pct_at(db, code, day, window_days=366) -> float | None:
    """1 - close/52w_high from historical_klines window."""
```

**build_stock_context_at 改动**:

| 字段 | 实现 | 数据源 |
|---|---|---|
| `dyr` | 直接 | `historical_valuations.dyr` |
| `forward_dyr` | trailing dyr proxy | `historical_valuations.dyr` (文档化偏差) |
| `pe_pct_10y` | 窗口 percentile | `historical_valuations.pe_ttm` |
| `pb_pct_10y` | 窗口 percentile | `historical_valuations.pb` |
| `price_drop_pct` | 52w window | `historical_klines.close/high` |
| `ocf_to_ni` | 直接 | `historical_financials.ocf_to_np_ratio` |
| `dividend_sustainability` | **未实现** | 需 C.2.3 historical_dividends |

**测试** (`test_point_in_time_stock_context.py`, 7 个):
- 用 sine 波 pe_ttm 数据验证 percentile 在 peak (i=15, pe=40) / trough (i=45, pe=20) 的预期值
- min_samples 不足时返回 None
- 缺数据时(current valuation 不存在 / kline 不存在)返回 None
- end-to-end: build_stock_context_at 全字段 populate

## 实测验证 (600519 × 2023-05-15)

```
ctx.dyr              = 0.0279    (2.79%)
ctx.forward_dyr      = 0.0279    (trailing dyr proxy)
ctx.pe_pct_10y       = 0.023     (6月窗口内低位)
ctx.pb_pct_10y       = 0.023     (同上)
ctx.ocf_to_ni        = 0.2437    (从 Q1 2023 财报)
ctx.price_drop_pct   = 0.113     (距 52w 高点 -11.3%)
```

**spot-check 输出**:
```
dyr_fwd >= 0.0400    →  CHECK: dyr_fwd = 0.0278  ✗ (0.0278 < 0.04)
dividend_sustainability >= 60  →  CHECK: dividend_sustainability = —  ✗ (data unavailable)
ocf_to_ni >= 0.8000  →  CHECK: ocf_to_ni = 0.2437  ✗ (0.2437 < 0.8)
```

策略**正确基于真实数据** fail,而非 "data unavailable"。pipeline 完整工作。

## 6 策略 × 6 字段依赖矩阵

| 策略 | dyr_fwd | dividend_sustainability | ocf_to_ni | pe_pct_10y | pb_pct_10y | price_drop_pct |
|---|---|---|---|---|---|---|
| high_dividend_cushion | ✓ | ✗ | ✓ | — | — | — |
| undervalued_entry | — | — | — | ✓ | ✓ | — |
| resource_hard_asset | ✓ | — | — | — | ✓ | — |
| bank_select | ✓ | — | — | — | — | — |
| cashflow_asset | ✓ | — | ✓ | ✓ | — | — |
| contrarian_oversold | ✓ | ✗ | — | — | — | ✓ |

**4/6 策略可用**(只有 high_dividend_cushion 和 contrarian_oversold 因 dividend_sustainability 缺失而无法完整评估)。

## 下一步选择

| 阶段 | 内容 | 估时 | 必要性 |
|---|---|---|---|
| **C.2.3** | 实现 dividend_sustainability(需 historical_dividends 表 + Lixinger dividend endpoint) | ~1 天 | 中 — 解锁 2/6 策略 |
| **C.2.4** | Full backfill 309 candidates × 5y × 3 endpoints | ~1-3 天 (Lixinger 配额) | 高 — 解锁真 backtest |
| **C.2.5** | 跑 6 策略 × 309 × 5y backtest | 小时级 | 高 |
| **C.2.6** | 3 轮 spot-check iter | ~1 hour | 高 |

**建议**: 先 C.2.4(扩数据),C.2.3 dividend_sustainability 留到 C.2.6 spot-check 时如果发现 2/6 策略评估受限再做。

## 文件清单

```
修改:
  backend/app/services/historical_data_pipeline.py   (+_nested_financial_value)
  backend/app/services/point_in_time_context_service.py (+derived fields)

新增:
  backend/tests/test_point_in_time_stock_context.py (7 tests)
```

## 测试

- 938 tests passed (+7 derived field tests + 1 helper test)
- 实测 600519 slice backtest 端到端跑通,derived 字段正确填充
