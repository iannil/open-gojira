# Phase 2 #10 (Q15) Run diff 视图 — 设计规格

> **日期**: 2026-06-16
> **状态**: 已确认 (grill-me 会话产出,代码下次实施)
> **关联**: `docs/reference/specs/2026-06-14-serenity-skill-integration.md` Q15 | `docs/progress/STATUS.md` P1-2 | `docs/progress/2026-06-16-phase2-num10-handoff.md`

## 背景

spec Q15 决策: Phase 1 只列 Run,Phase 2 设计 diff 语义。Phase 2 #9 (structured claims) 已 ship (2026-06-16),#10 是 serenity 模块剩余的最后 P1 项。

本规格定义 Run diff 功能的 7 个核心决策,代码实施工作量约 **3-4 小时** (含 grill + 实施 + dev server 验证)。

## 决策汇总

| # | 决策 | 选择 | 关键约束 |
|---|---|---|---|
| Q0 | 本轮范围 | C 纯 grill + spec,代码下次实施 | 数据质量差 (run 4 hallucinated),先锁设计 |
| Q1 | diff 目标场景 | A 时序对比,2 Run,同 theme | 唯一明确生产场景,周度调度自然延伸 |
| Q2 | diff 维度 | 1+2+3 三核心 | ranking / failure claims / scarce_layers;evidence 和 universe 后置 (YAGNI) |
| Q3a | ranking 算法 | stock_code 做 key,rank 升降 | 稳定标识,升降 = 用户感知 |
| Q3b | claims 算法 | subject 精确匹配,signal 文本变化 | 起步用 strict,漂移率高再升级 fuzzy |
| Q3c | scarce_layers 算法 | layer_index 做 key,set 比 | 天然稳定 key |
| Q4 | 视觉呈现 | A 并排两列 + summary 条 + tab 切换 | git diff 工业标准,桌面优先 |
| Q5 | 持久化 | A 实时算,不落库 | Run 数据 immutable,无 cache 必要 |
| Q6 | 入口点 | A History tab 内嵌 (checkbox + Compare 按钮) | 复用现有 IA,最少跳转 |
| Q7 | 边界处理 | 8 个 case 全接受 | 见下文 API 校验章节 |

## 数据维度与算法

### 维度 1: company_ranking 升降

数据源: `research_company_ranking` 表 (rank: 1-7, stock_code, name, constrains_what, chain_position, rank_reason, evidence_summary, main_risk)

**算法** (Q3a): `stock_code` 做 key,计算 rank delta。

```python
RankingDiffItem = {
    "stock_code": str,
    "name": str,
    "rank_from": int | None,   # None = new_in
    "rank_to": int | None,     # None = dropped
    "delta": int | None,       # rank_to - rank_from; None if new_in/dropped
    "category": "promoted" | "demoted" | "new_in" | "dropped" | "unchanged",
}

RankingDiff = {
    "promoted":  list[RankingDiffItem],  # delta > 0
    "demoted":   list[RankingDiffItem],  # delta < 0
    "new_in":    list[RankingDiffItem],
    "dropped":   list[RankingDiffItem],
    "unchanged": list[RankingDiffItem],
}
```

### 维度 2: failure_conditions claims 变化

数据源: `research_claims` 表 (type='failure_condition',subject/predicate/signal/outcome/stock_codes_json/layer_index)

**算法** (Q3b): `subject` 精确匹配。signal 字段文本变化标记 tightened/loosened (本次不解析阈值,只标"变化")。

```python
ClaimDiffItem = {
    "subject": str,
    "claim_from": ClaimSnapshot | None,   # None = new_risk
    "claim_to":   ClaimSnapshot | None,   # None = resolved
    "signal_changed": bool,
    "category": "new_risk" | "resolved" | "tightened" | "loosened" | "unchanged",
}

ClaimSnapshot = {
    "predicate": str,
    "signal": str | None,
    "outcome": str,
    "stock_codes": list[str],
    "layer_index": int | None,
}

ClaimsDiff = {
    "new_risks":  list[ClaimDiffItem],
    "resolved":   list[ClaimDiffItem],
    "tightened":  list[ClaimDiffItem],   # signal_changed && outcome 不变
    "loosened":   list[ClaimDiffItem],
    "unchanged":  list[ClaimDiffItem],
}
```

**Tightened/Loosened 判定 (简化版)**: signal 字段文本变化即标"tightened" (默认方向)。阈值语义化判定 (e.g. `<1.5%` → `<1.8%` 真的是 tighten) 需要正则或 LLM 二次解析,本次**不做**。

### 维度 3: scarce_layers 增减

数据源: `scarce_layers` 表 (rank: 1-5, layer_index: 1-8, scarcity_reason_md, expansion_difficulty)

**算法** (Q3c): `layer_index` 做 key,set 比。

```python
ScarceLayerDiffItem = {
    "layer_index": int,         # 1-8
    "layer_name": str,          # 从 value_chain_layers 查
    "rank_from": int | None,    # None = entered
    "rank_to":   int | None,    # None = exited
    "category": "entered" | "exited" | "reranked" | "unchanged",
}

ScarceLayerDiff = {
    "entered":   list[ScarceLayerDiffItem],
    "exited":    list[ScarceLayerDiffItem],
    "reranked":  list[ScarceLayerDiffItem],
    "unchanged": list[ScarceLayerDiffItem],
}
```

## API 契约

### `GET /api/research/runs/diff?run_a={id}&run_b={id}`

**Q5 决策**: 实时算,无 cache。

**成功响应** (200):
```json
{
  "run_a": {"id": 8, "started_at": "2026-06-16T...", "status": "completed"},
  "run_b": {"id": 12, "started_at": "2026-07-21T...", "status": "completed"},
  "summary": {
    "ranking": {"promoted": 1, "demoted": 2, "new_in": 1, "dropped": 1, "unchanged": 2},
    "claims": {"new_risks": 1, "resolved": 0, "tightened": 1, "loosened": 0, "unchanged": 3},
    "scarce_layers": {"entered": 1, "exited": 0, "reranked": 0, "unchanged": 3}
  },
  "ranking_diff": {...},          // RankingDiff
  "claims_diff": {...} | null,    // ClaimsDiff;null if legacy run (no structured claims)
  "scarce_layers_diff": {...},    // ScarceLayerDiff
  "degradations": []              // ["claims_diff_unavailable_legacy"] 等
}
```

**校验失败** (422):
```json
{"error": "both runs must be completed", "details": {"run_a_status": "running"}}
```

**校验规则** (Q7):
| # | 规则 | 错误信息 |
|---|---|---|
| 1 | run_a / run_b 必须 same theme | `"runs must be same theme"` |
| 2 | run_a / run_b 都必须 completed | `"both runs must be completed"` |
| 3 | run_a / run_b 必须存在 | 404 `"run {id} not found"` |
| 4 | run_a != run_b | `"pick two different runs"` |

**自动行为**:
- 时间顺序: API 不强制,UI 按 `started_at` 自动排序,左列显早的 / 右列显晚的
- Legacy run 处理: claims_diff = null,degradations 加 `"claims_diff_unavailable_legacy"`

**容错**:
- 某维度算法抛异常 → 该维度返回 null + degradations 标记,不影响其他维度
- 例: `claims_diff: null, degradations: ["claims_diff_failed: subject_match_error"]`

## UI 设计 (Q4 + Q6)

### 入口

`ResearchThemeDetailPage` 的 History tab,加 checkbox 列 + Compare 按钮:

```
History tab:
┌─────────────────────────────────────────────────────────────────┐
│ ☐ Run 12 (2026-07-21, completed, 28 evidence)                   │
│ ☐ Run 8  (2026-06-16, completed, 28 evidence)                   │
│ ☐ Run 6  (2026-06-16, completed, 15 evidence)                   │
│ ☐ Run 4  (2026-06-15, completed, legacy, no structured claims)  │
│ ☐ Run 3  (2026-06-15, failed)                                   │
│                                                                  │
│ [Compare selected] (disabled until 2 checked)                   │
└─────────────────────────────────────────────────────────────────┘
```

- 选中 2 个时按钮启用,>2 时禁用 + tooltip `"pick exactly 2"`
- 选中 failed Run 时按钮禁用 + tooltip `"both runs must be completed"`
- Theme 总 completed Run <2 时所有 checkbox 禁用

### Diff 视图 (Drawer 弹出,不跳新页面)

```
┌─ Theme: 银行 — Run 8 → Run 12 diff ─────────────────────────────┐
│ Summary:                                                        │
│   Ranking: 1↑ 2↓ 1+ 1- (2 unchanged)                           │
│   Claims: 1 new 1 tightened (3 unchanged)                       │
│   Scarce Layers: 1+ (3 unchanged)                               │
├─────────────────────────────────────────────────────────────────┤
│ [ Ranking ] [ Failure Claims ] [ Scarce Layers ]                │
├─────────────────────────────────────────────────────────────────┤
│ ┌─ Ranking ──────────────────────────────────────────────────┐ │
│ │ Rank │ Run 8              │ Run 12             │ Δ         │ │
│ │ 1    │ 002049 紫光国微    │ 002049 紫光国微    │ —         │ │
│ │ 2    │ 300348 长亮科技    │ 600036 招商银行    │ NEW ↑     │ │
│ │ 3    │ 600036 招商银行    │ 300348 长亮科技    │ -1 ↓      │ │
│ │ 4    │ 002152 广电运通    │ (dropped)          │ OUT ↓     │ │
│ └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 色标
- 🟢 绿 = 升 / 新进 (NEW ↑ / promoted / entered / new_risk)
- 🔴 红 = 降 / 退出 (OUT ↓ / demoted / dropped / exited)
- 🟡 黄 = 内部变化 (signal 变化 / rank reranked / tightened)
- ⚪ 灰 = 不变 (默认色,不显 badge)

### 维度特化渲染

- **Ranking**: 表格 (rank 对齐),3 列 (Run A / Run B / Δ)
- **Failure Claims**: 并排卡片网格,左右各 N 个。匹配的 claim 用连线表示 subject 配对,signal 变化高亮。
- **Scarce Layers**: 并排 8 层条带,左右对照层位,entered/exited/reranked 标色。

## 后端实施工作量

| 文件 | 内容 | 行数估算 |
|---|---|---|
| `app/services/research_diff_service.py` (新) | 3 个 `_diff_*` 函数 + `compute_diff` 主函数 + Pydantic schemas | ~250 |
| `app/routers/research.py` (改) | 加 `GET /runs/diff` endpoint + 422 校验 | ~40 |
| `tests/test_research_diff_service.py` (新) | unit tests 覆盖 3 维度算法 + 边界 case | ~250 |
| `tests/test_research_router_diff.py` (新或合并) | API endpoint tests | ~80 |
| **后端小计** | | **~620** |

## 前端实施工作量

| 文件 | 内容 | 行数估算 |
|---|---|---|
| `src/api/client.ts` (改) | 加 `getRunDiff(runA, runB)` 函数 | ~10 |
| `src/api/types.ts` (改) | 加 `RunDiffResponse` / `RankingDiff` 等类型 | ~50 |
| `src/features/research/HistoryTab.tsx` (改) | checkbox 列 + Compare 按钮 + 状态管理 | ~80 |
| `src/features/research/RunDiffDrawer.tsx` (新) | Diff 视图 Drawer,含 summary + tab + 3 维度渲染 | ~250 |
| `src/features/research/RunDiffPanel.tsx` (新) | 维度特化渲染组件 (RankingTable / ClaimsGrid / ScarceLayersChart) | ~200 |
| **前端小计** | | **~590** |

**总计**: ~1210 行代码,3-4 小时 (含 grill + dev server 验证)

## 验收标准

- [ ] 后端 3 个 `_diff_*` 函数 unit tests 全过
- [ ] API endpoint tests 全过 (含 4 个校验失败 case)
- [ ] 实测: 用 run 6 vs run 8 (同 theme 银行,同日两 Run) 调 API,返回正确 diff
- [ ] 实测: 用 run 4 vs run 8 (legacy vs structured) 调 API,claims_diff=null + degradations 正确
- [ ] 前端 History tab 加 checkbox + Compare 按钮,disabled 状态正确
- [ ] 前端 RunDiffDrawer 渲染 3 维度,色标正确
- [ ] dev server 启动,浏览器手动验证 happy path + 1 个 edge case

## 后置 / 未来工作

- **Claims 阈值语义化** — tightened/loosened 目前只看 signal 文本变化,未来加正则或 LLM 二次解析提取数字阈值
- **Timeline 视图 (Q1-D)** — 3+ Run 的时间轴演化,本次跳过,未来基于 2-Run diff 算法串联
- **Cross-theme diff (Q1-B)** — 不同 theme 的公司宇宙重合度,本次明确不做
- **Cache (Q5-B/C)** — Run 数量增长到几百级再考虑
- **持久化 diff (Q5-B)** — 用于历史审计,目前不需要

## 关联文件索引

实施时涉及的现有文件:

| 文件 | 修改内容 |
|---|---|
| `backend/app/routers/research.py` | 加 `GET /runs/diff` endpoint |
| `backend/app/services/research_diff_service.py` | **新建**,3 维度 diff 算法 |
| `backend/tests/test_research_diff_*.py` | **新建**,unit + API tests |
| `frontend/src/api/client.ts` | 加 `getRunDiff` API 函数 |
| `frontend/src/api/types.ts` | 加 diff 相关 TS 类型 |
| `frontend/src/features/research/HistoryTab.tsx` | 加 checkbox + Compare 按钮 |
| `frontend/src/features/research/RunDiffDrawer.tsx` | **新建**,diff 视图 Drawer |
| `frontend/src/features/research/RunDiffPanel.tsx` | **新建**,3 维度渲染组件 |
| `docs/progress/STATUS.md` | 完成后标 P1-2 ship |
