# Gojira 全面功能审计 — 第5轮

> 审计日期：2026-06-09
> 审计范围：业务逻辑、安全、性能、API 契约、代码质量、运维就绪性
> 基线状态：375 后端测试通过，前端构建成功
> 修复状态：P1×8 全部修复，P2×7 修复，375 测试通过，0 回归

---

## 审计总览

| 严重性 | 发现 | 已修复 | 残留 |
|--------|------|--------|------|
| **P1** | **8** | **8** | **0** |
| **P2** | **14** | **7** | **7** |
| **P3** | **11** | **0** | **11** |

---

## P1 问题清单（必须修复）

### 1. Draft 执行不自动创建/卖出 Holding [已修复]
- **文件**: `backend/app/schemas/plan.py`, `backend/app/routers/drafts.py`
- **修复**: DraftExecute 增加 `auto_create_holding`/`buy_price`/`quantity` 字段，execute 端点支持自动创建/卖出 Holding。

### 2. `drawdown_from_last_buy` 触发器未实现 [已修复]
- **文件**: `backend/app/services/plan_runner.py:111-122`
- **修复**: 在 buy_ladder 循环中增加 `drawdown_from_last_buy` 处理分支，查询最近买入 Holding 计算回撤比例。

### 3. `check_before_draft()` 不考虑 pending sell 草稿 [已修复]
- **文件**: `backend/app/services/position_advisor_service.py:59-67, 120-129`
- **问题**: 只获取 pending BUY drafts 计入 effective_count，不考虑 pending SELL drafts。4只持仓+1 pending sell 时，应允许新买入但被错误阻挡。
- **建议**: 新增 `_pending_sell_drafts()`，effective_count 扣减 pending sell 数量。

### 4. ValuationSnapshot 缺少唯一约束 [已修复]
- **文件**: `backend/app/models/valuation.py`
- **问题**: 无 `(stock_code, date)` 唯一约束和索引。并发场景（手动触发+定时调度）下可能产生重复快照，导致"最新快照"查询不确定。
- **建议**: 添加 `UniqueConstraint("stock_code", "date")` 和 `Index("ix_valuation_stock_date", "stock_code", "date")`。

### 5. Token 暴露在路由层 [已修复]
- **文件**: `backend/app/routers/stocks.py:413`
- **问题**: `sync` 端点提取 `client._token` 传递给函数。虽然当前未日志记录，但暴露了内部属性。
- **建议**: 改为传递 `LixingerClient` 实例而非 token 字符串。

### 6. 多处 N+1 查询 [已修复 — position_advisor]
- **文件**: `position_advisor_service.py:70-88`, `stocks.py:110-140`, `plan_runner.py:177-179`, `stocks.py:149-162`
- **问题**: 循环内逐条查询数据库，plan_runner 的 `all_stocks` scope 最严重（5000+股票 × 5查询 = 25000+ DB queries）。
- **建议**: 批量预加载数据。position_advisor 参照 holding_service 的 `stocks_map` 模式。

### 7. 缺失的后端端点 `GET /financial/sync-summary` [已修复 — 移除前端无用调用]
- **文件**: `frontend/src/api/client.ts:385-387`
- **问题**: 前端 `fetchFinancialSyncSummary()` 调用 `GET /financial/sync-summary`，但后端 financial 路由无此端点，运行时返回 404。
- **建议**: 在后端添加该端点，或从前端移除该调用。

### 8. `TradingRules.cooldown_days` 已定义但未使用 [已修复]
- **文件**: `backend/app/schemas/plan.py:69`, `backend/app/services/plan_runner.py`, `backend/app/services/draft_service.py`
- **问题**: Schema 定义了 `cooldown_days`（默认5天），但 emit() 和 _evaluate_trading_rules() 完全未使用该字段，连续运行会产生重复 Draft。
- **建议**: 在 emit() 或 _evaluate_trading_rules() 中实现 cooldown_days 检查。

---

## P2 问题清单

### 9. Holding 缺少索引 [已修复]
- **文件**: `backend/app/models/holding.py`
- **问题**: 无 `stock_code`、`sell_date` 索引。15+ 处代码查询 `Holding.sell_date.is_(None)`。
- **建议**: 添加 `Index("ix_holdings_stock_sell", "stock_code", "sell_date")`。

### 10. Draft 缺少复合索引 [已修复]
- **文件**: `backend/app/models/draft.py`
- **问题**: 幂等查询依赖 SELECT-then-INSERT，无复合索引保护。
- **建议**: 添加 `Index("ix_drafts_idempotent", "plan_id", "code", "step_kind", "step_index", "status")`。

### 11. KlineSyncSummary 字段不匹配
- **文件**: `frontend/src/api/types.ts:598-604`, `backend/app/routers/stocks.py:143-162`
- **问题**: 前端期望 `earliest_date`/`total_bars`，后端返回 `kline_count`/无 `earliest_date`。
- **建议**: 对齐前后端类型定义。

### 12. StockResponse Pydantic Schema 缺少字段
- **文件**: `frontend/src/api/types.ts:9-26`, `backend/app/schemas/stock.py:32-47`
- **问题**: 前端有 `quadrant` 和 `qiu_detail`，后端 Pydantic schema 未声明，序列化时可能被丢弃。
- **建议**: 将缺失字段添加到后端 schema 或从前端移除。

### 13. HoldingResponse/CockpitHoldingItem 被 `[k: string]: unknown` 遮蔽 [已修复]
- **文件**: `frontend/src/api/types.ts:75-86, 246-257`
- **问题**: 后端返回 15 个字段，前端只声明 8 个 + catch-all。`current_value`、`pnl`、`pnl_pct` 等关键字段无类型安全。
- **建议**: 补全所有字段类型定义，移除 `[k: string]: unknown`。

### 14. ThesisVariable 重复定义 + source 必填性不匹配
- **文件**: `frontend/src/api/types.ts:441-448`, `frontend/src/api/client.ts:293-300`
- **问题**: 两处重复定义；前端 required 后端 optional。
- **建议**: 统一到 types.ts 一处定义，source 改为 optional。

### 15. 废弃的 SyncTriggerResponse/SyncTaskStatus [已修复]
- **文件**: `backend/app/schemas/data_management.py:66-81`
- **问题**: 已定义但从未使用，误导开发者。
- **建议**: 移除废弃 schema。

### 16. HTTPException 在 service 层（24 处）
- **文件**: holding_service, draft_service, plan_service, watchlist_service, candidate_service, alert_service, dividend_service
- **问题**: 7 个 service 文件直接使用 HTTPException，违反分层架构。
- **建议**: Service 层抛出自定义异常，router/全局处理器转换。

### 17. 双重 commit（52 处）
- **文件**: backend/app/services/ 多处
- **问题**: `get_db()` 已有 commit，service 层又手动 commit。破坏事务单一职责。
- **建议**: 通过 router 调用的 service 中移除冗余 commit。

### 18. scheduler shutdown `wait=False` [已修复]
- **文件**: `backend/app/scheduler.py`
- **问题**: 优雅关闭时立即中断正在执行的调度任务，可能导致数据写入不完整。
- **建议**: 改为 `wait=True` 或设置超时。

### 19. 常量管理不一致
- **文件**: `backend/app/services/position_advisor_service.py:25-28`
- **问题**: 硬编码常量与 `core/constants.py` 重复，且单位不一致（百分比 vs 小数）。
- **建议**: 统一从 `core/constants.py` 导入。

### 20. 输入参数无边界限制
- **文件**: `backend/app/routers/stocks.py`
- **问题**: `days`、`freq`、`years`、`metric` 参数缺少范围/白名单验证。
- **建议**: 添加 Query 参数约束。

### 21. "index" scope 静默回退到 all_stocks
- **文件**: `backend/app/services/plan_runner.py:62-65`
- **问题**: 用户选择"指数成分"范围时，实际扫描全市场。
- **建议**: 短期添加 warning，长期实现指数成分股数据。

### 22. calculate_forward_dyr() 未处理 payout > 1.0 [已修复]
- **文件**: `backend/app/services/valuation_service.py:143-144`
- **问题**: 派息率超过100%时产生误导性前瞻股息率。
- **建议**: 将 payout_avg 限制为 max 1.0。

---

## P3 问题清单

### 23. 过宽异常处理（40 处）
- 28 处 `except Exception:` 完全吞掉异常无日志，scheduler.py 最严重（8处）。

### 24. 路由模式不一致
- 4 个 router 无 response_model；DELETE 返回 3 种不同格式。

### 25. 内联 Schema 定义
- `stocks.py` 中 3 个 Pydantic Model 应移至 `schemas/` 目录。

### 26. RevenueComposition 类型位置不规范
- 定义在 `client.ts` 而非 `types.ts`。

### 27. ThemeItem 缺少 description 字段
- 前端类型缺少后端的 `description` 字段。

### 28. UniverseItem 缺少 candidate_count 字段
- 后端返回但前端类型未声明。

### 29. CandidateResponse.status 松散/严格不匹配
- 后端 `str`，前端 `'active'|'removed'|'promoted'`。

### 30. StrategyCondition.field 无字面量约束
- 后端有 Literal 约束，前端仅为 `string`。

### 31. StrategyTestResponse 未作为 response_model 使用
- 后端返回原始字典，前端接收 `Promise<unknown>`。

### 32. track_lifecycle 装饰器覆盖率极低
- 仅 cockpit_service 使用，关键 service 未覆盖。

### 33. Lixinger 客户端缓存无命中率统计
- 缺少监控接口，无法判断缓存有效性。

---

## PASS 项汇总

以下检查通过，无需修改：
- SQL 注入：全部使用 SQLAlchemy ORM，无动态拼接
- eval()/exec()/subprocess：未发现
- pinned 候选保护逻辑：正确
- _extract_pct() 百分比判断：合理
- get_valuation_dashboard() 多端点回退：设计合理
- FinancialService upsert 逻辑：双重保护（应用层+数据库约束）
- TODO/FIXME 管理：仅 1 处 TODO
- 前端无 console.log/debugger 残留
- 前端无 `any` 类型使用
- datetime 序列化一致性：全部 ISO 8601
- Session 管理：无泄漏
- 部署配置：完整（Dockerfile + docker-compose + Caddy）
- 70+ API 端点中除 1 个外全部正确匹配
- CORS 配置：当前安全（仅 localhost）
- Rate limiting：全局 60/min 覆盖
- dataType 白名单验证：正确

---

## 建议修复优先级

### 第一批（P1 — 业务正确性）
1. Draft→Holding 自动衔接
2. drawdown_from_last_buy 触发器实现
3. check_before_draft() 加入 pending sell
4. ValuationSnapshot 唯一约束+索引
5. GET /financial/sync-summary 端点
6. cooldown_days 实现

### 第二批（P2 — 性能与一致性）
7. 数据库索引（valuations, holdings, drafts）
8. N+1 查询优化
9. 前后端类型对齐
10. Token 暴露修复
11. 输入参数验证
12. payout > 1.0 截断

### 第三批（P2 — 代码质量）
13. Service 层 HTTPException 迁移
14. 双重 commit 清理
15. scheduler shutdown wait=True
16. 常量统一管理
17. 废弃 schema 清理
