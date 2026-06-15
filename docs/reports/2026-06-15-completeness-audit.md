# 三层完成度审计报告 (2026-06-15)

> **审计日期**: 2026-06-15
> **审计人**: Claude (grill-me 会话)
> **审计对象**: Gojira 当前实现完成度 — 三层 (Phase 2 未提交批次 / Phase 1 ship 清单 / P0 阻塞链)
> **关联文档**: `docs/progress/STATUS.md` | `docs/reference/specs/2026-06-14-serenity-skill-integration.md` | `docs/active/roadmap.md`

## 验收范围 (Scope)

对 Gojira 项目当前实现做一次完整的三层审计,识别真实完成度、隐藏 bug、文档失真:

- **Layer A (未提交批次)**: 14 个修改文件 + 2 个新文件,涉及 Serenity Phase 2 主要项 (Candidate.source / sentinel Plan / Cockpit 卡片 / health/zhipu / LLM log / 反向链接 panel)
- **Layer B (Phase 1 ship 清单)**: 对照 2026-06-14 spec 17 项 ship checklist 逐项核对
- **Layer C (P0 阻塞链)**: roadmap.md 列的 3 个 P0 (Lixinger token / 跑首个 backtest / 去 watchlist 闸门)

**未审计**: 投资理论一致性 (`docs/reference/invest{1,2,3}.md`),前端 e2e 自动化 (无 Cypress/Playwright),Docker / DR (重审 #5 已明确不做)。

## 关键发现 (Top Findings)

1. **STATUS.md 已严重过期** — P0-3 (watchlist 闸门) 实测已完成,STATUS 仍写"未做";backtest 实测 3 次,STATUS 写"0 runs"。需要刷新。
2. **Sentinel Plan pattern 是绕路,非 spec 设计** — Q3 D 决策要求 `Candidate.source='serenity'` 区分来源,但没要求用 sentinel Plan。当前实现是临时绕路,正确做法是 `plan_id` nullable。
3. **7 个 bug 隐藏在 Phase 2 批次中** — 详见下文 [Bug Inventory](#bug-inventory)。
4. **~~Backtest 引擎结构上对当前 6 策略失效~~** (修正于 2026-06-15 晚,详见文末) — 原论断错误。实测 `build_stock_context_at` 已计算 3/4 derived fields。600519 0 trades 是因为标的高估值/低股息,不匹配任何保守策略,**正确行为**。只有 `dividend_sustainability` 缺失影响 2/6 策略。
5. **重审 #7B「双层闸门」仍是有效设计** (修正后) — backtest 验证层对 4/6 策略可用,仅高股息/超跌类受 `dividend_sustainability` 缺失阻塞。

---

## Layer A: Phase 2 未提交批次 审计

### 实测状态

| 项 | 状态 | 备注 |
|---|---|---|
| Candidate.source 字段 + s2 migration | ✅ 实现 | 但 plan_id 仍 NOT NULL,触发 Sentinel Plan 绕路 |
| Sentinel Plan pattern (research_export_service) | ⚠️ 绕路 | Q3 D 未要求,临时绕开 FK 约束 |
| `/api/health/zhipu` 深度探针 | ✅ 实现 | 含 429 quota 检测 |
| LLM log dumping (`data/llm_logs/{run_id}.json`) | ⚠️ CWD 依赖 | uvicorn 从非 backend/ 启动会失败 |
| Cockpit "今日 serenity" 卡片 | ✅ 实现 | 含 empty state + monthly spend |
| Cockpit `monthly_token_spend_cny` 指标 | ✅ 实现 | 但 magic constant 重复硬编码 |
| StockDetail 反向链接 panel | ✅ 实现 | empty state 隐藏 |
| CandidatesPage source badge | ✅ 实现 | badge 列加了 |
| CandidatesPage source filter | ❌ 缺失 | backend 接口已支持,前端未暴露 |
| Export to Candidate (sentinel) | ⚠️ 绕路 | 应改为 plan_id nullable |
| 3 个 e2e mock 测试 | ⚠️ 脆弱 | SessionLocal 共享 session + 写真实文件 |

### Bug Inventory

| # | Bug | 位置 | 影响 | 修复 |
|---|---|---|---|---|
| 1 | `_started` 永远 unset → `elapsed_sec` 始终 0 | `research_runner_service.py:255` | EventBus 事件字段错误值,无下游消费者 | 传 `started` 参数到 `_execute_single_attempt` |
| 2 | LLM log 写相对路径 `data/llm_logs/` | `research_runner_service.py:350` | uvicorn 从非 backend/ 启动失败 | 用 settings.DATA_DIR |
| 3 | `COST_PER_1K_TOKENS_CNY=0.005` 重复硬编码 | `research_runner_service.py:313` + `cockpit_service.py:290` | 调价时漏改,budget 与 cockpit 不一致 | 抽到 `research_config.py` |
| 4 | `scan_scope_json={"type":"manual"}` enum 违规 | `research_export_service.py:_get_or_create_serenity_export_plan` | sentinel Plan 被人手运行会崩 | Sentinel Plan 移除后自动消失 |
| 5 | e2e mock test monkeypatch SessionLocal 共享 session | `tests/test_research_e2e_mock.py` | worker `finally: db.close()` 关掉共享 session,测试间泄漏 | worker 用 with session,或 mock `_dump_llm_log` |
| 6 | `ResearchRun.llm_provider` 硬编码 `glm-4.7` | `research_runner_service.py:111` | 写库 provider 与实际调用 model 不一致 (`.env` 是 glm-5.1) | 改为 `settings.ZHIPU_MODEL` |
| 7 | e2e mock 测试触发 `_dump_llm_log` 写真实文件 | 同 #5 | 测试副作用,污染 `data/llm_logs/` | mock `_dump_llm_log` 或 tmpdir |

### 配置不一致链

```
spec Q5 决策:     glm-5.2 (default)
.env ZHIPU_MODEL:  glm-5.1
SERENITY_RUN_CONFIG["default_model"]: glm-4.7
zhipu_client.py docstring: "GLM-5.2 default ... fallback glm-4.7"
ResearchRun.llm_provider 字段写入: glm-4.7 (硬编码,不看 .env)
实际 LLM 调用 model: glm-5.1 (来自 .env)
```

三个 model 名浮动,docstring 过期。统一为: .env 是唯一真相,`SERENITY_RUN_CONFIG["default_model"]` 作为 fallback。

---

## Layer B: Phase 1 ship 清单 审计

对照 2026-06-14 spec 的 ship 标准 Checklist (17 项):

| # | 项 | 状态 | 备注 |
|---|---|---|---|
| 1 | 后端测试 ≥ 15 个新增 | ✅ | 实际 34 个 (Phase 1) + 3 e2e mock (Phase 2) |
| 2 | Alembic migration 1 个新版本 | ✅ | s1_serenity_research_module + s2_candidate_source_field |
| 3 | 前端 `/research` + 详情页 6 tab + Cockpit + StockDetail + Candidates badge | ✅ | 全到位 |
| 4 | Q10 异步 ThreadPoolExecutor | ✅ | runner executor 与 EventBus executor 隔离 |
| 5 | Q12 失败跳过 | ✅ | scheduler filter `last_run_status != 'failed'` |
| 6 | Q14 index | ✅ | 3 处 stock_code index |
| 7 | Q17 NotificationChannel | ✅ | EventBus → notification_service 复用 |
| 8 | Q18 Markdown 渲染 | ✅ | react-markdown + remark-gfm + rehype-raw |
| 9 | **真实研究跑过 3 次** | ❌ **BLOCKED** | GLM 账号 429 quota 不足 |
| 10 | LLM 完整日志落盘 | ✅ (有 Bug #2) | `data/llm_logs/{run_id}.json` |
| 11 | Cockpit monthly_token_spend | ✅ (有 Bug #3) | 在 cockpit payload |
| 12 | EventBus 事件注册 | ✅ | 3 个新事件 |
| 13 | 失败重试 + 多通道 notification | ✅ | retry_on_failure=1 |
| 14 | scheduler cron `0 8 * * 1` | ✅ | 周一 8am Asia/Shanghai |
| 15 | `.env` 加 ZHIPU_* 模板 | ✅ | .env.example 已配 |
| 16 | `/api/health/zhipu` | ✅ | Phase 2 批次补齐 |
| 17 | 文档 progress + STATUS + 完成报告 | ✅ | Day 7 commit `6098cdd` |

**16/17 done,1 项 external blocked**。

---

## Layer C: P0 阻塞链 审计

| # | 项 | STATUS.md 写的 | 实测状态 |
|---|---|---|---|
| P0-1 | 解 Lixinger token | "expired, 14 alerts silent" | ⚠️ token 在 .env,有效性未验证 (需外部调用 `/api/health/lixinger`) |
| P0-2 | 跑首个 backtest | "0 runs" | ⚠️ **3 runs 已跑过,但 metrics 全 0** |
| P0-3 | 去 watchlist 闸门 (line 494) | "未做" | ✅ **已完成** — `plan_runner.py:10-13` docstring 明示 |

### Backtest 0 metrics ~~根因~~ (修正:见下方"审计错误更正记录")

**原审计论断(已被修正)**: backtest_engine.py docstring 说 derived fields 全 None → 4/6 策略失效 → 0 trades。

**修正后**:docstring 是过期的,实际 `build_stock_context_at` 已计算 3/4 derived fields。0 trades 的真正原因是 600519 (茅台) 高估值 + 低 DYR,不匹配任何保守策略。**0 trades 是正确行为**。

详见文末"审计错误更正记录"。

### 真实生产状态 (DB 实测)

| 实体 | 计数 | 含义 |
|---|---|---|
| holdings | 0 | 无持仓 |
| trades | 6 | 少量测试 |
| drafts | 220 (全 pending) | 累积未执行 (印证 2026-06-13 重审观察) |
| candidates | 264 active + 45 removed (全 rule_based) | 候选池有数据 |
| research_runs | 0 | serenity 完全没真实跑过 |
| backtest_runs | 3 (全 0 metrics) | 见上 |

**结论**: 项目处于"架构完整,等待真实使用"状态。`production-readiness-plan` S0-S5 + 重审 #1/#2/#4/#6/#7B 都已 ship,但用户从未真正使用系统执行交易。

---

## 后续优先级 (Recommended Next Steps)

### P0 — 阻塞真实使用

1. **修 backtest derived fields 限制** — 实现 point-in-time 的 `pe_pct_10y` / `pb_pct_10y` / `dividend_sustainability` / `price_drop_pct` 计算。否则 #7B 双层闸门缺一层,且 backtest UI 误导。
2. **解 GLM 账号余额** — 充值后跑 Phase 1 #9 真实研究验证 (spike 1 + ship 后 2 次)。external blocker。
3. **验证 Lixinger token 有效性** — 调用 `/api/health/lixinger` 看实际状态。

### P1 — Phase 2 commit 落地 (本次 session 执行)

4. ✅ Schema: s2 migration 加 `ALTER COLUMN plan_id DROP NOT NULL`
5. ✅ 删除 Sentinel Plan (research_export_service)
6. ✅ 修 Bug #1 / #2 / #3 / #5 / #6 / #7
7. ✅ 更新测试 + 跑 pytest + commit
8. ✅ STATUS.md 刷新 (commit `508600a`)
9. ✅ CandidatesPage source filter UI (commit `e6e2518`)

### ~~P0-1~~ → **P1** (修正于 2026-06-15 晚)

~~修 backtest derived fields 限制~~ — **审计错误**。实测 `build_stock_context_at` 已计算 pe_pct_10y / pb_pct_10y / price_drop_pct / ocf_to_ni。backtest_engine.py docstring 过期。600519 (茅台) 在 2023-03-01 PIT context 实测:pe_pct_10y=0.51 / pb_pct_10y=0.51 / dyr=0.024 → 所有保守策略正确不通过 → 0 trades 是**正确行为**。

**修正后**:只有 `dividend_sustainability` 缺失(需要历史分红表),影响 2/6 策略(高股息安全垫 / 超跌逆向)。降为 P1。backtest_engine.py docstring 已同步修正。

### P0 — 阻塞真实使用 (修正后)

1. **解 GLM 账号余额** — 充值后跑 Phase 1 #9 真实研究验证 (spike 1 + ship 后 2 次)。external blocker。
2. ~~**验证 Lixinger token 有效性**~~ ✅ **已实测有效** (2026-06-15 晚) — Python 直调 `client.get_company_list()` 拉回 500 股成功 (`永大股份 920126` 等)。`.env` 的 token `2b365f7e-...` 工作正常。STATUS.md 之前说 expired 是过期信息,本次同步修正。

### P1 — 后续

3. 实现 `dividend_sustainability` PIT 计算 (需历史分红事件表 + 窗口计算,影响 2/6 策略 backtest)
4. Phase 2 #9 (失败条件 → 论点变量转译, Q19)
5. Phase 2 #10 (历史 Run diff 视图, Q15)

### P3 — 技术债

6. 统一 GLM model 配置 (spec / .env / SERENITY_RUN_CONFIG / docstring)
7. STATUS.md 自动化生成 (避免再次失真)
8. backtest 数据稀疏警告 (600519 只有 2 条 financials,窗口不足时 UI 应提示)

---

## 结论

- [x] **建议发布 Phase 2 commit**: 是 — `e0a915f` schema 变动 + Sentinel Plan 移除 + Bug #1-#7 修复;`508600a` STATUS.md 刷新;`e6e2518` source filter UI
- [ ] **建议生产可用**: 否 — 两大 external blocker 待解 (GLM quota / Lixinger token 验证)
- [ ] **遗留问题**: 7 项 (P0×2 external + P1×3 + P3×2 + Phase 1 #9 external)

---

## 审计错误更正记录 (2026-06-15 晚)

原报告称 backtest「结构上对当前 6 策略失效」(P0-1)。**这是错误的**。修正依据:

1. `point_in_time_context_service.py:141-203` `build_stock_context_at` 实测**已计算** 3/4 derived fields:
   - `pe_pct_10y` / `pb_pct_10y` (10y 窗口分位,需 ≥30 样本)
   - `price_drop_pct` (52w high 跌幅)
   - `ocf_to_ni` (从 ≤day 发布的最新 financial)
2. 只有 `dividend_sustainability` 未实现(docstring 明示 "needs historical dividend events table")
3. `backtest_engine.py:30-35` docstring 仍写"derived fields 全 None",**已过期**,本次更正同步修复
4. 实测 600519 (茅台) 2023-03-01 PIT context:
   - `pe_pct_10y=0.51` / `pb_pct_10y=0.51` → 高估值,正确不通过 strategy 2 (低估值)
   - `dyr=0.024` → 低于 4% 阈值,正确不通过所有 DYR 依赖策略
   - `price_drop_pct=0.05` → 跌幅不足 20%,正确不通过 strategy 6 (超跌)
5. 3 次 backtest runs 全用 strategy_id=1 (高股息安全垫),该策略依赖 `dividend_sustainability`(PIT 不可用)→ 必然 0 trades。换 strategy 2 / 3 / 4 / 5 仍可能 0 trades (取决于标的是否匹配策略),但**不是结构失效**

**修正影响**:
- 老报告 #7B「双层闸门」实际单层的论断**部分错误**。backtest 验证层**部分可用**(4/6 策略),仅高股息/超跌类策略受 `dividend_sustainability` 缺失阻塞。双层闸门仍是有效设计。
- backtest 模块从「不可用」修正为「可用,但受数据稀疏限制 + 缺 dividend_sustainability」
