"""CLI tool to trigger deep_research manually.

Usage:
    .venv/bin/python -m app.cli.research 600519
    .venv/bin/python -m app.cli.research 600519 --force --model opus
    .venv/bin/python -m app.cli.research 600519 --no-web-search
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path so we can run from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Gojira v2 deep_research CLI")
    parser.add_argument("stock_code", help="A-share stock code (e.g. 600519)")
    parser.add_argument("--force", action="store_true", help="bypass 30-day cache")
    parser.add_argument(
        "--model",
        choices=["sonnet", "opus", "haiku"],
        default="sonnet",
        help="GLM tier (sonnet=5.1 default, opus=5.2 top, haiku=4.8 cheap)",
    )
    parser.add_argument(
        "--no-web-search",
        action="store_true",
        help="disable web_search (degraded mode, only uses Lixinger data)",
    )
    parser.add_argument("--json", action="store_true", help="output raw JSON")
    args = parser.parse_args()

    # Late imports (after sys.path tweak)
    from app.services.llm.client import GLMTier, get_llm_client
    from app.services.pipelines.llm import deep_research_pipeline

    tier_map = {
        "sonnet": GLMTier.SONNET,
        "opus": GLMTier.OPUS,
        "haiku": GLMTier.HAIKU,
    }
    tier = tier_map[args.model]

    print(f"Running deep_research for {args.stock_code} (model={tier.value}, force={args.force}, web_search={not args.no_web_search})", file=sys.stderr)

    try:
        result = deep_research_pipeline.run(
            args.stock_code,
            model_tier=tier,
            use_web_search=not args.no_web_search,
        )
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "stock_code": result.stock_code,
            "overall_score": result.overall_score,
            "recommendation": result.recommendation,
            "evidence_grade": result.evidence_grade,
            "rejected": result.rejected,
            "rejection_reason": result.rejection_reason,
            "report_id": result.report_id,
            "data_conflicts": result.data_conflicts,
            "red_line_hits": result.red_line_hits,
            "markdown_report": result.markdown_report,
        }, ensure_ascii=False, indent=2))
    else:
        print()
        print("=" * 60)
        print(f"  {args.stock_code} — overall={result.overall_score} / rec={result.recommendation}")
        print(f"  evidence_grade={result.evidence_grade}  rejected={result.rejected}")
        print(f"  conflicts={len(result.data_conflicts)}  red_lines={len(result.red_line_hits)}")
        print(f"  report_id={result.report_id}")
        print("=" * 60)
        print()
        print(result.markdown_report or "(no markdown report)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
