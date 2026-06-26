# 纸面交易前端 UI 设计 (Paper-Trading Frontend UI)

> **日期**: 2026-06-26
> **状态**: 进行中 (设计已锁定 via grill-me, 实施未开始)
> **关联**: `docs/progress/2026-06-26-paper-trading-loop-design.md` (后端闭环, P0 已完成) · `docs/active/roadmap.md` (P0 前端 UI 四项) · grill-me 会话 2026-06-26

## 目标 (Goal)

后端纸面交易闭环已打通 (P0-1~P0-4, 555 测试): Trade 派生持仓/盈亏 + draft execute 回填 + 论点失效→SELL draft + 新 draft→signal alert。但**用户还看不到、点不动**。本设计补齐 P0 前端,使纸面跟踪真正开始:展示应买/应卖队列 → 一处确认成交回填 → Cockpit 信号置顶。

## 背景:现状盘点 (grill-me 2026-06-26)

- `/drafts` 是 stub (`features/drafts/DraftsPage.tsx`),但 hooks/API 客户端 (`listDrafts`/`executeDraft`/`cancelDraft`/`ExecuteDraftPayload`) 已存在。
- **`DraftResponse` (`schemas/draft.py:21-34`) 是瓶颈**:`Draft` 模型带 `target_price`/`strategy_tier`/`sizing_logic`/`expires_at`/`suggested_quantity`/`reduce_pct_of_position`/`serenity_thesis`/`thesis_status` 等实战字段,但响应一个都没暴露,反而漏 v1 管道字段 `step_kind`/`step_index`/`plan_id`。
- Cockpit **已有"待办信号"区** (`CockpitPage.tsx:135-157`),但渲染 v1 字段 `step_kind`、"审批"仅跳 `/drafts` 无 inline 动作。
- 后端 `record_trade` 已做全部校验:BUY 现金充足 / SELL T+1 可卖量 / 涨跌停区间 (`force` 可绕) / 费用按 active fee config 自动算。
- **SELL draft 不对称**:不设 `expires_at` (永不自动过期,`_cancel_expired` 只清 BUY) / 不设 `suggested_quantity` / `source` 落默认 `evaluator` (无意义,真正触发信息在 `step_kind=thesis_breach`)。
- `get_realtime_prices(codes)` 批量服务存在,但**无路由暴露实时报价**;`position_service.available_quantity` 存在但**无端点**。

## 锁定设计决策 (grill-me 6 问)

| # | 决策 | 理由 |
|---|---|---|
| **Q1 API 契约** | 重塑 `DraftResponse`:加实战字段、响应删 v1 管道 (模型保留,幂等索引仍用)、加服务端计算 `trigger_source`、list 暂不含 `price_ranges_json` | 前端无法渲染模型已有但响应未暴露的字段;v1 管道字段对 v2/LLM 无意义只会误导 |
| **Q1 修正** | `trigger_source` **由 `step_kind`+`side` 派生**,非 `source`:`buy_ladder`→区间建仓 / `thesis_breach`→论点失效 / (将来) `valuation_trim`→估值止盈 / `position_cap`→仓位超限 / `fundamental`→基本面恶化 | SELL 的 `source` 是默认 `evaluator`,用它做标签会误导;别在前端映射,服务端算好直接显示 |
| **Q2 页面结构** | 单表 + 状态 tab (待办/已执行/已取消,默认待办);买卖列差异靠"仓位动作"一格条件渲染;reason/serenity_thesis 行展开 | 这是"今日待办交易队列",单表可扫可排序、与 cockpit 风格统一;拆两块浪费纵向、卡片太重 |
| **Q3 确认成交弹窗** | 始终填 实际价+量;预填(买=target/suggested_qty,卖=可卖量×reduce_pct);时间默认 now 可改;信任后端校验内联报错;涨跌停错→展开"强制(新股/复牌)"勾选带 `force=true` | 偏离建议本身就是要观测的数据;后端已有校验,不前端复刻 |
| **Q3a 费用预览** | **不做实时预览**,成交后 toast+trades 页展示实算费用净额;若日后要,走后端 `/trades/fee-preview`,绝不前端复刻 `compute_fees` | 纸面阶段成交前不需精确费用;前端复刻公式会漂移 |
| **Q3b T+1 可卖量** | **新增端点暴露 `available_quantity`**,卖出弹窗预填上限 + 列表"可卖股数"列都用 (满足 roadmap P0-4) | 否则用户只在提交后才知卖超 |
| **Q4 cockpit 分工** | Cockpit 信号区 = **只读 teaser**(SELL 优先再按 TTL,"去处理"链 `/drafts`);`/drafts` = **唯一可操作队列**(确认成交/取消 inline);cockpit drafts **复用 `DraftResponse`**(统一一个 schema);抽公共 formatter,列定义各自保留 | 确认动作只一处维护免漂移;统一 schema 让 Q1 字段扩展自动惠及 teaser |
| **Q5 TTL/状态** | BUY 显示倒计时(`<24h` 标红),SELL 显示"无期限"(**刻意**:论点失效不该静默过期);`superseded` 单列 tag 区别于用户 `cancelled`(否则采纳率统计错) | 论点还是坏的就该一直卖;采纳率 = executed/cancelled/expired/superseded 需可分 |
| **Q6-A 现价可见性** | **A1 加现价列**:新批量端点 `GET /market/quotes?codes=`,pending tab 一次拉全、缓存 30-60s,显示 现价+相对建议价偏离%+是否仍在买区 | 纸面验证的意义就是按有效信号行动;不显示现价用户没法判断信号是否还成立 |
| **Q6-B 部分成交** | **B1 接受不追踪余量**:任何确认成交→executed,欠填=用户主动选更小仓位 | 纸面从简(决策 26);draft 是建议非订单;若日后欠填普遍伤归因再议 |

## 落地计划 (按依赖排序)

### 后端 (前置)

1. **重塑 `DraftResponse` + `trigger_source` 派生** (Q1/Q5):加 `target_price`/`strategy_tier`/`sizing_logic`/`suggested_quantity`/`add_pct`/`reduce_pct_of_position`/`expires_at`/`thesis_status`/`reason`/`serenity_thesis`/`research_report_id`;响应删 `step_kind`/`step_index`/`plan_id`;`trigger_source` 由 `step_kind`+`side` 派生。更新 `drafts.py:_to_response`。
2. **cockpit 序列化器复用 `DraftResponse`** (Q4):cockpit 端点的 drafts 列表改用统一 schema。依赖 1。
3. **T+1 可卖量端点** (Q3b):包 `position_service.available_quantity` (如 `GET /api/portfolio/positions/{code}/available`)。
4. **批量实时报价端点** (Q6-A1):`GET /api/market/quotes?codes=` 包 `realtime_quote_service.get_realtime_prices`。

### 前端

5. **公共 formatter 模块** (Q4):TTL 倒计时 / trigger_source 标签兜底 / tier 标签 / 仓位动作渲染。
6. **重建 DraftsPage** (Q2/Q5/Q6):单表 + 状态 tab;列 = 方向 · 代码+名称 · 触发来源 · 仓位动作(条件) · 建议价 · 现价+偏离+在区间标记 · 建议数量 · 可卖股数(SELL) · TTL(BUY)/无期限(SELL) · 操作;行展开 reason/serenity_thesis。依赖 1/3/4/5。
7. **确认成交弹窗** (Q3):预填 + 时间可改 + 信任后端校验内联报错 + 涨跌停 force 勾选;BUY/SELL 通用。依赖 1/3。
8. **Cockpit teaser 升级** (Q4):复用 DraftResponse、字段对齐(触发来源+建议价+TTL)、SELL 优先排序、"去处理"链。依赖 1/2/5。

### 归入文档的细枝 (不单独 grill)

- 轮询:pending tab `refetchInterval` 30s;TTL 倒计时客户端 tick;execute/cancel 后 invalidate(已在 mutations 接好)。
- 无 active fee config 时 `record_trade` 抛 500 → 弹窗友好提示"请先配置券商费率"。
- signal alert (system_alert category=signal) 可驱动 cockpit banner / 导航 badge (P1 可选)。

## 范围 (Scope)

- **影响模块**:后端 `schemas/draft.py` · `routers/drafts.py` · `routers/cockpit.py`(序列化) · `routers/portfolio.py`(可卖量) · `routers/market.py`(报价) · 前端 `features/drafts/*` · `features/cockpit/CockpitPage.tsx` · 新 formatter 模块 · `api/client.ts`/`api/types.ts`。
- **不在范围内**:费用预览端点 · 部分成交余量追踪 · 真实券商下单 · 评价系统(P1) · 估值/仓位/news/earnings 卖出触发(P2)。

## 验证 (Verification)

- [ ] `DraftResponse` 含全部实战字段、不含 v1 管道字段;`trigger_source` 对 BUY/SELL 均正确 (buy_ladder→区间建仓 / thesis_breach→论点失效)。
- [ ] cockpit drafts 与 `/drafts` 同一 schema,字段无漂移。
- [ ] T+1 可卖量端点 = `position_service.available_quantity` 口径 (当日买入冻结)。
- [ ] 报价端点批量返回,缓存生效。
- [ ] DraftsPage:买卖行渲染正确;BUY 现价列+在区间标记;SELL 可卖股数+无期限 TTL;superseded 与 cancelled tag 可分。
- [ ] 确认成交:预填正确;现金不足/T+1 不够/涨跌停 三类 400 内联报错;涨跌停 force 重提成功;成交后持仓/盈亏 Trade 派生正确。
- [ ] Cockpit teaser:SELL 优先排序;"去处理"跳转;无 inline 弹窗。
- [ ] 浏览器实测金路径 + 边角 (无 fee config / 卖超 / 价格越界)。
