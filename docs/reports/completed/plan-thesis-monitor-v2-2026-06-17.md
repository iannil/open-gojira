# Phase 2 #9 阶段 B v2 — Thesis Monitor 接入（含 Bug 1/2/3 修复 + 测试补齐）

> **完成日期**: 2026-06-17
> **开始日期**: 2026-06-16（v2 spec grill-me）
> **作者/执行人**: AI 代理（基于 grill-me 9 项决策执行）
> **关联进度日志**: `docs/reference/specs/2026-06-16-phase2-num9-stage-b-thesis-monitor.md` + 本轮 acceptance report
> **关联 commit**: d429ae6（spec v2） + 32ca600（前端） + e269913（后端） + 本轮修复 commits

## 目标 (Goal)

把 serenity LLM 输出的 structured claims（含 signal 字段）接入 thesis_monitor，实现"失败条件真实告警"—— invest3 "失败预警"闭环。

v2 spec 在一轮 grill 基础上二次 grill 产出 14 项修正，本次会话负责验收 + 修真实 bug + 同步文档，让 v2 真正达到 ship 标准。

## 最终状态 (Final State)

v2 全部 14 项决策已落地：claim.signal → LLM 二次提议 → 用户 review（StockDetail 提议区）→ 自动监控（thesis_evaluation_job 独立 17:32 cron）→ breach 触发 audit_log + EventBus + SystemAlert + notification dispatch。

**真实生产链路已验证**：工商银行（601398）NIM 持续 2 期 1.2% < 1.3% → thesis_alert_triggered audit_log + SystemAlert thesis category + dispatch_alert 真实写入。Bug 1 / Bug 2 / Bug 3 三处阻塞 bug 全部修复。

**测试覆盖**：1075 passed（基线 1063 + 本轮新增 12：4 source 单测 + 3 EventBus emit + 3 handler + 2 scheduler job）。真实 LLM spike artifact `thesis_variable_proposal_2026-06-16T14-33-39Z.json` 验证 breach_when 准确率 100%（8/8，spec 要求 ≥80%）。

## 关键修改 (Key Changes)

### 后端

- `backend/app/core/event_handlers.py`: **修 Bug 1**（P0）。3 处 SystemAlert 创建（serenity 失败 / 月度预算超限 / thesis 告警）误用了模型不存在的字段 `title` / `source` / `payload` / `triggered_at`，AttributeError 被 broad except 静默吞掉，导致所有 thesis 告警的 SystemAlert + notification 链路全断。修复：统一改为模型实际字段（severity / category / message / detail_json），原 title/source 信息并入 detail_json 保留可观察性。实测修复前 SystemAlert thesis 表 0 行 → 修复后 22 行。
- `backend/app/services/thesis_monitor_service.py`: 无代码变更。Bug 2 干净环境验证：dedup 工作正常（Run 1 suppress / Run 2 breach + 写入 last_alerted_at / Run 3 suppress），原始 1分38秒内 10 条同 cv_id audit_log 是 spike/dev 测试残留。
- `backend/tests/test_thesis_monitor_claim_variables.py`: 补 4 个未覆盖 source 单测（`test_financial_revenue_growth` / `test_financial_margin` / `test_valuation_PB_percentile` / `test_kline_price_drop_52w`）+ 3 个 EventBus emit 验证（`test_breach_emits_thesis_alert_triggered` / `test_no_breach_no_emit` / `test_dedup_blocks_second_emit`）。原 13 → 20 测试。
- `backend/tests/test_thesis_alert_handler.py`: **新文件**。3 个 handler 集成测试验证 Bug 1 修复回归：`test_writes_audit_log` / `test_writes_system_alert_with_correct_schema` / `test_dispatch_alert_invoked`。
- `backend/tests/test_scheduler.py`: 加 2 个 thesis_evaluation_job 触发测试（`test_thesis_evaluation_job_invokes_both_checks` / `test_run_job_now_thesis_evaluation_executes`）。

### 前端

- `frontend/src/api/types.ts`: **修 Bug 3**。`ThemeExposure` 类型期望 `{themes, targets, warnings}` 但后端 `/themes/exposure/analysis` 实际返回 `{exposure, targets, warnings}`，导致 Cockpit 加载崩溃（rawData.some is not a function）。新增 `ThemeExposureAnalysis` 类型 + `ThemeExposureItem`，`getThemeExposure` 返回类型对齐。
- `frontend/src/api/client.ts`: `getThemeExposure` 返回类型 `ThemeExposure` → `ThemeExposureAnalysis`。
- `frontend/src/features/cockpit/CockpitPage.tsx`: `ThemeExposureCard` 重写为读 `data.exposure`（list），columns 简化为 主题/权重/市值/数量（删除 target_pct / drift_pct / warning 等不存在的字段）。

### 数据库

- 无 migration 变更。v2 spec s5_3 migration `s5_3_research_claim_variables.py`（research_claim_variables 表 + net_interest_margin 列 + last_alerted_at）已在 e269913 落地。

### 文档

- `docs/progress/STATUS.md`: 顶部表格（最新 commit + 测试数 + Alembic head）+ P2-1 ship + 5.2 里程碑加 2026-06-17 + ADR #13 + 真实使用统计同步。
- `docs/reference/specs/2026-06-16-phase2-num9-stage-b-thesis-monitor.md`: 末尾加 v2 实施完成章节 + 40 项验收清单逐条勾选 + 17:30→17:32 cron 说明。
- `docs/reports/completed/plan-thesis-monitor-v2-2026-06-17.md`: 本文件。
- `docs/reports/thesis-monitor-v2-acceptance-2026-06-17.md`: 验收报告（含 4 张截图引用）。
- `docs/reports/screenshots/thesis-monitor-v2-*.png`: 4 张 dev server 验证截图。
- `~/.claude/projects/.../memory/`: 加 3 条 memory（project-thesis-monitor-v2-ship / feedback-system-alert-schema-mismatch / reference-thesis-monitor-architecture）。

## 测试结果 (Test Results)

```
pytest: 1075 passed, 0 failed (基线 1063 + 新增 12)
- test_thesis_monitor_claim_variables.py: 20 passed (原 13 + 新 7)
- test_thesis_alert_handler.py: 3 passed (新文件)
- test_scheduler.py: 6 passed (原 4 + 新 2)
真实 LLM spike: thesis_variable_proposal_2026-06-16T14-33-39Z.json
  - run_id=8, 11 claims → 8 proposals / 9 dedup skipped
  - breach_when 准确率 100% (8/8, spec ≥80%)
  - source 分布: NIM=5 / NPL=3
  - GLM-5.1 token: input=2058 output=2056
前端 tsc --noEmit: 0 errors
dev server 浏览器手动验证: 4 张截图全部通过
```

## 验收检查 (Acceptance Checklist)

- [x] 功能验收: Cockpit badge + StockDetail 三态卡片 + Edit modal 两态 + scheduler job 真实跑通（详见 acceptance report）
- [x] 回归测试: 1063 → 1075 测试全过，无回归
- [x] 文档更新: STATUS / spec / MEMORY / completed / acceptance 5 处同步
- [x] 性能验收: thesis_evaluation_job 单次跑 < 1 秒（仅 1 持仓）
- [x] Bug 1 (P0) 修复: SystemAlert thesis 行 0 → 22
- [x] Bug 2 (suspicion) 澄清: 干净环境 dedup 正常，原现象是 spike 残留
- [x] Bug 3 (P0 顺带) 修复: Cockpit 不再因 theme_exposure schema 崩溃

## 遗留问题 (Known Issues)

- **5 个 source 未真实 LLM 验证**: revenue_growth / margin / PB_percentile / price_drop_52w + valuation PE_percentile 单测覆盖，但真实 LLM spike 只有 NIM/NPL 两种 source 被提议（因为 run_id=8 是银行 theme）。下次跑非银行 theme（半导体 / 资源）时这些 source 会进入提议 → monitor 自动覆盖。跟踪于 P2 列表。
- **scheduler thesis_evaluation_job 17:32 vs spec 17:30**: 避让 alert_evaluation（17:30），合理调整，spec 已标注。
- **cockpit theme_exposure schema mismatch 是长期 bug**: 不属于 v2 范围，本次顺带修，但 `ThemeExposure` 旧 type 保留为 `@deprecated`，全量删除可放下一轮 cleanup。

## 参考 (References)

- 设计文档: `docs/reference/specs/2026-06-16-phase2-num9-stage-b-thesis-monitor.md`
- 验收报告: `docs/reports/thesis-monitor-v2-acceptance-2026-06-17.md`
- 截图: `docs/reports/screenshots/thesis-monitor-v2-{01-cockpit-badge,02-stock-detail-cards,03-edit-modal-proposed,04-edit-modal-active}.png`
- ADR #13: 见 `docs/progress/STATUS.md` 第 6 节
- 上游 serenity spec: `docs/reference/specs/2026-06-14-serenity-skill-integration.md` Q19
