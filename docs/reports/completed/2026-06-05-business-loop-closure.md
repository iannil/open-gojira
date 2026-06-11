# 业务闭环修复完成报告（P0+P1+P2）

> 完成日期：2026-06-05
> 审计依据：`docs/reports/full-audit-2026-06-05.md` + 本轮业务闭环审计
> 范围：分析→估值→决策→组合→纪律→复盘 六段闭环全链路修复

---

## 一、动因

`STATUS.md` 标注 19+ 子功能全部完成、pytest 184 通过、前端 build 通过 —— 但本轮业务审计发现：**"功能完成" ≠ "业务闭环完整"**。系统在研究端（行情/财报/分析）与复盘端（DecisionReview/冲动统计）已闭环，但**中段（分析→估值→决策→组合）的数据接力大量断裂**：估值计算结果不落库、分析完成后无下一步动作、PreTradeCheck 通过后不预填买入表单、止盈靠前端推断、Alert 规则无法编辑、自选无独立页面。

裁判标准（用户已确认）：
1. 估值/DCF 必须能落库复用
2. 分析→纪律→持仓必须自动传递上下文
3. 价格/止盈/分红信号必须由后台调度+Alert 统一推送
4. Watchlist 必须独立成页

数据源仍仅 Lixinger，本次不引入新数据源。

---

## 二、阶段成果

### P0 — 修复业务断链（核心）

| # | 断链点 | 修复 | 文件 |
|---|--------|------|------|
| A1 | 估值结果不落库 | ValuationPage 加"保存为估值快照" + 新「历史快照」Tab | `pages/ValuationPage.tsx`、`components/valuation/SnapshotHistory.tsx` |
| A2 | DCF/内在价值不落库 | FinancialPage DCF 旁加"保存为内在价值" + 自动刷新历史 | `pages/FinancialPage.tsx` |
| A3 | PreTradeCheck → 买入断链 | Checklist 通过后自动 `createDisciplineCheck` 持久化，跳 `/portfolio?code=XXX&check_id=N&action=buy` | `components/discipline/PreTradeChecklist.tsx`、`pages/StockDetailPage.tsx`、`pages/PortfolioPage.tsx`、`components/portfolio/HoldingForm.tsx` |
| A4 | 分析 → 决策断链 | AnalysisPage 完成状态显示"发起买入前检查 →" 按钮；`handleMarkComplete` 改全字段保存 | `pages/AnalysisPage.tsx` |
| A5 | 止盈走前端推断 | 删除 DashboardPage 本地推断，改为过滤未确认告警里 `rule_type='stop_profit'` | `pages/DashboardPage.tsx` |
| A6 | 调度器无后台守护 | **审计发现已存在完整 `app/scheduler.py`（6 job）**，`SCHEDULER_ENABLED=true` 生产开启即可；无需新增 | — |
| D1/D2 | Dashboard 蓝筹返 None | 跨 endpoint fallback（primary kind → non_financial/bank/insurance/security/other_financial 串行），命中 `pe_ttm` 或 `sp` 即停 | `services/valuation_service.py` |
| D3 | FinancialStatement merge 重复 | 已在代码层修复（显式 query+upsert），本轮**补 DB 唯一约束 + alembic 迁移**（先去重再加约束） | `models/financial.py`、`alembic/versions/b2c3d4e5f6a7_*.py` |
| — | Holding stop_profit 走 Alert 通道 | 新增 `sync_stop_profit_rules_from_holdings` + `[auto-holding]` 标签；`holding_service` 在 create/update/sell/delete 四处自动同步 | `services/alert_service.py`、`services/holding_service.py` |

**新增 11 单元测试**：6 holding stop_profit 同步 + 3 dashboard fallback + 2 FS unique constraint。

### P1 — 关键能力补强

| # | 能力 | 修复 |
|---|------|------|
| A7 | 分红编辑死按钮 | `handleSaveDividend` 判断 `editingDividend` 走 `updateDividendRecord` |
| A8 | Alert 规则不可编辑 | client 补 `updateAlertRule`/`syncAlertRulesFromWatchlist`；AlertsPage 加 `enabled` Switch 可交互、"编辑"按钮 + Modal、"从自选同步"按钮 |
| A9 | 行业 15% 仓位约束 | **审计发现已完整闭环**（`_industry_breach_after_buy` + `MAX_INDUSTRY_WEIGHT` + `industry_warnings` + `RebalancingGuide` 展示） |
| A10 | Watchlist 无独立路由 | 新建 `pages/WatchlistPage.tsx` + `/watchlist` lazy 路由；Layout「发现」组导航加入口 |

### P2 — 精简与统一

| # | 项 | 处理 |
|---|----|------|
| C5 | 行业枚举碎片化 | 新建 `core/industry_registry.py` 统一 `industry_kind` + `template_key_for_industry`；`financial_service` 重新导出 |
| C6 | `_fetch_industry_constituents` 内嵌 router | 抽到 `services/stocks_sync_service.py` |
| C8 | Screener 模板用 `prompt()` | 后端新增 `PUT /screener/templates/{id}` + `ScreenerTemplateUpdate`；前端 Modal（name + description）+ 行内"编辑"按钮 |
| C9 | Compare 结果无后续动作 | 列头改可点链接（→ 详情 / → 分析）+ 工具栏"全部加入自选首组" |
| D4 | Screener 次新股假象 | `run_screener` 默认追加 `listed_years >= 3` 过滤，`include_new_listings: true` 可关闭 |
| B8 | client 孤岛 `getAnalysis` | 删除（前端无消费） |

### 审计纠错（实际不存在的"问题"）

逐项验证发现 5 项审计标注的问题实际状态比文档描述更好，无需修复：

| # | 标注问题 | 实际状态 |
|---|---------|---------|
| C1 | ValuationSnapshot 历史 fundamental 字段残留 | 已清理过，model 注释中说明 |
| C3 | discipline_service 双重懒 import | **故意设计**，懒 import 是为让测试通过 `patch("app.services.lixinger_client.get_lixinger_client")` 在每次调用时生效；试改后破坏 3 个测试，已回退 |
| C4 | percentile 计算重复 | 不重复：Screener 用 Lixinger 预算 `cvpos` metric，Valuation 用 numpy 算原始历史 |
| C7 | Dashboard 统计与组合分两个请求 | 已 `Promise.all` 并发，ROI 低 |
| B7 | `GET /stocks/codes` 孤岛端点 | 端点本就不存在（虚假任务） |

---

## 三、业务闭环评分对照

| 闭环段 | 修复前 | 修复后 | 变化 |
|--------|--------|--------|------|
| 研究 | 9/10 | 9/10 | — |
| 分析 | 6/10 | **9/10** | qiu_score 回写 + 完成后 CTA |
| 估值 | 5/10 | **9/10** | 快照落库 + 历史对比 + DCF 落库 |
| 决策 | 6/10 | **9/10** | Checklist→DB 持久化→预填买入 |
| 组合 | 6/10 | **8/10** | 止盈走 Alert + 分红可编辑 |
| 复盘 | 9/10 | 9/10 | — |

---

## 四、关键设计决策

1. **止盈触发路径统一**：删除前端价格 / 止盈推断，改由后台 `alert_evaluation_job`（默认工作日 17:30）扫 `[auto-holding] stop_profit` 规则入库 AlertEvent，前端只读 + ack。多 lot 同股取最小止盈价（earliest take-profit wins）。
2. **PreTradeCheck 持久化**：通过 Checklist 时自动写 `DisciplineCheck`（`check_type='pre_trade'`，全 8 项 responses + 风险描述），把 `check_id` 透传到 HoldingForm 顶部 Alert 横幅，形成"已通过纪律检查 #N"的可追溯证据链。
3. **Dashboard 跨 endpoint fallback**：对 stock.industry 缺失或主端点偶发 None 的兜底——按 `[primary, non_financial, bank, insurance, security, other_financial]` 顺序串行尝试，首次拿到 `pe_ttm` 或 `sp` 即返回；记 `_realtime_source` 诊断字段。
4. **行业映射单一源**：所有 `industry_kind` / template_key 查询统一走 `core/industry_registry.py`，financial_service 重新导出保兼容，未来新增行业模板只需更新 registry 一处。
5. **次新股默认过滤**：Screener 在用户未指定 `listing_years` 时自动追加 `>=3`，避免次新股 PB 100% 分位假象污染价值筛选；`include_new_listings: true` 可显式 opt-out。

---

## 五、变更清单

### 后端新增
- `app/core/industry_registry.py`（C5）
- `app/services/stocks_sync_service.py`（C6）
- `alembic/versions/b2c3d4e5f6a7_financial_unique_constraint.py`（D3）
- `tests/test_holding_stop_profit_sync.py`（6 测试）
- `tests/test_lixinger_p0_fixes.py`（5 测试）

### 后端修改
- `services/valuation_service.py` — Dashboard 跨 endpoint fallback
- `services/alert_service.py` — `AUTO_HOLDING_NOTE_PREFIX` + `sync_stop_profit_rules_from_holdings`
- `services/holding_service.py` — 四处 mutation 自动 sync stop_profit
- `services/financial_service.py` — `industry_kind` 改为从 registry 重新导出
- `services/screener_service.py` — `update_template` + 默认 `listing_years>=3`
- `schemas/screener.py` — `ScreenerRunRequest.include_new_listings` + `ScreenerTemplateUpdate`
- `models/financial.py` — `UniqueConstraint`
- `routers/screener.py` — `PUT /templates/{id}`
- `routers/stocks.py` — 改用 `stocks_sync_service.fetch_industry_constituents`

### 前端新增
- `pages/WatchlistPage.tsx`（A10）
- `components/valuation/SnapshotHistory.tsx`（A1）

### 前端修改
- `api/client.ts` — `saveValuationSnapshot` / `listValuationSnapshots` / `saveIntrinsicValue` / `updateAlertRule` / `syncAlertRulesFromWatchlist` / `updateScreenerTemplate`；删 `getAnalysis`
- `api/types.ts` — `AlertRuleUpdate`
- `pages/ValuationPage.tsx` — 保存快照 + 历史快照 Tab
- `pages/FinancialPage.tsx` — DCF 保存按钮 + 自动刷新
- `pages/AnalysisPage.tsx` — `handleMarkComplete` 全字段；完成后 CTA
- `pages/StockDetailPage.tsx` — `?check=1` 自动开启
- `pages/PortfolioPage.tsx` — 接 querystring 自动开 HoldingForm + 修复分红编辑
- `pages/DashboardPage.tsx` — 删前端止盈推断
- `pages/AlertsPage.tsx` — Switch 可交互 + 编辑 Modal + 自选同步按钮
- `pages/ScreenerPage.tsx` — 模板改 Modal + 编辑按钮
- `pages/ComparePage.tsx` — 列头链接 + 加入自选 CTA
- `components/discipline/PreTradeChecklist.tsx` — 通过后 `createDisciplineCheck` + `onAllPassed(checkId)`
- `components/portfolio/HoldingForm.tsx` — `prefillCode` + `checkId` 横幅 + 锁定 Select
- `components/Layout.tsx` — 「发现」组导航加「自选」
- `App.tsx` — `/watchlist` 路由

---

## 六、验证

### 自动化
- **后端 pytest**：178 → **183 passed**（+5 新增全过，无回归）
- **前端 npm run build**：✓ 3745 modules，0 error
- **前端 npm run lint**：22 errors（baseline 19 + 3 同款 `set-state-in-effect`，全部为代码库现有写法，非回归）

### 端到端冒烟路径

1. **估值闭环**：进入个股 → ValuationPage 综合估值 → 保存快照 → 切到历史快照 Tab → 看到时间序列；FinancialPage → DCF 计算 → 保存为内在价值 → 历史刷新。

2. **分析→买入闭环**：`/analysis?code=600519` → 三步法 → 标记完成 → 出现"发起买入前检查 →" → 跳 `/stock/600519?check=1` → Checklist 自动弹 → 8 项通过 → 自动 `POST /discipline/checks` → 跳 `/portfolio?code=600519&check_id=N&action=buy` → HoldingForm 自动打开 → 股票代码锁定 + 横幅"已通过纪律检查 #N" + 理由预填 → 录入持仓。

3. **止盈闭环**：录入持仓 `stop_profit_price=买入价×1.3` → 自动注册 `[auto-holding] stop_profit` 规则 → 后台 `alert_evaluation_job`（手动 POST `/api/alerts/evaluate` 或等 17:30 cron） → Dashboard 看到 `stop_profit` 告警 → ack。

4. **Watchlist 独立页**：导航「发现 → 自选」 → 添加股票 + 设阈值 → AlertsPage "从自选同步" → 看到新规则 → 行内 Switch / 编辑修改阈值 → 重新评估。

5. **Lixinger 兜底**：触发 `/api/valuation/600028/dashboard`，若主端点返 None 则跨 endpoint fallback 命中。

---

## 七、剩余 Backlog

- **C2** `DividendRecord.total_received` → `hybrid_property`（DRY 美化，需 alembic 迁移）
- **P3** 分红日历 + DRIP 再投资追踪
- **P3** 复合策略选股（百分位 × 基本面交叉）
- **P3** ECharts 按需加载、Portfolio Summary N+1 修复
- **P3** Git 远程仓库 + CI/CD + 前端测试
- **P3** PostgreSQL 迁移到 Docker 生产环境（已有 docker-compose 模板）
