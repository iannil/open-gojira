# Gojira v2 Prompts

Prompt 文件按 Pipeline + 版本组织：

```
prompts/
├── README.md                       (本文件)
├── shared/                         (跨 Pipeline 共享)
│   ├── system_base.md              (通用 system prompt)
│   ├── defense_methodology.md      (ai-berkshire 8 红线 + A/B/C 评级 + 芒格逆向)
│   └── evidence_grading.md         (serenity 证据分级 strong/medium/weak/lead)
├── deep_research/                  (Phase 2 实现)
│   └── v1/  (占位,Phase 2 添加)
├── thesis_tracker/                 (Phase 4 实现)
├── news_pulse/                     (Phase 4 实现)
├── earnings_review/                (Phase 4 实现)
└── quality_screen/                 (Phase 2 实现)
```

## 加载机制

`app/services/llm/prompt_loader.py` 提供：

```python
def load_prompt(pipeline: str, name: str, version: str = "v1") -> str:
    """Load prompt content from app/prompts/{pipeline}/{version}/{name}.md"""

def load_shared(name: str) -> str:
    """Load from app/prompts/shared/{name}.md"""

def build_system_prompt(pipeline: str, version: str = "v1") -> str:
    """Assemble shared system_base + defense_methodology + evidence_grading
    + pipeline-specific system prompt."""
```

## 版本管理

- 每个 Pipeline 有 `v1/`, `v2/`, ... 子目录
- `research_reports.prompt_version` 记录用哪个版本生成
- 改 prompt 时新建版本目录，不修改旧版本（支持 A/B 测试和回滚）

## 原则

- Prompt 是代码，受 git 版本控制
- 重要 prompt 改动走 code review
- 不在 DB 存 prompt（避免热更新绕过 review）
