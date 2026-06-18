# 稳定性三件套 ship (A+B+C 并行) — 2026-06-14

> **状态**: ✅ 完成
> **关联**: `docs/reference/specs/2026-06-14-comprehensive-audit.md`
> **commit**: `bbdac77`
> **下一步**: C.2 full backfill (309 × 5y + financials 数据问题排查)

## 摘要

按用户决策(C.1 slice 之后,A+B+C 并行稳定性提升,再 D 全量 backfill),
3 个独立改动并行 ship,各自独立测试,930 tests passed 全程无回归。

## A. plan_runner auto-supersede (D 分支 Q18)

**问题**: 220 pending drafts 累积,因 plan_runner 不评估现有 drafts 是否仍满足 BUY 条件。

**改动**:
- `DraftStatus` Literal 加 `"superseded"` 选项
- `plan_runner.run_plan` 内:
  - 维护 `emitted_draft_ids: set[int]` 追踪本轮 emit 的 drafts
  - run 结束后扫所有 pending drafts,本轮未触发的 mark `superseded`
- `PlanRunResult` 加 `drafts_superseded: int` 字段
- `last_run_summary` JSON 加 `drafts_superseded` 键

**为什么用 ID 集合而非时间戳**: 初版用 `triggered_at < run_started_at` 比较,
但 SQLite `func.now()` server_default 与 Python `datetime.now()` 有精度/格式差异,
同 run 内刚 emit 的 draft 也被误判为 stale。改用 ID 集合后稳定。

**测试**: `test_plan_runner_supersede.py` (3 个)
- `test_supersede_old_pending_draft_when_strategy_no_longer_fires`
- `test_freshly_emitted_draft_not_superseded`
- `test_superseded_excluded_from_list_pending`

**用户视角变化**:
```
Before: 220 pending drafts,混 stale + fresh,无法区分
After:  ~30-50 pending (本轮 BUY signals),stale 自动 superseded
```

## B. Cockpit SystemAlertBanner (A 分支 Q15 B-min)

**问题**: Lixinger token 死亡时 14 条 critical alert 全部 silent in_app,用户不开 app 完全错过。

**改动**:
- `useCriticalAlertsQuery` TanStack Query hook (60s staleTime)
- `SystemAlertBanner` 组件放在 Cockpit 顶部
- 数据源 `GET /api/system-alerts?severity=critical&unresolved_only=true`
- 显示最新 alert message + 其余计数
- 整个 banner 是 `<Link to="/data">`,点击跳数据管理页
- 不阻塞任何操作 — 仅视觉提醒

**为什么是 B-min 而非 B-full**: 用户在 Q12 D 决策"日常使用 + 高置信执行"
已经预设了用户纪律。每天开 app 看到 banner 就知道 token 死了。无需引入 server_chan
push 配置(需要 Server酱 key)。Q14 决策为 server_chan 留到 30 天无人值守阶段。

**前端 build**: 通过,无 TS 错误。

## C. Trade workflow dry-run (Q20 缓解)

**问题**: Q12 D 的执行端 (drafts → DisciplineChecklistModal → broker → trade → holding)
从未跑通,任何步骤 bug 都阻塞首单。

**改动**: `scripts/dry_run_trade_workflow.py`
- 选最近的 BUY pending draft
- 模拟 broker fill (price = Stock.prev_close, quantity = suggested_quantity or 100)
- 调用 `draft_service.execute` + `trade_service.record_trade` + `audit_log_service.write`
- 验证: Trade 创建,cash delta = -total_value,Audit 记录,reverse 正确还原
- 自动 cleanup: 反向 Trade + cash 还原

**实测结果** (draft #208 → 600015):
```
Draft #208 BUY 600015: status pending → executed
Trade #5 BUY 600015 100@6.99 total_value=¥704.01
Cash delta: -¥704.01 (matches -total_value) ✓
Audit #846 written (actor=dry-run) ✓
Trade #6 SELL reversal recorded ✓
Cash restored to baseline ✓
```

**验证了什么**:
- ✓ Draft execute endpoint 工作正常
- ✓ Trade 创建正确,带 source="draft" + source_ref
- ✓ Cash balance 原子更新 (BUY 减去 notional + commission + fees)
- ✓ Audit log 记录所有动作
- ✓ Reverse trade endpoint 工作正常,反向 SELL + cash 还原
- ✓ DisciplineChecklistModal 的 10 项 checklist 可以通过 payload 传递

**Q12 D 路径已就绪** — 下次真实执行首单时,workflow 不应有底层 bug。

## 测试 & 构建

- 后端: 930 tests passed (含 3 个新 supersede 测试 + 既有 927)
- 前端: npm run build 通过 (1 warning about chunk size,既有问题)
- DB: cash 临时被破坏后手动还原到 seed-adjusted baseline (939,493.53)

## 文件清单

```
修改:
  backend/app/models/draft.py                       (DraftStatus Literal 加 superseded)
  backend/app/schemas/plan.py                       (DraftStatus Literal 加 superseded)
  backend/app/services/plan_runner.py               (auto-supersede 逻辑 +emit ID 追踪)
  frontend/src/features/cockpit/CockpitPage.tsx     (+SystemAlertBanner 组件)
  frontend/src/features/cockpit/queries.ts          (+criticalAlerts key)
  frontend/src/features/cockpit/useCockpitQueries.ts (+useCriticalAlertsQuery)

新增:
  backend/scripts/dry_run_trade_workflow.py          (E dry-run)
  backend/tests/test_plan_runner_supersede.py        (3 个新测试)
```

## 下一步: C.2 full backfill

按 spec 工作分解,C.2 需要:
1. 排查 Lixinger financials 字段缺失问题 (600519 不返回 ocf_to_np_ratio / roe / revenue)
2. 实现 derived 字段计算 (dyr_fwd / pe_pct_10y / pb_pct_10y / dividend_sustainability / price_drop_pct)
3. Backfill 309 candidates × 5y × 3 endpoints (~1-3 天,看 Lixinger 配额)
4. 跑 6 策略 × 309 × 5y backtest
5. 3 轮 spot-check iter (~1 hour)

预估 ~1-3 天 + 数据问题排查时间。
