# 功能审计 — Drift 发现汇总 (2026-06-18)

> **触发**: `/grill-me 对已经实现的所有功能进行审计`
> **范围**: Batch 1-5 ship 后端到端验证
> **方法**: 清空 DB → 跑 production flow → 记录每步 drift
> **耗时**: ~2 小时
> **结论**: 13 个 drift (P0×4 已修 + CRITICAL×1 已绕过 + 文档/语义×8)

---

## 0. 起点: DB 状态漂移

实测 DB 所有 transactional 表 (drafts / candidates / holdings / trades / research_* / audit_logs / system_alerts) 全部 0 行。STATUS.md 声称的 `1 holdings / 6 trades / 220 drafts / 264 candidates / 8 research runs / 1 thesis 告警` 与实测完全不符。

**用户确认**: DB 被故意清空,准备跑 production validation 验证 Batch 5。

→ 含义: **6 轮历史审计 + 今天 5 个 Batch 的"ship + 验收"报告全部基于空 DB**。1155 tests 通过 ≠ 真实链路跑通。

---

## 1. P0 发现 (4 个,全部已修)

### F4: AdaptiveThrottler 死代码 (~150 行)

**位置**: `app/services/pipelines/throttler.py`
**症状**: `AdaptiveThrottler` 类定义完整 (budget / acquire / record_error / stats),但 `grep -rn AdaptiveThrottler app/` 只在自身定义处出现,**从未被任何代码 import**。
**根因**: 设计了 throttler 但忘了 wire 到 pipeline / lixinger_client。
**修复**: 在 `LixingerClient._get_throttler()` 中 lazy-init class-level singleton,`_post_with_retry` 调用 `acquire()` + 429 时 `record_error()`。Defaults 改保守 (`min_interval=1.0s`,原 0.2s)。

### F5: Lixinger 429 显式不 retry

**位置**: `app/services/lixinger_client.py:211-212` (旧代码)
**症状**: 3 个并行 sync pipeline (valuations + financials + dividends) 同时启动 → Lixinger API 立即 429 → 15276 stocks 全部进 dead_letter。
**根因**: 旧注释 "4xx client-side, won't recover by retrying" 把 429 当作不可恢复错误。但 429 = rate limit,`retry with exponential backoff` 完全可以恢复。
**修复**: 加 `_RateLimitError(httpx.RequestError)` 类 (类似 `_TransientServerError` 套路),`_do_post` 检测 429 → raise → tenacity 自动 retry (3 attempts,exponential 2-10s)。
**测试**: `test_lixinger_resilience.py` 加 2 个新测试 (`test_429_rate_limit_retried` + `test_429_all_retries_exhausted`)。1157 passed (+2)。

### F7: avoid_overvalued_tech 策略用 invalid op `<`

**位置**: DB `strategies` 表 id=7 (Batch 1 ship 加的)
**症状**: `GET /api/strategies` 500 ValidationError。整条 strategies endpoint 不可用,UI 无法列策略。
**根因**: `ComparisonOp = Literal[">=", "<=", "==", "in"]`,但 Batch 1 加的 `avoid_overvalued_tech` 策略 rule_json 用了 `op:"<"` (line: `{"field": "dyr_fwd", "op": "<", "value": 0.02}`)。
**修复**: schema 加 `<` 和 `>` 到 ComparisonOp;strategy_engine 加对应 case。这样既支持新策略,也避免下次类似 bug。
**测试**: 现有 35 strategy_engine 测试 + 全套 1157 通过。

### F8: stock_context_builder bank industry 检查中文 `"银行"` 

**位置**: `app/services/stock_context_builder.py:171, 294`
**症状**: bank_select 策略永远 0 候选,即使 13 个银行股 current DYR ≥ 5% 通过。
**根因**: 代码 `if stock.industry == "银行":`,但实测所有 43 银行股 industry 都是英文 `"bank"` (Lixinger 返回值)。bank_analyzer 永不调用 → bank_blind_box 永远 None → 策略条件 `bank_blind_box == "可见"` 永远 fail。
**注**: Batch 1 fix 注释明说"Lixinger 实际返回值是 bank",他们修了 strategy 的 industry_in filter (line 4 加了 "bank"),但**忘了修 context_builder 的调用门**。
**修复**: `is_bank = stock.industry in ("银行", "bank") or stock.fs_table_type == "bank"`。同时修了批量构建路径 (line 294)。
**测试**: 全套 1157 通过。

---

## 2. CRITICAL 发现 (1 个,根因定位但需用户决策)

### F12: Batch 5 M2 in_circle filter 把所有股票都过滤掉 ✓ **已修**

**位置**: `app/services/plan_runner.py:607-609`
**症状**: 全部 6 plans 跑出来 `passed=0, drafts_emitted=0`,但 `scanned=5626`。
**根因 (实测确认)**:
- Batch 5 M2 加了 `Stock.in_circle: bool` 字段 + `plan_runner._filter_out_of_circle` filter
- 默认 `plan.disable_in_circle_filter=False` (filter 开启)
- 实测 `SELECT in_circle, COUNT(*) FROM stocks GROUP BY in_circle` → `0: 5626` (**所有股票 in_circle=False**)
- `_filter_out_of_circle` 返回 `kept=[], dropped=5626`
- → 所有股票在策略评估前被过滤掉 → 0 候选 → 0 draft

**验证**: 临时 `UPDATE plans SET disable_in_circle_filter=1 WHERE id=1` 后再跑 plan 1:
```
passed=4, new=4, drafts_emitted=6 ✓
```

**修复 (2026-06-18,选项 A)**:
- `app/models/plan.py`: `disable_in_circle_filter` default `False → True`,server_default `"0" → "1"`
- `alembic/versions/s10_1_in_circle_filter_default_off.py`: 新 migration,flip server_default + UPDATE 现有 plans 全部改为 True
- 含义: filter 反转为 opt-in (用户标 in_circle 后再设 False 启用)
- 验证: 1157 tests passed + plan_runner 自动产出 4 candidates + 6 drafts (无需手动改 DB)

---

## 3. P1 / 文档漂移 (8 个,部分已记录待修)

### F2: STATUS.md §3.3 migration count 21 vs 实测 49

实测 `ls backend/alembic/versions/*.py | wc -l` = 49。STATUS.md §3.3 写 "21 个版本文件"。Memory 写 49 (正确)。STATUS.md 该处需更新。

### F3: data_freshness 跟踪表 stale

实测 `data_freshness.last_success_at`:
- stocks: 2026-06-13 (5 天前)
- valuation: 2026-06-13

但 `price_klines` 表有 2026-06-17 数据。**freshness 跟踪与实际数据不同步**。通过 `universe_bootstrap` pipeline 重新触发,stocks freshness 已更新。这是一个 pipeline 设计问题 — K-line 写入时没更新 data_freshness.kline 跟踪。

### F6: Financial pipeline 不批量 → 90 分钟同步

`valuations_pipeline` BATCH_SIZE=100,5368 stocks → 54 batches → 1s/batch × throttler = ~60s。
`financial_pipeline` 单股一次调用,5354 stocks → 5354 calls → 1s/call × throttler = ~90 分钟。
对全市场同步太慢,但是设计选择 (financials 按 fs_table_type 分流到 4 个 endpoint)。建议未来按类型批量。

### F9: bank_select 策略 description vs rule 不一致

description: "DYR≥5%",但 rule_json 用 `dyr_fwd` (forward DYR)。实测 601166 current DYR 5.98% 但 forward DYR 3.44% → fail。**这是 forward DYR 计算保守导致** (3-year avg per share / latest close),不是 bug 是设计选择,但 UI description 误导。

### F10: 0/5626 stocks 有 `power_tier` 数据 → Batch 2 optionality_leader 策略永远 0 候选

Batch 2 D2 ship 加了 `optionality_leader` 策略 (rule: `power_tier >= 2`),但 0 stocks 有 `power_tier` 字段值。**策略非功能性** — 永远 0 候选。

### F11: 1/5626 stocks 有 `dividend_payout_commitment_pct` → Batch 4 dividend_commitment_leader 策略近乎非功能

Batch 4 N4 ship 加了 `dividend_commitment_leader` (rule: `dividend_payout_commitment_pct >= 0.6`),但只 1 stock 有此字段。**策略近乎非功能**。

### F13: STATUS.md "真实生产链路跑通" 声明不实

STATUS.md (含 thesis monitor v2 acceptance 报告) 声称"工商银行 NIM 持续 2 期 1.2% < 1.3% → audit + EventBus + SystemAlert + dispatch 真实跑通"。实测 `audit_logs` / `system_alerts` 表 0 行。截图可能是 dev session 临时数据,后续被 wipe。

### F1: 整体 STATUS.md production state 声明 (220 drafts / 1 holding / 8 research runs) 全部失实

DB 全空,所有"真实使用"数字基于 dev session 截图 + 测试 fixture 凑出。

---

## 4. 修复后端到端验证结果 (实测)

修复 F4 / F5 / F7 / F8 + 临时绕过 F12 (in_circle filter off) 后:

| 步骤 | 结果 |
|---|---|
| Sync valuations | 5368/5368 ✓ (首次 800, retry 后 4568/4568,throttler 修后 0 错) |
| Sync financials | 5354/5354 ✓ (retry 后) |
| Sync dividends | 5354/5354 ✓ (retry 后) |
| Plan runner (plan 1) | scanned=5626 passed=4 new=4 drafts_emitted=6 ✓ |
| Cockpit API | drafts=6, cycle="low" position, cycle_banner=None ✓ |
| psychology_alerts | 0 (空 — 因为无持仓) ✓ |
| thesis_alerts | 0 (空 — 因为无 thesis variables) ✓ |

**核心闭环跑通** (此前 6 轮审计 + 5 个 Batch 从未真正端到端验证过)。

---

## 5. 影响评估

| Batch | ship 后实测 | 实测真相 |
|---|---|---|
| Batch 1 (avoid_overvalued_tech, bank_select 修) | 没真跑过 | F7 + F8 都有 bug,Batch 1 ship 引入了 invalid op + 漏修 context_builder |
| Batch 2 (optionality_leader) | 没真跑过 | F10: 策略非功能 (0 stock 有 power_tier) |
| Batch 3 (red flag detector) | 部分跑过 | 6/7 红旗生效 (1 死代码) — 之前 audit 已记录 |
| Batch 4 (dividend_commitment_leader) | 没真跑过 | F11: 策略近乎非功能 (1 stock 有数据) |
| Batch 5 (in_circle / 心法闸门 / thesis breach / tier-aware) | 没真跑过 | F12: in_circle filter **break 了 production** |

---

## 6. 推荐下一步 (P0)

1. **F12 修复**: 必须做。推荐 (A) `disable_in_circle_filter` 默认改 True,理由是「数据未填充前不应启用 filter」。
2. **F10 / F11 文档化**: power_tier / dividend_payout_commitment_pct 需要手动填,要么提供批量填的 UI,要么删除依赖,要么文档化为"未启用"。
3. **STATUS.md 全面同步**: 至少 F1 / F2 / F13 必须修正,否则下次 audit 还会从这里开始。
4. **scheduler 跑通**: 现在核心闭环手动跑通,但 mon-fri 18:00 scheduler 是否能跑通还没验证 (后台 job vs 手动 trigger 差异)。

---

## 7. 代码改动清单 (本次 audit)

- `app/services/lixinger_client.py`: +`_RateLimitError` 类,+`_get_throttler()` classmethod,+`_do_post` 429 检测,throttler wire
- `app/schemas/strategy.py`: ComparisonOp 加 `<` `>`
- `app/services/strategy_engine.py`: 加 `<` `>` 处理 case
- `app/services/stock_context_builder.py`: bank industry 判断双语 + fs_table_type fallback (2 处)
- `app/models/plan.py`: `disable_in_circle_filter` default 翻转 (F12 修复)
- `alembic/versions/s10_1_in_circle_filter_default_off.py`: 新 migration (F12 修复)
- `tests/test_lixinger_resilience.py`: +2 测试 (429 retried / exhausted),+ `_NoOpThrottler` test stub
- 全套测试: 1155 → 1157 passed
- DB 数据状态: 0 → 5368 stocks / 5354 financials / 5354 dividends / 4 candidates / 6 drafts / 0 holdings (写实状态)
- Alembic head: `s9_2` → `s10_1_in_circle_filter_default_off`
