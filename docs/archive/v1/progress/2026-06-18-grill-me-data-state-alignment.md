# 2026-06-18 grill-me 数据状态完整对齐 → v0.2 起点

> **日期**: 2026-06-18 (21:00–21:45 晚)
> **状态**: 已完成 (待 #3 明天 2026-06-19 17:45 autopilot 触发)
> **关联**: STATUS.md §5.2 (本条已写入里程碑) / `2026-06-18-grill-me-feature-audit.md` (上一轮功能审计) / `wipe_usage_data.py` (本日新增)

## 目标 (Goal)

用户问 "项目基础数据全部更新同步好了吗" 并 invoke `/grill-me`。需求:**完整状态对齐**——Lixinger 数据层 + 业务 action 层 + STATUS.md 文档三层是否都符合"可进入 v0.2 长期运行"的标准。结果是 6 项决策 + 5 项执行清单。

## 范围 (Scope)

- **影响模块**: STATUS.md (文档) / .gitignore / wipe_usage_data.py (脚本) / 任务跟踪
- **不在范围内**: 代码改动 (AdaptiveThrottler wire / price_klines backfill 留作 task #4 后续); Cockpit 排版优化 (用户独立 in-progress)

## 决策 (6 项,grill-me 走完整 design tree)

| # | 分支 | 选择 | 理由 |
|---|---|---|---|
| 1 | wipe 意图 | **进入 v0.2 长期运行前清零** | F29 v0.1-paper-verified 通过 → paper 测试产物可弃 → 干净起点进 v0.2 |
| 2 | 数据就绪标准 | **A: 四大表新鲜 + autopilot 跑通** | "架构尽可能简化" + v0.2 重点是开始跑,不是数据完美 |
| 3 | dividends pipeline failed | **B: 手动重跑验证** | 实测 5 股 pipeline `cd178ed8` 5.8s completed 0 failed,**Lixinger 限流已恢复** |
| 4 | STATUS.md 改写 | **A: 改为 v0.2 起点 + v0.1 artifact 归档** | 文档与实测脱节是最大信任问题,必须明确 |
| 5 | v0.2 验收标准 | **A: autopilot 跑通即验收(去期限化)** | "1 个月长期运行"是人为约束,个人项目无意义 |
| 6 | price_klines 601 股 / corp_actions 0 行 | **B: 全量 backfill price_klines (5354 股)** | contrarian_oversold 策略覆盖不全影响候选池多样性;corp_actions 仅影响 backtest 不修 |

## 变更摘要 (Changes)

| 文件 | 修改类型 | 说明 |
|---|---|---|
| `docs/progress/STATUS.md` | 修改 | 顶部主表 v0.1-paper-verified → v0.2-started; §5.2 加 2 条里程碑 (21:30 grill-me + 21:06 wipe); §5.3 加 4 项 known limitations (L1-L4); 下次 milestone 去 "1 个月" |
| `.gitignore` | 修改 | 加 `backend/data/backups/*.db` / `*.db-shm` / `*.db-wal` (185MB+ 快照不入 git) |
| `backend/scripts/wipe_usage_data.py` | 新增 | 业务 action 表全清脚本 (单事务 + 子→父依赖顺序 + sqlite_sequence 重置) |
| `backend/data/backups/pre-usage-wipe-2026-06-18.db` | 新增 (gitignored) | v0.1 artifact 归档 (2 holdings + 4 trades + 86 drafts + 179 candidates + audit_logs 123 行) |
| `docs/progress/2026-06-18-grill-me-data-state-alignment.md` | 新增 | 本文档 |

## 已知限制 (写入 STATUS.md §5.3)

- **L1**: price_klines 仅覆盖 601/5626 股 (11%) — 不阻塞 Pass 1,仅影响 contrarian_oversold 覆盖
- **L2**: corp_actions 表 0 行 — 仅影响 backtest 准确性
- **L3**: AdaptiveThrottler 是死代码 (F4 复发) — base.py 未 wire,导致全速并发触发 Lixinger 429
- **L4**: dividends pipeline 6-18 00:50 FAILED — 历史状态,已实测验证可恢复

## 验证 (Verification)

- [x] DB 状态实测: stocks 5626 / valuations 14928 (date=今天) / financials 26799 / dividends 48989 (ex_date=2026-06-29) / price_klines 702950 (601股, latest 2026-06-17) / corp_actions 0 / 业务表全 0
- [x] Pipeline 测试: `POST /api/data-management/pipeline/dividends/start` 5 股 → `cd178ed8` status=completed 5/5 0 failed 5.8s
- [x] git commit `7989718` 三件 staged 干净
- [x] backup .db 已 ignore (`git check-ignore -v` 验证)
- [ ] **#3 明天 2026-06-19 17:45 scheduler autopilot 跑首次 v0.2 run**: job_executions 有 daily_plan_evaluation success + candidates/drafts 表非 0 + audit_logs 沉淀

## 下一步 (Next Steps)

- **#3 明天 2026-06-19 17:45** (Asia/Shanghai) 等 scheduler `daily_plan_evaluation` (cron `45 17 * * 1-5`) 触发; 通过 = v0.2-verified (按决策 #5)
- **#4 price_klines 全量 backfill (5354 股)**: 前置需先 wire AdaptiveThrottler (L3 修复,约 30 分钟),再触发 klines pipeline 全量 (预计 1-2 小时 + Lixinger 流量)
- **可选: wire AdaptiveThrottler (L3)** — v0.2 期间根本性稳定性修复,且是 #4 前置
- **可选: dev.sh clear_port + CockpitPage.tsx + theme.css** — 用户独立改动,本任务未触碰,待用户自己决定

## 参考 (References)

- `STATUS.md` §5.2 / §5.3 — 主里程碑 + known limitations 已同步
- `backend/data/backups/pre-usage-wipe-2026-06-18.db` — v0.1 artifact (gitignored)
- `2026-06-18-grill-me-feature-audit.md` — 同日上一轮功能审计 (F14-F28)
- `2026-06-18-feature-audit-drift-findings.md` — 同日早晨 Batch 1-5 后端到端验证 (5 P0)
- commit `7989718` chore(wipe): 进入 v0.2 起点 + STATUS.md 同步 + backup gitignore
