# Gojira 长期记忆

> 此文件是项目内的长期记忆 (沉积层),与 `docs/progress/STATUS.md` 互补。
> `memory/daily/*.md` 是每日笔记 (流层),仅追加。
> 此文件代表**当前真实状态**,过时信息会被更新或移除。
> **注意**: 此文件与 `~/.claude/projects/-Users-rong-zhu-Code-gojira/memory/MEMORY.md` (auto-memory) 是两个独立系统。

## 项目上下文

- **定位**: 个人股票自动驾驶舱 (策略→预案→候选→草稿→持仓→审计,全流程自动化)
- **技术栈**: FastAPI (Python 3.14) + React 19 + SQLite (WAL) + Ant Design 6 + ECharts 6
- **当前状态**: 402 测试通过,业务闭环已打通 (2026-06-11 第 6 轮审计后)
- **远程仓库**: 暂无 (P1 待办)

## 用户偏好

(用户首次明确表达偏好时,在此追加)

## 关键决策 (ADR-style)

1. **统一预案模型**: 筛选+交易合并到 Plan,删除 PlanExecHistory/PlanTemplate/resource_profiles/portfolio_settings/bank_profiles 表
2. **Pydantic-first 序列化**: ORM→Response 走 schemas + response_model,禁裸 dict (详见 `docs/standards/serialization.md`)
3. **Lixinger 唯一数据源**: 不接 Yahoo/Tushare/AKShare
4. **SQLite + WAL**: 单机部署,不引入 PostgreSQL
5. **EventBus 异步非阻塞**: 与 Scheduler 互补;数据到达后的自动响应链
6. **可观测性装饰器驱动**: 158 函数自动埋点;`OBSERVABILITY_LEVEL=full|compact|off`
7. **行业模板硬编码**: 内置 6 策略 + 4 预案硬编码在 `builtin_seeder.py`,不读外部 JSON
8. **个人使用无认证**: CORS/Rate Limit/文件上传校验等基础防护已就位

## 经验教训

- **Plan DSL AND/OR 逻辑** (2026-06-11 第 6 轮 P0): `_strategy_definitely_fails` 不能逐条 strategy 独立判断,必须考虑 plan 级 composition。OR 预案在 AND 实现下完全失效,这是深层逻辑缺陷,需要整体审计才能发现
- **权重计算基数** (2026-06-11 第 6 轮 P0): 持仓权重必须统一用市值 (current_value),不能用成本基数 (buy_price × quantity)。前后检查也要用相同基数
- **price 不可用 vs 持平** (2026-06-11 第 6 轮 P0): 价格获取失败时 `total_pnl` 应为 None 而非 0,前端显示"数据不可用"。否则用户无法区分
- **Pydantic dataclass 转换** (2026-06-11 第 6 轮 P2): 所有 domain dataclass (RebalanceSuggestion/CycleAssessment/DividendProjection/ThesisAlert) 必须转 Pydantic 才能用 `.model_dump()` 序列化
- **LIKE 通配符注入** (2026-06-11 第 6 轮 P1): search_stocks 必须转义 `%` 和 `_`,否则可枚举全量股票
- **EventBus 异步非阻塞** (2026-06-11 第 6 轮 P2): emit 而非 emit_async 会阻塞主流程;失败 handler 不能影响业务
- **Scheduler 并发保护** (2026-06-11 第 6 轮 P1): `run_job_now` 必须 threading.Lock + running set,否则可耗尽 API 配额

## 文档导航 (与 docs/ 一致)

- `docs/progress/STATUS.md` — 项目当前状态真相 (AI 首读)
- `docs/active/roadmap.md` — 下一步计划
- `docs/standards/serialization.md` — 序列化标准
- `docs/templates/` — 文档骨架
- `docs/reports/completed/` — 已完成的修改 (含 4 轮审计)
- `docs/reports/` — 验收报告
- `docs/reference/` — 投资理论 + 设计规格

## 维护规则

- 检测到有意义的信息 (用户偏好 / 错误修复模式 / 项目规则) 时,智能合并到本文件
- 信息过时立即更新或移除
- 与 `memory/daily/` 配合:daily 是日志,本文件是浓缩
- 与 `docs/` 配合:docs 是详细版,本文件是高频访问版
- 若记忆与 `docs/progress/STATUS.md` 冲突,以 STATUS.md 为准 (实测最新)
