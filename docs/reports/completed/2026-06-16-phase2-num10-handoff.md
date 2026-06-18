# Phase 2 #10 (Q15) Run diff 视图 — Handoff

> **日期**: 2026-06-16
> **状态**: 待 grill (STATUS.md P1-2)
> **关联**: spec `docs/reference/specs/2026-06-14-serenity-skill-integration.md` Q15

## 背景

spec Q15 决策: Phase 1 只列 Run,Phase 2 设计 diff 语义。今天 (2026-06-16) 已完成 Phase 2 #9 (structured claims),#10 是 serenity 模块剩余的最后 P1 项。

## 已有的实测数据 (下次直接拿来 diff)

| run_id | 时间 | pipeline | 主题 | 关键产物 |
|---|---|---|---|---|
| 4 | 2026-06-15 | Path A (hallucinated) | 银行 | 5 failure_conditions_md (text only) |
| 6 | 2026-06-16 | Path B 早期 | 银行 | 4 failure_conditions_md (text only) |
| 8 | 2026-06-16 | Path B + #9 structured | 银行 | 5 failure + 6 next_step **structured claims** |

**注意**: run 4 是 hallucinated 数据,diff 时不要混入设计参考。run 6/8 都是真实 Path B,但只有 run 8 有 structured claims。

理想: 下次会话先用 Path B 跑 1-2 个**新 theme** (e.g. 半导体 / 资源) 拿真实对照,再跑一次"银行"做时序 diff 测试。

## 设计决策树 (按依赖顺序)

### Q1: diff 的目标用户场景是什么?

| 选项 | 描述 |
|---|---|
| A | **时序对比** — 同 theme 不同时间两次 Run,看判断有没有变化 |
| B | **跨主题对比** — 不同 theme 的 Run,看稀缺层/公司宇宙重合度 (低价值,大概率丢弃) |
| C | **A/B 对比** — 同 theme 同时间不同 pipeline (Path A vs Path B) |

推荐 A — 唯一明确用户价值的场景。

### Q2: 哪些维度值得 diff?

候选 (按价值排序):
1. **company_ranking 升降** — rank 1-7 的公司进出 + 排名变化 (Top N 视图)
2. **failure_conditions claims 变化** — 同 subject 的 signal 阈值是否更严/松
3. **scarce_layers 增减** — 哪些层进了 / 出了稀缺榜
4. **evidence 强度** — strong grade 证据占比变化
5. **company_universe 涨缩** — 公司池规模变化 (低价值)

推荐 1+2+3 做 (4+5 后置)。

### Q3: diff 算法语义?

- ranking diff: `claim.rank_from / rank_to / delta` — rank_to=None 表示新进,None from 表示跌出
- claims diff: 用 `subject` 做匹配键 (LLM 措辞可能漂移,需 fuzzy match 或人工确认)
- scarce_layers diff: `layer_index` 是天然 key,直接比 set

### Q4: 视觉呈现?

候选:
- 并排两列 (左旧右新),变化项高亮
- 单列时间轴,每行带"vs 上次"badge
- Diff summary 卡片 (Top 3 升降),点击展开详情

推荐并排两列 + 变化高亮 (最直观)。

### Q5: 持久化?

- 计算后存吗? 或每次访问 Run 详情页时实时算?
- 推荐实时算 — Run 数量小 (个位数),无性能压力,避免 stale diff 数据

## 实施工作量估算

- backend service `research_diff_service.py`: ~150 行 (3 维度 diff 函数 + tests)
- backend router `/api/research/themes/{id}/diff?run_a=X&run_b=Y`: ~30 行
- 前端 `RunDiffPanel.tsx`: ~200 行 (并排两列 + 高亮)
- 测试: ~15 个 unit + 1 个 e2e

总计 **~3-4 小时** (含 grill + 实施 + dev server 验证)。

## 建议下次会话开场

1. 跑一次新 theme 的 Path B 真实研究 (e.g. 半导体 / 资源),拿到 run_id=9
2. 再跑一次"银行"做时序对照 (run_id=10 vs run_id=8)
3. 开 grill,从 Q1 开始走决策树
