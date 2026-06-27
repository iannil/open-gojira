# Gojira 选股原理

> **状态**：定稿 (2026-06-27)。本文档解释 Gojira 如何从全市场 A 股中选出值得买入的标的，涵盖双引擎分工、完整 pipeline 流程、评分机制、去重规则与风控底线。
>
> **配套**：`trading-philosophy.md`（交易思想权威总纲）· `scoring_config.py`（声明式评分配置）· `docs/progress/2026-06-26-v2-architecture-and-progress.md`（架构全景）

---

## 1. 一句话定位

Gojira 的选股不是单一模型，而是 **「双引擎 sourcing → hybrid 汇合 → 持续证伪」** 的自动化管道：

1. **两条独立的选股来源**同时运行，发现不同类型的机会
2. **汇入同一套估值/风控闸门**，产出统一的买卖草稿
3. **买入后持续尝试推翻自己的论点**，触发卖出信号

---

## 2. 双引擎架构

两条引擎**独立发现机会，不互相裁决**，各有所长：

| | 价值复利引擎 (ai-berkshire) | 产业链卡点引擎 (serenity) |
|---|---|---|
| **找什么** | 好生意 + 宽护城河 + 长期确定性的复利机器 | 市场叙事 → 产业链稀缺层 → 卡点公司 |
| **典型标的** | 茅台、腾讯 —— 稳定复利 | CPO、HBM、先进封装 —— 新兴卡点 |
| **思想来源** | 段永平 / 巴菲特 / 芒格 / 李录 | Serenity 产业链卡点方法论 |
| **触发方式** | 定时调度（`quality_screen` 周跑） | 用户触发（`theme_scan` 按主题扫描） |
| **当前状态** | ✅ 完整闭环 | ✅ MVP 已完成（用户触发单主题） |

### 2.1 分工与汇合

```
serenity 引擎  ── 负责「选哪只」(WHICH)：产业链位置 / 稀缺度 / 主题时机
                          │
                          ▼
ai-berkshire 引擎 ── 负责「多贵 / 多安全 / 该不该否」(PRICE + RISK)：
                     三策略价格区间 / 安全边际 / 8 红线否决
                          │
                          ▼
               一张草稿 (Draft)：同时携带
                 · serenity 卡点论证 (thesis)
                 · ai-berkshire 价格区间 (aggressive/steady/conservative)
```

**关键边界**：
- Serenity 选的卡点标的，**仍然跑完整四大师评分**，不是「serenity 选了就买」
- 但使用**主题加权 profile**（李录降权 + 卡点维度），避免用 10 年确定性标准把新兴卡点一票否决

---

## 3. 选股 Pipeline 全流程

### 3.1 路径①：价值复利引擎

```
universe（全市场 ~5000 A 股）
  │
  ├─ quality_screen（7 条硬规则粗筛）
  │   ├─ 市值 ≥ 100 亿
  │   ├─ 股价 ≥ 5 元
  │   ├─ 营收增长不崩
  │   ├─ ROE 历史为正
  │   ├─ 分红可持续
  │   ├─ 质押率适中
  │   └─ NOT ST / 退市风险
  │
  ▼
StockLifecycle → 观察池（30-50 只通过前置粗筛的候选）
  │
  ▼
deep_research（每只股票：4 大师并行 LLM 调用）
  ├─ 段永平 · 商业模式本质（1-5 分）
  ├─ 巴菲特 · 护城河+管理+估值（1-5 分）
  ├─ 芒格 · 逆向+风险（1-5 分）
  ├─ 李录 · 10 年确定性+文明趋势（1-5 分）
  └─ Team Lead 综合 → synthesis
       ├─ overall_score（advisory）
       ├─ BUY / HOLD / PASS 建议
       ├─ 三策略价格区间（aggressive/steady/conservative）
       └─ 8 条红线否决检查
```

### 3.2 路径②：产业链卡点引擎

```
用户输入主题（如「算力铜连接」「HBM」）
  │
  ▼
theme_scan（5 步 LLM 工作流）
  ├─ Step 1：解析市场叙事
  ├─ Step 2：识别系统变化
  ├─ Step 3：定位产业链环节
  ├─ Step 4：评估稀缺层/卡点
  └─ Step 5：推荐卡点公司（按 scarcity_score 排序）
  │
  ▼
ThemeScanReport → 用户评估
  │
  ▼
手动触发 deep_research（带 source=theme_scan + scarcity_score）
  ├─ 使用**主题 profile**（李录 10% + 卡点 24%）
  └─ 其余流程同路径①
```

### 3.3 汇合：Draft 生成

```
research_report（评分 + 价格区间 + 红线否决）
  │
  ▼
draft_generator（每日调度，检查触发条件 D）
  ├─ 价格落入策略区间（aggressive/steady—conservative 不生成）
  ├─ 论文健康（thesis_status 非 INVALIDATED）
  ├─ 组合有空间：现金 ≥ 20%
  ├─ 单股 < 10% 仓位
  └─ 行业集中度 < 30%（F20 跳过，因 Lixinger 无申万映射）
  │
  ▼
Draft（应买，TTL 7 天）
  ├─ 仓位：激进 8% / 稳健 4%
  ├─ 携带 price_ranges_json + serenity_thesis + target_price
  └─ status: pending（等待用户 execute）
```

### 3.4 执行与持仓

```
用户 execute → 回填实际成交价
  │
  ▼
trade_service.record_trade（**唯一写持仓入口**）
  │
  ▼
Trade 账本
  │
  ▼
position_service（**持仓/盈亏唯一真相源**）
  ├─ 移动加权平均成本
  ├─ 已实现盈亏 + 浮动盈亏
  └─ T+1 冻结股数
```

---

## 4. Hybrid 评分机制

### 4.1 架构

**LLM 算分 = advisory，Python 复核 = 权威分**：

```
LLM 合成输出：
  overall_score: 4.2 (advisory)
  master_scores: {duan: 4.5, buffett: 4.0, munger: 3.5, lilu: 4.8}
  advantage_sources: {duan: "brand", buffett: "brand"}

Python 复核：
  1. 按 source 查 PROFILE_WEIGHTS 获取权重
  2. 同源优势维度折叠（见 §5.1）
  3. 加权平均得 authoritative_score
  4. 查阈值 → BUY / HOLD / PASS
  5. 与 LLM advisory 对比，偏差 >0.5 记日志（prompt drift 信号）
```

### 4.2 两套 Profile 权重

| 维度 | 复利 profile（`quality_screen`） | 主题 profile（`theme_scan`） |
|---|---|---|
| 段永平 · 商业模式 | 25% | 22% |
| 巴菲特 · 护城河+估值 | 30% | 26% |
| 芒格 · 逆向+风险 | 20% | 18% |
| 李录 · 10年确定性 | 25% | **10%**（降权） |
| Serenity 产业链卡点 | — | **24%**（新增维度） |

**选择规则**（确定性查表，可单测）：

```python
source == "quality_screen"  →  复利 profile
source == "theme_scan"      →  主题 profile
```

### 4.3 推荐阈值

| authoritative_score | 推荐 |
|---|---|
| ≥ 4.0 | BUY |
| ≥ 3.0 | HOLD |
| < 3.0 | PASS |

---

## 5. 三层去重（防同一优势被重复计分）

### 5.1 持久优势折叠（§4.1）

段永平「好生意」≈ 巴菲特「护城河」≈ Serenity「卡点」——三者都在衡量"持久竞争优势"。

**规则**：
1. 每位优势型大师（段/巴/卡点）输出唯一一个 `advantage_source` 标签：`brand` / `network_effect` / `cost_advantage` / `switching_cost` / `regulatory_barrier` / `intangible_assets` / `chain_scarcity`。非优势驱动填 `null`。
2. 标签相同且 ≥2 个成员的组，折叠为一个维度：`weight = max(组内权重)`，`score = mean(组内分数)`。
3. 芒格/李录**永不参与折叠**（风险轴/确定性轴）。

**示例**：段 0.25@4.5 与 巴 0.30@4.4 同标 `brand` → 折叠为 0.30@4.45 → 总分从 ≈4.14 降至 ≈4.05。

### 5.2 证据分级去重（两层，不同粒度）

| 层级 | 量表 | 作用对象 |
|---|---|---|
| **条目级** | strong / medium / weak / unverified_lead | 单条 evidence 的来源质量 |
| **包级** | A / B / C | 整份研究的信息丰富度（能否支撑强结论） |

两者**不矛盾**：A 级 + 某条 medium = 整包丰富但其中一条引用一般。

### 5.3 失败条件去重

| 机制 | 合并后归属 |
|---|---|
| 芒格 `failure_scenarios` | 主载体——什么情况会让公司死/跌 |
| Serenity 失败条件 | **并入芒格**——卡点专属证伪条件作为子项追加 |
| 8 红线 | **保持独立**——二元否决，不参与评分加权 |

---

## 6. 四层防御（风控与抗幻觉）

| 层 | 机制 | 位置 | 作用 |
|---|---|---|---|
| ① Prompt 约束 | 每位大师 prompt 内嵌约束（不许重复表达、不许评论行业、严格按 schema 输出） | `app/prompts/deep_research/v1/*_master.md` | 源头减少错误 |
| ② 代码后验 | `conflict_validator` 检查 LLM 输出的 PE/PB/DYR 与 Lixinger 数据偏差 >5% 标记为冲突 | `app/services/llm/conflict_validator.py` | 检测 LLM 幻觉 |
| ③ Pipeline 熔断 | 冲突率 >20% 阻断新运行，防止系统性漂移 | `app/services/pipelines/llm/deep_research_pipeline.py` | 系统级保护 |
| ④ **8 条红线** | 管理层诚信污点 / 财务造假嫌疑 / 重大违规 / 连年亏损 / 高质押 / 频繁减持 / 复杂关联交易 / Benford 异常 | `app/services/llm/red_line_checker.py` | **二元否决**，命中即 reject |

**成本防御**：`cost_tracker` $150/月硬熔断（生产）+ $100/月（测试）。

---

## 7. 买入后：持续证伪

选股不是终点。买入后的标的进入**三套监控 pipeline**：

| Pipeline | 触发 | 行为 | 输出 |
|---|---|---|---|
| `thesis_tracker` | 每周 | 原买入论文 vs 最新数据（财报/事件/股价），判断是否仍成立 | VALID / WARNING / **INVALIDATED** |
| `news_pulse` | 股价异动 ±5% | 10-15 分钟 web_search 归因（公司/政策/对手/情绪四维） | 异动是否动摇论点 |
| `earnings_review` | 财报发布 | 电话会指引 + 卖方反应深度精读 | 基本面是否兑现 |

### 卖出 4 信号（不做止损）

| # | 信号 | 来源 | 建议卖价 |
|---|---|---|---|
| 1 | 论点证伪（优先） | `thesis_tracker INVALIDATED` | 现价 |
| 2 | 估值 1.3x 止盈 | 三策略价格区间上限 x1.3 | 公允价 x1.3 |
| 3 | 仓位 15% 超限 | `position_service` | 风控现价 |
| 4 | 基本面恶化 | `news_pulse` / `earnings_review` 告警 | 现价 |

---

## 8. 完整数据流图示

```
                     ┌─────────────────────────────────────┐
                     │        全市场 universe               │
                     │         (~5000 A 股)                 │
                     └──────────┬──────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                                    ▼
  ┌──────────────────────┐          ┌──────────────────────────┐
  │  quality_screen      │          │  theme_scan              │
  │  7 条硬规则 (SQL 层)  │          │  5 步 LLM 工作流        │
  │  ai-berkshire sourcing│          │  serenity sourcing       │
  └──────────┬───────────┘          └────────────┬─────────────┘
              │                                    │
              ▼                                    │
  ┌──────────────────────┐                        │
  │  StockLifecycle      │◄───────────────────────┘
  │  观察池 / 候选       │
  └──────────┬───────────┘
              │
              ▼
  ┌──────────────────────────────────────────────┐
  │  deep_research                               │
  │  段·巴·芒·李 并行 LLM 调用                   │
  │  + 5% 冲突后验 + 8 红线否决 + advantage_tag  │
  │  + profile 切换（复利/主题）                  │
  └──────────────────┬───────────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │  synthesis → research_report                │
  │  BUY/HOLD/PASS + 三策略价格区间 + 失败条件   │
  │  Python 复核权威分                           │
  └──────────────────┬───────────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │  draft_generator (每日调度)                   │
  │  触发条件 D：价格入区间 + 论文健康 + 仓位空间 │
  └──────────────────┬───────────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │  Draft（TTL 7 天）→ 用户 execute              │
  │  → trade_service.record_trade                │
  │  → Trade 账本 → position_service 派生持仓    │
  └──────────────────┬───────────────────────────┘
                      │
                      ▼
  ┌──────────────────────────────────────────────┐
  │  持续证伪监控                                 │
  │  thesis_tracker / news_pulse / earnings_review│
  │  → INVALIDATED → SELL Draft                  │
  └──────────────────────────────────────────────┘
```

---

## 9. 关键代码映射

| 组件 | 文件 |
|---|---|
| 评分配置 | `backend/app/core/scoring_config.py` |
| Python 权威评分 | `backend/app/services/llm/scoring.py` |
| 8 红线检查 | `backend/app/services/llm/red_line_checker.py` |
| 5% 冲突后验 | `backend/app/services/llm/conflict_validator.py` |
| Deep Research Pipeline | `backend/app/services/pipelines/llm/deep_research_pipeline.py` |
| Quality Screen Pipeline | `backend/app/services/pipelines/llm/quality_screen_pipeline.py` |
| Theme Scan Pipeline | `backend/app/services/pipelines/llm/theme_scan_pipeline.py` |
| 草稿生成 | `backend/app/services/draft_generator.py` |
| 持仓真相源 | `backend/app/services/position_service.py` |
| 交易录入 | `backend/app/services/trade_service.py` |
| 生命周期状态机 | `backend/app/services/lifecycle_service.py` |
| 论点跟踪 | `backend/app/services/pipelines/llm/thesis_tracker_pipeline.py` |
| 异动归因 | `backend/app/services/pipelines/llm/news_pulse_pipeline.py` |
| 财报精读 | `backend/app/services/pipelines/llm/earnings_review_pipeline.py` |

---

## 10. 常见问题

**Q：两引擎选出的股票冲突怎么办？**
A：两引擎是独立来源，不互相裁决。同一只股票可能被两个引擎都发现，此时用其 sourcing path 选择对应的评分 profile。8 红线是唯一共享否决。

**Q：LLM 评分和 Python 评分不一致怎么办？**
A：不一致（偏差 >0.5）记 observability 日志，不阻断运行。这是 prompt drift 的早期信号，用于后续分析。

**Q：为什么不直接用单一模型？**
A：价值四大师会天然 pass 新兴成长卡点（缺乏 10 年确定性），而 Serenity 擅长发现这些机会。双引擎保留这种互补性，再用 hybrid 汇合确保风控统一。
