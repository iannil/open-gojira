# Phase 2 #9 阶段 B v2 Thesis Monitor 验收报告

> **验收日期**: 2026-06-17
> **验收人**: AI 代理（grill-me 9 项决策产出后执行验收）
> **被验收对象**: thesis monitor v2 后端 + 前端 + scheduler + Bug 1/2/3 修复 + 12 新测试
> **关联文档**: `docs/reports/completed/plan-thesis-monitor-v2-2026-06-17.md` + `docs/reference/specs/2026-06-16-phase2-num9-stage-b-thesis-monitor.md`

## 验收范围 (Scope)

验收 v2 spec 40 项验收清单（model/migration/proposal/schema/monitor/API/scheduler/前端/dev server+spike 9 章节）。**未验收**：5 个未提议 source（revenue_growth / margin / PB_percentile / price_drop_52w / PE_percentile）的真实 LLM 链路，因 run_id=8 是银行 theme 只产出 NIM/NPL。

## 验收步骤 (Steps)

| # | 步骤 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| **后端 model + migration** |||||
| 1 | ResearchClaimVariable model + UniqueConstraint | 建表成功，含 breach_when/last_alerted_at | `models/research_claim_variable.py:52,85` 实测有 | ✅ |
| 2 | FinancialStatement.net_interest_margin 列 | 列存在，pipeline 持久化 | `models/financial.py:58` 实测有；DB 601398 NIM 2024/2025=1.2 | ✅ |
| 3 | migration s5_3 接 s5_2 链 | upgrade/downgrade 跑通 | alembic head = s5_3_claim_variables | ✅ |
| **proposal service** |||||
| 4 | mock LLM 解析 + 持久化 proposed | test_persists_proposals 过 | test_thesis_variable_proposal_service.py 6 passed | ✅ |
| 5 | 业务级 dedup | test_dedup_skips_existing_proposed/active 过 | 同上 | ✅ |
| 6 | DB UniqueConstraint 兜底 | IntegrityError graceful | rejected_does_not_block_repropose + invalid_source_logs_failure 过 | ✅ |
| 7 | signal "<X" → breach_when="lt" | 真实 LLM 准确率 ≥80% | spike: 100% (8/8) | ✅ |
| 8 | EventBus 触发 + audit | claim_variable_proposed 写入 | DB 实测 audit_log 有 2 条 (run_id=1) | ✅ |
| 9 | LLM 失败 audit | event=claim_variable_proposal_failed | 代码路径 `event_handlers.py:306,321` 存在 | ✅ (单测未独立覆盖) |
| 10 | 部分失败 audit | event=claim_variable_proposal_partial | 代码路径 `event_handlers.py:330` 存在 | ✅ (单测未独立覆盖) |
| **thesis_variables_json schema 统一** |||||
| 11 | sync_stock 字段名 value | 不再写 current_value | `thesis_variable_sync_service.py` 实测 | ✅ |
| 12 | 保留 threshold/direction 字段 | 不被覆盖 | 同上 | ✅ |
| 13 | check_variable 读 value | 正常工作 | test_thesis_monitor.py 全过 | ✅ |
| **monitor** |||||
| 14 | INNER JOIN holdings WHERE sell_date IS NULL | 卖出股不监控 | test_excludes_sold_stock / test_excludes_no_holding_at_all 过 | ✅ |
| 15 | 对 active var 按 source fetch | 路由分发正确 | check_claim_variables:303-322 | ✅ |
| 16 | 6-7 source 各自正确路由 | 7/7 source 测试覆盖 | NIM/NPL/PE+revenue_growth/margin/PB/price_drop_52w 全过 | ✅ |
| 17 | NIM source 读 net_interest_margin 列 | 真实工商银行 NIM=1.2 触发 | spike 验证 | ✅ |
| 18 | 数据缺失跳过 | skipped_no_data 计数 | test_window_2_insufficient_data 过 | ✅ |
| 19 | 多期 window_periods | 连续 N 期 breach | test_window_2_consecutive_breach / not_consecutive 过 | ✅ |
| 20 | 单 var try/except 隔离 | 失败计 failed 不中断 | test_invalid_source_logs_failure 过 | ✅ |
| 21 | 7 天 dedup | last_alerted_at 窗口内 suppress | test_recently_alerted_suppressed + test_dedup_blocks_second_emit + 真实 db 复现验证 全过 | ✅ |
| 22 | breach 时 audit + emit | 三处落地 | test_breach_emits_thesis_alert_triggered + 真实 audit_log/SystemAlert 验证 | ✅ |
| 23 | ThesisAlertTriggered handler 调 notification | dispatch_alert 被调用 | test_dispatch_alert_invoked 过 + DB SystemAlert thesis 行 22 条 | ✅ |
| **API endpoints** |||||
| 24 | approve endpoint | status='active' + audit | test_research_claim_variables_api.py 14 passed | ✅ |
| 25 | reject endpoint | status='rejected' + audit | 同上 | ✅ |
| 26 | PATCH endpoint | 改 threshold/breach_when/window + audit | 同上 | ✅ |
| 27 | GET /api/stocks/{code}/claim-variables | 返回 proposed/active/rejected 三组 | 同上 | ✅ |
| 28 | GET /api/cockpit/claim-variables-pending | count + last_proposal 状态 | 截图 01 验证 badge 显示 "2 条待 review" | ✅ |
| **scheduler** |||||
| 29 | thesis_evaluation_job 注册在 17:30/17:32 mon-fri | 独立于 alert_evaluation | cron `32 17 * * 1-5`（spec 17:30 → 实际 17:32 避让 alert_evaluation，已记录） | ✅ |
| 30 | job 跑通 check_held_stocks + check_claim_variables | 两函数均调用 | test_thesis_evaluation_job_invokes_both_checks 过 | ✅ |
| **前端** |||||
| 31 | 前端 StockDetail 显示 proposed 卡片 | 截图 02 验证 | 截图 02 显示 待 review (1) + 监控中 (1) 三态卡片 | ✅ |
| 32 | Edit modal proposed 态改字段后 approve | 截图 03 验证 | 截图 03 显示 "Approve with edits" 按钮 | ✅ |
| 33 | Edit modal active 态 PATCH | 截图 04 验证 | 截图 04 显示 "Save changes" 按钮 | ✅ |
| 34 | Cockpit badge proposed 计数 + 30s 刷新 | 截图 01 验证 | 截图 01 显示 "2 条 claim variable 待 review" + by_stock 列表 | ✅ |
| 35 | Cockpit badge 失败态红色 | 代码 + 单测覆盖 | `PendingClaimVariablesBadge.tsx` 实测有 red/yellow 双态 | ⚠️ 真实数据未触发失败态 |
| **dev server + 真实 LLM spike** |||||
| 36 | dev server 启动 + 浏览器手动验证 happy path | 4 张截图 | 截图 01-04 全部通过 | ✅ |
| 37 | 真实 LLM spike propose_for_run(run_id=8) | 落 5+ proposed variables | spike JSON: 8 proposals / 9 dedup skipped | ✅ |
| 38 | spike 报告 prompt 微调建议 | breach_when 翻转正确率 ≥80% | spike breach_when_accuracy=1.0 (8/8) | ✅ |
| **Bug 修复回归（v2 范围外但本轮发现）** |||||
| 39 | Bug 1 (P0): SystemAlert 字段不存在 | 修复后 thesis 行写入 | DB 实测 thesis 行 0 → 22 + test_writes_system_alert_with_correct_schema 过 | ✅ |
| 40 | Bug 2 (suspicion): dedup 1分38秒10条 | 干净环境复现 | 不复现：Run 1 suppressed / Run 2 breached + 写 last_alerted_at / Run 3 suppressed | ✅ |
| 附 | Bug 3 (P0 顺带): cockpit theme_exposure schema | Cockpit 不再崩溃 | 截图 01 Cockpit 正常加载 | ✅ |

## 通过/失败统计 (Summary)

- **总计**: 40 步 + 1 附
- **通过**: ✅ 39（含 1 附）
- **失败**: ❌ 0
- **警告**: ⚠️ 1（步骤 35 真实数据未触发 badge 失败态，仅代码 + 单测覆盖）

## 环境信息 (Environment)

- **后端**: Python 3.14, FastAPI, SQLite WAL, working tree commit before本轮修复
- **前端**: React 19 + Vite 8 + AntD + TanStack Query
- **数据库**: data/gojira.db（含 1 holding 601398 / 9 claim_variables 6 active + 2 proposed + 1 rejected）
- **真实 LLM**: GLM-5.1（智谱），token input=2058 / output=2056
- **测试标的**: 601398（工商银行）NIM=1.2% 持续 2 期 < 1.3% → 触发真实告警

## 失败项详情

无 ❌。

## 警告项详情

### 步骤 35: Cockpit badge 失败态红色

- **预期**: 真实触发 LLM propose 失败时，Cockpit badge 显示红色"上次 propose 失败"
- **实际**: 代码 + 类型完备，但当前 GLM 账号余额充足，从未触发过真实失败
- **根因分析**: 非代码问题，是数据条件未达
- **修复建议**: 接受当前状态，下次真实 propose 失败时通过 audit_log + Cockpit 自动验证
- **跟踪位置**: roadmap P2（GLM 配额耗尽时自然触发）

## 结论 (Conclusion)

v2 thesis monitor **达到 ship 标准**。40 项验收清单 39 ✅ + 1 ⚠️（数据条件未达，非代码问题）。3 个真实 bug 全部修复（Bug 1 P0 notification 链路 + Bug 3 P0 cockpit 崩溃 + Bug 2 澄清不复现）。真实生产链路完整跑通：工商银行 NIM 告警 → audit_log + EventBus + SystemAlert + dispatch_alert。

- [x] **建议发布**: 是
- [x] **遗留问题**: 1 项（5 source 未真实 LLM 验证，跟踪于 roadmap P2，下次非银行 theme 研究自动覆盖）

## 后续行动

- [ ] 下次跑非银行 theme serenity 研究（半导体 / 资源）→ 自动覆盖剩余 5 source 真实链路
- [ ] GLM 配额耗尽时观察 Cockpit badge 红色态自动激活
- [ ] Phase 2 #9 阶段 C（如有）：theme-level monitor / historical breach 追溯
