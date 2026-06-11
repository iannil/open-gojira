# Gojira 下一步计划

> 更新日期：2026-06-06（自动驾驶舱 Step 1-4 全部 ship）

## 已完成 ✅

四步重定位全部 ship，详见 `docs/progress/2026-06-06-autopilot-step{1,2,3,4}.md`。

- Step 1：cashflow_goal / audit_log / stock.quadrant + Alembic
- Step 2：Plan DSL + 纯函数 evaluator + drafts + scheduler job
- Step 3：cashflow_service + cockpit_service + 前端 4 页 IA
- Step 4：删除 30+ 旧文件，仅留预案闭环所需

---

## P1：操作收尾

- **端到端手动验收**：起 `./dev.sh` → 建预案 → 立即评估 → 看草稿 → 标记成交 → 验证 audit_log
- **远程 Git 仓库**：当前无 remote，需要在 GitHub/GitLab 新建仓库并 push
- **CI**：GitHub Actions 跑 `pytest` + `npm run build`
- **cashflow_goal UI 编辑入口**：当前只能通过 API PUT，Cockpit 应加"设定目标"按钮

## P2：体验补全

- 月度复盘视图：基于 audit_log 时间轴 + 草稿命中率统计
- 预案模板库：把 PlanEditor 的两个 JSON 预设挪到后端 `plan_templates` 表，可保存自定义模板
- 预案 diff 视图：版本切换时显示与上一版的差异
- StockDetail 加入"为该股新建预案"时回填 `code` 字段

## P3：技术债

- 把 `holding_service.get_portfolio_summary` 拆成纯计算 + 持久查询两层（cashflow_service 强依赖）
- 把 `cashflow_goal.cash_reserve` 与 `portfolio_settings.cash_reserve` 合并（目前两份配置）
- 前端代码分块：esm.js 已 1.1MB，按需拆分 echarts
- 把 `datetime.utcnow()` 全部换成 `datetime.now(UTC)`（pytest 跑出 30+ 个 DeprecationWarning）

## 移除的旧路线

- ~~行业模板评分~~：文档主张人脑第一性原理判断
- ~~DCF / 内在价值~~：文档反对精算
- ~~手动纪律打勾（8 项门控）~~：纪律已上移到 Plan DSL 的 gates 字段
- ~~candidate_pool 三道筛~~：被预案 + watchlist 取代
- ~~决策复盘 manual~~：被 audit_log 自动替代
