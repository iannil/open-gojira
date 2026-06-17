# invest1/2/3 对齐审计 Batch 3 完成报告

> 日期: 2026-06-17
> 范围: grill-me 会话复核 Batch 1/2 实际状态 + spike 验证 + 5 missed 文档化
> 关联: `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md`
> 状态: ✅ ship

## 背景

Batch 1 (commit 258f750) + Batch 2 (commit f3d04bf) ship 后,用户再次发起 grill-me 复核。审计声称对齐度 58% → 78%,但用户怀疑口径不准。

复核发现实际状态与审计口径存在 4 处偏差:
1. D3 6/7 红旗中 3/7 是死代码 (goodwill + OCF/NI + dividend_sustainability 真生效)
2. D3 `accounts_receivable_pct_change` + `audit_opinion` schema 字段声称已加,实际未加
3. D3 + D6 `plan.invalidation:[]` schema 决策未实施 (走 plan_runner 代码路径)
4. 5 个 invest1/2/3 核心概念审计完全未覆盖 (进度条/治理瑕疵/60%承诺/数人头/周期拐点)

## 5 项 grill-me 决策

详见审计 spec 末尾"Batch 3 验证决策"段。摘要:

| # | 决策 | 工作量 |
|---|---|---|
| 1 | 立即 spike 3 个 Lixinger field keys | 0.5 天 |
| 2 | D3+D6 invalidation 架构接受现状,改文档对齐代码 | 0.2 天 |
| 3 | 5 missed 概念全部文档化为已知限制 | 0.3 天 |
| 4 | invest2 §23 4 块分类不引入 Plan.cyclicality,文档化 theme_id 已足够 | 0.1 天 |
| 5 | 3 阶段执行: spike → 接入 → 文档同步 + 测试 → Batch 3 commit | 总 1.5 天 |

## Spike 关键发现 (Phase 1)

`backend/spikes/probe_redflag_metrics.py` v3 直接 httpx 调 Lixinger fs 端点,用 4 真实股票 (宝丰能源/南山铝业/芭田股份/紫金矿业) 验证。**v1 bug 教训**: parser 用 flat `row.get("y.bs.ar.t")` 而非 nested `row["y"]["bs"]["ar"]["t"]` 导致全 false negative。

| 候选 metric | Lixinger 支持 | 数据示例 |
|---|---|---|
| `bs.ar.t` (应收账款) | ✅ 4/4 股票 | 600989 (宝丰): 37.0M (2025) / 20.2M (2024) |
| `m.i_tor.t` (存货周转率) | ✅ 4/4 股票 | 600989: 17.4 / 15.4 / 15.4 / 16.7 (近 4 年) |
| `auditOpinionType` (top-level) | ✅ 4/4 股票 = "unqualified_opinion" | 每个 fs row 顶层字段 |
| `bs.inv.t` (存货绝对值) | ❌ 400 ValidationError | Lixinger 不提供 |
| `ps.np_wd_s_r.t` (扣非净利率) | ❌ 400 ValidationError | Lixinger 不提供 |

**额外发现**: D3 原审计说"Lixinger 标准 API 不提供审计意见,跳过"是错的。`auditOpinionType` 是 Lixinger fs 端点每行的 top-level 字段,但 `financial_service.py` 之前没消费它。spike 之后立即激活一个新红旗 (非标准审计意见)。

Artifact: `backend/spikes/output/probe_redflag_metrics_2026-06-17T08-27-18Z.json`

## Phase 2 实施内容

### Schema 变更

- `backend/app/models/financial.py` — 加 `audit_opinion: Mapped[str | None]` (String)。修正 4 个已有字段注释,从"待 API 确认"改为"已 spike 验证"+ "Lixinger 不提供"
- `backend/alembic/versions/s7_1_audit_opinion_field.py` — alembic migration, down_revision=s6_1_red_flag_fields

### Service 变更

- `backend/app/services/lixinger_client.py` — `get_financials` 默认 metrics 加 `bs.ar.t` (m.i_tor.t 已存在)
- `backend/app/services/financial_service.py` —
  - 显式 metrics list 加 `bs.ar.t` + `m.i_tor.t`
  - FinancialStatement 构造加 `accounts_receivable=_get_nested(bs, "ar.t")` + `inventory_turnover_ratio=_get_nested(m, "i_tor.t")` + `audit_opinion=item.get("auditOpinionType")`
  - upsert 字段循环加 `accounts_receivable / inventory_turnover_ratio / audit_opinion`
- `backend/app/services/red_flag_detector_service.py` —
  - 新增 `_check_non_standard_audit_opinion` (audit_opinion != "unqualified_opinion"/"standard_unqualified")
  - 加入 `_CHECKS_FINANCIAL` 列表
  - `RedFlagKind` literal 加 `"non_standard_audit_opinion"`
  - 修正 `_check_non_recurring_dominant` docstring 注明"Lixinger 不提供,死代码"

### 测试

- `backend/tests/test_red_flag_detector_service.py` — 新增 `TestAuditOpinionFlag` 5 测试 (qualified / adverse / disclaimer / standard / missing),共 25 测试 (+5)

## Phase 3 验证

### 端到端 smoke test

```
python -c "...fetch_and_store_financials + detect_financial_red_flags..."
```

结果 (600989 宝丰能源):
- Stored 4 annual rows
- date=2025-12-31 AR=37000363.0 inv_tor=17.3846 audit_opinion=unqualified_opinion ✓
- date=2024-12-31 AR=20246151.0 inv_tor=15.3803 audit_opinion=unqualified_opinion ✓
- date=2023-12-31 AR=26383931.0 inv_tor=15.3638 audit_opinion=unqualified_opinion ✓
- date=2022-12-31 AR=70869058.0 inv_tor=16.6815 audit_opinion=unqualified_opinion ✓
- Red flags: count=0 kinds=[] ✓ (宝丰资产质量正常,无红旗)

### 全测试套件

```
pytest --tb=short
====================== 1126 passed, 58 warnings in 42.91s ======================
```

测试增量: +5 (Batch 2 后 1121 → Batch 3 后 1126)

### alembic migration

```
alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade s6_1_red_flag_fields -> s7_1_audit_opinion_field
```

## 文档同步

- `docs/progress/STATUS.md` — 加 Batch 3 进展条目 + 重写"已知限制"段 (5 missed 概念 + invalidation 架构 + 资源 7→6 维)
- `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md` — 状态改"已确认 + 已验证"; 替换"对齐度评估"表为 Batch 3 后实际 75%; 末尾加"Batch 3 验证决策"段
- `docs/reports/completed/plan-invest-alignment-batch3-2026-06-17.md` — 本报告

## 对齐度修正

| 维度 | Batch 2 声称 | Batch 3 实测 |
|---|---|---|
| invest2 §10 财报避坑 | 95% | 85% (6/7 红旗生效,扣非死代码) |
| invest2 §13 三类禁投 | 85% | 80% (invalidation schema 未启用) |
| 整体 | 78% | 75% |

剩余 25% 全部文档化为已知限制,符合 CLAUDE.md "架构尽可能简化" 原则。

## 经验教训

1. **审计 verification 不应只读 audit spec**: 必须 spot-check 实际代码。本次发现 audit 声称已加的 2 字段实际未加,声称 invalidation 已启用实际未启用。
2. **Spike parser 必须 match production parser**: v1 用 flat lookup 与 `financial_service._get_nested` 不一致,导致全 false negative。Spike 脚本若与 production 解析路径不一致,验证结果无效。
3. **top-level 字段 ≠ metric key**: Lixinger response 中 `auditOpinionType` 是顶层字段不是 metric path,但 audit 误以为是 metric key。Spike 直接看 raw response 是最快的发现方式。
4. **无效候选要 trim**: v1 spike 跑了 8 个 400-invalid 候选 → 触发 Lixinger 熔断 (5 次 400 → 300s 冷却)。生产客户端保护有效但 spike 应跳过已知无效项。
