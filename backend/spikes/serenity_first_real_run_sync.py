"""Spike: 同步跑 serenity 研究 (Path B 两步法) — 不用 ThreadPoolExecutor。

目标:
1. 验证新 pipeline 端到端工作: query gen → web_search collect → synthesis LLM → persist
2. 验证 search_count > 0 (真实搜索)
3. 抽样 curl evidence URLs 确认非 hallucinated
4. 捕获真实 failure_conditions_md (Phase 2 #9 grill 输入)

用法:
    cd backend && source .venv/bin/activate
    python spikes/serenity_first_real_run_sync.py
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.services.research_context_builder import build_user_context
from app.services.research_persistence_service import persist_research_result
from app.services.search_collector_service import (
    collect_results,
    generate_queries,
    persist_search_results,
)
from app.services.research_runner_service import _extract_candidates_hint
from app.services.llm.zhipu_client import get_zhipu_client


THEME_NAME = "银行"


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"serenity_pathB_run_{date_str}.json"

    db_path = Path(__file__).parent.parent / "data" / "gojira.db"
    engine = create_engine(f"sqlite:///{db_path}")

    print(f"[Path B] theme={THEME_NAME!r} — {date_str}")

    with Session(engine) as db:
        theme = db.query(ResearchTheme).filter(ResearchTheme.name == THEME_NAME).first()
        if not theme:
            print("[FAIL] theme not found")
            return 1
        print(f"[Path B] theme_id={theme.id}")

        # Clean orphaned running rows
        prior = db.query(ResearchRun).filter(
            ResearchRun.research_theme_id == theme.id,
            ResearchRun.status == "running",
        ).all()
        for r in prior:
            r.status = "failed"
            r.error_message = "orphaned (killed by spike restart)"
            r.completed_at = datetime.utcnow()
        if prior:
            db.commit()

        actual_model = settings.ZHIPU_MODEL or "glm-4.7"
        run = ResearchRun(
            research_theme_id=theme.id,
            status="running",
            scope_market=theme.market,
            scope_time_window="3-12M",
            triggered_by="sync_spike_pathB",
            llm_provider=actual_model,
            attempt_count=1,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
        print(f"[Path B] created run_id={run_id}")

        # Step 1: build context
        print("\n[Path B] step 1: build_user_context...")
        user_context = build_user_context(THEME_NAME, theme.market, "3-12M")
        candidates = _extract_candidates_hint(user_context)
        print(f"[ok] context size: {len(user_context)} chars, candidates: {len(candidates)}")

        # Step 2: Path B step 1 — collect real search results
        print("\n[Path B] step 2: generate_queries + collect_results...")
        t0 = time.monotonic()
        queries = generate_queries(THEME_NAME, candidates)
        print(f"[ok] generated {len(queries)} queries in {int(time.monotonic()-t0)}s")
        for i, q in enumerate(queries[:5]):
            print(f"  [{i}] {q}")
        if len(queries) > 5:
            print(f"  ... ({len(queries)-5} more)")

        t1 = time.monotonic()
        collected = collect_results(queries)
        elapsed = int(time.monotonic() - t1)
        print(f"[ok] collected {len(collected)} results in {elapsed}s")

        # Persist search results
        search_inserted = persist_search_results(db, run_id, collected)
        db.flush()
        db.commit()
        print(f"[ok] persisted {search_inserted} unique search_result rows")

        # Step 3: Path B step 2 — LLM synthesis with constrained URLs
        print("\n[Path B] step 3: LLM synthesis (this takes 2-5 min)...")
        t2 = time.monotonic()
        try:
            client = get_zhipu_client()
            search_dicts = [r.model_dump() for r in collected]
            result = client.run_serenity_research(
                user_context=user_context,
                search_results=search_dicts,
            )
            usage = result.pop("_usage", {})
            print(f"[ok] synthesis in {int(time.monotonic()-t2)}s")
            print(f"     tokens in={usage.get('token_input')} out={usage.get('token_output')}")
            print(f"     search_count (passed in) = {usage.get('search_count')}")
        except Exception as e:
            print(f"[FAIL] LLM synthesis: {type(e).__name__}: {e}")
            traceback.print_exc()
            _fail(db, run, theme, f"LLM synthesis: {e}")
            return 3

        # Step 3.5: dump full result
        full_dump = output_dir / f"serenity_pathB_run_{run_id}_full_result.json"
        full_dump.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print(f"[ok] full result → {full_dump}")

        # Step 4: persist structured output
        print("\n[Path B] step 4: persist_research_result...")
        try:
            persist_research_result(db, run, result)
            print("[ok] persist done")
        except Exception as e:
            print(f"[FAIL] persist: {type(e).__name__}: {e}")
            traceback.print_exc()
            db.rollback()
            _fail(db, run, theme, f"persist: {type(e).__name__}: {e}")
            return 4

        # Step 5: finalize
        print("\n[Path B] step 5: finalize run...")
        run.status = "completed"
        run.llm_token_input = usage.get("token_input", 0)
        run.llm_token_output = usage.get("token_output", 0)
        run.llm_search_count = search_inserted  # 真实统计 = 持久化的 URL 数
        run.completed_at = datetime.utcnow()
        theme.last_run_at = run.started_at
        theme.last_run_status = "completed"
        theme.last_run_error = None
        db.commit()
        print(f"[ok] committed, run.status=completed")

    # Step 6: capture artifact
    with Session(engine) as db:
        r = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        artifact = {
            "ok": r.status == "completed",
            "timestamp": date_str,
            "run_id": run_id,
            "theme_id": theme.id,
            "pipeline": "Path B (search → synthesis)",
            "queries_generated": len(queries),
            "search_results_collected": len(collected),
            "search_results_persisted_unique": search_inserted,
            "final_status": r.status,
            "llm_token_input": r.llm_token_input,
            "llm_token_output": r.llm_token_output,
            "llm_search_count": r.llm_search_count,
            "failure_conditions_md": r.failure_conditions_md,
            "system_change_md": (r.system_change_md or "")[:500],
        }

        counts = {}
        for t in ["value_chain_layers", "scarce_layers", "research_company_universe",
                  "research_evidence", "research_company_ranking",
                  "research_search_results"]:
            cnt = db.execute(text(f"SELECT COUNT(*) FROM {t} WHERE research_run_id=:rid"),
                            {"rid": run_id}).scalar()
            counts[t] = cnt
        artifact["child_table_counts"] = counts

        # Sample 5 evidence URLs for curl validation
        evidence_urls = [
            row[0] for row in db.execute(text(
                "SELECT source_url FROM research_evidence WHERE research_run_id=:rid LIMIT 5"
            ), {"rid": run_id})
        ]
        artifact["evidence_url_samples"] = evidence_urls

        # Sample 5 search_result URLs (should be REAL)
        search_urls = [
            row[0] for row in db.execute(text(
                "SELECT url FROM research_search_results WHERE research_run_id=:rid LIMIT 5"
            ), {"rid": run_id})
        ]
        artifact["search_result_url_samples"] = search_urls

    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str))
    print(f"\n[Path B] artifact → {output_path}")

    print(f"\n[Path B] failure_conditions_md ({len(artifact['failure_conditions_md'] or '')} chars):")
    if artifact["failure_conditions_md"]:
        for line in artifact["failure_conditions_md"].splitlines()[:30]:
            print(f"  {line}")

    print(f"\n[Path B] search URL samples (should be REAL):")
    for u in artifact["search_result_url_samples"]:
        print(f"  {u}")

    return 0


def _fail(db: Session, run: ResearchRun, theme: ResearchTheme, err: str) -> None:
    try:
        run.status = "failed"
        run.error_message = err[:2000]
        run.completed_at = datetime.utcnow()
        theme.last_run_status = "failed"
        theme.last_run_error = err[:2000]
        db.commit()
    except Exception as e:
        print(f"[double-fail] {e}")
        db.rollback()


if __name__ == "__main__":
    sys.exit(main())
