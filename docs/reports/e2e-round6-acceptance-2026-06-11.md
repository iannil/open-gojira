# E2E Round6 修复回归 验收报告

> **验收日期**: 2026-06-12
> **验收人**: Claude Code (smoke_test.py + 人工 UI 走查)
> **被验收对象**: round6 审计修复 (P0×5 + P1×15 + P2×12)
> **关联文档**: `docs/reports/completed/full-audit-round6-2026-06-11.md`

## 验收范围 (Scope)

验收 round6 中 6 项用户可见/原子性修复:
- P0-03 持仓权重计算基数一致 (Universe vs Cockpit)
- P0-05 行业权重前后检查基数一致
- P0-01/02 Plan DSL OR composition 生效
- P1-12 updateThesisVariables 返回 StockResponse
- P1-13 CockpitDraft 含 source 字段
- P1-15 service 层 db.commit() 已分类 (请求路径 vs 后台)

**未验收**: 其它 26 项 P0/P1/P2 由 402 单元测试覆盖,不在 E2E 范围。

**Base URL**: `http://localhost:3001`

## 验收步骤 (Steps)

| # | 场景 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| 1 | **P1-15** services db.commit() 全部归类到后台路径 | 0 个请求路径 commit;所有 commit 都在 pipelines/scheduler/seeder | background=23, suspicious=2; suspicious 位置: app/services/alert_service.py:352  →  db.commit(); app/services/alert_service.py:384  →  db.commit() | ❌ |
| 2 | **P1-13** CockpitDraft.source 非空 | drafts non-empty (setup should have created some) | drafts=[] — setup failed or no plan produced drafts | ❌ |
| 3 | **P1-12** thesis-variables 返回 StockResponse | response contains: {'code', 'name'} | all required fields present (code=600519) | ✅ |
| 4 | **P0-03** Universe vs Cockpit 权重一致 | max |diff| < 0.1% | max diff = 0.0000% across 1 holdings | ✅ |
| 5 | **P0-05** 行业权重撞上限返回 4xx | 4xx + error message contains industry/weight keyword | HTTP 409; industry keyword found in response | ✅ |
| 6 | **P0-01/02** Plan DSL OR composition 生效 | ≥1 candidate after OR plan run | 871 candidates produced | ✅ |

## 通过/失败统计 (Summary)

- **总计**: 6 场景
- **通过**: ✅ 4
- **失败**: ❌ 2

## Setup Artifacts

- created holding id=1 for 600519
- triggered plan id=1 run: status=200

## 失败项详情 (Failures Detail)

### P1-15 services db.commit() 全部归类到后台路径

- **预期**: 0 个请求路径 commit;所有 commit 都在 pipelines/scheduler/seeder
- **实际**: background=23, suspicious=2; suspicious 位置: app/services/alert_service.py:352  →  db.commit(); app/services/alert_service.py:384  →  db.commit()
- **Artifacts**:
  - `total_commits`: `25`
  - `background_commits`: `23`
  - `suspicious_commits`: `2`
  - `alert_service_note`: `alert_service.py 的 2 处 db.commit() 经 call-graph 确认在请求路径 (sync_stop_profit_rules_from_holdings 经 holding_service 被 router 调; evaluate_all_rules 被 routers/alerts.py:82 直接调)。属 round6 P1-15 尾巴, Task 11 修。`

### P1-13 CockpitDraft.source 非空

- **预期**: drafts non-empty (setup should have created some)
- **实际**: drafts=[] — setup failed or no plan produced drafts

## 后续动作 (γ 分级策略)

- **round6 尾巴**(本应已修但实测未生效)→ 当场修复,新开 commit
- **无关存量 bug** → 开新 P1 ticket,不在本验收 scope
- **cosmetic** → 仅记录

## 环境信息 (Environment)

- **后端 commit**: 见 `git log -1 --format=%H`
- **数据库**: SQLite + WAL,`backend/data/gojira.db`
- **Python**: 见 `python --version`
