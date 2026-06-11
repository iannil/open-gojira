# Gojira 第六轮全面深度审计报告

**审计日期**: 2026-06-11
**审计范围**: 6 维度全面覆盖（业务逻辑、安全性、性能、API 契约、代码质量、架构一致性）
**审计方式**: 维度驱动深度审查
**审计基准**: main 分支，375+ 测试通过

## 修复状态：已完成 P0×5 + P1×15 + P2×12（全部 32 项）

所有审计发现已修复，402 测试通过，前端构建成功。
- P0/P1 详细步骤见 `docs/superpowers/plans/2026-06-11-audit-round6-fixes.md`
- P2 最终化计划见 `docs/superpowers/plans/2026-06-11-audit-p2-finalization.md`

---

## 审计发现汇总

| 严重级别 | 数量 | 说明 |
|---------|------|------|
| **P0** | **5** | 数据损坏/业务逻辑错误/系统不可用 |
| **P1** | **15** | 安全漏洞/性能退化/契约不一致 |
| **P2** | **12** | 代码质量/架构偏离/可维护性风险 |
| **合计** | **32** | — |

---

## P0 - 必须立即修复

### P0-01: Plan DSL `_strategy_definitely_fails` 忽略 AND/OR 逻辑
- **文件**: `backend/app/services/plan_runner.py:88-101`
- **问题**: Pass 1 快速淘汰函数逐个检查条件，任一失败即淘汰。但 OR 策略应该任一条件通过即存活。当前逻辑将所有策略都当作 AND 处理。
- **影响**: 使用 OR 逻辑的 Plan 会错误淘汰本应存活的股票，导致投资决策偏差。
- **修复**: Pass 1 淘汰逻辑需感知策略的 AND/OR composition。

### P0-02: Plan 双 pass 筛选未考虑组合逻辑
- **文件**: `backend/app/services/plan_runner.py:284-290`
- **问题**: Pass 1 对每个 strategy 独立判断淘汰，但未考虑 plan 级的 composition（AND/OR）。OR composition 的 plan 应在所有 strategy 都失败时才淘汰。
- **影响**: 与 P0-01 叠加，OR 逻辑的计划完全失效。
- **修复**: Pass 1 需同时评估所有 strategy 和 plan composition。

### P0-03: 持仓权重计算基数不一致
- **文件**: `backend/app/routers/stocks.py:91-108` vs `backend/app/services/holding_service.py:369-387`
- **问题**: Universe 端点用 `buy_price * quantity`（成本基数），Portfolio Summary 用 `current_value`（市值，回退成本）。两者权重百分比不一致。
- **影响**: 同一持仓在 Universe 页和 Cockpit 页显示不同权重，误导资产配置决策。
- **修复**: 统一使用市值计算权重，Universe 也应获取当前价格。

### P0-04: total_pnl 在价格获取失败时为 0
- **文件**: `backend/app/services/holding_service.py:369-374`
- **问题**: 价格获取失败时 `current_value` 回退到成本基数，导致 `total_pnl = total_value - total_cost = 0`，用户无法区分"持平"和"数据不可用"。
- **影响**: 财务准确性受损，可能误导用户以为投资组合不赚不亏。
- **修复**: 价格不可用时 `total_pnl` 应为 `None`，前端显示"数据不可用"而非 "0.00%"。

### P0-05: 行业权重前检查与后警告基数不一致
- **文件**: `backend/app/services/holding_service.py:142-152` vs `386-391`
- **问题**: `_industry_breach_after_buy` 加入新成本后计算行业权重（含新交易的基数），而 `get_portfolio_summary` 用现有市值计算。用户看到 14% 安全，但买入时被拒说超过 15%。
- **影响**: 阻止合法交易并给出混乱错误信息。
- **修复**: 统一行业权重计算基数，或在 UI 上明确标注"含拟买入"。

---

## P1 - 本迭代修复

### P1-01: LIKE 通配符注入
- **文件**: `backend/app/routers/stocks.py:150`
- **问题**: `keyword` 未转义 `%` 和 `_`，可枚举全量股票。
- **修复**: 转义 LIKE 通配符后再拼接。

### P1-02: Scheduler 手动触发无并发保护
- **文件**: `backend/app/scheduler.py:599-633`
- **问题**: 多个并发 `run_job_now` 请求可同时执行同一 job，耗尽 API 配额。
- **修复**: 添加 `threading.Lock` + running set 保护。

### P1-03: `_evaluate_condition` 对不可用数据返回 False
- **文件**: `backend/app/services/strategy_engine.py:65-77`
- **问题**: 不可用字段标记为 `passed=False`，对 AND 逻辑正确但对 OR 逻辑会导致策略意外失败。
- **修复**: 引入 "inconclusive" 状态，OR 逻辑中 inconclusive 不导致失败。

### P1-04: 年化收益率极端值
- **文件**: `backend/app/services/holding_service.py:268-274`
- **问题**: `cost` 极小时 `ratio ** (365/days)` 产生天文数字。
- **修复**: 添加合理上限（如 ±500%）或 `cost` 最小阈值。

### P1-05: 估值百分位边界启发式脆弱
- **文件**: `backend/app/scheduler.py:364`
- **问题**: `val <= 1.0` 判断在 API 返回格式变化时静默损坏所有百分位数据。
- **修复**: 明确 API 返回格式，去除启发式判断。

### P1-06: 止盈价使用不同数据源
- **文件**: `backend/app/services/alert_service.py:254-283` vs `holding_service.py:394-405`
- **问题**: alert 用实时价格，holding 用缓存价格，可能一个触发一个不触发。
- **修复**: 统一数据源，或在触发时同时刷新缓存。

### P1-07: 分红可持续性全零返回"健康"
- **文件**: `backend/app/services/valuation_service.py:191-195`
- **问题**: 三个参数均为 0 时 `0 >= 0 >= 0` 为 True，返回 "healthy"。
- **修复**: 全零时返回 "data_unavailable"。

### P1-08: 负 payout_avg 产生负 DYR
- **文件**: `backend/app/services/valuation_service.py:129-143`
- **问题**: `payout_capped = min(payout_avg, 1.0)` 不截断负值。
- **修复**: `payout_capped = max(0, min(payout_avg, 1.0))`。

### P1-09: Scheduler 串行执行瓶颈
- **文件**: `backend/app/scheduler.py:251-335`
- **问题**: 所有同步 job 串行逐股票处理，50 只股票需 15-30 分钟，5000 只需 2 小时。
- **修复**: 引入 ThreadPoolExecutor 并行批处理。

### P1-10: Cockpit 串行聚合链
- **文件**: `backend/app/services/cockpit_service.py:102-218`
- **问题**: 11 个子服务串行调用，响应时间 2-5 秒。
- **修复**: 独立服务并行化（ThreadPoolExecutor）。

### P1-11: Universe N+1 查询
- **文件**: `backend/app/routers/stocks.py:96-108`
- **问题**: 每只持仓股票单独查询 Holding，50 只 = 51 次查询。
- **修复**: 批量查询后内存映射。

### P1-12: updateThesisVariables 返回类型不匹配
- **文件**: `frontend/src/api/client.ts:290-295` vs `backend/app/routers/stocks.py:434-449`
- **问题**: 前端期望 `void`，后端返回 `StockResponse`。更新后 UI 不刷新。
- **修复**: 前端改为 `Promise<StockResponse>` 并刷新数据。

### P1-13: CockpitDraft 缺失 source 字段
- **文件**: `backend/app/services/cockpit_service.py:63-76`
- **问题**: `_serialize_draft` 未包含 `source` 字段，前端类型定义了但永远 undefined。
- **修复**: 序列化中添加 `"source": d.source`。

### P1-14: Service 层 HTTPException 泄露
- **文件**: 8 个 service，32 处 HTTPException
- **问题**: service 层抛 HTTPException 阻碍 scheduler 复用。
- **修复**: 引入自定义业务异常，router 层捕获转换。

### P1-15: 双 commit 数据一致性风险
- **文件**: 53 处 service 层 `db.commit()` + `get_db` 自动 commit
- **问题**: `create_holding` 有 3 次 commit，中间异常导致部分数据持久化。
- **修复**: 移除 service 层 commit，仅在 `get_db` 统一提交。

---

## P2 - 下迭代修复

### P2-01: Lixinger Token 日志泄露风险
- **文件**: `backend/app/main.py:113-127`
- **问题**: 请求体日志可能包含敏感字段。

### P2-02: Cache key 包含 token
- **文件**: `backend/app/services/lixinger_client.py:83`
- **问题**: `sorted(payload.items())` 包含 token，日志泄露风险。

### P2-03: 交易锁定窗口未实现
- **文件**: `backend/app/config.py:19-20`
- **问题**: 配置存在但无代码使用。

### P2-04: stock_context_builder "batch" 实为串行
- **文件**: `backend/app/services/stock_context_builder.py:135-144`
- **问题**: 函数名暗示批量但实际串行。

### P2-05: Lixinger cache key 不稳定
- **文件**: `backend/app/services/lixinger_client.py:83`
- **问题**: `sorted()` 对嵌套 dict 排序不稳定，20-30% 缓存命中率损失。

### P2-06: SQLite 双重 commit 写锁竞争
- **文件**: `backend/app/db/session.py:14`
- **问题**: get_db + service 双重 commit 增加写锁竞争。

### P2-07: 宽泛 except Exception（36 处）
- **文件**: stock_context_builder.py 等
- **问题**: `except Exception: pass` 完全吞掉异常，bug 永远静默。

### P2-08: json.loads 无异常处理（12 处）
- **文件**: data_service.py:40,48 等
- **问题**: 数据库 JSON 损坏导致 500 错误。

### P2-09: 33 个端点缺失 response_model
- **文件**: 多个 router 文件
- **问题**: 无响应结构验证，前后端可能静默漂移。

### P2-10: Router 直接 DB 查询（36 处）
- **文件**: `backend/app/routers/stocks.py`（占 32 处）
- **问题**: 违反 Routers → Services → Models 分层。

### P2-11: ORM-Response 转换散布（4 种模式）
- **文件**: valuation_service, data_service, cockpit_service, rebalance_service
- **问题**: 手动 dict、dataclass.to_dict、schema.from_orm、service helper 四种模式并存。

### P2-12: EventBus 同步执行阻塞
- **文件**: `backend/app/core/events.py:92-112`
- **问题**: handler 含 DB/API 操作时阻塞请求。

---

## 量化扫描统计

| 指标 | 计数 |
|------|------|
| Service 层 `db.commit()` | 53 处 |
| Service 层 `HTTPException` | 32 处（8 个 service） |
| Service 层 `except Exception` | 36 处 |
| Router 层直接 DB 查询 | 36 处（stocks.py 32 处） |
| `json.loads` 无异常处理 | 12 处 |
| 缺失 `response_model` 端点 | 33 个 |
| 大前端组件 (>500 行) | 3 个（CockpitPage 1220, UniversePage 727, StockDetailPage 630） |

---

## 与前 5 轮审计的关系

- 前 5 轮修复了 23+ 项 P0/P1 问题（分层违规、N+1 查询、缺失约束等）
- 本轮发现均为新问题，主要源于：
  1. 新增功能（Plan DSL、EventBus、Pipeline）引入的逻辑缺陷
  2. 前后端独立开发导致的契约漂移
  3. 已知技术债的深度影响（双 commit、HTTPException 泄露）未充分评估
- P0-01/P0-02（Plan DSL OR 逻辑）是最严重的发现，直接影响投资决策正确性

---

## 修复优先级建议

### 第一批（立即）
1. P0-01 + P0-02: 修复 Plan DSL AND/OR 逻辑（plan_runner.py）
2. P0-03: 统一持仓权重计算基数（stocks.py + holding_service.py）
3. P0-04: 价格不可用时 total_pnl 为 None
4. P0-05: 统一行业权重检查基数

### 第二批（本周）
5. P1-01 ~ P1-08: 安全+业务逻辑修复
6. P1-12 + P1-13: 前后端契约修复

### 第三批（下周）
7. P1-09 ~ P1-11: 性能优化
8. P1-14 + P1-15: 架构修复（HTTPException + 双 commit）

### 第四批（迭代积压）
9. P2-01 ~ P2-12: 代码质量和架构优化

---

## P2 修复记录

### 已修复 P2（12 项 — 全部完成）

| 编号 | 修复内容 | Commit |
|------|---------|--------|
| P2-01 | 请求体日志敏感字段脱敏 | `ecb7bce` |
| P2-02+05 | Lixinger cache key 稳定化 + token 排除 | `cf823ba` |
| P2-03 | 移除未实现的 TRADING_LOCK 配置 | `a5198e3` |
| P2-04 | build_contexts_batch 批量查询优化（N×3→3） | `249ec3d` |
| P2-06 | 移除 5 个 service 中 20 处冗余 commit | `9b000d4`..`1fbb331` |
| P2-07 | stock_context_builder 异常添加日志 | `55a4cf2` |
| P2-08 | json.loads 添加异常处理 | `d88809c` |
| P2-09 | 所有端点补齐 response_model（含 CockpitResponse） | `c6baf7b`..`7c1000f` |
| P2-10 | get_universe 下沉到 universe_service | `13b8924` |
| P2-11 | RebalanceSuggestion + CycleAssessment 转 Pydantic + 标准文档 | `ecef3f1`..`a805e83` |
| P2-12 | EventBus emit_async 非阻塞派发 + 优雅关闭 | `bf4bf09`..`d63b2e3` |

**审计全部 32 项已修复。**
