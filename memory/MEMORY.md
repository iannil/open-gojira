# Gojira 长期记忆

> 此文件是项目内的长期记忆 (沉积层),与 `docs/progress/STATUS.md` 互补。
> `memory/daily/*.md` 是每日笔记 (流层),仅追加。
> 此文件代表**当前真实状态**,过时信息会被更新或移除。
> **注意**: 此文件与 `~/.claude/projects/-Users-rong-zhu-Code-gojira/memory/MEMORY.md` (auto-memory) 是两个独立系统。

## 项目上下文

- **定位**: 个人股票自动驾驶舱 (规则+LLM 混合 → 全流程自动化,除券商下单外)
- **技术栈**: FastAPI (Python 3.14) + React 19 + SQLite (WAL) + Ant Design 6 + ECharts 6
- **当前状态**: **2026-06-24 v2 大重写 Phase 0 完成**。基于新参考 ai-berkshire + serenity-skill,通过 grill-me 锁定 26 条决策,已删除 v1 代码 ~22K 行,5 张 v2 表已建,backend/frontend 验证通过
- **评判锚点**: `docs/active/redesign-decisions-v2.md` (26 决策) — **任何代码/功能必须能追溯到这 26 条之一**,否则 over-engineering。冲突时:此文件 > docs/active/ 其他 > docs/progress/ > memory
- **实施计划**: `docs/active/v2-implementation-plan.md` (8 Phase / 12 周)。当前 Phase 0 已完成,下一步 Phase 1 (LLM 基础设施)
- **分支**: `v2-rewrite` (从 master 切出)
- **远程仓库**: 暂无 (P1 待办)

## v2 核心范式 (2026-06-24 重设)

- **混合架构**: 上层规则筛选 / 中层 LLM 深度研究 / 下层规则+人工审批
- **LLM 模型栈**: GLM 4.8 (后勤) / GLM 5.1 (战术) / GLM 5.2 (战略,top 3 候选) — 替代 Claude
- **数据源**: Lixinger + Zhipu web_search tool (Phase 1),二期加本地公告采集
- **5 核心 Pipeline**: quality_screen / deep_research / thesis_tracker / news_pulse / earnings_review
- **deep_research 内部**: 4 大师 (段永平/巴菲特/芒格/李录) 并行 + Team Lead 综合,6 LLM 调用/家,JSON + Markdown 双输出
- **漏斗容量**: 观察池 30-50 / 候选池 3-5 / Draft 0-3/月,30 天 re-research 缓存
- **Draft 触发**: D 全条件 (价格入区间 + 论文健康 + 组合有空间),仓位 10/30/20,TTL 7 天
- **卖出**: 1+2+3+5 (论文证伪 / 估值 1.3x / 仓位 15% / 基本面恶化),不做止损
- **防御**: 3 层 (Prompt + 代码后验 5% + Pipeline 熔断 20%) + 8 红线否决
- **预算**: 生产 $150/月 + 测试 $100/月,GLM 实际预估 $20-40/月
- **UX**: 信号优先 dashboard,1-click inline 审批,仅应用内通知
- **测试**: Unit + Integration + Eval Set 20-30 家 + Snapshot + E2E
- **DB**: 大重写,保留 Lixinger 数据,不迁移用户决策数据
- **部署**: Docker dev/prod 两环境

## v1 已废弃 (docs/archive/v1/)

- `redesign-decisions-v1.md` (14 决策,基于 invest{1,2,3}.md)
- ADR 0002-0006 (Phase 1 manual→Phase 2 auto / reliability gate / split worker / etc.)
- `2026-06-24-implementation-audit.md` (~5000 LOC 待删审计)

## 用户偏好

(用户首次明确表达偏好时,在此追加)

## 经验教训

- **Plan DSL AND/OR 逻辑** (v1 第 6 轮 P0): `_strategy_definitely_fails` 不能逐条 strategy 独立判断,必须考虑 plan 级 composition。v2 已删除 Plan 概念,此教训归档
- **权重计算基数** (v1 第 6 轮 P0): 持仓权重必须统一用市值 (current_value),不能用成本基数。v2 仍然适用
- **Pydantic dataclass 转换** (v1 第 6 轮 P2): 所有 domain dataclass 必须转 Pydantic 才能用 `.model_dump()` 序列化
- **LIKE 通配符注入** (v1 第 6 轮 P1): search_stocks 必须转义 `%` 和 `_`
- **EventBus 异步非阻塞** (v1 第 6 轮 P2): emit 而非 emit_async 会阻塞主流程
- **Scheduler 并发保护** (v1 第 6 轮 P1): `run_job_now` 必须 threading.Lock + running set
- **APScheduler day_of_week 是 0=Mon 不是 0=Sun** (v1 F14): `CronTrigger.from_crontab()` 不翻译,所有 crontab `1-5` 配置错位一天。v2 仍适用
- **Lixinger 完全不提供 stock_code → 申万行业映射** (v1 F20): 需 AkShare 才能彻底修
- **测试隔离要看 `SessionLocal` 不只看 `get_db`** (v1 F16): scheduler jobs / event_handlers / pipeline manager 用 `SessionLocal()` 直接创建 session
- **GLM SDK httpx timeout 失效** (v1 F23/F26): "连接开但无数据"场景下 SSL read 永久阻塞。需 ThreadPoolExecutor + future.result(timeout=N) 在 Python 层强制超时。**v2 LLMClient 设计要遵循**
- **闰年 Feb 29 触发 backtest ValueError** (v1 F28): try/except fallback 到 Feb 28
- **测试通过 ≠ 真实链路跑通** (v1 F1 教训): ship 必须真实 DB 端到端验证,不只 fixture+unit test
- **大重写必须先备份 DB** (2026-06-24 v2): 即使是Phase 0 删表也要先 backup,中途回滚成本高

## 文档导航 (v2)

- `docs/active/redesign-decisions-v2.md` — **评判锚点(AI 首读)**,26 决策
- `docs/active/v2-implementation-plan.md` — 8 Phase 实施计划
- `docs/archive/v1/` — v1 废弃文档 (redesign-decisions-v1 / ADRs / 审计)
- `docs/standards/serialization.md` — 序列化标准
- `docs/templates/` — 文档骨架
- `docs/reference/ai-berkshire/` — 四大师方法论参考 (gitignored)
- `docs/reference/serenity-skill/` — 产业链卡点方法论参考 (gitignored)

## 维护规则

- 检测到有意义的信息 (用户偏好 / 错误修复模式 / 项目规则) 时,智能合并到本文件
- 信息过时立即更新或移除
- 与 `memory/daily/` 配合:daily 是日志,本文件是浓缩
- 与 `docs/` 配合:docs 是详细版,本文件是高频访问版
