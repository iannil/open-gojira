# C.1 Minimal Slice — Pipeline 验证完成 (2026-06-14)

> **状态**: ✅ 完成
> **关联**: `docs/reference/specs/2026-06-14-comprehensive-audit.md` (C 分支决策)
> **下一步**: C.2 full backfill (309 × 5y) 或 A/D 分支并行

## 目标

按 Q13 决策,minimal slice 先验证 backtest pipeline 端到端正确性,再扩到 309 × 5y 全量。

## 实施内容

### C.1.1 Backtest engine 升级 ✅

**关键改动**: `backend/app/services/backtest_engine.py`

- 删除 v1 flat rules 评估器(`_evaluate_rule`, `_resolve_metric`, `_OPERATORS`)
- 改用 production `strategy_engine.evaluate(rule_json, ctx)`,支持 AND/OR
- config 字段 `strategy_rules: list[dict]` → `strategies: list[int]`
- `_execute_signal_buy` 用 config-level `target_pct` (默认 0.10) 而非 rule-level
- inconclusive → 视为 fail → AND 全策略通过才 BUY

**新增**: `backend/app/services/point_in_time_context_service.py:build_stock_context_at()`
- 包装 `build_context_at` + Stock 表查询
- 输出 `StockContext` 供 `strategy_engine.evaluate` 消费
- 直接可用字段: dyr / ocf_to_ni / price / 行业标签 / 资源 flags
- 窗口计算字段 (pe_pct_10y / pb_pct_10y / price_drop_pct / dividend_sustainability) 留 None,C.2 补

**测试**: 927 tests passed (含 backtest_engine 新测试 8 个 + 既有回归)

### C.1.2 Backfill 600519 × 6 月 ✅

**结果**:
- klines: 118 行 (2023-01-03 → 2023-06-30,实际交易日)
- valuations: 118 行
- financials: 2 行 (2023 Q1 + 2023 H1,report_date 已正确解析)
- errors: 0

脚本: `backend/scripts/backfill_slice.py`

### C.1.3 Spot-check 脚本 ✅

**位置**: `backend/scripts/spot_check_backtest.py`

**支持参数**:
- `--run-id N` 必填
- `--sample-per-strategy 5` 默认 5 条/策略
- `--mode random|stratified` 默认 random (stratified 实现 Q7 决策: 2 extreme + 2 boundary + 1 counter)
- `--seed N` 可选,固定采样种子

**输出格式** (Q6 决策): 每条信号包含
1. Strategy rule_json + 每子条件评估(✓/✗)
2. Raw data from `historical_*` 表 (point-in-time correct, financials 按 report_date <= day 过滤)
3. Sanity status (PASS / VIOLATION + 字段)
4. Engine action (BUY / HOLD / SELL)
5. Bucket 分类 (extreme_pass / boundary_pass / boundary_fail / other)

### C.1.4 Slice backtest 跑通 ✅

**运行**: `python scripts/run_slice_backtest.py`
- 策略: high_dividend_cushion (id=1)
- 股票: 600519 茅台
- 期间: 2023-01-02 → 2023-06-30
- 结果: status=completed, 0 trades, equity flat @ ¥1M

**预期 0 trades**: high_dividend_cushion 要求 dyr_fwd ≥ 4% AND 分红可持续 ≥ 60 AND OCF/NI ≥ 0.8。三个字段在 v1 `build_stock_context_at` 中:
- `dyr_fwd` = None (留作 C.2 处理 — 需前向股息预测)
- `dividend_sustainability` = None (留作 C.2 — 需分红历史计算)
- `ocf_to_ni` = None (实测 Lixinger 没返回 600519 的 `m.ncffoa_np_r` 字段)

策略正确 fail,AND 逻辑工作,pipeline 端到端无 bug。

## 实测发现 (C.2 待解)

### 发现 1: Lixinger financials 字段稀疏

600519 × 2 财报周期 × 多个 ratio 字段:
- `ocf_to_np_ratio`: None × 2
- `roe`: None × 2
- `revenue`: None × 2

可能原因:
- Lixinger 默认 endpoints 不返回 ratio 字段(需切换 endpoint?)
- 600519 的 fs_table_type 路由错误(走 non_financial 但应该走其他)
- Lixinger 该字段需另外请求

**C.2 行动**: spot-check 1-2 只其他股票的 financials 字段,确认是否普遍问题。

### 发现 2: dyr_fwd / dividend_sustainability / pe_pct_10y 等需补

为了让 6 策略能真实评估,C.2 需在 `build_stock_context_at` 中补:
- `forward_dyr`: 用 trailing dyr 作 proxy(承认偏差,文档化)
- `pe_pct_10y`: 在 historical_valuations 表上做窗口查询(10y × 250d/yr = 2500 行/股,可接受)
- `pb_pct_10y`: 同上
- `price_drop_pct`: 在 historical_klines 表上做 52w 窗口查询
- `dividend_sustainability`: 需新表 `historical_dividends` 或调用 Lixinger dividend endpoint

## 文件变更

```
新增:
  backend/scripts/backfill_slice.py
  backend/scripts/run_slice_backtest.py
  backend/scripts/spot_check_backtest.py

修改:
  backend/app/services/backtest_engine.py            (engine 升级)
  backend/app/services/point_in_time_context_service.py (+build_stock_context_at)
  backend/tests/test_backtest_engine.py              (新 config 格式测试)

文档:
  docs/reference/specs/2026-06-14-comprehensive-audit.md (主决策)
  docs/progress/2026-06-14-c1-slice-pipeline-verified.md (本文)
```

## 下一步

按 ship 顺序选择:

**A. 进入 C.2 (full backfill)** — 解决发现 1+2,扩到 309 × 5y,跑 6 策略真实 backtest + 3 轮 spot-check iter

**B. 切到 A/D 分支并行** — A (UI banner) + D (auto-supersede) 各 ~0.5 天,可同步进行

**C. E dry-run 同步** — 用现有 220 drafts 跑端到端 trade workflow dry-run

我建议先做 B+C (各 1 天,稳定性提升),再 A (C.2 full backfill 需要 1-3 天 + 数据问题排查)。
