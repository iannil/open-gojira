# Gojira 下一步计划 (Roadmap)

> **最后更新**: 2026-06-13 (production-readiness-plan 重审后)
> **当前状态**: 402 测试通过,production-readiness S0-S5 已 ship,但 **0 真实使用** — 重审发现 watchlist 闸门静默吞 296 候选股
> **关联**: `docs/progress/STATUS.md` (项目快照) | `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md` (重审决策)

---

## 已完成里程碑 ✅

### 2026-06-13: production-readiness-plan 重审

7 项决策锁定 (基于一次完整 grill-me 会话,详见 `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md`):

1. 删除 PROMOTE 闸门 → 候选股自动评估交易规则
2. EXECUTE + TRADE_ENTRY 合并为单 modal
3. 保留回测引擎 (0 runs,但 #7B 前置依赖)
4. watchlist 去闸门语义,留股池语义
5. **跳过 S6 (Docker/DR)** — 0 实盘前不容器化
6. draft 全表现,Qiu 评分排序
7. **双层闸门**: backtest 验证 + 严格人工评审 (DisciplineChecklistModal)

### 2026-06-12: production-readiness S0-S5 ship

完整 6 阶段计划 (除 S6 外) 全部实现:
- S1 trades/cash/fees 模型 + 迁移
- S2 T+1 + 价格校验 + position sizing
- S3 Lixinger 多层防御 + system_alerts (实测 14 alerts 正常工作)
- S4A corp_actions + S4B historical_* + S4C+D 回测引擎与 UI
- S5 intraday_monitor + 多通道通知 + stop_loss

### 2026-06-11: 第 6 轮全面深度审计修复

6 维度 32 项发现全部修复 (P0×5 + P1×15 + P2×12):
- **P0**: Plan DSL OR 逻辑失效 / 持仓权重计算基数不一致 / total_pnl 价格不可用处理 / 行业权重前后检查不一致 / (另一项架构问题)
- **P1**: LIKE 通配符注入 / Scheduler 并发保护 / strategy_engine inconclusive 状态 / 年化收益率极端值 / + 11 项
- **P2**: 自定义异常替代 HTTPException / EventBus 异步派发 / 批量查询优化 / domain dataclass 转 Pydantic / 33 端点补 response_model / + 7 项

详见 `docs/reports/completed/full-audit-round6-2026-06-11.md`。

### 2026-06-09: 数据管理模块精细化升级

新增 5 Tab (健康概览 / Pipeline 控制 / 股票池 / 质量 / 清理),14 个前端组件,sync 统一到 Pipeline 入口。

### 2026-06-09: 全链路可观测系统

装饰器驱动 + 模块级批量注入,158 函数自动 instrument。

### 2026-06-06: 自动驾驶舱 Step 1-4

四步重定位全部 ship,详见 `docs/progress/2026-06-06-autopilot-step{1,2,3,4}.md`:
- Step 1: cashflow_goal / audit_log / stock.quadrant + Alembic
- Step 2: Plan DSL + 纯函数 evaluator + drafts + scheduler job
- Step 3: cashflow_service + cockpit_service + 前端 4 页 IA
- Step 4: 删除 30+ 旧文件,仅留预案闭环所需

### 2026-06-05: 业务闭环打通

(分析 → 决策 → 持仓) 自动接力,375 测试通过。详见 `docs/reports/completed/2026-06-05-business-loop-closure.md`。

---

## P0: 阻塞真实使用 (立即修)

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | **解 Lixinger token** | ❌ 失效中 | 2026-06-13 实测 token expired,14 条 critical alert silent (只配 in_app)。不解决一切停摆 |
| 2 | **跑首个 backtest** | ❌ 未做 | 回测引擎 ship 但 0 runs。重审决策 #7B 要求"先验证策略再信任 draft"。跑内置 6 策略 5-10 年回测,看 CAGR/Sharpe |
| 3 | **去 watchlist 闸门 (line 494)** | ❌ 未做 | `plan_runner.py:494 if code not in watchlisted: return` 静默吞 296 候选 → 0 draft。改:对所有候选评估交易规则。重审 #1+#4 |

## P1: 架构改动 (重审决策落地)

| # | 项 | 决策来源 | 说明 |
|---|---|---|---|
| 1 | **删除 PROMOTE 流程** | 重审 #1 | candidates 不再走"手动提升 watchlist"通道。Watchlist 仅保留作手动股池 |
| 2 | **合并 EXECUTE + TRADE_ENTRY** | 重审 #2 | 点"执行" → modal 预填 draft → 填 broker 回报 → 存 = trade 写入 + draft 关闭 |
| 3 | **Cockpit draft 按 Qiu 排序** | 重审 #6 | 30-100 draft/天流入,按评分排序展示,用户自选 Top N 深审 |
| 4 | **强制 DisciplineChecklistModal** | 重审 #7B | 10 项纪律 (4 AUTO + 6 MANUAL) 全勾才能启用执行按钮。AUTO 项失败即拒 |
| 5 | **端到端手动验收** (回归) | 既有 P1-1 | round6 修复 + 重审改动后,起 `./dev.sh` → 跑通: token → backtest → draft → checklist → execute → trade → holding |
| 6 | **远程 Git 仓库** | 既有 P1-2 | 当前无 remote,需在 GitHub/GitLab 新建仓库并 push |
| 7 | **CI** | 既有 P1-3 | GitHub Actions 跑 `pytest` + `npm run build`,阻止 main 腐烂 |
| 8 | **cashflow_goal UI 编辑入口** | 既有 P1-4 | 当前只能 API PUT,Cockpit 应加"设定目标"按钮 |
| 9 | **配置 server_chan 通道** | 实测发现 | 当前仅 in_app,14 alerts silent。配 server_chan 微信推送 critical alerts |

---

## P2: 体验补全 (中优先级)

- **月度复盘视图**: 基于 audit_log 时间轴 + 草稿命中率统计。当前 `ReviewPage` 仅基础展示,缺统计图表
- **预案 diff 视图**: 版本切换时显示与上一版的差异 (`PlanDiffDrawer.tsx` 已删除,需重新实现)
- **StockDetail 加入"为该股新建预案"**: 自动回填 `code` 字段
- **候选池筛选持久化**: 当前 7 个筛选条件刷新后丢失,需存到 URL 或 localStorage
- **Cockpit 数据快过期提示**: 当 Lixinger 数据超过 N 天未更新时,UI 给出红色警告

---

## P3: 技术债 (低优先级)

- **holding_service 拆层**: 把 `get_portfolio_summary` 拆成纯计算 + 持久查询两层 (cashflow_service 强依赖)
- **datetime.utcnow() 迁移**: 全部换成 `datetime.now(UTC)` (pytest 跑出 30+ 个 DeprecationWarning)
- **前端 bundle 分块**: esm.js 已 1.1MB,按需拆分 ECharts (`React.lazy` 已就位,但 echarts 全量引入)
- **observability_report.py CLI 分离**: 当前 11 个 `print()` 在文件内,可考虑分离为独立 CLI 模块

---

## 移除的旧路线 (历史决策)

- ~~行业模板评分~~: 文档主张人脑第一性原理判断
- ~~DCF / 内在价值~~: 文档反对精算
- ~~手动纪律打勾 (8 项门控)~~: 纪律已上移到 Plan DSL 的 gates 字段
- ~~candidate_pool 三道筛~~: 被预案 + watchlist 取代
- ~~决策复盘 manual~~: 被 audit_log 自动替代
- ~~预案模板库 (plan_templates 表)~~: 表已删除,内置 4 预案硬编码在 `builtin_seeder.py` 即可
- ~~cashflow_goal.cash_reserve 与 portfolio_settings.cash_reserve 合并~~: portfolio_settings 表已删除 (round4),合并已完成

---

## 不在路线图上 (明确不做)

- 用户认证 / 多用户支持 (个人投资工具)
- PostgreSQL 迁移 (SQLite WAL 已满足并发需求)
- 移动端 App (响应式 Web 已够用)
- 第三方数据源接入 (Lixinger 唯一数据源决策已确认)
- **S6 Docker / DR** (重审 #5, 2026-06-13): 0 实盘前不容器化,先用 dev 模式跑通 2-4 周再回访
- **watchlist 闸门语义** (重审 #4, 2026-06-13): candidates 不再走"手动提升"通道,自动评估交易规则
- **draft Top-N 系统强制阈值** (重审 #6, 2026-06-13): 全表现 + Qiu 排序,用户时间天然约束 N
- **税务 / 合规导出** (原 Q12)
- **交割单 CSV 自动导入** (原 Q13, 用户选择手动录入)
