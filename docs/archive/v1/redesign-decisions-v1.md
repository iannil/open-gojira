# Gojira 重新设计决策清单(2026-06-24 grill-me 产出)

> **日期**: 2026-06-24
> **状态**: 锁定(作为后续实施与审计的评判锚点)
> **来源**: grill-me 全程访谈(忽略此前所有 plans/progress,目标不变)
> **目标回顾**: 个人 A 股自动驾驶舱 / 对齐 invest{1,2,3}.md / 除真实券商下单外全自动化 / 架构尽可能简化

## 为什么有这份文档

此前的 `docs/active/roadmap.md` / `production-readiness-plan.md` / `STATUS.md` 等文档堆积了大量「增量改进」决策,但没有从根节点重新审视过「这套系统到底为谁、解决什么、怎么自动化」。2026-06-24 用 `grill-me` 从设计树根部重新拷问 14 次,锁定方向。**本文档是后续所有实施的评判锚点**——任何代码/功能必须能追溯到这 14 条决策之一,否则属于 over-engineering / 范围蔓延。

冲突时:本文件 > docs/active/ 其他文件 > docs/progress/ > memory。

---

## 决策清单(14 条)

### A. 用户与目标层

#### 决策 1 — 纯单用户,不写 speculative 多租户代码

- **使用者**: 当前只有我一人。「多用户」= 预留扩展位,**不实现**
- **不做**: user_id 列、auth 中间件、per-user schema、tenant 隔离
- **做**: ADR 存档「如何迁移到多用户」,真需要(配偶/朋友开口)时再重构
- **依据**: CLAUDE.md 明令「Don't design for hypothetical future requirements」;项目是 Personal use only、无远程仓库
- **推翻**: 现有 ADR #8「个人使用无认证」继续成立;memory 里「未来可扩展」的暗示全部降级为「文档级预留,不落代码」

#### 决策 2 — 主痛点 = 时间(不是纪律)

- **痛点排序**: 时间 > 纪律 > 覆盖 > 审计
- **含义**: autopilot 的首要价值是「替我干活省时间」,不是「拦着我防情绪」
- **张力**: 现有设计是「纪律官」(DisciplineChecklistModal / psychology_alerts / manual execute),每一项都反时间。Phase 1 无法立刻省时间(modal + manual 都在),但为 Phase 2 auto 打基础
- **评判准绳**: 任何「增加用户操作步骤」的功能必须证明其纪律价值 > 时间成本,否则砍

### B. 执行与节奏层

#### 决策 3 — 分阶段执行:Phase 1 manual → Phase 2 auto(per-plan toggle)

- **Phase 1(当前)**: BUY/SELL 都 manual execute,`DisciplineChecklistModal` 保留
- **Phase 2(未来)**: BUY/SELL 都 auto-execute,modal 砍掉
- **迁移单位**: per-plan,不是全局
- **基础设施**: `Plan.auto_execute_enabled: bool` 字段(Phase 1 全部默认 false)
- **代码路径**: 同时支持 manual / auto 两种模式,翻 config 切换,**不允许**「Phase 2 大重写」
- **推翻**: 决策初稿曾选「A 全砍 auto-execute」,被决策 4 的「确认可靠性之前都 manual」推翻
- **详见**: ADR-002

#### 决策 4 — 运行节奏:autopilot daily 跑 + 用户 weekly review

- **autopilot**: 工作日 17:45 daily_plan_evaluation(保留现状)
- **用户**: 周末 batch review,~30min/周 处理 5 天累积 drafts
- **事故**: 6 类事故(决策 11)推桌面通知,不必每天主动查 Cockpit
- **Cockpit 新增**: 「weekly batch review」视图(批量 execute/cancel)+ worker heartbeat 卡片
- **依据**: 周末有大块时间冷静 review,工作日晚上累易情绪化(违反 invest2 §23 心法)

#### 决策 5 — 可靠性闸门:per-plan 5 条件同时满足才翻 auto

每个 plan **独立**评估、独立翻 `auto_execute_enabled`。5 条件同时满足:

1. **时间**: 连续 ≥ 8 周 elapsed(不要求 uptime,见决策 13)
2. **volume**: ≥ 40 个 plan run
3. **零事故**: 6 类事故(决策 11)零触发
4. **paper 不爆雷**: 期间 paper portfolio 不出现离谱亏损(单 plan 亏 30%+ 算爆雷)
5. **你签字**: 月度 review 时看着记录,手动翻开关

- **回滚**: 翻后不放心可单 plan 回滚(false 回去)
- **前置闸门**: 进 paper 之前必须先 backtest 通过(决策 9),否则拿垃圾策略 paper 8 周是浪费时间
- **详见**: ADR-003

### C. 数据与架构层

#### 决策 6 — 数据策略:全量 maximal

- **范围**: 全市场 5626 股,不收窄到 watchlist
- **深度**: 5y K线 + 10y 分红 + 季报财报,全维度
- **代价接受**: backfill 2-3 小时、SQLite 持续膨胀、Lixinger API 配额消耗
- **依赖**: 必须解决 L9(决策 7)、必须有 WAL checkpoint + 维护策略
- **不选分层**: 明确拒绝「on-watch 全量 + off-watch 轻量」,因为不想丢失 watchlist 外的机会
- **评判准绳**: 任何「为省成本而收窄数据范围」的提案都违反此决策,拒绝

#### 决策 7 — 进程模型:拆 API + Worker

- **API 进程**: `uvicorn --reload`,只管 HTTP,**不跑** scheduler/pipeline/plan_runner
- **Worker 进程**: production 模式(无 reload),跑 APScheduler + pipeline manager + plan_runner
- **共享**: 同一 SQLite(WAL 支持多连接并发读 + 单写)
- **IPC**: `job_queue` 表(API 写请求,worker 轮询执行),不上 Celery/Redis
- **EventBus**: 限 worker 进程内
- **入口**: 新增 `backend/app/worker_main.py`
- **解决**: L9(backend reload 中断 daemon thread)从根上消除
- **详见**: ADR-004

#### 决策 8 — 风险熔断:无组合级熔断(Phase 1)

- **保留**: per-draft 三层防护(价格 band ±15% / cash 不足 / industry cap 15%)+ cycle gate
- **不做**: drawdown breaker / cash floor / monthly loss limit / daily trade count
- **防线**: weekly review 是唯一的系统性风险防线
- **风险接受**: Phase 2 翻 auto 后,大盘崩盘可能连环 auto-BUY 抄底(违反 invest3 §5 极端 cycle 才布局)
- **复审点**: 翻 auto 时重新评估是否加 drawdown breaker
- **详见**: ADR-005

#### 决策 9 — 验证机制:backtest + paper 双轨

- **漏斗**: 策略定义 → backtest(历史回放,夏普 > 0 + drawdown < 25%)→ paper(8 周 daily autopilot)→ auto
- **前置**: backtest 是 paper 的前置,**不允许**跳过 backtest 直接进 paper
- **数据成本**: 0(决策 6 maximal 数据已备)
- **backtest engine**: 已有雏形,需强化为「plan 进 paper 的强制闸门」
- **不选 walk-forward**: 复杂度高,单用户没必要

#### 决策 10 — 事故 + 通知:窄定义 6 类 + macOS 桌面通知

**事故**(需立刻决策、推送通知):

1. plan_runner 连续 2 天拒绝跑(freshness gate fail / cycle unavailable)
2. 三层防护连续被触发 ≥3 次/天
3. thesis breach 触发(渣男股)
4. pipeline_runs failed 且 dead_letter 新增 ≥10 条
5. paper portfolio 单日 drawdown ≥ 5%
6. worker 进程崩溃(scheduler 不跑了)

**非事故**(只进 audit_log,不打扰):Lixinger 单次 429、个别 stock 数据缺失、cycle_position 变化、draft 正常 supersede

**通知通道**: macOS Notification(零配置);webhook 留扩展口(未来接 Telegram/钉钉)

### D. 运维层

#### 决策 11 — 运维:全手动(无 supervisor / 无自动 backup)

- **保活**: 无 launchd/systemd,worker 挂了你手动重启
- **backup**: 无自动定时,你手动每周 `cp backend/data/gojira.db /backup/`
- **维护**: 无自动清理,SQLite/日志膨胀你手动处理
- **依据**: 与决策 1/8 一致的 YAGNI 路线
- **风险**: 与决策 5(8 周 reliability gate)冲突,用决策 12 松解
- **强烈建议(不强加)**: 每周至少手动 cp 一次,8 周数据丢不起
- **Cockpit 补救**: worker heartbeat 卡片(weekly review 时一眼看到 worker 是否活着)
- **详见**: ADR-006

#### 决策 12 — Q5/Q11 冲突松解:8 周 = elapsed,不要求连续 uptime

- **解读**: 「8 周连续」= 经过时间 8 周,**不要求** worker 7×24 不挂
- **run count**: DB 持久化,worker 重启后从上次 count 续跑
- **宽限**: 40 run 在 ~10 周内攒够即算过
- **Phase 2 复审**: 翻 auto 后 uptime 才真正关键,届时重新评估要不要 launchd
- **解决**: 决策 5 与决策 11 的冲突

---

## 🔴 Phase 2 必须复审的风险点

| # | 风险 | 触发复审的事件 |
|---|---|---|
| R1 | 决策 2 时间痛点 vs 现有「纪律官」设计 | Phase 1 跑 4-6 周后,你发现 manual execute 仍然太烦 |
| R2 | 决策 6 maximal 数据 + 决策 11 manual 运维 | SQLite 文件 > 500MB 或某次 backfill 中断丢数据 |
| R3 | 决策 8 无组合熔断 | 准备翻 auto 时,或 paper 期间遇到大盘剧烈波动 |
| R4 | 决策 11 全手动运维 + 无 supervisor | worker 挂了 >3 天你没发现(heartbeat 卡片报警) |

---

## 📝 对现有代码的影响(粗估,非实施计划)

### 新增(Phase 1 必做)

| 路径 | 用途 | 决策来源 |
|---|---|---|
| `backend/app/worker_main.py` | worker 进程入口 | 决策 7 |
| `Plan.auto_execute_enabled: bool` | per-plan auto 开关 + alembic migration | 决策 3 |
| `job_queue` 表 + 模型 | API→worker IPC | 决策 7 |
| `backtest_engine` 强化 | plan 进 paper 的前置闸门 | 决策 5 / 9 |
| 事故检测 service + macOS Notification | 6 类事故检测 + 推送 | 决策 10 |
| Cockpit `WeeklyBatchReview` 视图 | weekly batch 操作 | 决策 4 |
| Cockpit `WorkerHeartbeatCard` | worker 存活可视化 | 决策 11 |

### 保留(Phase 1 不动)

- `DisciplineChecklistModal` + manual execute endpoint(Phase 2 才砍)
- 现有 6 策略 + 6 预案 + rule_json DSL(目标 #3 invest 对齐要求)
- 三层 per-draft 防护 + cycle gate
- EventBus / @tracked 可观测性骨架

### Phase 2 才动

- 砍 `DisciplineChecklistModal`(per-plan 翻 auto 时砍)
- manual execute 强制语义 → auto 路径

### 重构(Phase 1)

- APScheduler / pipeline manager / plan_runner 从 API 进程移到 worker 进程

### 审计怀疑对象(待审计报告确认)

以下功能在 grill-me 决策框架下**疑似 over-engineering 或 unaligned**,审计阶段逐个评估:

- `serenity` LLM 研究模块(7 张表 + ThreadPoolExecutor + GLM SDK)— 决策 2 时间痛点下,LLM 研究是时间消耗还是节省?
- `business_patterns` 推断 service — invest 对齐映射里没看到强映射
- `intraday_monitor` / `intraday_price_poll` cron — 决策 4 是 daily + weekly,intraday 与此冲突
- `historical_klines` / `historical_valuations` / `historical_financials` 三张历史表 — 与 backtest 的关系?是否冗余?
- `broker_fee_config` / `holding_risk_rule` / `notification_channels` — 单用户 + 全手动下是否必要?
- `research_search_result` / `research_claim_variable` 等细粒度研究表 — 是否过度规范化?
- 79 个 service 文件 — 是否有职责重叠 / 死代码?

---

## ADR 索引

| ADR | 标题 | 决策 |
|---|---|---|
| 0001 | 不使用 Playwright E2E | (既有) |
| 0002 | 分阶段执行模型(manual → auto per-plan) | 决策 3 |
| 0003 | 可靠性闸门(per-plan 5 条件) | 决策 5 |
| 0004 | 进程模型(拆 API + Worker) | 决策 7 |
| 0005 | 无组合级熔断(Phase 1) | 决策 8 |
| 0006 | 全手动运维模型 | 决策 11 |

---

## 审计挂钩

本文档是「审计评判锚点」。后续 `docs/progress/2026-06-24-implementation-audit.md` 将对照这 14 条决策,逐个评估现有 31 routers / 79 services / 42 models / 17 pages / 24 crons:

- **keep**: 直接服务某条决策,不可或缺
- **simplify**: 服务决策但实现过重,可减负
- **remove**: 不服务任何决策,或与决策冲突,删除
- **defer**: 服务决策但非 Phase 1 必须,推迟

审计报告将作为 `docs/active/roadmap.md` 重写的输入(现有 roadmap 2113 行,很多内容可能在新决策下失效)。
