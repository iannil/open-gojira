# Gojira 长期记忆

> 此文件是项目内的长期记忆 (沉积层),与 `docs/progress/STATUS.md` 互补。
> `memory/daily/*.md` 是每日笔记 (流层),仅追加。
> 此文件代表**当前真实状态**,过时信息会被更新或移除。
> **注意**: 此文件与 `~/.claude/projects/-Users-rong-zhu-Code-gojira/memory/MEMORY.md` (auto-memory) 是两个独立系统。

## 项目上下文

- **定位**: 个人股票自动驾驶舱 (规则+LLM 混合 → 全流程自动化,除券商下单外)
- **技术栈**: FastAPI (Python 3.14) + React 19 + SQLite (WAL) + Ant Design 6 + ECharts 6
- **当前状态**: **2026-06-26 纸面交易后端闭环全部完成 (P0-1~P0-4)**。全套测试 **555 passed / 0 failed**。买入主链路 + 卖出后端闭环(论点失效→SELL draft / 实际价回填→Trade / in-app signal alert)+ research_v2 API + 报告查看 UI 已建。双引擎评分核心 + serenity theme_scan 引擎 + v1-leftover 清理为前序完成
- **评判锚点(两份互补)**:
  - `docs/standards/trading-philosophy.md` — **交易思想权威**(双引擎/hybrid/评分 profile/去重×3/弃用清单)。取代 invest{1,2,3} 散落约定
  - `docs/active/redesign-decisions-v2.md` (26 决策) — **工程决策锚点**。任何代码必须能追溯,否则 over-engineering
- **实施计划**: `docs/active/v2-implementation-plan.md`。trading-philosophy Phase 2 已基本完成,剩 §7 Draft dual-thesis(绑 Phase-5 draft_generator)+ Phase-3 cockpit dashboard 重建
- **分支**: `master`(v2 已并入);**远程仓库**: 暂无

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

- **交互简洁**:常用「继续」「先 commit」等极简指令推进;偏好我做完一段就停下汇报,而非一口气大改
- **commit 拆分**:倾向按逻辑拆成多个 commit(feature / cleanup / fix 分开),不要一个巨型 commit
- **决策前先调查**:涉及金钱路径/财务语义/feature scope 的分叉,要先调查 v2 意图(读设计文档+代码)再给方案,不擅自猜;真 bug 可直接修,scope 决策要确认
- **遵循 grill-me**:重大设计先 grill 锁定决策再动代码

## v2 双引擎交易体系 (2026-06-25 trading-philosophy.md)

- **双引擎**:价值复利 (ai-berkshire 四大师:段/巴/芒/李) + 产业链卡点 (serenity)。两条选股来源,不互相裁决
- **hybrid 汇合**:serenity 选股 (WHICH) + ai-berkshire 估值/8红线 (PRICE+RISK) → 一张草稿
- **评分 hybrid**:LLM 算分=advisory,**Python 按 source profile 复核为权威分**;`PROFILE_WEIGHTS` 按 source 切(quality_screen 复利 / theme_scan 主题:李录降权+卡点维度)
- **去重×3**:① 持久优势三镜(卡点≈护城河≈好生意)同源**整师折叠**封顶(advantage_source 枚举) ② 证据分级**两层**(条目级 strong/med/weak/lead + 包级 A/B/C,各自归属 evidence_grading / defense_methodology) ③ 失败机制:serenity 失败条件**并入芒格** failure_scenarios(§4.3)
- **持仓/盈亏 = Trade 账本派生(✅ 2026-06-26 完成)**:`position_service` 唯一真相源(移动加权/已实现+浮动盈亏/T+1 冻结);**Holding 模型/表已删**(migration v2_4)。写交易走 `trade_service.record_trade`。详见下方"纸面交易闭环"
- **notifications = 仅 in-app**:外部渠道(NotificationChannel)已弃用,`notification_service.dispatch_alert` 是 no-op,告警走 system_alert_service

## 关键决策 (2026-06-25)

- **trading-philosophy.md 放 docs/standards/**(不是 docs/reference/ —— 后者整目录被 gitignore)
- **Alembic 已压缩为单一基线** `v2_baseline_squash`(down_revision=None,从 Base.metadata.create_all 建全量 schema)。原 52 条迁移因 base 被删而断根、空库无法 upgrade,故 squash。**现有 DB 须 `alembic stamp v2_baseline_squash --purge` 一次**(旧 version_num 已不存在,普通 stamp 会失败)
- **§7 Draft dual-thesis 绑 Phase-5**:v2 无 BUY-draft 生成流程(emit 是无调用方 stub),现在加 Draft 字段=死字段反模式,推迟到 draft_generator 落地时一并做
- **cockpit = Phase-3 stub**:v2 cockpit router 是有意 stub,旧 cockpit_service 已删(孤立 v1)。信号优先 dashboard 待 Phase-3 重建 → **已建**(2026-06-25 后 Phase-3/Phase-5 commits:cockpit aggregator + draft_generator BUY)

## 纸面交易评估闭环 (2026-06-26 grill 锁定,P0 后端闭环已完成)

> 权威文档 `docs/progress/2026-06-26-paper-trading-loop-design.md`。目的:paper 跟踪验证系统选股能否稳定盈利,再决定是否接券商真自动买卖。

- **6 决策**:① 实际价=Trade 账本(source_ref→Draft,manual→broker_api) ② 持仓/盈亏=Trade 派生(推翻 Holding-only,新建 position_service,CSV→开仓 Trade) ③ 卖出 4 信号(论点失效优先),建议卖价=风控类现价/止盈类公允×1.3 ④ 回填=UI"确认成交"弹窗,7天过期=cancelled,实际可偏离建议 ⑤ 评价四层(组合+vs沪深300+夏普/交易/双引擎归因[只算 source_ref 非空]/信号质量滑点) ⑥ 一本账+归因分离,提醒=in-app system_alert
- **P0 后端闭环全部完成 (2026-06-26, 4 commits)**:
  - P0-1 (494a1e3→bfe9894):position_service 唯一真相源 + Holding 模型/表物理删除 (migration v2_4) + T+1 冻结 + 移动加权 + 全消费者切 Trade 派生 + stop_profit 告警退役
  - P0-2 (7eaa72e):`POST /drafts/{id}/execute` 实际价/量/时间回填 → manual Trade(source_ref=draft.id)+ executed;BUY/SELL 通用,可偏离建议
  - P0-3 (44bd63d):thesis_tracker INVALIDATED → 100% SELL draft + supersede pending BUY;周跑 v2_thesis_tracker_job 自动触发
  - P0-4 (97af44c):新买卖 draft → system_alert(category=signal) "应买入/应卖出…回填成交",仅 in-app
- **待办**:P0 前端 UI(drafts 页+确认弹窗+cockpit 信号区,task#9 批量延后);P1 评价系统(四层指标 + 沪深300);P2 估值止盈/仓位超限/news·earnings 接线;P3 删 scheduler v1 孤儿 job
- **research_v2 API + 报告查看 UI** (4d5c6f1):deep_research 路由扩展 + StockDetail 研究触发/报告展示 + ReportsPage

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
- **v2-rewrite 留下大量 v1-leftover** (2026-06-25): service 层多个孤立/半坏服务(cockpit/cashflow/market_temp/universe/notification)靠惰性 import 或 try/except 掩盖,app 能启动但端点崩;旧 tests/ 树有 ~60 个测已删 v1 功能的死测试 + ~25 个 stale 断言。教训:大重写后必须跑**全套**测试(不只新测试)+ 逐 live 服务 grep 已删模块引用
- **死测试 vs 真 bug 要分辨** (2026-06-25 #15): collection error 的多是 v1 死测试(删);但「测现存 v2 代码却失败」的可能是真 bug(如 universe_service 引用已删模型致 /universe 崩)。不能一律删
- **Lixinger 数据表是 squash 基线的前提** (2026-06-25): alembic 从空库 upgrade 失败的根因是早期 base 迁移被删;凡删迁移文件要确认不破坏 down_revision 链
- **docstring 的 "0 callers" 不可信** (2026-06-26 文档治理): `datetime_utils.utcnow()` docstring 自称 0 callers,实际 `events.py:17/59` 仍用作 Event timestamp default_factory。删任何函数前必 `grep -rn`,不信注释
- **scheduler.py 是 v1/v2 混合 latent bug 源** (2026-06-26): 残留 v1 孤儿 job 引用已删模块(`watchlist_service`/`plan_runner`/`ResearchRun`);registry 内 `_watched_and_held_codes` 触及从未 import 的 `watchlist_service` → latent NameError。默认 SCHEDULER_ENABLED=false 未暴露,P3 清理

## 文档导航 (v2)

- `docs/progress/STATUS.md` — **高频快照**(2026-06-26 重写为 v2 真相)
- `docs/progress/2026-06-26-v2-architecture-and-progress.md` — **v2 完整架构与进展**(LLM 友好,迭代必读)
- `docs/reports/2026-06-26-codebase-cleanup-audit.md` — 代码库清理审计(冗余/过期/失效项 + 已执行清理)
- `docs/standards/trading-philosophy.md` — **交易思想权威**(双引擎/评分/去重×3/弃用清单/as-is→to-be)
- `docs/reports/completed/2026-06-25-legacy-cleanup-test-and-migration.md` — 本轮清理完整记录(测试/迁移/服务)
- `docs/active/redesign-decisions-v2.md` — **工程决策锚点(AI 首读)**,26 决策
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
