# Gojira 交易思想总纲 (trading-philosophy)

> **状态**：Phase 1 草案 (2026-06-25)，待用户 review 确认。确认后即为 Gojira 交易体系的**唯一权威来源**，Phase 2 代码整合以此为准。
>
> **目的**：当前 v2 实现整合了多套投资体系（ai-berkshire 四大师 + serenity 产业链），存在重叠、冗余与理念张力。本文档对「整个交易思想」做一次梳理、归纳、清洗、整合，给出**收敛后的目标体系**，并记录被弃用的旧思路。
>
> **本文档不含**：每个「镜」（段/巴/芒/李/卡点）的逐条评分细则——那些留在 `app/prompts/deep_research/v1/*_master.md`。本文档只定义**体系层**的北极星、引擎结构、评分 profile、去重规则、监控哲学与弃用清单。

---

## 1. 北极星 (North Star)

**Gojira 是一台双引擎个人股票自动驾驶舱。** 它不押注单一投资流派，而是同时运行两类互补的机会发现引擎，并在**同一个买入决策**上汇合。

两类机会被显式承认为「不同的游戏」，**不互相裁决**：

| 引擎 | 找什么 | 思想来源 | 典型标的 |
|---|---|---|---|
| **A. 价值复利引擎** | 好生意 + 宽护城河 + 长期确定性，在安全边际买入 | ai-berkshire 四大师（段永平/巴菲特/芒格/李录） | 茅台 / 腾讯 级稳定复利机器 |
| **B. 产业链卡点引擎** | 市场叙事 → 系统变化 → 产业链稀缺层 → 卡点公司 | serenity 产业链卡点猎手 | CPO / HBM / 先进封装 / 机器人 等新兴卡点 |

**关键立场（grill 决策）**：
- 两引擎是**两条独立的选股来源**，各自有自己的候选池视图。
- 但它们**不产出两套割裂的买卖决策**——见 §2 hybrid 汇合。
- 共同底线只有一条：**8 红线**（见 §4.4），任一引擎的标的命中红线一律否决。

> **为什么是双引擎而非单一价值机器**：serenity 擅长发现价值四大师（尤其李录/段永平的 10 年确定性 + 能力圈）会直接 PASS 的新兴成长卡点。把 serenity 降为「价值引擎的一个护城河探测器」会丢掉这种独特的主题发现力。所以保留它为**独立的选股引擎**，但用 hybrid 方式让两边在估值/风控上对齐。

---

## 2. 双引擎 + Hybrid 汇合

### 2.1 分工

二者**不是**两套平行的买卖流水线，而是**职责分工后汇入同一张草稿**：

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

### 2.2 两条来源路径，一个估值/风控闸门

```
路径①  universe → quality_screen(7硬规则) ─────┐
                                               ├──► deep_research(四师评分) ──► synthesis ──► Draft
路径②  serenity theme-scan(待建) ──────────────┘     (估值 + 三策略价格 + 8红线)
```

- **路径①（价值复利）**：现状已实现。`quality_screen` 在全市场 universe 上跑 7 条硬规则筛出 watchlist，再逐股跑 `deep_research`。
- **路径②（产业链卡点）**：**Phase 2 待建**。serenity 的「叙事→系统变化→产业链→稀缺层→公司」工作流目前只存在于 `docs/reference/serenity-skill/`，尚未接成 pipeline。需要新建 `theme_scan_pipeline`，产出按层级排序的卡点候选，喂入同一个 `deep_research` + `synthesis` 闸门。

### 2.3 汇合后的边界（grill 决策：full 4师 + 主题加权）

serenity 选出的卡点标的，**仍然跑完整四大师评分**，但用**主题加权 profile**（见 §3），并把 **serenity 卡点作为一个新的评分维度**加入。即：
- 不是「serenity 选了就买」——四师 + 估值 + 红线仍然作用。
- 也不是「用价值标准硬卡」——李录的 10 年确定性在主题 profile 下降权，避免把新兴卡点一票否决。

---

## 3. 评分 Profile（单一框架，两套权重）

**一个评分框架，按来源引擎切换权重**（grill 决策：profile 按 sourcing path 选择，与个股性质解耦，简单且确定）。

| 维度 | 复利 profile（路径①） | 主题 profile（路径②） | 说明 |
|---|---|---|---|
| 段永平 · 商业模式本质 | 25% | 保留 | 这门生意赚什么钱、是不是好生意 |
| 巴菲特 · 护城河+管理+估值 | 30% | 保留 | 企业级竞争优势 + 资本配置 + 安全边际 |
| 芒格 · 逆向+风险 | 20% | 保留 | 什么会让公司死、心理偏误、反共识 |
| 李录 · 10年确定性+文明趋势 | 25% | **降权 (≈10%)** | 主题 profile 下降权，避免新兴卡点被确定性一票否决 |
| **serenity · 产业链卡点** | —（不计） | **新增维度** | 链位置 + 稀缺层 + 主题时机 |

**Profile 选择规则**（确定性、可单测）：
```
source == "quality_screen"  →  复利 profile
source == "theme_scan"      →  主题 profile
```

> **已知取舍**：「按来源」会误分类「成熟垄断型卡点」（如一家成熟的滤材/认证壁垒龙头，本该用复利 profile 却因 serenity 来源被降权李录）。这是为换取确定性与可测试性而**有意接受**的边缘误差，可通过人工 override 修正个例。后续若误差频发，再升级为「按个股确定性分级」。

> **维度总和**：主题 profile 引入第 5 维度后，权重需重新归一化（段/巴/芒/李↓/卡点 合计 100%）。具体数值在 Phase 2 落地 `synthesis` 时定稿，本文档只锁定「李录降权、卡点新增」的方向。

> **评分math 归属（grill 决策 2026-06-25：hybrid）**：当前权重/加权平均/BUY-HOLD-PASS 阈值全是 `synthesis.md` 里的**散文，由 LLM 计算**。Phase 2 改为 **hybrid**：
> - LLM 仍输出 `overall_score`/`recommendation`，但**降级为 advisory**（仅供观测/交叉核对）。
> - **Python 复核为权威值**：从 LLM 返回的 `master_scores`（各师 1-5）按 `PROFILE[source]` 权重重算 `overall_score`，应用 §4.1 同源封顶，按阈值 config 推 BUY/HOLD/PASS。
> - **权重 + 阈值 = 声明式 config dict**（按 source 键），profile 切换 = dict 查表。
> - **LLM 与 Python 分数偏离时记 observability 日志**（不阻断），便于发现 prompt 漂移。
> - 同源封顶需要 LLM 在每个维度输出 `advantage_source` 标签供 Python 判断同源。

---

## 4. 去重规则 ×3（清洗的核心）

当前多套体系叠加，三处「其一包含其二」的重叠必须显式定一个 owner，否则同一件事被重复计分或重复表述。

### 4.1 「持久优势」轴去重（grill 决策：三镜并存，同源只计一次）

`serenity 卡点 ≈ 巴菲特护城河 ≈ 段永平好生意`——三者本质都在衡量「持久竞争优势」。

**规则**：三个维度**各自独立打分**（保留三种视角的声音），但 Python 复核时按下述**整师折叠**去重（grill 决策 2026-06-25，已实现）：

1. **打标签**：每个优势型大师（段/巴/卡点）输出**唯一一个**主导 `advantage_source`（受控枚举，见 `app/core/scoring_config.py::ADVANTAGE_SOURCES`：brand / network_effect / cost_advantage / switching_cost / regulatory_barrier / intangible_assets / chain_scarcity），非优势驱动则填 `null`。芒格/李录是风险/确定性轴，**永不参与折叠**（`ADVANTAGE_MASTERS = {duan, buffett, scarcity}`）。
2. **折叠**：标签相同（非 null）且 ≥2 个成员的组，**折叠为一个维度**：`weight = max(组内权重)`，`score = mean(组内分数)`。
3. **归一**：在折叠后的有效维度集合上做加权平均。

> 实现：`app/services/llm/scoring.py::compute_overall_score(..., advantage_sources=...)`，纯函数 + 单测（`tests/v2/test_scoring.py::TestSameSourceCap` + pipeline e2e）。
> 例：段0.25@4.5 与 巴0.30@4.4 同标 `brand` → 折叠为 0.30@4.45 → 4.145 降至 ≈4.05。

### 4.2 证据分级去重（grill 决策：两层明确分工，去重措辞）

两套分级**不是冗余，而是不同粒度**，必须分清角色：

| 层级 | 量表 | 作用对象 | 来源 |
|---|---|---|---|
| **条目级** | strong / medium / weak / unverified_lead | 每一条 evidence（这条声明的来源质量） | serenity 证据分级 |
| **包级** | A / B / C | 整份研究的信息丰富度（够不够支撑强结论） | ai-berkshire 信息丰富度评级 |

> 「A 级 + 某条 medium」**不矛盾**：A 说的是整包，medium 说的是其中一条。

**清洗动作**：`shared/system_base.md`、`shared/defense_methodology.md`、`shared/evidence_grading.md` 三处各有一份**重复的来源优先级清单**（公告 > 交易所 > Lixinger > 媒体 > 研报 > 社交）。合并为**唯一一份共享引用**，其余两处链接到它，不再各写一遍。

### 4.3 「会出什么错」去重（已确认 2026-06-25）

三处「下行/失败」机制重叠：

| 机制 | 问什么 | 性质 | 来源 |
|---|---|---|---|
| 芒格 failure_scenarios | 什么情况会让公司**死/跌** | 评分输入（概率+触发信号+下行幅度） | ai-berkshire |
| serenity 失败条件 | 什么证据会证明这个**论点错** | 论点证伪清单 | serenity |
| 8 红线 | 是否命中硬性否决项 | 二元否决（pass/veto） | ai-berkshire |

**规则（已实现 2026-06-25）**：
- 芒格 failure_scenarios 与 serenity 失败条件**高度同义**，在主题 profile 下**合并到芒格的 failure_scenarios 字段**（serenity 的卡点专属失败条件——替代覆盖/对手扩产/认证流失——作为子项并入），避免两份「会出错清单」。
- 8 红线**保持独立**，它是二元否决底线，不参与评分加权，两引擎共同遵守。

> 实现：`deep_research.run(failure_conditions=[...])` → `_build_master_prompt` 仅给**芒格**追加「serenity 已识别的失败条件」段落，指示并入 `failure_scenarios`（不另列）；`research_v2` 路由加 `failure_conditions` 参数透传；munger_master.md 文档说明；e2e 测试断言仅芒格 prompt 收到、其余三师不收到。theme_scan 候选已携带 `failure_conditions`（CANDIDATE_RANK_SCHEMA），手动衔接时由请求体传入。

### 4.4 8 红线（共同底线，不去重，强调归属）

8 红线是**两引擎唯一的共享硬闸门**，任一标的命中即 `rejected`，与来源 profile 无关：
管理层诚信污点 / 财务造假嫌疑 / 重大违规 / 连年亏损 / 高质押 / 频繁减持 / 复杂关联交易 / Benford 异常。

> 注：`quality_screen` 的 7 硬规则与 8 红线**部分重叠**（如「NOT ST」≈「重大违规/退市风险」、「营收不崩」≈「连年亏损」预警）。7 硬规则是**前置粗筛**（便宜的 SQL 层），8 红线是**研究后的终审否决**（LLM 层确认）。两者角色不同，保留，但 Phase 2 文档需注明这层重叠避免读者困惑。

---

## 5. 持仓后证伪哲学

买入不是终点。Gojira 对已持仓标的执行**持续逻辑证伪**——三条事件驱动的监控 pipeline，本质是「不断尝试推翻自己的买入论点」：

| Pipeline | 触发 | 做什么 | 证伪角色 |
|---|---|---|---|
| `thesis_tracker` | 定期 | 复核买入论文是否仍成立（原 thesis vs 最新财报/事件/股价） | 论点是否还活着 |
| `news_pulse` | 股价异动 ±5% | 10-15 分钟快速归因（公司/政策/对手/情绪四维 web_search） | 异动是否动摇论点 |
| `earnings_review` | 财报发布 | 财报深度精读（电话会指引 + 卖方反应） | 基本面是否兑现 |

**思想归属**：这套监控直接对应芒格「持续逆向自查」+ serenity「失败条件持续验证」。它是两引擎**共享**的后置层——无论标的来自路径①还是②，买入后都进同一套证伪监控。

---

## 6. 弃用清单 (Retired)

v2-rewrite（2026-06-24, commit bcb2b34 系列）把 v1 的**量化规则策略**整体下线，改为 LLM 四大师研究框架。以下旧思路**已弃用**，记录在此以免被误认为「遗漏」而重新引入：

| 弃用策略 | 原思路 | 为什么弃用 |
|---|---|---|
| `contrarian` | 逆向/超跌买入 | 与四大师「买好生意」冲突——容易捞到便宜的烂公司（价值陷阱）。逆向思维改由**芒格维度**承载，而非独立买入策略 |
| `core_value` | 核心价值规则筛 | 被 `quality_screen` 7 硬规则 + 巴菲特维度完全覆盖 |
| `bank_anchor` | 银行锚定 | 行业专用硬规则，泛化性差；银行的护城河（监管牌照）已在巴菲特护城河类型中 |
| `pure_cash_machine` | 纯高股息现金机器 | 单因子（股息率）选股，已退化为 `quality_screen` 规则 6（分红可持续性）的一个输入 |

**Phase 2 清理动作**：
- ~~`deep_research_schema.py` 残留死引用~~ **已核实为误报**（2026-06-25）：grep 命中的 `contrarian_view` 是芒格维度的合法输出字段，非弃用的 `contrarian` 策略。全 app word-boundary grep `bank_anchor|pure_cash_machine|core_value` + `'contrarian'` **零真实死引用**。v1 策略 `.py` 已在 v2-rewrite 干净删除，无需额外清理。

---

## 7. As-Is → To-Be

### 7.1 As-Is（当前实现，2026-06-25 实测）

```
universe
  └─ quality_screen (7 硬规则, ai-berkshire)        ✅ 已实现
       └─ watchlist
            └─ deep_research (段/巴/芒/李 四师, 单股)  ✅ 已实现
                 └─ synthesis (BUY/HOLD/PASS + 三策略价格区间 + 8红线)  ✅ 已实现
                      └─ Draft → Holding
                           └─ 监控 (thesis_tracker / news_pulse / earnings_review)  ✅ 已实现

serenity 产业链引擎                                  ❌ 未接线（仅 reference 文件 + 证据分级碎片入 prompt）
两套来源优先级清单                                   ⚠️ 重复（3 文件各一份）
持久优势三镜                                         ⚠️ 未去重（可能虚高）
失败/红线三机制                                      ⚠️ 未去重
deep_research_schema.py 旧策略死引用                  ⚠️ 1 处残留
```

### 7.2 To-Be（本文档确认后的目标体系）

```
路径① universe → quality_screen → watchlist ─┐
                                             ├─► deep_research(profile 切换) ─► synthesis(去重+封顶) ─► Draft(双 thesis) ─► Holding ─► 监控
路径② theme_scan(新建, serenity) ────────────┘
                                                     ▲
   共享底线：8 红线否决（两引擎通用）  ───────────────┘
```

### 7.3 Phase 2 代码整合清单（待本文档 sign-off 后执行）

1. ~~新建 `theme_scan_pipeline`~~ **MVP 已完成**（serenity 引擎端到端可用）：
   - ✅ deep_research 接收端：`run(source, scarcity_score)` 注入 scarcity 维度（advantage_source=chain_scarcity），theme profile live + e2e 测试。
   - ✅ `ThemeScanReport` 模型 + migration `v2_2_theme_scan_reports` + round-trip 测试。
   - ✅ 5 步输出 schemas（`theme_scan_schema.py`）。✅ serenity prompts（`prompts/theme_scan/v1/` system + 5 步）。
   - ✅ `theme_scan_pipeline.run(theme)` 编排 + A 股代码主表校验（编造代码丢弃）+ scarcity 排序 + empty 短路 + TDD。
   - ✅ router `POST /api/theme-scan` + GET reports/{id} + research trigger 加 `source`/`scarcity_score` 参数 + API 测试。
   - **决策（grill 2026-06-25）**：MVP=用户触发单主题；scarcity 复用（传入分数不重跑）；手动衔接（→ POST /api/research/{code} body source=theme_scan + scarcity_score）。
   - ⬜ **后续**：调度/自动主题发现（v2）；§4.3 failure-merge + §7 Draft dual-thesis（见下）。
2. ~~`deep_research` 加 profile 切换~~ **已完成**：`run(source=)` 按 source 选 `PROFILE_WEIGHTS`（复利/主题）；主题 profile 降权李录 + 新增 scarcity 维度 + 重归一化；scoring.py 实现 + 单测。
3. ~~`synthesis` 加同源优势封顶逻辑~~ **已完成**（§4.1：scoring.py 整师折叠 + advantage_source 枚举入 schema/prompt + e2e 测试）。
4. ~~合并三处来源优先级清单为一份共享引用~~ **已完成**（§4.2：统一清单入 evidence_grading.md，另两处改为引用；三处清单原本互相**冲突**已消除）。
5. ~~主题 profile 下合并芒格 failure_scenarios 与 serenity 失败条件~~ **已完成**（§4.3）：`deep_research.run(failure_conditions=)` 仅注入芒格 prompt（并入 failure_scenarios，不另列）+ munger_master.md 说明 + research 路由 `failure_conditions` 参数 + e2e 测试（仅芒格收到）。
6. ~~`shared/*.md` 措辞清洗~~ **已完成**：A/B/C 包级权威落 defense_methodology、strong/med/weak/lead 条目级落 evidence_grading，system_base 改为双指针；删除 system_base 里重复的 A/B/C。
7. **Draft schema 扩展**：携带 serenity thesis + ai-berkshire 价格区间双字段。
8. ~~删除旧策略死引用~~ **已核实无需做**（§6，误报）。
9. ~~文档注明 `quality_screen` 7 硬规则与 8 红线的重叠角色~~ **已完成**（§4.4：注释加在 quality_screen_pipeline.py docstring：7 规则=前置粗筛 / 8 红线=研究后否决，重叠但角色不同）。

---

## 附录：思想来源对照

| 概念 | ai-berkshire | serenity |
|---|---|---|
| 核心范式 | 自下而上选好生意 + 安全边际 | 自上而下主题 → 产业链稀缺层定位 |
| 持久优势 | 护城河（品牌/网络/成本/转换/监管/无形） | 产业链卡点（低供应商数/长认证/难扩产/know-how） |
| 风险机制 | 8 红线 + 芒格逆向 | 每条推荐的「失败条件」 |
| 证据 | A/B/C 信息丰富度（包级） | strong/medium/weak/lead（条目级） |
| 输出 | 单股 BUY/HOLD/PASS + 价格区间 | 主题内排序的研究优先级 |
| 执行 | 含价格/仓位逻辑 | **仅研究，无下单逻辑**（故由 ai-berkshire 补估值/风控） |
