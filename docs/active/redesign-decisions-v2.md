# Open Gojira 重新设计决策清单 v2（2026-06-24 grill-me 产出）

> **日期**: 2026-06-24
> **状态**: 锁定（后续实施与审计的评判锚点）
> **基础**: `docs/reference/ai-berkshire/` + `docs/reference/serenity-skill/`
> **目标回顾**: 个人 A 股自动驾驶舱 / 除真实券商下单外全自动化 / 架构尽可能简化
> **与 v1 的关系**: v1（`redesign-decisions.md`）基于 `invest{1,2,3}.md`，**已废弃**。本文档基于新参考体系（ai-berkshire + serenity-skill），是当前权威。

## 为什么有这份文档

2026-06-24 用 `grill-me` 基于新的参考体系（AI Berkshire 16 Skill + Serenity Skill 产业链方法论）从设计树根部重新拷问 20 次，锁定方向。

**核心范式转变**：v1 是「规则驱动 + 纪律官」；v2 是「规则 + LLM 混合 + 研究伙伴」。AI Berkshire 提供四大师对抗的多视角研究框架，Serenity 提供产业链卡点分析方法论，Gojira 把两者自动化成无人值守的 Pipeline。

**本文档是后续所有实施的评判锚点**：任何代码/功能必须能追溯到这 20 条决策之一，否则属于 over-engineering / 范围蔓延。

冲突优先级：本文件 > `docs/active/` 其他文件 > `docs/progress/` > memory。

---

## 决策清单（20 条）

### A. 架构基础（4 条）

#### 决策 1 — 引擎范式：混合架构

- **上层（漏斗入口）**：规则驱动。PE/ROE/现金流/分红等硬指标用 SQL 筛，毫秒级、零成本、可审计
- **中层（深度研究）**：LLM 驱动。四大师视角对抗 + 产业链卡点分析，生成结构化报告
- **下层（决策执行）**：规则 + 人工。LLM 报告的结构化输出转成 Draft，人工 1-click 审批
- **依据**：规则负责"快和便宜"，LLM 负责"深和判断"，人工负责"最终决策"
- **替代方案**：全 LLM（贵且不可复现）/ 全规则（表达力不足）均被否决

#### 决策 2 — LLM 执行：原生 Pipeline

- **选择**：把 ai-berkshire 的 prompt 方法论提取出来，用 GLM API 原生实现，接入现有 `pipelines/` 基础设施
- **不做**：通过 Claude Code CLI / Agent SDK 调用 ai-berkshire Skill
- **依据**：自动驾驶必须自治，能被 scheduler / EventBus / API 触发；多 Agent 并行 = 4 个独立 prompt + 并发，无需 Claude Code 运行时；可观测性要求原生接入 `@tracked`
- **代价**：ai-berkshire 上游更新时 Gojira 不会自动同步（投资方法论变化不快，手动同步可接受）

#### 决策 3 — 数据源：Lixinger + WebSearch

- **Phase 1**：Lixinger（结构化财务）+ Zhipu API web_search tool（实时联网搜索公告/新闻/研报）
- **Phase 2**：加本地公告采集 Pipeline（巨潮/cninfo、东财），高频公司优先
- **不做**：Lixinger only（幻觉风险高）
- **依据**：ai-berkshire 强调多源交叉验证，serenity 要求至少 25 个 source；Lixinger 单源对规则筛选够用但对 LLM 研究远远不够

#### 决策 4 — 模型栈：GLM 替换 Claude

- **战略层（top 3 候选）**：GLM 5.2（对等 Opus 4.7）
- **战术层（默认）**：GLM 5.1（对等 Sonnet 4.6）
- **后勤层（高频）**：GLM 4.8（对等 Haiku 4.5）
- **月度成本上限**：$150 硬熔断（远超实际所需，GLM 比 Claude 便宜 5-10x，实际预估 $20-40/月）
- **熔断行为**：超过 $150 → 暂停 deep_research，保留 thesis_tracker / news_pulse / earnings_review（持仓监控不能停）
- **依据**：中文 A 股任务、成本敏感、Zhipu API 原生支持 web_search + function calling

### B. Pipeline 范围（2 条）

#### 决策 5 — MVP Pipelines：5 个核心

| Pipeline | 触发 | 频率 |
|----------|------|------|
| `quality_screen_pipeline` | Cron | 每日收盘后 |
| `deep_research_pipeline` | Cron + 状态转换 | 每周 + 即时 |
| `thesis_tracker_pipeline` | Cron | 每周 |
| `news_pulse_pipeline` | EventBus（PriceChange ±5%） | 实时 |
| `earnings_review_pipeline` | EventBus（EarningsPublished） | 季度 |

- **二期**：`industry_funnel_pipeline` / `bottleneck_hunter_pipeline`（主题驱动）
- **三期**：交互式工具（investment-checklist / team / portfolio-review / management-deep-dive）
- **不做**：deep-company-series / earnings-team / wechat-article / dyp-ask / private-company-research / industry-research / financial-data（内容创作 / 哲学 / A 股不适用 / 与核心重叠）

#### 决策 6 — deep_research 内部：并行 + 双格式

- **执行模式**：4 大师并行（段永平/巴菲特/芒格/李录）+ Team Lead 综合 = 6 次 LLM 调用/家
- **输出格式**：JSON（结构化评分/信号，喂下游 Pipeline）+ Markdown（人类阅读，ai-berkshire 风格）
- **依据**：并行才是真多视角对抗；单一 LLM 顺序走四大师是"自己跟自己对抗"，张力是假的
- **成本**：Sonnet 等价 ≈ $0.72/家，Opus 等价 ≈ $3.60/家

### C. 候选漏斗与触发（3 条）

#### 决策 7 — 漏斗容量：30-50 / 3-5

- **观察池**：30-50 家（通过 quality-screen 7 条硬指标）
- **研究池**：每周对前 10 家深度研究
- **候选池**：3-5 家（镜子测试通过 + 综合 ≥3.5/5）
- **信号**：0-3 Draft/月（价格进入安全边际区间）
- **依据**：平衡覆盖度与成本；ai-berkshire industry-funnel 实测也是全市场 → 10 → 3

#### 决策 8 — 缓存与关卡：30 天 + 单关卡

- **Re-research 缓存**：30 天。除非财报发布 / 价格 ±15% / 用户强制刷新，否则不重复 deep_research
- **人工关卡**：仅在 Draft 审批（单点）。其他全自动
- **依据**：CLAUDE.md 定位「除真实券商下单外全自动化」；多关卡偏离 autopilot

#### 决策 9 — Draft 触发：D 全条件

- **条件**：价格进入区间 AND 论文未被标记 INVALIDATED AND 组合有空间（现金 ≥20% / 行业 <30% / 单股 <10%）
- **Draft TTL**：7 天，价格离开区间则自动取消
- **Draft 内容**：stock / action / shares / target_price / order_type / reason_ref（研究报告 ID）/ strategy_tier / sizing_logic / thesis_status / expires_at
- **仓位阈值**：单股 10% / 行业 30% / 现金 20%；激进型 100% 目标仓位、稳健型 50%、保守型不生成

### D. 交易信号（2 条）

#### 决策 10 — Draft 仓位规则

- **单股上限**：10% 组合
- **行业上限**：30% 组合
- **现金下限**：20% 组合
- **策略层仓位**：激进型 100%（如 8%）/ 稳健型 50%（如 4%）/ 保守型不生成
- **TTL**：7 天 + 价格离开区间自动取消

#### 决策 11 — 卖出触发：1+2+3+5，无止损

| # | 触发 | 动作 |
|---|------|------|
| 1 | thesis_tracker 标记 INVALIDATED | SELL 100% |
| 2 | 价格 > 综合估值 ×1.3 | TRIM 50% |
| 3 | 单股仓位 > 15%（因上涨） | TRIM 回到 10% |
| 5 | news_pulse 判定"基本面恶化" | SELL 100% |

- **不做**：止损（价值投资哲学，依赖论文证伪 + 估值触发）
- **不做（MVP）**：再平衡（候选评分对比 + 调仓逻辑，二期）
- **依据**：ai-berkshire 不止损；自动驾驶靠多触发组合兜底

### E. 安全与防御（2 条）

#### 决策 12 — 幻觉防御：三层 + 红线

- **Prompt 层**：system_prompt 内置 ai-berkshire 防御方法论（A/B/C 评级 / 2 源规则 / 8 红线 / 留白原则）；LLM 必须在 JSON 输出中带 `evidence_grade` / `uncertainty_flags` / `conflict_warnings`
- **代码后验层**：LLM 输出的 PE/ROE/市值/增速 vs Lixinger 比对，误差 >5% 写入 `data_conflict` 数组（不阻断但标记）
- **Pipeline 熔断层**：近期 50 份报告 conflict 率 >20% → throttler 暂停 + 告警人工介入
- **阈值**：5% 误差 / 20% 冲突率

#### 决策 13 — 8 条红线否决

任一命中 → 报告强制 `rejected`，不进候选池：

1. 管理层诚信污点
2. 财务造假嫌疑（Benford 异常）
3. 重大违规 / 行政处罚
4. 连年亏损（3 年）
5. 高质押（>50%）
6. 频繁减持（控股股东 12 月内 >10%）
7. 复杂关联交易（>30% 营收）
8. 其他重大风险（LLM 标注 + 人工确认）

### F. 运维与可观测（3 条）

#### 决策 14 — 错误恢复：多层

| 失败 | 处理 |
|------|------|
| LLM API 超时/限流 | 指数退避重试 3 次 |
| LLM 返回 malformed JSON | 严格 schema 重试 1 次；再失败 → dead_letter |
| LLM 数据幻觉（post-validation 拦截） | 标记 `data_conflict`，继续 Pipeline |
| LLM 命中红线 | **硬停**，报告 `rejected` |
| Web search 失败 | 降级：仅 Lixinger + `evidence_grade: C` |
| DB 写失败 | Dead letter（复用现有 `dead_letter.py`） |

#### 决策 15 — LLM 可观测性：扩展 @tracked

- **新增 `llm_call_log` 表**：trace_id / model / tokens_in / tokens_out / cost_usd / latency_ms / prompt_hash / conflict_flags / tool_calls
- **扩展 `@tracked` 装饰器**：自动埋点 LLM 调用
- **前端 Pipeline 监控页**：运行状态 / 失败队列 / LLM 成本累计 / 冲突报告

#### 决策 16 — 质量度量：全三层

- **Tier 1（运营健康，实时）**：Pipeline 成功率 / `data_conflict` 率（target <5%）/ `red_line` 触发分布 / 月度 LLM 成本
- **Tier 2（决策质量，3 月后启用）**：Draft 批准率 / 论文证伪率（target <20%/年）/ 批准 Draft P&L vs 沪深300
- **Tier 3（系统校准，6 月后启用）**：四大师评分与后续股价相关性 / 同公司 6 月 research 对比 / 反测 2 年前能筛出什么

### G. 数据与配置（2 条）

#### 决策 17 — 新增 5 张表

| 表 | 关键字段 |
|----|---------|
| `stock_lifecycle` | stock_code, current_state, entered_at, last_research_at, history(JSON) |
| `research_report` | stock_code, pipeline_type, json_output, markdown_output, evidence_grade, data_conflict(JSON), red_line_hit(JSON), expires_at |
| `decision_audit` | draft_id, approved_at, stock_code, target_price, status_30d/90d/365d, benchmark_diff |
| `llm_call_log` | trace_id, model, tokens_in/out, cost_usd, latency_ms, prompt_hash, conflict_flags |
| `red_line_event` | stock_code, red_line_type, triggered_at, report_id, action_taken |

#### 决策 18 — 配置三层

| 层 | 内容 | 改动方式 |
|----|------|---------|
| **UI 可调** | watchlist_size / position_caps / draft_ttl / cost_cap / trim_thresholds | 前端设置页，写入 `app_config` 表 |
| **Config 文件** | model_selection / pipeline schedules / web_search 配置 | `backend/app/config.py` + `.env` |
| **硬编码** | defense_thresholds（5%/20%）/ red_line_rules（8 条）/ prompt 模板 | 代码常量 |

- **依据**：UI 可调 = 用户个性化；Config 文件 = 环境差异；硬编码 = 安全底线（不能让用户调低防御阈值自欺）

### H. 用户体验（2 条）

#### 决策 19 — Dashboard：信号优先

- **布局**：顶部待办信号（Drafts 待审批）/ 中部持仓概览 / 底部候选池 + 观察池
- **审批流**：1-click inline 批准；拒绝必须填理由（喂回 LLM 作反馈）
- **通知**：仅应用内（红点 + signals 列表）。不做邮件 / 微信（MVP）
- **报告阅读**：markdown 渲染（ai-berkshire 风格表格/评分/语录）
- **历史对比**：同公司多次研究的评分漂移 / 论文演化视图

#### 决策 20 — 冷启动：C+B 组合

- **首次启动**：`universe_bootstrap_pipeline` 填全市场 → `quality_screen_pipeline` 生成 watchlist 30-50 → onboarding 引导用户导入持仓 CSV（标为 holding + 立即触发 thesis_tracker）
- **渐进式 deep_research**：每天 2-3 家，2-3 周覆盖完 watchlist
- **进入稳态**：每周 cron 增量
- **持仓 CSV 格式**：`stock_code, shares, cost_price, buy_date, thesis_note`
- **不做**：导入历史 Draft / 决策（Gojira 从空白开始追踪）

---

## 端到端状态机

```
[universe] 全市场 ~5000 家
    │ quality_screen_pipeline（每日 16:00 cron）
    ▼
[watchlist] 观察池 30-50 家
    │ deep_research_pipeline（每周 cron + 进入 watchlist 即触发）
    │   内部：data_collect → 4 大师并行 → synthesis（JSON + MD）
    │   防御：prompt 防御 + 代码后验 + 红线检查
    ▼
[researched] 已研究 10-15 家（带报告 + 四大师评分）
    │ 镜子测试 + 综合 ≥3.5/5 AND 无红线
    ▼
[candidate] 候选池 3-5 家
    │ valuation_trigger（每日估值检查）
    │   条件 D：价格入区间 + 论文健康 + 组合有空间
    ▼
[signaled] 信号（生成 Draft，TTL 7 天）
    │ 人工 1-click approve
    ▼
[holding] 持仓
    │ thesis_tracker（每周）+ news_pulse（±5%）+ earnings_review（财报日）
    │   卖出触发：1（论文证伪）/ 2（估值 1.3x）/ 3（仓位 15%）/ 5（基本面恶化）
    ▼
[exited] 退出
```

---

## 不在范围（显式排除）

- **多用户**：单用户系统，不写 user_id / auth / per-user schema
- **真实下单**：Draft 生成到人工审批为止，不在券商 API 下单
- **未上市公司**：A 股不适用，`private-company-research` 不做
- **内容创作**：`deep-company-series` / `earnings-team` / `wechat-article` 不做
- **哲学问答**：`dyp-ask` 不做
- **止损**：价值投资哲学，依赖论文证伪 + 估值触发
- **再平衡**：MVP 不做（二期）
- **邮件 / 微信通知**：MVP 仅应用内
- **行业研究 / 产业链**（Tier 2 Pipeline）：MVP 不做
- **本地公告采集**：MVP 仅 web search（二期加）

---

### I. 迁移与实施（4 条，第二轮 grill 产出）

#### 决策 21 — 大重写（非渐进式）

- **选择**：新分支从零写 v2，迁移完成后切换主分支
- **不做**：feature flag 渐进迁移 / 新旧代码共存
- **代价**：丢失现有 402 测试（部分基础设施测试可移植：Pipeline base/checkpoint 等）
- **依据**：用户明确"忽略之前所有的项目规划和进度"；干净彻底

#### 决策 22 — 旧代码直接删除

- **删除**：`builtin_seeder.py`（6 策略 + 4 预案）/ `strategy_engine.py` / `plan_runner.py` / `thesis_variable_sync_service.py` / `DisciplineChecklistModal` / 老的 scheduler 任务（daily_plan_evaluation 等）
- **不保留 fallback**：直接删，不做 enabled=false 的软禁用
- **依据**：v2 是范式转变（规则 → 混合），旧逻辑无法与新 Pipeline 共存

#### 决策 23 — 测试策略：全类型 + 独立预算

- **测试类型矩阵**：

| 类型 | 数量 | 频率 | LLM | 预算 |
|------|------|------|-----|------|
| Unit | 100+ | 每次 commit | Mock | $0 |
| Integration | 30+ | 每次 commit | Mock | $0 |
| Eval Set | 20-30 家 | 每周 | 真实 | $80-100/月 |
| Snapshot | 关键 Pipeline | 每次发版 | 真实 | $20-40 |
| E2E | 3-5 路径 | 每次发版 | 真实 | $10 |

- **Eval Set 设计**：覆盖各类型（高分 A 级 / 灰色地带 / 红线 / 周期股 / 成长股），每家含 `expected_score_range` / `expected_red_line` / `expected_recommendation` / `key_checks`
- **预算**：生产 $150 + 测试 $100 = 总 $250/月

#### 决策 24 — Prompt 外部文件 + REST + 自封装 GLM Client

- **Prompt 管理（B）**：`backend/app/prompts/{pipeline}/{version}/*.md`，按版本目录组织；`research_report.prompt_version` 记录生成版本
- **API（C）**：REST + FastAPI 自动生成 OpenAPI → 前端 `openapi-typescript` 生成类型，替代手写 `types.ts`
- **GLM Client（B）**：基于 Zhipu SDK 封装 `LLMClient`，加 `@tracked`/缓存/重试/成本追踪/冲突后验

### J. 部署与运维（2 条）

#### 决策 25 — DB 迁移：保留 Lixinger 数据

- **保留表数据**：stocks / financial_statements / price_klines / dividend_records / valuation_snapshots / audit_logs
- **删除表**：strategies / plans / themes / candidates(旧) / drafts(旧) / thesis_variables / watchlist_items(旧) / scheduler_jobs
- **用户决策数据（Draft/Candidate/Holding）不迁移**：从空白开始，符合冷启动设计
- **新增 5 表**：stock_lifecycle / research_report / decision_audit / llm_call_log / red_line_event
- **改造 2 表**：drafts（加新字段）/ holdings（加新字段）

#### 决策 26 — 部署：Docker + dev/prod 两环境

- **基础结构**：`docker-compose.yml`（base）+ `docker-compose.dev.yml` override（reload + hot mount）+ `docker-compose.prod.yml` override（gunicorn + nginx）
- **网络**：独立 `gojira-net`（符合 CLAUDE.md 要求）
- **GLM API key**：`.env` + docker secrets，不进 git
- **数据库备份**：每日 cron 备份到 `data/backups/`，30 天轮转
- **不做 staging**：单用户系统，dev → prod 直接部署

---

## 待 grill 的开放问题（已基本完成）

剩余次要问题（可在实施中决定）：

1. **CI/CD 细节**：GitHub Actions / pre-commit hooks 已有基础，按现有模式扩展
2. **缓存粒度**：30 天缓存按 (stock_code, pipeline_type) 组合键
3. **GLM 限流策略**：指数退避 3 次后 dead_letter
4. **日志输出**：JSON 结构化 + docker logs 双写
5. **性能调优**：LLM 并发上限（建议 5 并发，避免 rate limit）

---

## 下一步

1. ✅ 完成 grill-me 26 条决策（本文件）
2. ✅ 继续 grill 开放问题（已完成）
3. ⏳ 基于决策出实施计划（DB schema / Pipeline 模块 / 前端 / 配置 / 测试 / 上线）
