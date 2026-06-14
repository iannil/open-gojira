# Serenity Skill 集成规格 (Gojira 内嵌实现)

> 日期：2026-06-14
> 状态：已确认 (grill-me 会话产出)
> 关联：`docs/reference/serenity-skill/SKILL.md` (方法论来源) | `docs/progress/STATUS.md` (项目当前状态)

## 背景

`docs/reference/serenity-skill/` 是一份「供应链卡点猎手」研究方法论 skill,核心工作流:

```
市场叙事 → 系统变化 → 价值链 → 稀缺层 → 上市公司 → 证据分级 → 排名 → 失败条件 → 下一步验证
```

serenity-skill 要求 ≥20 公司宇宙 + ≥25 sources + 证据 4 档分级(strong / medium / weak / lead)。

Gojira 现状对照:

| 维度 | Gojira 现状 | serenity-skill 要求 | 差距 |
|---|---|---|---|
| `Theme` 模型 | 5 个宏观主线(能源/资源/金融/粮食/民生) | 具体研究方向(AI 半导体/CPO/HBM) | **粒度冲突** |
| 数据源 | Lixinger(年报/季报/K线/分红/估值/财务比率/customers/suppliers) | + 公告/问询函/招投标/环评/专利 | 公告类完全缺 |
| LLM 推理 | 零集成 | 推理 + 结构化输出 + 证据分级 | 从零搭建 |
| 网络搜索 | 零集成 | ≥25 sources,LLM 自己抓 | 从零搭建 |

本规格定义 Gojira 内嵌实现 serenity-skill 的完整方案,基于 grill-me 会话产出 9 项决策。

## 决策汇总

第一轮 grill (Q1-Q9, 核心架构):

| # | 决策 | 选择 | 推理摘要 |
|---|---|---|---|
| 1 | Phase 1 范围 | **B** 完整工作流(3-4 周) | 用户主动选最重路径,需对应完整 schema + 完整 UI |
| 2 | Theme 语义冲突 | **A** 新建 `ResearchTheme` 表 | 粒度正交不该合并,职责分离零侵入现有 Theme 消费者 |
| 3 | 研究产物落地 | **D** 6 张结构化表 + 用户手动导出 | rule-based Candidate 跟 LLM 推理 Candidate 语义不同,强行合并会污染审计 |
| 4 | 公告数据源 | **D** Lixinger + LLM Web Search 多源融合 | 不破坏 ADR #3「Lixinger 唯一数据源」;Lixinger 已有 customers/suppliers 是稀缺层判断金矿 |
| 5 | LLM provider | **GLM-5.2** | 国内访问无障碍 / 用户已在 GLM 环境跑 / 原生 web_search tool 保住 D 决策 |
| 6 | 触发模型 | **D** 手动为主 + 可选每周调度 | 满足「除下单外全自动化」原则;默认不自动避免成本失控 |
| 7 | UI 形态 | **D** 多入口(主页面 `/research` + Cockpit 卡片 + StockDetail 反向链接 + Candidates 徽章) | 报告内容量大必须有专门页面;交叉链接提升单股信息密度 |
| 8 | 成本与限流 | **C** 单 Run 硬约束 + 失败告警 + 月度预算软上限(¥100) | 单 Run 硬约束是真 bug 兜底;月度软上限允许 Phase 1 收集实际成本数据 |
| 9 | 测试与 ship | **D** 先 spike 后 ship(5-7 天) | GLM-5.2 在中文金融领域的输出质量未知,spike 把发现点从第 3 周提前到第 1 天 |

第二轮 grill (Q10-Q19, 实施细节):

| # | 决策 | 选择 | 关联章节 |
|---|---|---|---|
| 10 | 执行模式 | 异步 ThreadPoolExecutor | 见「已解决的子问题」表 |
| 11 | 导出 Checklist | 不过 | 同上 |
| 12 | weekly 失败跳过 | 跳过 | 同上 |
| 13 | LLM 死循环兜底 | 仅三重硬约束 | 同上 |
| 14 | StockDetail 反向链接 | 加 index | 同上 |
| 15 | 历史 Run diff 视图 | Phase 1 只列表 | 同上 |
| 16 | LLMProvider 抽象 | 不做 | 同上 |
| 17 | 告警通道 | 复用 NotificationChannel | 同上 |
| 18 | Markdown 渲染 | react-markdown + remark-gfm + rehype-raw | 同上 |
| 19 | 失败条件 → 论点变量 | Phase 1 不做 | 同上 |

## 决策依赖图

```
Q1 B 完整工作流 ─────► 需要 6 张结构化表 (Q3 D)
                       │
Q2 A ResearchTheme ────┤
                       │
Q4 D LLM Web Search ──► 需 LLM provider 有原生 web_search
                       │
Q5 GLM-5.2 ────────────┤ (GLM-5.2 有原生 web_search, 保住 Q4)
                       │
                       ▼
Q3 D 6 张表 + 手动导出 ─► Q7 D 多入口 UI (主页面 + 反向链接)
                       │
Q6 D 手动+可选调度 ────┤
                       │
Q8 C 硬约束+软上限 ────► Q9 D spike 先验证 LLM 输出
                       │
                       ▼
              Phase 1 ship (5-7 天)
```

## 完整数据库 Schema (6 张新表 + 1 张扩展表)

### 1. `research_themes` (扩展 Q2 草案,加 Q6/Q8 字段)

```python
# app/models/research_theme.py
class ResearchTheme(Base):
    """研究方向 (serenity 主题) — 跟现有 Theme (宏观主线) 正交。"""
    __tablename__ = "research_themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str] = mapped_column(String, nullable=False, default="A_SHARE")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)

    # Q6 触发配置
    auto_refresh_freq: Mapped[str] = mapped_column(
        String, nullable=False, default="manual"  # "manual" / "weekly" / "monthly"
    )

    # Q8 状态跟踪
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_run_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 可选: 归到宏观主线伞下
    parent_theme_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("themes.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())
```

### 2. `research_runs` (每次跑 serenity 一行)

```python
# app/models/research_run.py
class ResearchRun(Base):
    """单次 serenity 研究运行。"""
    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_theme_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_themes.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
        # "running" / "completed" / "failed"

    # Scope
    scope_market: Mapped[str] = mapped_column(String, nullable=False)
    scope_time_window: Mapped[str] = mapped_column(String, nullable=False, default="3-12M")
    triggered_by: Mapped[str] = mapped_column(String, nullable=False, default="manual")
        # "manual" / "scheduler"

    # LLM 配置与统计 (Q8)
    llm_provider: Mapped[str] = mapped_column(String, nullable=False, default="glm-5.2")
    llm_token_input: Mapped[int] = mapped_column(Integer, default=0)
    llm_token_output: Mapped[int] = mapped_column(Integer, default=0)
    llm_search_count: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 结构化结果摘要 (详情落子表)
    system_change_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_conditions_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

### 3. `value_chain_layers` (每次运行 8 行)

```python
class ValueChainLayer(Base):
    __tablename__ = "value_chain_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    layer_index: Mapped[int] = mapped_column(Integer, nullable=False)
        # 1=下游客户 / 2=系统集成 / 3=模块子系统 / 4=芯片器件 /
        # 5=工艺封装测试 / 6=设备与计量 / 7=材料耗材 / 8=物理基建
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### 4. `scarce_layers` (每次运行 3-5 行,带排名)

```python
class ScarceLayer(Base):
    __tablename__ = "scarce_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=最稀缺
    layer_ref_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("value_chain_layers.id"), nullable=False
    )
    scarcity_reason_md: Mapped[str] = mapped_column(Text, nullable=False)
        # 客户数低 / 认证慢 / 工艺难 / 设备专用 / 客户预定 ...
    expansion_difficulty: Mapped[str] = mapped_column(String, nullable=False)
        # "high" / "medium" / "low"
```

### 5. `research_company_universe` (每次运行 ≥20 行)

```python
class ResearchCompanyUniverse(Base):
    __tablename__ = "research_company_universe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True  # Q14: 反向链接查询走此 index
    )
    classification: Mapped[str] = mapped_column(String, nullable=False)
        # "controls" / "supplies" / "benefits" / "weak" / "story"
    layer_ref_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("value_chain_layers.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### 6. `research_evidence` (每次运行 ≥25 行)

```python
class Evidence(Base):
    __tablename__ = "research_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    stock_code: Mapped[str | None] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=True, index=True  # Q14: 反向链接查询走此 index
        # nullable: 稀缺层证据可能不绑公司
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
        # "filing" / "announcement" / "transcript" / "patent" /
        # "standard" / "regulator_doc" / "media" / "trade_pub" / "social_lead"
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    grade: Mapped[str] = mapped_column(String, nullable=False, index=True)
        # "strong" / "medium" / "weak" / "lead"
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
```

### 7. `research_company_ranking` (每次运行 3-7 行)

```python
class CompanyRanking(Base):
    __tablename__ = "research_company_ranking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=top
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True  # Q14: 反向链接查询走此 index
    )
    constrains_what: Mapped[str] = mapped_column(String, nullable=False)
        # "卡住的环节"
    chain_position: Mapped[str] = mapped_column(String, nullable=False)
        # "产业链位置"
    rank_reason_md: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    main_risk_md: Mapped[str] = mapped_column(Text, nullable=False)
```

### 表关系图

```
research_themes (1) ───────< (N) research_runs
                                     │
                                     ├──< (8)   value_chain_layers
                                     │              │
                                     │              └──< (3-5) scarce_layers
                                     │
                                     ├──< (≥20) research_company_universe
                                     │
                                     ├──< (≥25) research_evidence
                                     │
                                     └──< (3-7) research_company_ranking

themes (1) ──< (N) research_themes  # parent_theme_id 可选 FK
stocks (1) ──< (N) research_company_universe / evidence / company_ranking
```

## Spike 阶段执行 (Day 1-2)

### Day 1 上午: GLM-5.2 接入确认

**Step 1**: 注册 GLM-5.2 API key
- 访问 https://open.bigmodel.cn/pricing 确认 GLM-5.2 定价
- 访问 https://open.bigmodel.cn/dev/api 确认:
  - GLM-5.2 的 model name (例如 `glm-5.2` 或 `glm-5-plus`)
  - context window 大小 (目标 ≥128K)
  - tools 字段格式 (function calling + web_search 是否独立 tools)
  - web_search tool 的入参 / 出参 schema

**Step 2**: `.env` 加配置
```bash
ZHIPU_API_KEY=<your-key>
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4  # 默认,可改 OpenRouter 反代
SERENITY_MONTHLY_BUDGET_CNY=100  # Q8 软上限
```

**Step 3**: 写 spike 脚本 `backend/spikes/serenity_glm_spike.py`

```python
"""Spike: 验证 GLM-5.2 能否跑通 serenity-skill 完整工作流。

不入 app/, 不入测试。仅产出 demo JSON + Markdown 报告。
"""
import json
from pathlib import Path
from zhipuai import ZhipuAI

from app.services.lixinger_client import get_lixinger_client
from app.config import settings

SYSTEM_PROMPT = """
你是 Gojira 投资驾驶舱的「供应链卡点猎手」研究助手,遵循 serenity-skill 方法论。

工作流:
1. 把主题翻译为系统变化
2. 列价值链 8 层
3. 找稀缺层并排名 (3-5 层)
4. 构建公司宇宙 (≥20 家,跨各层)
5. 收集证据 (≥25 sources,4 档分级:strong/medium/weak/lead)
6. 选出 Top 3-7 公司,每家带:卡住的环节 / 位置 / 排序原因 / 证据 / 主要风险
7. 列失败条件 (≥3 条)
8. 列下一步验证 (≥3 条)

证据来源优先级 (高→低):
1. 年报/季报/公告/问询函/招投标/环评/专利 (grade=strong)
2. 公司 IR / 财报电话会议 / 官方订单文档 (grade=strong/medium)
3. 权威财经媒体 / 行业期刊 (grade=medium)
4. 行业协会 / 标准 / 技术论文 (grade=medium/weak)
5. KOL / 社交媒体线索 (grade=lead,不作证明)

强制约束:
- 每条证据必须有 source_url
- 未经 URL 验证的一律降为 lead
- 优先访问 cninfo.com.cn / sse.com.cn / szse.cn / eastmoney.com 等官方源
- 输出严格按 submit_research 工具 schema,不要裸文本

可用工具:
- web_search: 抓取实时数据 (上限 30 次)
- submit_research: 提交结构化研究结果 (必须调用)
"""

def build_user_context(theme: str, market: str) -> dict:
    """从 Lixinger 拉取上下文数据。"""
    lixinger = get_lixinger_client()

    # 拉行业成分股 (主题候选宇宙)
    industries = lixinger.get_industry_list()
    # 根据 theme 匹配行业 (AI 半导体 → 半导体元件 / 半导体设备 / 集成电路封测)
    matched_industries = _match_industries(theme, industries)
    candidates = []
    for ind_code in matched_industries:
        constituents = lixinger.get_industry_constituents(ind_code)
        candidates.extend(constituents[:30])  # 每个行业最多 30 家

    # 拉每家公司的 customers / suppliers / revenue_composition
    enriched = []
    for c in candidates[:50]:  # 上限 50 家,避免 Lixinger 配额
        code = c["stock_code"]
        enriched.append({
            "code": code,
            "name": c["name"],
            "industry": c.get("industry"),
            "customers": lixinger.get_customers(code, "2020-01-01"),
            "suppliers": lixinger.get_suppliers(code, "2020-01-01"),
        })

    return {
        "theme": theme,
        "market": market,
        "time_window": "3-12M",
        "candidates_snapshot": enriched,
    }


def main():
    client = ZhipuAI(api_key=settings.zhipu_api_key)

    user_context = build_user_context(
        theme="AI 半导体",
        market="A_SHARE",
    )

    response = client.chat.completions.create(
        model="glm-5.2",  # 待官方文档确认
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_context, ensure_ascii=False, indent=2)},
        ],
        tools=[
            {
                "type": "web_search",
                "web_search": {"enable": True, "search_result": False},
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_research",
                    "description": "提交 serenity 研究结果",
                    "parameters": SERENITY_RESEARCH_JSON_SCHEMA,  # 见下
                },
            },
        ],
        tool_choice="auto",
        max_tokens=16000,
        temperature=0.3,
    )

    # 提取 submit_research tool call
    result = _extract_tool_call(response, "submit_research")

    # 落盘 demo
    out_dir = Path("backend/spikes/output")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "serenity_demo.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    (out_dir / "serenity_demo.md").write_text(_render_markdown(result))

    # 统计
    print(f"Token usage: {response.usage}")
    print(f"Companies: {len(result['company_universe'])}")
    print(f"Evidence: {len(result['evidence'])}")
    print(f"Top picks: {len(result['company_ranking'])}")


SERENITY_RESEARCH_JSON_SCHEMA = {
    "type": "object",
    "required": [
        "system_change", "value_chain", "scarce_layers",
        "company_universe", "evidence", "company_ranking",
        "failure_conditions", "next_steps",
    ],
    "properties": {
        "system_change": {"type": "string", "description": "一句话技术/经济变化"},
        "value_chain": {
            "type": "array", "minItems": 8, "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["layer_index", "name", "description"],
                "properties": {
                    "layer_index": {"type": "integer", "minimum": 1, "maximum": 8},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "scarce_layers": {
            "type": "array", "minItems": 3, "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["rank", "layer_index", "reason", "difficulty"],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1},
                    "layer_index": {"type": "integer"},
                    "reason": {"type": "string"},
                    "difficulty": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        },
        "company_universe": {
            "type": "array", "minItems": 20,
            "items": {
                "type": "object",
                "required": ["stock_code", "classification"],
                "properties": {
                    "stock_code": {"type": "string", "pattern": r"^\d{6}$"},
                    "classification": {
                        "type": "string",
                        "enum": ["controls", "supplies", "benefits", "weak", "story"],
                    },
                    "layer_index": {"type": "integer"},
                    "note": {"type": "string"},
                },
            },
        },
        "evidence": {
            "type": "array", "minItems": 25,
            "items": {
                "type": "object",
                "required": ["source_url", "source_title", "source_type", "grade", "summary"],
                "properties": {
                    "stock_code": {"type": "string", "pattern": r"^\d{6}$"},
                    "source_url": {"type": "string"},
                    "source_title": {"type": "string"},
                    "source_type": {
                        "type": "string",
                        "enum": ["filing", "announcement", "transcript", "patent",
                                 "standard", "regulator_doc", "media", "trade_pub", "social_lead"],
                    },
                    "published_at": {"type": "string", "format": "date"},
                    "grade": {"type": "string", "enum": ["strong", "medium", "weak", "lead"]},
                    "summary": {"type": "string"},
                },
            },
        },
        "company_ranking": {
            "type": "array", "minItems": 3, "maxItems": 7,
            "items": {
                "type": "object",
                "required": ["rank", "stock_code", "constrains_what",
                             "chain_position", "rank_reason", "evidence_summary", "main_risk"],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1},
                    "stock_code": {"type": "string", "pattern": r"^\d{6}$"},
                    "constrains_what": {"type": "string"},
                    "chain_position": {"type": "string"},
                    "rank_reason": {"type": "string"},
                    "evidence_summary": {"type": "string"},
                    "main_risk": {"type": "string"},
                },
            },
        },
        "failure_conditions": {
            "type": "array", "minItems": 3,
            "items": {"type": "string"},
        },
        "next_steps": {
            "type": "array", "minItems": 3,
            "items": {"type": "string"},
        },
    },
}


if __name__ == "__main__":
    main()
```

### Day 1 下午: 跑 spike + 评估

跑 `python backend/spikes/serenity_glm_spike.py`,评估以下维度:

| 维度 | 通过标准 | 失败处置 |
|---|---|---|
| 公司宇宙数量 | ≥20 家 | 降级到 Q1 选 A (MVP) 或 Q5 选 A (Anthropic Claude) |
| 证据数量 | ≥25 sources | 同上 |
| 证据分级合理性 | strong 全是官方源,lead 才是 KOL | 调整 system prompt |
| JSON schema 严格度 | 一次通过 schema 校验 | 加 Pydantic 验证 + retry-once |
| source URL 真实可达 | 抽样 5 条手动访问,全部 200 | 调整 prompt 强制 cite 真实 URL |
| 单次 token 消耗 | input < 80K / output < 12K | 调整 max_tokens / max_searches |
| 单次耗时 | < 5 分钟 | 切异步执行 (Q6 已锁定) |
| 公告源覆盖度 | 至少 5 条来自 cninfo/sse/szse | 加 prompt 强制优先官方源 |

### Day 2: 根据 spike 调整

1. **schema 调整**: 如果 spike 输出有 6 张表未覆盖的字段,加列;如果某些字段从未填,删列。
2. **prompt 调整**: 如果 LLM 偏向 KOL 源,加更强约束;如果公司分类不准,加 examples。
3. **config 调整**: 如果 token 爆炸,降 `max_searches` 到 20;如果不够,加到 40。
4. **异步决策**: 如果耗时 > 3 分钟,确认必须异步执行。

## Phase 1 正式实现 (Day 3-7)

### Day 3: 后端骨架

- [ ] 写 Alembic migration (7 个新表)
  - **注意 Q14**: `research_company_universe.stock_code` / `research_company_ranking.stock_code` / `research_evidence.stock_code` 全部 `index=True`
- [ ] 写 7 个 ORM model (`research_theme.py` / `research_run.py` / `value_chain_layer.py` / `scarce_layer.py` / `research_company_universe.py` / `research_evidence.py` / `research_company_ranking.py`)
- [ ] 写 7 个 Pydantic schema
- [ ] 写 `app/services/llm/zhipu_client.py` (复用 spike 验证过的 prompt + config,直接调用不抽象 Q16)
- [ ] 写 `app/services/research_runner_service.py`
  - **Q10 异步**: `run_serenity()` 立即创建 `ResearchRun(status='running')` + 提交到 `ThreadPoolExecutor` + 返回 run_id
  - **Q13 三重硬约束**: max_tokens / max_searches / timeout
  - **Q17 告警**: 失败时 publish `ResearchRunFailed` 事件,EventBus 订阅调 `notification_service.send()` 复用 NotificationChannel
- [ ] 写 `app/core/research_config.py` (`SERENITY_RUN_CONFIG` + `SERENITY_MONTHLY_BUDGET_CNY`)
- [ ] 加 EventBus 事件 `ResearchRunCompleted` / `ResearchRunFailed` / `MonthlyBudgetExceeded`
- [ ] 加 EventBus 订阅触发 notification (复用 Q17 NotificationChannel)

### Day 4: 后端 router + scheduler

- [ ] 写 `app/routers/research.py`:
  - `GET /api/research/themes` 列表
  - `POST /api/research/themes` 新建
  - `GET /api/research/themes/{id}` 详情
  - `POST /api/research/themes/{id}/run` 触发研究 (**Q10 异步**: 立即返回 `{run_id, status: 'running'}`,不阻塞)
  - `GET /api/research/runs/{id}` 查 Run 状态 + 完整结构化结果(供前端 polling)
  - `POST /api/research/runs/{id}/export` 导出 Top N 到 Watchlist/Candidate (**Q11 不过 Checklist**)
  - `GET /api/research/appearances/{stock_code}` 反向链接查询(走 Q14 index)
- [ ] 在 `app/scheduler.py` 加 cron `0 8 * * 1` (每周一 8 点扫 `auto_refresh_freq='weekly'`)
- [ ] 在 `app/services/research_scheduler_service.py` 写 `run_due_research_themes()`
  - **Q12 跳过失败**: `db.query(ResearchTheme).filter(status='active', auto_refresh_freq='weekly', last_run_status != 'failed')`
- [ ] 在 `app/main.py` 注册 router + scheduler

### Day 5: 前端 UI

- [ ] **新增依赖**: `cd frontend && npm install react-markdown remark-gfm rehype-raw` (Q18)
- [ ] 写 `frontend/src/features/research/ResearchThemesPage.tsx` (列表 + 新建)
- [ ] 写 `frontend/src/features/research/ResearchThemeDetailPage.tsx` (6 个 tab)
  - OverviewTab / ValueChainTab / CompaniesTab / EvidenceTab / FailureTab / HistoryTab
  - 所有 markdown 字段(`system_change_md` / `scarcity_reason_md` / `failure_conditions_md` / `next_steps_md` / `rank_reason_md` / `evidence_summary_md` / `main_risk_md`)用 `react-markdown` + `remark-gfm` 渲染
- [ ] 写 `frontend/src/features/research/useResearchRunPolling.ts` (Q10 异步 polling hook,基于 TanStack Query 的 `refetchInterval`)
- [ ] 写 `frontend/src/api/client.ts` 加 research 相关函数
- [ ] 写 `frontend/src/api/types.ts` 加 research 相关类型
- [ ] 在 `frontend/src/components/Layout.tsx` 加 "Research / 研究" 菜单项
- [ ] 在 `CockpitPage.tsx` 加 "今日 serenity" 卡片
- [ ] 在 `StockDetailPage.tsx` 加 "出现在以下研究中" panel (查 `GET /api/research/appearances/{stock_code}`,走 index 优化 Q14)
- [ ] 在 `CandidatesPage.tsx` 加 `source='serenity'` 过滤 + 徽章

### Day 6: 后端测试

- [ ] `tests/test_research_runner_service.py` (≥8 个测试)
  - 测 run_serenity 成功路径 (LLM mock)
  - 测 run_serenity 失败 + retry
  - 测 schema 校验失败
  - 测 rate_limit_per_theme_minutes
  - 测 triggered_by='manual' / 'scheduler'
  - 测 **Q10 异步**: `run_serenity()` 立即返回 run_id,后台线程后续写库
  - 测 **Q13 三重硬约束**: max_tokens / max_searches / timeout 任一触发的失败路径
  - 测 **Q17 告警**: 失败时 publish `ResearchRunFailed` 事件 + notification 调用断言
- [ ] `tests/test_research_persistence.py` (≥4 个测试)
  - 测 7 张表正确写入
  - 测 FK 约束
  - 测 cascade delete
  - 测 **Q14 index 存在**: 查询走索引(可用 EXPLAIN 验证,或测试大数量级查询性能不退化)
- [ ] `tests/test_research_export_service.py` (≥3 个测试)
  - 测导出到 Watchlist
  - 测导出到 Candidate (source='serenity')
  - 测 **Q11 不过 Checklist**: export 调用不触发 DisciplineChecklistModal 服务
- [ ] `tests/test_research_scheduler.py` (≥2 个测试)
  - 测 weekly 调度
  - 测 **Q12 跳过失败**: last_run_status='failed' 的主题不被 scheduler 触发
- [ ] 3 个集成测试用 spike 真实输出做 fixture
- [ ] `tests/test_research_appearance_index.py` (≥1 个测试)
  - 测 **Q14**: 100 Run × 20 公司 universe 大数据量下,`GET /api/research/appearances/{code}` < 100ms

### Day 7: 文档 + 验收

- [ ] 写 `docs/progress/2026-06-XX-serenity-skill-integration.md` (实施记录)
- [ ] 更新 `docs/progress/STATUS.md` (新模块 + 新表 + 新 router)
- [ ] 写 `docs/reports/completed/serenity-skill-integration-2026-06-XX.md` (完成报告)
- [ ] 跑 2 次真实研究 (AI 半导体 + 银行) 人工验收
- [ ] 跑全测试套件,确认 ≥ 831 测试通过 (816 baseline + ≥15 新增)

## ship 标准 Checklist

- [ ] 后端测试 ≥ 15 个新增,全部通过(816 → 831+ baseline)
- [ ] Alembic migration 1 个新版本,head 推进
- [ ] 前端 `/research` 路由 + 详情页 6 个 tab + Cockpit 卡片 + StockDetail panel + Candidates 徽章
- [ ] **Q10 异步**: 后端 `run_serenity()` 走 ThreadPoolExecutor,前端 polling `/api/research/runs/{id}` < 100ms 单次响应
- [ ] **Q12 失败跳过**: scheduler 不触发 `last_run_status='failed'` 主题
- [ ] **Q14 index**: `GET /api/research/appearances/{code}` 100 Run × 20 公司数据量下 < 100ms
- [ ] **Q17 复用 NotificationChannel**: `ResearchRunFailed` 事件触发后,in_app / server_chan (如启用) 都收到告警
- [ ] **Q18 Markdown 渲染**: react-markdown + remark-gfm + rehype-raw 装好,所有 `_md` 字段渲染表格/列表/链接正常
- [ ] 真实研究跑过 3 次 (spike 1 次 + ship 后 2 次),人工评估报告质量
- [ ] LLM 完整日志落盘到 `data/llm_logs/{run_id}.json`
- [ ] Cockpit 显示 monthly_token_spend 指标 (Q8 软上限告警依据)
- [ ] EventBus 事件 `ResearchRunCompleted` / `ResearchRunFailed` / `MonthlyBudgetExceeded` 注册
- [ ] 失败重试机制 + Q17 多通道 notification 触发
- [ ] scheduler cron `0 8 * * 1` 注册 + Q12 失败跳过逻辑
- [ ] `.env` 加 `ZHIPU_API_KEY` / `ZHIPU_BASE_URL` / `SERENITY_MONTHLY_BUDGET_CNY`
- [ ] `health` router 加 `/api/health/zhipu` 深度探针
- [ ] 文档 progress.md + STATUS.md 更新 + 完成报告

## 已解决的子问题 (第二轮 grill 产出,2026-06-14)

第二轮 grill (批 1-3) 锁定全部 10 个细节决策,全部按推荐落地:

| # | 子问题 | 决策 | 落地动作 |
|---|---|---|---|
| 10 | 执行模式 | **异步 ThreadPoolExecutor** | 沿用 `app/core/events.py:30` 的 `_executor` 模式,新建 `app/services/research_runner_service.py` 提交 background task;前端 polling `GET /api/research/runs/{id}` 看进度 |
| 11 | 导出 Checklist | **不过** | `research_export_service` 直接写 Candidate,`source='serenity'`;DisciplineChecklistModal 仍只在 Candidate → Draft 执行时触发(现有逻辑) |
| 12 | weekly 失败跳过 | **跳过** | `research_scheduler_service.run_due_research_themes()` 加 `filter(ResearchTheme.last_run_status != 'failed')`;UI 显示"⏸ 上次失败,已暂停自动调度",用户可手动重启 |
| 13 | LLM 死循环兜底 | **仅三重硬约束** | max_tokens=16K + max_searches=30 + timeout=300s;Phase 1 监控实际发生率,如频繁(>5% Run 失败因重复搜索)再加重复 tool call 检测 |
| 14 | StockDetail 反向链接 | **加 index** | `research_company_universe.stock_code` / `research_company_ranking.stock_code` / `research_evidence.stock_code` 全部 `index=True`;SQLAlchemy 查询时 `db.query(...).filter(stock_code=X).all()` 走索引 |
| 15 | 历史 Run diff 视图 | **Phase 1 只列表** | History tab 显 Run 列表 + 时间戳 + status + Top N 公司快照;Phase 2 设计 diff 语义(排名升降?稀缺层增减?证据强度变化?) |
| 16 | LLMProvider 抽象 | **不做** | Phase 1 直接写 `ZhipuClient`,不抽 `LLMProvider` Protocol;Phase 2 如需 DeepSeek 备选再重构(YAGNI + [[feedback-defer-infra-until-core-flow]]) |
| 17 | 告警通道 | **复用现有 NotificationChannel** | `notification_service.send()` 已支持 in_app + server_chan + email + dingtalk + telegram;EventBus `ResearchRunFailed` / `MonthlyBudgetExceeded` 事件订阅直接调用,零新增基础设施 |
| 18 | Markdown 渲染 | **react-markdown + remark-gfm + rehype-raw** | Day 5 `npm install react-markdown remark-gfm rehype-raw`;bundle 增加 ~50KB 可接受 |
| 19 | 失败条件 → 论点变量转译 | **Phase 1 不做** | UI 只显示 `failure_conditions_md` 文本;Phase 2 专项设计(LLM 二次推理 / 结构化 schema / 与 `thesis_variable_sync_service` 衔接) |

### 落地影响

**新增依赖**:
- 前端: `react-markdown` + `remark-gfm` + `rehype-raw` (3 个)

**复用现有基础设施**:
- 异步执行: `app/core/events.py:30` `_executor: ThreadPoolExecutor(max_workers=4)`
- 告警通道: `app/services/notification_service.py` + `NotificationChannel` 表
- Lixinger 上下文装配: `get_industry_list` / `get_industry_constituents` / `get_customers` / `get_suppliers` / `get_revenue_composition`

**Phase 2 待办**(从 grill 中识别的后续工作):
- 历史 Run diff 视图设计(Q15)
- 失败条件 → 论点变量结构化转译(Q19)
- 多 provider 抽象(如 GLM-5.2 实测质量不足时,Q16)
- LLM 死循环重复 tool call 检测(如 Phase 1 监控发现频繁,Q13)

## 关联文件索引

实施时涉及的现有文件:

| 文件 | 修改内容 |
|---|---|
| `backend/app/main.py` | 注册 research router + scheduler cron |
| `backend/app/config.py` | 加 zhipu_api_key / zhipu_base_url / serenity_monthly_budget_cny |
| `backend/app/scheduler.py` | 加 weekly cron |
| `backend/app/core/events.py` | 加 ResearchRunCompleted / ResearchRunFailed / MonthlyBudgetExceeded 事件 (Q10/Q17) |
| `backend/app/core/event_handlers.py` | 加事件订阅触发 notification_service.send() (Q17 复用 NotificationChannel) |
| `backend/app/services/notification_service.py` | **不修改**,仅复用 send() 方法 (Q17) |
| `backend/app/services/lixinger_client.py` | **不修改**,仅复用 get_industry_list / get_industry_constituents / get_customers / get_suppliers / get_revenue_composition |
| `backend/app/routers/health.py` | 加 `/api/health/zhipu` 深度探针 |
| `backend/app/models/__init__.py` | 注册 7 个新 model |
| `backend/alembic/versions/` | 新增 1 个 migration 文件 (含 Q14 三个 index) |
| `frontend/src/App.tsx` | 加 `/research` 路由 |
| `frontend/src/components/Layout.tsx` | 加 "Research" 菜单项 |
| `frontend/src/api/client.ts` | 加 research 相关 API 函数 |
| `frontend/src/api/types.ts` | 加 research 相关类型 |
| `frontend/src/features/cockpit/CockpitPage.tsx` | 加 "今日 serenity" 卡片 |
| `frontend/src/pages/StockDetailPage.tsx` 或 features/ | 加反向链接 panel (走 Q14 index) |
| `frontend/src/features/candidates/CandidatesPage.tsx` | 加 source 徽章 + 过滤 (Q11 不过 Checklist 仍打 source 标) |
| `frontend/package.json` | 加 react-markdown + remark-gfm + rehype-raw 依赖 (Q18) |
| `.env.example` | 加 ZHIPU_API_KEY / ZHIPU_BASE_URL / SERENITY_MONTHLY_BUDGET_CNY 模板 |
| `CLAUDE.md` | 在「模块清单」加 research 模块说明 |
| `docs/progress/STATUS.md` | 更新模块数 / 表数 / router 数 |

## 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| GLM-5.2 中文金融质量不足 | 中 | 高 (整个模块无价值) | spike Day 1 验证;失败则切 Q5 选项 A (Anthropic Claude) |
| GLM-5.2 web search 抓不到 cninfo/sse 公告 | 中 | 中 (证据 grade 偏低) | system prompt 强制优先官方源;Phase 2 评估是否加 cninfo 直连 |
| LLM token 成本超预算 | 低 | 中 (单月 > ¥100) | Q8 软上限告警;Phase 1 跑通后调参 |
| JSON schema 不严格 | 中 | 中 (落库脏数据) | Pydantic 验证 + retry-once;spike 阶段验证 |
| LLM 死循环 / 重复搜索 | 低 | 中 (单次 Run 失败) | max_tokens / max_searches / timeout 三重兜底 |
| 跟 Q3 决策(用户手动导出)的用户体验割裂 | 中 | 低 (用户多一步操作) | Q7 决策的多入口(徽章 + 反向链接)缓解 |
| 跟 2026-06-14 锁定的 5-7 天 ship 路径冲突 | 中 | 中 (插队) | serenity 实施不阻塞数据 / drafts / backtest 路径;可并行 |
