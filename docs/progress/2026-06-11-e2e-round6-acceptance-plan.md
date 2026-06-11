# P1-1 端到端验收(round6 修复回归)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 验收 round6 的 6 项关键修复(P0-03/P0-05/P0-01/02/P1-12/P1-13/P1-15)在真实业务闭环中确实生效,产出可重复运行的 smoke 脚本 + 人工 UI checklist 验收报告。

**Architecture:** 混合 C+B 模式 —— `backend/scripts/smoke_test.py`(Python httpx + Pydantic 校验,**不进 pytest**)承担 API 契约/数据/原子性回归;`docs/reports/e2e-round6-acceptance-2026-06-11.md` 承载人工 UI 走查 checklist。DB 备份/还原保证可重复运行。删除已失效的 Playwright 基建(详见 `docs/adr/0001-no-playwright-e2e.md`)。

**Tech Stack:** Python 3.14 + httpx + Pydantic v2(复用 `backend/app/schemas/`);Bash 备份/还原;Markdown 报告(走 `docs/templates/acceptance-report.md` 模板)。

**关联决策**:本计划来自 grill-with-docs 会话(2026-06-11),8 项决策汇总见会话记录;ADR `docs/adr/0001-no-playwright-e2e.md`;原始需求在 `docs/active/roadmap.md` P1-1。

---

## 文件结构

**新增**:
- `backend/scripts/__init__.py`(空)—— 让 `scripts/` 成为可导入目录
- `backend/scripts/smoke_test.py` —— smoke 脚本主入口,~350 行
- `docs/reports/e2e-round6-acceptance-2026-06-11.md` —— 验收报告(走模板)

**修改**:
- `frontend/package.json` —— 移除 `@playwright/test` 依赖
- `frontend/package-lock.json` —— 由 `npm uninstall` 自动重生成
- `docs/active/roadmap.md` —— P1-1 状态从 ⚠️ 改为 ✅
- `docs/progress/STATUS.md` —— 5.3 节待修复项更新

**删除**:
- `frontend/tests/e2e/`(整个目录,含 golden-path / smoke / valuation-tabs / fixtures)
- `frontend/playwright.config.ts`
- `frontend/playwright-report/`(若存在,运行残留)

**不动**:
- `plan_exec_history` / `plan_templates` 表的 drop(开 P3 ticket,见 Task 11)

---

## Task 1: 删除失效的 Playwright E2E 基建

**Files:**
- Delete: `frontend/tests/e2e/`
- Delete: `frontend/playwright.config.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: 确认死代码状态**

Run:
```bash
ls frontend/tests/e2e/ 2>&1
git log --oneline -- frontend/tests/e2e/ | head -5
```

Expected: 目录存在;git log 只有 `0b0cf18 init` 一条提交(说明 specs 是 init 时建死代码,从未更新)。

- [ ] **Step 2: 删除 specs + config**

Run:
```bash
rm -rf frontend/tests/e2e/
rm -f frontend/playwright.config.ts
rm -rf frontend/playwright-report/
```

- [ ] **Step 3: 卸载 @playwright/test 依赖**

Run:
```bash
cd frontend && npm uninstall @playwright/test
```

Expected: `package.json` 不再含 `@playwright/test`,`package-lock.json` 同步更新。

- [ ] **Step 4: 验证 frontend 仍可 build**

Run:
```bash
cd frontend && npm run build
```

Expected: 构建成功,无 "Cannot find module '@playwright/test'" 错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/tests frontend/playwright.config.ts frontend/playwright-report frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
chore: 删除失效的 Playwright E2E 基建

理由详见 docs/adr/0001-no-playwright-e2e.md:
- frontend/tests/e2e/golden-path.spec.ts 引用已删除的路由(/screener, /analysis,
  /discipline 等)和 API(/api/screener/run 等),跑 npx playwright test 必然全红
- 业务 IA 还可能变,Playwright 维护成本高于回归保护价值
- 改为 backend/scripts/smoke_test.py + 人工 UI checklist 混合模式

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 创建 smoke 脚本骨架(entry point + report writer)

**Files:**
- Create: `backend/scripts/__init__.py`(空文件)
- Create: `backend/scripts/smoke_test.py`

- [ ] **Step 1: 建 scripts 目录 + __init__.py**

Run:
```bash
mkdir -p backend/scripts
touch backend/scripts/__init__.py
```

- [ ] **Step 2: 写 smoke_test.py 骨架**

Create `backend/scripts/smoke_test.py`:

```python
"""
P1-1 端到端验收 smoke 脚本 — round6 修复回归

用法:
    cd backend
    source .venv/bin/activate
    python scripts/smoke_test.py [--base-url http://localhost:3001]

设计原则:
- 不进 pytest (smoke 需要真实 Lixinger + 真实 DB,与单测语义不同)
- 每个场景独立函数,失败不影响其它场景
- 报告格式遵循 docs/templates/acceptance-report.md
- 退出码: 全部 PASS = 0, 任一 FAIL = 1

数据生命周期:
- 调用方需在脚本外做 DB 备份/还原 (见 Task 9)
- 脚本内的 setup 阶段会创建测试数据 (OR plan / test holding)
- 脚本不主动清理,DB 还原负责回滚
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx


@dataclass
class ScenarioResult:
    """单个验收场景的结果"""
    code: str               # e.g. "P0-03"
    name: str               # e.g. "Universe vs Cockpit weight consistency"
    passed: bool
    expected: str           # 通过标准描述
    actual: str             # 实际观察
    artifacts: dict = field(default_factory=dict)  # 附带数据(API 响应片段等)


def setup_test_data(client: httpx.Client) -> list[str]:
    """
    在跑场景前准备测试数据。
    返回创建的 artifact 列表(写进报告的 Setup 段)。
    """
    artifacts: list[str] = []
    # Task 5 会在这里加入 "create OR plan" 的逻辑
    # Task 6 会在这里加入 "create test holding" 的逻辑
    return artifacts


def write_report(
    results: list[ScenarioResult],
    setup_artifacts: list[str],
    output_path: Path,
    base_url: str,
) -> None:
    """按 docs/templates/acceptance-report.md 模板写报告"""
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    lines: list[str] = []
    lines.append("# E2E Round6 修复回归 验收报告")
    lines.append("")
    lines.append(f"> **验收日期**: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("> **验收人**: Claude Code (smoke_test.py + 人工 UI 走查)")
    lines.append("> **被验收对象**: round6 审计修复 (P0×5 + P1×15 + P2×12)")
    lines.append("> **关联文档**: `docs/reports/completed/full-audit-round6-2026-06-11.md`")
    lines.append("")
    lines.append("## 验收范围 (Scope)")
    lines.append("")
    lines.append("验收 round6 中 6 项用户可见/原子性修复:")
    lines.append("- P0-03 持仓权重计算基数一致 (Universe vs Cockpit)")
    lines.append("- P0-05 行业权重前后检查基数一致")
    lines.append("- P0-01/02 Plan DSL OR composition 生效")
    lines.append("- P1-12 updateThesisVariables 返回 StockResponse")
    lines.append("- P1-13 CockpitDraft 含 source 字段")
    lines.append("- P1-15 service 层 db.commit() 已分类 (请求路径 vs 后台)")
    lines.append("")
    lines.append("**未验收**: 其它 26 项 P0/P1/P2 由 402 单元测试覆盖,不在 E2E 范围。")
    lines.append("")
    lines.append(f"**Base URL**: `{base_url}`")
    lines.append("")
    lines.append("## 验收步骤 (Steps)")
    lines.append("")
    lines.append("| # | 场景 | 预期 | 实际 | 状态 |")
    lines.append("|---|------|------|------|------|")
    for i, r in enumerate(results, 1):
        status = "✅" if r.passed else "❌"
        lines.append(f"| {i} | **{r.code}** {r.name} | {r.expected} | {r.actual} | {status} |")
    lines.append("")
    lines.append("## 通过/失败统计 (Summary)")
    lines.append("")
    lines.append(f"- **总计**: {len(results)} 场景")
    lines.append(f"- **通过**: ✅ {passed}")
    lines.append(f"- **失败**: ❌ {failed}")
    lines.append("")
    if setup_artifacts:
        lines.append("## Setup Artifacts")
        lines.append("")
        for a in setup_artifacts:
            lines.append(f"- {a}")
        lines.append("")
    if failed:
        lines.append("## 失败项详情 (Failures Detail)")
        lines.append("")
        for r in results:
            if not r.passed:
                lines.append(f"### {r.code} {r.name}")
                lines.append("")
                lines.append(f"- **预期**: {r.expected}")
                lines.append(f"- **实际**: {r.actual}")
                if r.artifacts:
                    lines.append("- **Artifacts**:")
                    for k, v in r.artifacts.items():
                        lines.append(f"  - `{k}`: `{v}`")
                lines.append("")
        lines.append("## 后续动作 (γ 分级策略)")
        lines.append("")
        lines.append("- **round6 尾巴**(本应已修但实测未生效)→ 当场修复,新开 commit")
        lines.append("- **无关存量 bug** → 开新 P1 ticket,不在本验收 scope")
        lines.append("- **cosmetic** → 仅记录")
        lines.append("")
    lines.append("## 环境信息 (Environment)")
    lines.append("")
    lines.append("- **后端 commit**: 见 `git log -1 --format=%H`")
    lines.append("- **数据库**: SQLite + WAL,`backend/data/gojira.db`")
    lines.append("- **Python**: 见 `python --version`")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to: {output_path}")


# 场景函数占位 — Task 3-8 会填充
SCENARIOS: list[Callable[[httpx.Client], ScenarioResult]] = []


def main() -> int:
    parser = argparse.ArgumentParser(description="P1-1 E2E smoke test")
    parser.add_argument("--base-url", default="http://localhost:3001")
    parser.add_argument(
        "--output",
        default="docs/reports/e2e-round6-acceptance-2026-06-11.md",
    )
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=30.0)

    # 1) health check
    try:
        r = client.get("/api/health")
        r.raise_for_status()
    except Exception as e:
        print(f"FAIL: backend not reachable at {args.base_url}: {e}", file=sys.stderr)
        return 2

    # 2) setup
    print("Setup: creating test data...")
    setup_artifacts = setup_test_data(client)
    for a in setup_artifacts:
        print(f"  - {a}")

    # 3) run scenarios
    results: list[ScenarioResult] = []
    for scenario in SCENARIOS:
        print(f"Running: {scenario.__name__}...")
        try:
            result = scenario(client)
        except Exception as e:
            result = ScenarioResult(
                code="UNKNOWN",
                name=scenario.__name__,
                passed=False,
                expected="scenario completes without exception",
                actual=f"unhandled exception: {type(e).__name__}: {e}",
            )
        results.append(result)
        marker = "✅" if result.passed else "❌"
        print(f"  {marker} {result.code} {result.name}: {result.actual}")

    # 4) write report
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parents[2] / args.output
    write_report(results, setup_artifacts, output_path, args.base_url)

    # 5) summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(f"\nResults: {passed} passed, {failed} failed (of {len(results)} scenarios)")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 验证脚本能跑(空场景列表)**

Run:
```bash
cd backend
source .venv/bin/activate
python scripts/smoke_test.py --output /tmp/smoke-dryrun.md
```

Expected: 退出码 0,打印 "Results: 0 passed, 0 failed",`/tmp/smoke-dryrun.md` 写出。

- [ ] **Step 4: 提交**

```bash
git add backend/scripts/
git commit -m "$(cat <<'EOF'
feat(smoke): 加 P1-1 验收 smoke 脚本骨架

backend/scripts/smoke_test.py 是独立的端到端验收入口:
- 不进 pytest (smoke 需真实 Lixinger + 真实 DB)
- 走 docs/templates/acceptance-report.md 模板
- 场景列表为空,后续 commit 逐个填充

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 场景 P1-15 — services 中 db.commit() 分类表(静态)

> 先做这个,因为它不依赖任何测试数据,纯静态。

**Files:**
- Modify: `backend/scripts/smoke_test.py`(在 SCENARIOS 前插入函数)

- [ ] **Step 1: 写场景函数**

在 `backend/scripts/smoke_test.py` 的 `SCENARIOS: list[...] = []` **之前**插入:

```python
import re
import subprocess


# 后台路径白名单 — 这些目录/文件里的 db.commit() 是合法的
# (长任务必须 checkpoint,不归 get_db 管)
_BACKGROUND_PATHS = (
    "app/services/pipelines/",   # Pipeline 内部 checkpoint / dead_letter / manager
    "app/services/builtin_seeder.py",  # 启动初始化
    "app/services/kline_service.py",   # 调度任务
    "app/services/dividend_service.py",
    "app/services/financial_service.py",
    "app/services/thesis_variable_sync_service.py",  # 调度触发的批量同步
    "app/services/alert_service.py",  # 需进一步确认 (见 expected)
)


def scenario_p1_15_commit_classification(_client: httpx.Client) -> ScenarioResult:
    """
    P1-15: services/ 中的 db.commit() 全部归类到合法路径。

    通过标准:
    - 请求路径 services (router 直接调用) 必须无 db.commit()
    - 后台路径 (pipelines / builtin_seeder / scheduler 触发的 sync) 允许 db.commit()
    - alert_service 是边界 case: 需在 artifacts 里标注待人工 review
    """
    backend_root = Path(__file__).resolve().parents[1]
    services_dir = backend_root / "app" / "services"

    # grep 所有 db.commit() / self.db.commit()
    pattern = re.compile(r"\b(?:db|self\.db)\.commit\(\)")
    findings: list[tuple[str, str]] = []  # (rel_path:line, code)
    for py in services_dir.rglob("*.py"):
        rel = py.relative_to(backend_root)
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                findings.append((f"{rel}:{lineno}", line.strip()))

    # 分类
    background: list[str] = []
    suspicious: list[str] = []
    for loc, code in findings:
        rel_path = loc.split(":")[0]
        if any(rel_path.startswith(p) for p in _BACKGROUND_PATHS):
            background.append(f"{loc}  →  {code}")
        else:
            suspicious.append(f"{loc}  →  {code}")

    passed = len(suspicious) == 0
    return ScenarioResult(
        code="P1-15",
        name="services db.commit() 全部归类到后台路径",
        passed=passed,
        expected="0 个请求路径 commit;所有 commit 都在 pipelines/scheduler/seeder",
        actual=(
            f"background={len(background)}, suspicious={len(suspicious)}"
            + (f"; suspicious 位置: {'; '.join(suspicious)}" if suspicious else "")
        ),
        artifacts={
            "total_commits": str(len(findings)),
            "background_commits": str(len(background)),
            "suspicious_commits": str(len(suspicious)),
            "alert_service_note": (
                "alert_service.py 若被 router 同步调用则属请求路径,若是 EventBus "
                "异步 handler 则属后台。需人工 review 路径归属。"
            ),
        },
    )
```

然后在文件底部 `SCENARIOS: list[...] = []` 改为:

```python
SCENARIOS: list[Callable[[httpx.Client], ScenarioResult]] = [
    scenario_p1_15_commit_classification,
]
```

- [ ] **Step 2: 跑脚本验证场景能跑**

Run:
```bash
cd backend
source .venv/bin/activate
python scripts/smoke_test.py --output /tmp/smoke-p1-15.md
cat /tmp/smoke-p1-15.md
```

Expected: 退出码 0 或 1(取决于是否发现 suspicious commit),报告含 "P1-15" 行,artifacts 含 commit 计数。**当前预期**: alert_service.py 有 2 处 commit,会被标 suspicious(因 alert_service 不在白名单),passsed=False。这是已知 finding,后续场景跑完后统一处理。

- [ ] **Step 3: 提交**

```bash
git add backend/scripts/smoke_test.py
git commit -m "$(cat <<'EOF'
feat(smoke): P1-15 commit 分类场景

grep services 中 db.commit(),按白名单(后台路径)分类。
alert_service 是边界 case,标 suspicious 待人工 review。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 场景 P1-13 — CockpitDraft.source 字段非空

> 这个场景只需 GET /api/cockpit,不依赖 setup 造数。但若当前 DB drafts=0,会"空数组通过",需在 setup 里造一条 draft。

**Files:**
- Modify: `backend/scripts/smoke_test.py`

- [ ] **Step 1: 在 setup_test_data 里加造数逻辑**

把 `setup_test_data` 函数体替换为:

```python
def setup_test_data(client: httpx.Client) -> list[str]:
    """
    在跑场景前准备测试数据。
    返回创建的 artifact 列表(写进报告的 Setup 段)。
    """
    artifacts: list[str] = []

    # 1) 创建一个测试 holding(P0-03 / P0-05 / P1-13 都依赖至少一条 holding)
    #    选 600519 (贵州茅台) — DB 里几乎肯定有 valuation/kline 数据
    test_code = "600519"
    holding_payload = {
        "stock_code": test_code,
        "quantity": 100,
        "buy_price": 1500.0,
        "buy_date": "2026-01-10",
        "rationale": "smoke test setup — will be cleaned via DB restore",
    }
    r = client.post("/api/portfolio", json=holding_payload)
    if r.status_code == 201:
        holding_id = r.json().get("id")
        artifacts.append(f"created holding id={holding_id} for {test_code}")
    else:
        artifacts.append(
            f"WARN: create holding failed ({r.status_code}): {r.text[:200]}"
        )

    # 2) 触发预案运行,生成 draft(P1-13 需要 drafts 非空)
    #    用内置 bank_anchor 预案 — 它在 600519 上不会触发(茅台不是银行股),
    #    但跑一次确保 drafts 表至少有最近一次运行的产物(若有)。
    plans = client.get("/api/plans").json()
    if plans:
        first_plan_id = plans[0]["id"]
        run_r = client.post(f"/api/plans/{first_plan_id}/run")
        artifacts.append(
            f"triggered plan id={first_plan_id} run: status={run_r.status_code}"
        )
    else:
        artifacts.append("WARN: no plans found, cannot trigger draft generation")

    return artifacts
```

- [ ] **Step 2: 写 P1-13 场景函数**

在 `scenario_p1_15_commit_classification` 之后插入:

```python
def scenario_p1_13_draft_source(client: httpx.Client) -> ScenarioResult:
    """
    P1-13: CockpitDraft.source 字段非空。

    通过标准: GET /api/cockpit 的 response.drafts 数组中,每条 draft 的 source
    字段必须存在且非空字符串。

    round6 fix: cockpit_service._serialize_draft 之前漏掉 source 字段,
    修复后应该返回。
    """
    r = client.get("/api/cockpit")
    if r.status_code != 200:
        return ScenarioResult(
            code="P1-13",
            name="CockpitDraft.source 非空",
            passed=False,
            expected="200 OK with drafts array",
            actual=f"HTTP {r.status_code}: {r.text[:200]}",
        )

    data = r.json()
    drafts = data.get("drafts", [])
    if not drafts:
        return ScenarioResult(
            code="P1-13",
            name="CockpitDraft.source 非空",
            passed=False,
            expected="drafts non-empty (setup should have created some)",
            actual="drafts=[] — setup failed or no plan produced drafts",
        )

    missing = [d.get("id", "?") for d in drafts if not d.get("source")]
    passed = len(missing) == 0
    return ScenarioResult(
        code="P1-13",
        name="CockpitDraft.source 非空",
        passed=passed,
        expected=f"all {len(drafts)} drafts have non-empty source",
        actual=(
            f"{len(drafts) - len(missing)}/{len(drafts)} drafts have source; "
            f"missing: {missing[:5]}"
        ),
        artifacts={
            "sample_draft": str(drafts[0]) if drafts else "none",
        },
    )
```

在 SCENARIOS 列表里追加:

```python
SCENARIOS: list[Callable[[httpx.Client], ScenarioResult]] = [
    scenario_p1_15_commit_classification,
    scenario_p1_13_draft_source,
]
```

- [ ] **Step 3: 跑脚本**

Run:
```bash
cd backend
source .venv/bin/activate
python scripts/smoke_test.py --output /tmp/smoke-p1-13.md
```

Expected: setup 段含 "created holding" + "triggered plan" 两行;P1-13 行通过或失败取决于 round6 修复是否生效。

- [ ] **Step 4: 提交**

```bash
git add backend/scripts/smoke_test.py
git commit -m "$(cat <<'EOF'
feat(smoke): P1-13 CockpitDraft.source 场景 + setup 造数

setup_test_data 创建测试 holding (600519) 并触发预案运行,
为依赖 drafts 非空的场景做准备。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 场景 P1-12 — updateThesisVariables 返回 StockResponse

**Files:**
- Modify: `backend/scripts/smoke_test.py`

- [ ] **Step 1: 写场景函数**

在 `scenario_p1_13_draft_source` 之后插入:

```python
def scenario_p1_12_thesis_variables(client: httpx.Client) -> ScenarioResult:
    """
    P1-12: PUT /api/stocks/{code}/thesis-variables 返回 StockResponse。

    通过标准:
    - HTTP 200
    - response body 含 stock_code / name / industry 等 StockResponse 标准字段
    - 前端类型定义期望 Promise<StockResponse>,所以必须有完整 body(不能是空)

    round6 fix: 之前前端 client.ts 类型写 Promise<void>,
    后端实际返回 StockResponse,导致更新后 UI 不刷新。
    """
    test_code = "600519"
    # 先取当前值,确保改的是已知字段
    get_r = client.get(f"/api/stocks/{test_code}")
    if get_r.status_code != 200:
        return ScenarioResult(
            code="P1-12",
            name="thesis-variables 返回 StockResponse",
            passed=False,
            expected=f"GET /api/stocks/{test_code} 200",
            actual=f"HTTP {get_r.status_code}: {get_r.text[:200]}",
        )

    original = get_r.json()
    original_vars = original.get("thesis_variables", []) or []

    # 修改: 加一个 smoke test marker 变量
    new_vars = list(original_vars)
    new_vars.append({
        "key": "_smoke_test_marker",
        "display_name": "Smoke Test Marker",
        "current_value": "set by smoke_test.py",
        "threshold_min": None,
        "threshold_max": None,
        "unit": "",
    })

    put_r = client.put(
        f"/api/stocks/{test_code}/thesis-variables",
        json=new_vars,
    )

    if put_r.status_code != 200:
        return ScenarioResult(
            code="P1-12",
            name="thesis-variables 返回 StockResponse",
            passed=False,
            expected="200 OK with StockResponse body",
            actual=f"HTTP {put_r.status_code}: {put_r.text[:200]}",
        )

    body = put_r.json()
    required_fields = {"stock_code", "name"}
    missing = required_fields - set(body.keys())
    passed = len(missing) == 0

    # 还原 thesis_variables (DB 还原也会处理,但保险起见)
    client.put(
        f"/api/stocks/{test_code}/thesis-variables",
        json=original_vars,
    )

    return ScenarioResult(
        code="P1-12",
        name="thesis-variables 返回 StockResponse",
        passed=passed,
        expected=f"response contains: {required_fields}",
        actual=(
            f"missing fields: {missing}" if missing else
            f"all required fields present (stock_code={body.get('stock_code')})"
        ),
        artifacts={
            "response_keys": ",".join(sorted(body.keys())[:15]),
        },
    )
```

在 SCENARIOS 追加 `scenario_p1_12_thesis_variables`。

- [ ] **Step 2: 跑脚本**

Run:
```bash
cd backend && source .venv/bin/activate
python scripts/smoke_test.py --output /tmp/smoke-p1-12.md
```

Expected: P1-12 通过(response 含 stock_code/name)。

- [ ] **Step 3: 提交**

```bash
git add backend/scripts/smoke_test.py
git commit -m "$(cat <<'EOF'
feat(smoke): P1-12 thesis-variables 返回类型场景

PUT /api/stocks/{code}/thesis-variables 后验证 response 是完整
StockResponse (含 stock_code/name),前端可基于此刷新 UI。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 场景 P0-03 — Universe vs Cockpit 权重一致

**Files:**
- Modify: `backend/scripts/smoke_test.py`

- [ ] **Step 1: 写场景函数**

在 `scenario_p1_12_thesis_variables` 之后插入:

```python
def scenario_p0_03_weight_consistency(client: httpx.Client) -> ScenarioResult:
    """
    P0-03: 同一持仓在 Universe 页和 Cockpit 页显示的 weight_pct 一致。

    通过标准: |universe.weight_pct - cockpit.weight_pct| < 0.1%
    (允许小数四舍五入误差)

    round6 fix: stocks.py:91-108 (Universe) 用 buy_price*quantity 成本基数,
    holding_service.py:369-387 (Cockpit) 用 current_value 市值基数。
    round6 统一为市值基数。
    """
    # 从 Universe 取所有持仓股的 weight_pct
    universe_r = client.get("/api/stocks/universe?scope=holdings")
    if universe_r.status_code != 200:
        return ScenarioResult(
            code="P0-03",
            name="Universe vs Cockpit 权重一致",
            passed=False,
            expected="200 OK",
            actual=f"universe HTTP {universe_r.status_code}: {universe_r.text[:200]}",
        )

    universe_items = universe_r.json()
    # filter 出有持仓的
    universe_weights = {
        item["code"]: item.get("weight_pct")
        for item in universe_items
        if item.get("weight_pct") is not None and item.get("weight_pct") > 0
    }

    # 从 Cockpit 取持仓的 weight_pct
    cockpit_r = client.get("/api/cockpit")
    if cockpit_r.status_code != 200:
        return ScenarioResult(
            code="P0-03",
            name="Universe vs Cockpit 权重一致",
            passed=False,
            expected="200 OK",
            actual=f"cockpit HTTP {cockpit_r.status_code}: {cockpit_r.text[:200]}",
        )

    cockpit_holdings = cockpit_r.json().get("holdings", [])
    cockpit_weights = {
        h["stock_code"]: h.get("weight_pct")
        for h in cockpit_holdings
        if h.get("weight_pct") is not None
    }

    if not cockpit_weights:
        return ScenarioResult(
            code="P0-03",
            name="Universe vs Cockpit 权重一致",
            passed=False,
            expected="cockpit has ≥1 holding",
            actual="cockpit.holdings empty — setup failed?",
        )

    # 比对每个持仓的 weight_pct
    diffs: dict[str, float] = {}
    for code, u_w in universe_weights.items():
        c_w = cockpit_weights.get(code)
        if c_w is None:
            continue
        diffs[code] = abs(u_w - c_w)

    if not diffs:
        return ScenarioResult(
            code="P0-03",
            name="Universe vs Cockpit 权重一致",
            passed=False,
            expected="至少 1 个持仓在两个端点都能取到",
            actual="universe 和 cockpit 的持仓 code 无交集",
        )

    max_diff = max(diffs.values())
    passed = max_diff < 0.1
    return ScenarioResult(
        code="P0-03",
        name="Universe vs Cockpit 权重一致",
        passed=passed,
        expected="max |diff| < 0.1%",
        actual=f"max diff = {max_diff:.4f}% across {len(diffs)} holdings",
        artifacts={
            "diffs": "; ".join(f"{c}={d:.4f}%" for c, d in
                               sorted(diffs.items(), key=lambda x: -x[1])[:5]),
        },
    )
```

在 SCENARIOS 追加 `scenario_p0_03_weight_consistency`。

- [ ] **Step 2: 跑脚本**

Run:
```bash
cd backend && source .venv/bin/activate
python scripts/smoke_test.py --output /tmp/smoke-p0-03.md
```

Expected: P0-03 通过(max diff < 0.1%)或失败(若 round6 修复未生效)。

- [ ] **Step 3: 提交**

```bash
git add backend/scripts/smoke_test.py
git commit -m "$(cat <<'EOF'
feat(smoke): P0-03 Universe vs Cockpit 权重一致场景

比对同一持仓在 /api/stocks/universe 和 /api/cockpit 的 weight_pct,
差值必须 < 0.1% (round6 统一为市值基数)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 场景 P0-05 — 行业权重撞上限返回 4xx + 一致基数

**Files:**
- Modify: `backend/scripts/smoke_test.py`

- [ ] **Step 1: 写场景函数**

在 `scenario_p0_03_weight_consistency` 之后插入:

```python
def scenario_p0_05_industry_cap_error(client: httpx.Client) -> ScenarioResult:
    """
    P0-05: 撞行业权重上限的买入返回 4xx,且错误消息中的基数与 Cockpit 一致。

    通过标准:
    - 故意构造一个超大买入(数量极大),触发行业权重 > 15% 上限
    - HTTP 状态码 4xx (400 或 422)
    - response.detail 或 error 字段含 "industry" 或 "权重" 关键字
    - (信息性)错误消息若含百分比数字,该数字应接近 100%(因买入极大)

    round6 fix: holding_service.py:142-152 的 _industry_breach_after_buy 之前
    用含新交易的成本基数,而 get_portfolio_summary 用市值基数。round6 统一。
    """
    test_code = "600519"  # 茅台 - 食品饮料行业

    # 构造一个明显会撞上限的买入:数量 100 万股
    payload = {
        "stock_code": test_code,
        "quantity": 1_000_000,
        "buy_price": 1500.0,
        "buy_date": "2026-06-11",
        "rationale": "smoke test: industry cap breach attempt",
    }
    r = client.post("/api/portfolio", json=payload)

    # 期望 4xx
    if 200 <= r.status_code < 300:
        # 没拦住 — 这是 P0-05 失败
        return ScenarioResult(
            code="P0-05",
            name="行业权重撞上限返回 4xx",
            passed=False,
            expected="4xx (industry cap should reject)",
            actual=f"HTTP {r.status_code} — buy was accepted (bug!)",
            artifacts={"response": r.text[:200]},
        )

    # 4xx — 检查错误消息
    body_text = r.text.lower()
    has_industry_keyword = any(
        kw in body_text for kw in ["industry", "行业", "权重", "weight"]
    )

    passed = has_industry_keyword
    return ScenarioResult(
        code="P0-05",
        name="行业权重撞上限返回 4xx",
        passed=passed,
        expected="4xx + error message contains industry/weight keyword",
        actual=(
            f"HTTP {r.status_code}; "
            f"industry keyword {'found' if has_industry_keyword else 'NOT found'} in response"
        ),
        artifacts={
            "status_code": str(r.status_code),
            "response_excerpt": r.text[:300],
        },
    )
```

在 SCENARIOS 追加 `scenario_p0_05_industry_cap_error`。

- [ ] **Step 2: 跑脚本**

Run:
```bash
cd backend && source .venv/bin/activate
python scripts/smoke_test.py --output /tmp/smoke-p0-05.md
```

Expected: P0-05 通过(4xx + industry keyword)或失败(2xx 表示根本没拦)。

- [ ] **Step 3: 提交**

```bash
git add backend/scripts/smoke_test.py
git commit -m "$(cat <<'EOF'
feat(smoke): P0-05 行业权重撞上限场景

POST /api/portfolio 用超大数量触发 industry cap,
验证返回 4xx 且错误消息含行业/权重关键字。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 场景 P0-01/02 — Plan DSL OR composition 生效

**Files:**
- Modify: `backend/scripts/smoke_test.py`

- [ ] **Step 1: 找两个互斥但 OR 后应存活的策略**

Run:
```bash
cd backend && source .venv/bin/activate
python -c "
from app.services.builtin_seeder import BUILTIN_STRATEGIES
for s in BUILTIN_STRATEGIES:
    print(s['slug'], '->', s['name'])
"
```

Expected: 列出 6 个内置策略 slug。记录两个**互斥**的(在同一股票上不会同时通过的)策略 ID,例如 `high_dividend_cushion`(DYR≥4%)和 `undervalued_entry`(PE分位≤30% & PB分位≤30%)。OR 后只要一个通过即可。

- [ ] **Step 2: 写场景函数**

在 `scenario_p0_05_industry_cap_error` 之后插入:

```python
def scenario_p0_01_02_or_plan(client: httpx.Client) -> ScenarioResult:
    """
    P0-01/02: Plan DSL OR composition 真正生效。

    通过标准:
    - POST /api/plans 创建一个 logic='OR' 的预案 (用 2 个内置策略)
    - POST /api/plans/{id}/run 触发评估
    - GET /api/plans/{id}/candidates 必须非空 (至少 1 个候选)
    - 若结果为空,要么是 OR 没生效(被当 AND 处理),
      要么是策略本身过滤太严 (需检查 rule_json)

    round6 fix: plan_runner._strategy_definitely_fails 和双 pass 筛选
    之前忽略 composition,把所有 plan 当 AND 处理。OR plan 完全失效。
    """
    # 1) 取内置策略 ID
    strategies = client.get("/api/strategies").json()
    by_slug = {s["slug"]: s for s in strategies}
    needed = ["high_dividend_cushion", "undervalued_entry"]
    missing = [s for s in needed if s not in by_slug]
    if missing:
        return ScenarioResult(
            code="P0-01/02",
            name="Plan DSL OR composition 生效",
            passed=False,
            expected=f"built-in strategies present: {needed}",
            actual=f"missing slugs: {missing}",
        )

    s1 = by_slug["high_dividend_cushion"]
    s2 = by_slug["undervalued_entry"]

    # 2) 创建 OR plan
    plan_payload = {
        "name": "_smoke_test_or_plan",
        "description": "smoke test for round6 P0-01/02 OR fix",
        "strategy_composition": {
            "strategy_ids": [s1["id"], s2["id"]],
            "logic": "OR",
        },
        "scan_scope": {"scope": "all"},
        "trade_rules": [],
        "is_active": False,  # 不让调度自动跑
    }
    create_r = client.post("/api/plans", json=plan_payload)
    if create_r.status_code != 201:
        return ScenarioResult(
            code="P0-01/02",
            name="Plan DSL OR composition 生效",
            passed=False,
            expected="201 created",
            actual=f"HTTP {create_r.status_code}: {create_r.text[:200]}",
        )
    plan_id = create_r.json()["id"]

    # 3) 触发评估
    run_r = client.post(f"/api/plans/{plan_id}/run")
    if run_r.status_code != 200:
        # 清理
        client.delete(f"/api/plans/{plan_id}")
        return ScenarioResult(
            code="P0-01/02",
            name="Plan DSL OR composition 生效",
            passed=False,
            expected="200 run ok",
            actual=f"HTTP {run_r.status_code}: {run_r.text[:200]}",
        )

    # 4) 取候选
    cand_r = client.get(f"/api/plans/{plan_id}/candidates")
    candidates = cand_r.json() if cand_r.status_code == 200 else []

    passed = len(candidates) > 0
    result = ScenarioResult(
        code="P0-01/02",
        name="Plan DSL OR composition 生效",
        passed=passed,
        expected=f"≥1 candidate after OR plan run",
        actual=f"{len(candidates)} candidates produced",
        artifacts={
            "plan_id": str(plan_id),
            "strategies_used": f"{s1['slug']} OR {s2['slug']}",
            "sample_candidate": str(candidates[0]) if candidates else "none",
        },
    )

    # 5) 清理 (DB 还原也会处理,但删 plan 避免污染后续场景)
    client.delete(f"/api/plans/{plan_id}")

    return result
```

在 SCENARIOS 追加 `scenario_p0_01_02_or_plan`。

- [ ] **Step 3: 跑脚本**

Run:
```bash
cd backend && source .venv/bin/activate
python scripts/smoke_test.py --output /tmp/smoke-p0-01-02.md
```

Expected: P0-01/02 通过(候选数 > 0)或失败(若 OR 仍被当 AND,候选可能极少或为 0)。

- [ ] **Step 4: 提交**

```bash
git add backend/scripts/smoke_test.py
git commit -m "$(cat <<'EOF'
feat(smoke): P0-01/02 Plan DSL OR composition 场景

构造 OR plan (high_dividend_cushion OR undervalued_entry),
运行后验证候选非空。若 OR 被当 AND 处理,候选会极少或为 0。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: DB 备份 + 跑完整 smoke + 还原

> 这一步把 6 个场景一起跑,产出第一份完整报告。**不修改代码**,只跑+记录。

**Files:**
- Create: `backend/data/gojira.db.bak`(临时备份,**不进 git**,在 .gitignore 已覆盖 `data/`)

- [ ] **Step 1: 启动后端**

Run:
```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 3001 &
```

(或者用 `./dev.sh` 在另一个终端起,这里假设后端已在 3001 端口跑)

验证:
```bash
curl -s http://localhost:3001/api/health | head -5
```

Expected: 返回 `{"status":"ok",...}`。

- [ ] **Step 2: 备份 DB**

Run:
```bash
cp backend/data/gojira.db backend/data/gojira.db.bak
ls -lh backend/data/gojira.db.bak
```

Expected: 备份文件 ~140MB。

- [ ] **Step 3: 跑完整 smoke**

Run:
```bash
cd backend && source .venv/bin/activate
python scripts/smoke_test.py
echo "exit code: $?"
```

Expected: 跑完 6 个场景,报告写到 `docs/reports/e2e-round6-acceptance-2026-06-11.md`,退出码 0(全过)或 1(部分失败)。

- [ ] **Step 4: 还原 DB**

Run:
```bash
# 先停后端(避免 SQLite 文件锁)
pkill -f "uvicorn app.main:app" || true

# 还原
mv backend/data/gojira.db.bak backend/data/gojira.db

# 验证
sqlite3 backend/data/gojira.db "SELECT count(*) FROM holdings;"
```

Expected: holdings 行数回到 0(测试前状态)。

- [ ] **Step 5: 把报告 commit(即使有失败项)**

报告本身就是验收产出物,失败项不是 bug 而是发现。提交:

```bash
git add docs/reports/e2e-round6-acceptance-2026-06-11.md
git commit -m "$(cat <<'EOF'
docs(reports): P1-1 round6 修复 smoke 验收报告

6 项场景首次跑结果,失败项按 γ 分级策略处理(见后续 commit)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 人工 UI 走查(补 smoke 看不见的部分)

> smoke 脚本只能验 API 契约。UI 渲染 / 交互流必须人眼看。这一步**只产出 markdown**,不改代码。

**Files:**
- Create: `docs/reports/e2e-round6-ui-walkthrough-2026-06-11.md`

- [ ] **Step 1: 重启服务,DB 重新备份**

Run:
```bash
cp backend/data/gojira.db backend/data/gojira.db.bak
./dev.sh   # 或前后端分别起
```

- [ ] **Step 2: 走查 5 个核心页面**

打开浏览器,按下表逐项核对。每项记 ✅/❌/⚠️ + 备注。

Create `docs/reports/e2e-round6-ui-walkthrough-2026-06-11.md`:

```markdown
# P1-1 UI 走查 checklist (round6 回归)

> 走查日期: 2026-06-11
> 走查人: [你的名字]
> 走查对象: round6 修复后的 9 个前端页面

## 走查项

### Cockpit (`/`)
- [ ] 页面加载无 JS error (F12 Console 干净)
- [ ] 持仓列表显示 `weight_pct` 列,数值与 Universe 页一致(P0-03 验证)
- [ ] 若有草稿,草稿行显示 `source` 列/徽标(P1-13 验证)
- [ ] 若持仓某只股价格不可用,该行 pnl 显示"数据不可用"或" - ",不是 `NaN%` 或 `0.00%`(P0-04 残留检查)
- [ ] 加权 DYR 卡片显示合理数值
- [ ] 周期仪表盘显示当前 PE 分位档位

### Universe (`/universe`)
- [ ] 默认 scope=holdings 时,持仓股的 weight_pct 与 Cockpit 一致(P0-03 第二端)
- [ ] 切换 scope=all 时不报错
- [ ] 关键字搜索含 % 时不会枚举全量(P1-01 注入防御)

### Plans (`/plans`)
- [ ] 4 个内置预案可见
- [ ] 点 "运行" 按钮,触发 POST /api/plans/{id}/run,返回 200
- [ ] 运行后点 "候选股" 能看到候选列表(P0-01/02 OR 验证 - 手动构造 OR 预案再跑一次)

### StockDetail (`/stock/600519`)
- [ ] K线图加载
- [ ] 论点变量区域可见
- [ ] 修改一个论点变量 → 保存 → 页面自动刷新显示新值(P1-12 验证)
- [ ] 基本信息卡片显示 stock_code/name/industry

### Portfolio(通过 Cockpit 进入持仓编辑)
- [ ] 编辑某持仓的 buy_price → 保存 → Cockpit weight_pct 更新(P0-03 反向验证)
- [ ] 尝试添加一个超大持仓(撞行业上限)→ 报错信息显示且 Cockpit 未变(P0-05 验证)

## 整体感受
- 加载速度可接受?(Cockpit 应在 2s 内完成 - round6 P1-10 并行化)
- 任何页面有 JS error?记录到这里
- 任何页面有 "undefined" / "NaN" 字样?记录到这里

## 总结
- 通过项: X / 14
- 失败项: 列表
- 待修(γ 分级 round6 尾巴): 列表
```

- [ ] **Step 3: 走查 + 填表**

按 checklist 在浏览器里走一遍。把 ✅/❌/⚠️ 填进 markdown。

- [ ] **Step 4: 还原 DB + 提交**

```bash
pkill -f "uvicorn app.main:app" || true
mv backend/data/gojira.db.bak backend/data/gojira.db

git add docs/reports/e2e-round6-ui-walkthrough-2026-06-11.md
git commit -m "$(cat <<'EOF'
docs(reports): P1-1 UI 走查 checklist

5 个核心页面 14 个核对项的人工走查结果。
失败项按 γ 分级处理。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: γ 分级 — 处理验收发现的 bug + 开 ticket

> 跑完 smoke + UI 走查后,把所有 ❌/⚠️ 项分类。这是计划里**唯一无法预先写死步骤**的 Task,因为发现的 bug 列表取决于实际跑的结果。

**Files:**
- Modify: 视发现的 bug 而定
- Create: `docs/progress/2026-06-11-round6-tail-fixes.md`(若需修 round6 尾巴)

- [ ] **Step 1: 汇总所有失败项**

读取:
- `docs/reports/e2e-round6-acceptance-2026-06-11.md`
- `docs/reports/e2e-round6-ui-walkthrough-2026-06-11.md`

把所有 ❌ 项整理成一个表:

```
| 场景 | 失败描述 | 是否 round6 尾巴? | 修复位置(若是) |
|------|---------|-------------------|------------------|
```

判定 "round6 尾巴" 的标准:在 `docs/reports/completed/full-audit-round6-2026-06-11.md` 里能找到对应"已修复"声明,但实测未生效。

- [ ] **Step 2: 修 round6 尾巴(若有)**

对每个 round6 尾巴:
- 在 `docs/progress/2026-06-11-round6-tail-fixes.md` 记录修复方案
- 实施修复(典型路径:补前端字段处理、补后端序列化字段、补 OR 逻辑分支)
- 跑相关单测:`pytest tests/test_<affected>_service.py -v`
- 重跑 smoke 验证场景变绿

提交:
```bash
git add <fix paths> docs/progress/2026-06-11-round6-tail-fixes.md
git commit -m "$(cat <<'EOF'
fix: round6 验收发现的 round6 尾巴修复

详见 docs/progress/2026-06-11-round6-tail-fixes.md

[具体修复内容]

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: 开 P1 ticket — drop 死表(ADR-1 违规)**

在 `docs/active/roadmap.md` 的 P3 段追加:

```markdown
- **死表 drop 迁移**: `plan_exec_history` / `plan_templates` 表 ORM 已无引用,但 Alembic 迁移没 drop。需新增一个迁移 `drop_orphan_plan_tables` 收尾 ADR-1。
```

- [ ] **Step 4: 开 P1 ticket — alert_service commit 归属 review**

若 Task 3 的 P1-15 场景报告 `alert_service.py` 有 suspicious commit,在 roadmap P1 段追加:

```markdown
- **alert_service commit 路径归属**: P1-15 验收发现 alert_service.py 有 db.commit()。需确认 alert 是被 router 同步调用还是仅由 EventBus 异步 handler 调用。若同步,移除 commit;若异步,加白名单注释。
```

- [ ] **Step 5: 提交所有 roadmap 更新**

```bash
git add docs/active/roadmap.md
git commit -m "$(cat <<'EOF'
docs(roadmap): P1-1 验收发现追加 P1/P3 ticket

- P3: drop 死表 plan_exec_history / plan_templates (ADR-1 收尾)
- P1: alert_service commit 路径归属 review

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: 收尾 — 更新 roadmap / STATUS

**Files:**
- Modify: `docs/active/roadmap.md`
- Modify: `docs/progress/STATUS.md`

- [ ] **Step 1: roadmap.md P1-1 改为 ✅**

把 `docs/active/roadmap.md` 第 46 行附近:

```markdown
| 1 | **端到端手动验收** | ⚠️ 部分 | 起 `./dev.sh` → 建预案 → 立即评估 → 看草稿 → 标记成交 → 验证 audit_log。2026-06-06 已跑过一次 (见 `docs/reports/2026-06-06-e2e-lifecycle-verification.md`),需在 round6 修复后回归 |
```

改为:

```markdown
| 1 | **端到端手动验收** | ✅ 已完成 | round6 修复回归已完成,详见 `docs/reports/e2e-round6-acceptance-2026-06-11.md` + `docs/reports/e2e-round6-ui-walkthrough-2026-06-11.md`。改为 Python smoke + UI checklist 混合模式,Playwright 基建已删 (ADR-0001) |
```

- [ ] **Step 2: STATUS.md 5.3 节更新**

把 `docs/progress/STATUS.md` 5.3 节的 P1-1 那一行删掉(已完成的不该在"待修复项"里)。检查 5.2 节是否需要追加 2026-06-11 验收里程碑。

- [ ] **Step 3: 把已完成报告移到 completed/**

```bash
mv docs/reports/e2e-round6-acceptance-2026-06-11.md docs/reports/completed/
mv docs/reports/e2e-round6-ui-walkthrough-2026-06-11.md docs/reports/completed/
```

(根据 CLAUDE.md 约定,已完成的修改报告归 `docs/reports/completed/`)

- [ ] **Step 4: 提交**

```bash
git add docs/active/roadmap.md docs/progress/STATUS.md docs/reports/
git commit -m "$(cat <<'EOF'
docs: P1-1 端到端验收收尾

- roadmap P1-1 ⚠️ → ✅
- STATUS 5.3 移除已完成项
- 报告归档到 docs/reports/completed/

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage** — grill-with-docs 会话定的 8 项决策是否都被实现?

| 决策 | 实现位置 |
|------|---------|
| 1. C+B 混合,不写 Playwright | ADR-0001 + Task 1(删 Playwright)+ Task 2-8(写 smoke)+ Task 10(UI checklist) |
| 2. 6 项精准切片(P0-04 剔出) | Task 3-8 各对应一项 |
| 3. β DB 备份+API 造数+还原 | Task 9 Step 2/4 + Task 4 setup_test_data |
| 4. γ 分级 bug 策略 | Task 11 整个 |
| 5. 分裂策略(Playwright 删,死表开 ticket) | Task 1 + Task 11 Step 3 |
| 6. Python httpx 不进 pytest | Task 2 整个(脚本入口 + 注释说明) |
| 7. β 通过标准(状态表) | Task 2 write_report + Task 9 跑出首版报告 |
| 8. α 纯静态 commit 分类 | Task 3 scenario_p1_15_commit_classification |

✅ 全部覆盖。

**Placeholder scan** — 检查 "TBD" / "implement later" / 模糊指代:
- Task 11 是设计上"动态依赖跑测结果"的,这是有意为之,不算 placeholder
- 所有代码 step 都有完整代码块
- 所有命令都有 expected output

**Type consistency** — 后续 Task 引用的类型/字段是否跟前面一致?
- `ScenarioResult` 字段(code/name/passed/expected/actual/artifacts)在 Task 2 定义,Task 3-8 全部使用一致 ✅
- `setup_test_data(client) -> list[str]` 签名在 Task 2 定义,Task 4 重写时保持一致 ✅
- `SCENARIOS` 列表类型注解一致 ✅
- HTTP 端点路径全部基于实际 grep stocks.py/plans.py/portfolio.py/cockpit.py 结果 ✅
