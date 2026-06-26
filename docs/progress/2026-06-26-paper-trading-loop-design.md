# 纸面交易评估闭环设计 (Paper-Trading Evaluation Loop)

> **日期**: 2026-06-26
> **状态**: 进行中 (设计已锁定,实施未开始)
> **关联**: `docs/standards/trading-philosophy.md` (双引擎权威) · `docs/active/v2-implementation-plan.md` (8 阶段交付清单) · grill-me 评估会话 2026-06-26

## 目标 (Goal)

把 Gojira 从"只会买"补成完整的**买卖信号 → 自动记录 → 用户手动券商操作 → 回填实际价 → 持仓/盈亏跟踪**闭环,目的是**纸面跟踪验证系统选股能否稳定盈利**,据此判断是否值得真正接入券商接口实现自动买卖。每条买入/卖出记录同时携带**系统建议价**与**实际手动成交价**,便于持续对比两者差异(滑点 + 是否听信号)。

## 背景:当前完成度评估 (grill-me 2026-06-26)

以 `trading-philosophy.md` 双引擎规格为真相源核对,**买入主链路已闭环,但"证伪监控 → 卖出"半边、度量系统、评估/部署收尾基本未做**。

**已实现**:双引擎选股 (quality_screen 复利 + theme_scan 主题) → deep_research 四师评分 (profile 切换 + 同源折叠) → synthesis (8 红线 + 三策略价格区间) → **买入** Draft (双 thesis) → Cockpit/Reports 可视化。规格 §7.3 整合清单 1-9 实质完成。

**真实缺口** (本设计要补):
1. 卖出闭环完全缺失 — `draft_generator` 只有 `generate_buy_drafts`;thesis_tracker 判 INVALIDATED 后无下游;`sell_trigger`/`valuation_trigger` 不存在
2. news_pulse 未接线 — 缺 `PriceChange ±5%` 事件,代码空转
3. earnings_review 未接线 — 缺 `EarningsPublished` 事件,代码空转
4. 度量系统 Tier1/2/3 缺失 — `services/metrics/` 不存在,`decision_audit` 表 0 producer
5. 实际成交价回填 / 建议-vs-实际对比 — 无此流程

**次级 / 延后**:Eval Set + E2E (原 Phase 7)、部署收尾 (原 Phase 8)、theme_scan 自动主题发现 (规格内显式延后)。
**清理债**:`scheduler.py` 残留 v1 孤儿 job 函数 (未注册,不崩,纯清理)。

## 锁定设计决策 (grill-me 6 问)

| # | 决策 | 理由 |
|---|---|---|
| 基准 | `trading-philosophy.md` 双引擎为功能真相,原 8 阶段计划作交付清单 | pivot 已取代原计划前提 (原计划要删 serenity,pivot 保留并做成 theme_scan) |
| **Q1 实际价归属** | **Trade 账本** (`source_ref→Draft`;paper 阶段 `source=manual`,接券商后 `broker_api`,账本不变) | Trade 模型本就是"all position changes 不可变事件源",`source_ref`/`broker_api` 早已预留 → paper 与真实共用一套账本/盈亏/对比逻辑 |
| **Q2 持仓/盈亏** | **从 Trade 账本事件溯源推导** (推翻旧 Holding-only) | 可审计可回放,组合任意时点可重建;已实现/浮动盈亏、建议-vs-实际滑点同源算出 |
| **Q3 卖出** | 4 类信号 (论点失效优先);建议卖价 = 风控类用触发时现价 / 估值止盈类用公允价×1.3 (算不出退化现价) | 卖出皆风控/证伪驱动的"该走了"=市价离场;止盈是唯一有意义目标卖点 |
| **Q4 回填** | UI"确认成交"弹窗填实际价/量/时间 (费用按 broker config 自动算) → 生成 Trade;7 天 TTL 过期 = cancelled (不生成 Trade,留作采纳率统计);实际可自由偏离建议 | 偏离本身就是要观测的数据 |
| **Q5 评价** | 四层指标 + 沪深300 主基准 + 夏普单列;暂不做行业归因 | 见下 |
| **Q6 冷启动/提醒** | CSV 真实持仓 → 开仓 Trade (`source=csv_import`);一本账 + 归因分离;提醒 = in-app system_alert | 既能监控老持仓,又能干净评价"系统自己选的票" |

### Q3 卖出信号表

| 触发 | 来源 | 建议数量 | 建议卖出价 |
|---|---|---|---|
| 论点失效 INVALIDATED | thesis_tracker (已周跑) | 清仓 100% | 触发时现价 |
| 基本面恶化 | news_pulse / earnings_review (待接线) | 清仓 100% | 触发时现价 |
| 估值过高 > 公允 1.3x | 每日估值扫描 (待建) | 减仓 50% 止盈 | 公允价 × 1.3 |
| 单股仓位 > 15% | 组合检查 | 减仓回到 10% | 触发时现价 |

### Q5 四层评价指标 (数据全部来自 Trade 账本)

1. **组合层**:累计总收益率 + equity curve + **vs 沪深300 超额收益 (alpha)**;最大回撤 + 夏普 衡量"稳定"
2. **交易层**:胜率、平均盈/亏比、已实现 vs 浮动盈亏拆分、平均持有周期
3. **双引擎归因 (最关键)**:按 `source` 分别统计 quality_screen 复利 vs theme_scan 主题各自盈亏 — **只统计 `source_ref` 非空 (Draft 触发) 的 Trade**,老持仓买入不计系统战绩,但系统生成的卖出计入
4. **信号质量**:建议价 vs 实际价滑点 (均值/分布)、信号采纳率 (executed/cancelled/expired)、建议价命中率 (实际成交价是否落在建议区间内)

## 闭环数据流

```
买入信号 (draft_generator.generate_buy_drafts) ─┐
卖出信号 (draft_generator.generate_sell_drafts) ─┤  ← thesis_tracker/估值扫描/仓位检查/news_pulse/earnings
                                                ▼
                              Draft (pending, 带建议价) ──► in-app system_alert 提醒
                                                ▼
                              用户去券商手动下单
                                                ▼
                        UI "确认成交" 弹窗 (实际价/量/时间)
                                                ▼
                  Trade (source=manual, source_ref=draft.id, price=实际价)
                  Draft.status = executed
                                                ▼
              position_service 从 Trade 账本重算持仓 + 已实现/浮动盈亏
                                                ▼
              评价指标 (组合/交易/双引擎归因/信号质量) → Cockpit/Reports 视图
```

## 落地计划 (按依赖排序)

### P0 — 闭环地基 (最小可用 paper 闭环)

1. **Trade 派生持仓/盈亏 (地基)**:新建 `position_service`,从 Trade 账本推导当前持仓 + 成本基准 + 已实现/浮动盈亏;CSV 导入改为生成开仓 Trade (`source=csv_import`);`holding_service` 持仓/盈亏计算迁移至 Trade 派生 (Holding 表退役或降为派生视图)
2. **Draft 执行回填**:`POST /api/drafts/{id}/confirm` → 写 Trade (source=manual, source_ref) + `Draft.status=executed`;前端"确认成交"弹窗;过期 sweep job (7 天 → cancelled)
3. **卖出 Draft 生成 (先做论点失效清仓)**:`draft_generator.generate_sell_drafts` 接 thesis_tracker INVALIDATED 下游 → SELL 100% draft (现价)
4. **买卖 Draft → in-app 提醒**:新 Draft 生成时写 system_alert

### P1 — 评价系统

5. **四层指标 service + 前端评估视图**:equity curve / vs 沪深300 / 双引擎归因 / 滑点统计,落 Cockpit 或 Reports

### P2 — 补全卖出触发

6. **估值止盈 + 仓位超限**:每日估值扫描 (>1.3x公允 TRIM 50%) + 组合检查 (>15% TRIM 回 10%)
7. **news_pulse / earnings_review 接线**:`PriceChange ±5%` 事件 (价格监控产出) + `EarningsPublished` 事件 (财报同步检测) → 基本面恶化 → SELL 100%

### P3 — 清理债

8. 删 `scheduler.py` v1 孤儿 job 函数;更新 memory (Trade-账本反转 Holding-only)

## 范围 (Scope)

- **影响模块**:`app/services/position_service.py` (新) · `draft_generator.py` (加 sell) · `draft_service.py`/`trade_service.py`/`holding_service.py` · `app/routers/drafts.py`/`portfolio.py` · `app/core/events.py` (PriceChange/EarningsPublished) · `app/core/event_handlers.py` · `scheduler.py` · `app/services/metrics/` (新) · 前端 Cockpit/Reports/确认成交弹窗 · alembic (Draft 无需新字段;Trade 已够)
- **不在范围内**:真实券商 API 下单 (这正是本闭环要先验证再决定的);自动主题发现;行业归因;Eval Set / E2E (原 Phase 7);Docker 部署收尾 (原 Phase 8)

## 验证 (Verification)

- [ ] 单元测试:`position_service` 持仓/成本基准/已实现盈亏 (FIFO 或移动加权) 纯函数测试
- [ ] 单元测试:`generate_sell_drafts` 四类触发 + 建议卖价规则
- [ ] 端到端:买入信号 → confirm → Trade → 持仓/盈亏正确;论点失效 → 卖出 draft → confirm → 平仓盈亏正确
- [ ] 回归:现有 Trade/Holding/portfolio 测试;CSV 导入 → 开仓 Trade 后持仓数与旧 Holding 口径一致
- [ ] 评价指标:双引擎归因只计 `source_ref` 非空 Trade;滑点 = Trade.price − Draft.target_price
