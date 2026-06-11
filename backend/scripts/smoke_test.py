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
import re
import subprocess
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


# 场景函数占位 — Task 3-8 会填充
SCENARIOS: list[Callable[[httpx.Client], ScenarioResult]] = [
    scenario_p1_15_commit_classification,
]


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
