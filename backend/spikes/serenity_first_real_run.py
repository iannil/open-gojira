"""Spike: 跑首次真实 serenity 研究 (theme=银行).

目标:
1. 验证 pipeline 端到端工作 (Lixinger context → GLM 推理 → 6 张子表持久化)
2. 拿到真实 failure_conditions_md 样本,为 Phase 2 #9 schema 设计提供校准数据
3. 实测 reasoning model 对 max_tokens/timeout/成本的真实影响
4. 顺便解 Phase 1 spec ship 标准 #9 (真实研究 ≥ 3 次) 的第 1 次

注意:
- 这是真实 LLM 调用,会消耗 token (估算 ¥1-5)
- 跑完一次预计 5-15 分钟 (reasoning model 速度限制)
- 失败时记录 error_message,不抛异常 (避免污染 DB)

用法:
    cd backend && source .venv/bin/activate
    python spikes/serenity_first_real_run.py

输出:
    backend/spikes/output/serenity_first_real_run_{date}.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models.research_theme import ResearchTheme  # noqa: E402
from app.services.research_runner_service import trigger_run  # noqa: E402


THEME_NAME = "银行"
POLL_INTERVAL_SEC = 20
MAX_WAIT_SEC = 1800  # 30 minutes — reasoning model + persistence buffer


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"serenity_first_real_run_{date_str}.json"

    db_path = Path(__file__).parent.parent / "data" / "gojira.db"
    engine = create_engine(f"sqlite:///{db_path}")

    print(f"[spike] Serenity first real run — theme={THEME_NAME!r} — {date_str}")

    # Capture as plain values BEFORE session close (avoid DetachedInstanceError)
    theme_id: int
    run_id: int
    t0: float

    with Session(engine) as db:
        # 1) Create theme if not exists
        existing = db.query(ResearchTheme).filter(ResearchTheme.name == THEME_NAME).first()
        if existing:
            theme_id = existing.id
            print(f"[spike] reuse existing theme id={theme_id} status={existing.status}")
            if existing.status != "active":
                existing.status = "active"
                db.commit()
        else:
            theme = ResearchTheme(
                name=THEME_NAME,
                description="银行业稀缺层研究 (首次真实 Run,Phase 1 ship #9)",
                market="A_SHARE",
                status="active",
                auto_refresh_freq="manual",
            )
            db.add(theme)
            db.commit()
            db.refresh(theme)
            theme_id = theme.id
            print(f"[spike] created theme id={theme_id}")

        # 2) Trigger run
        print(f"\n[spike] triggering run for theme_id={theme_id}...")
        t0 = time.monotonic()
        try:
            run = trigger_run(db, theme_id, triggered_by="spike")
            run_id = run.id
            db.commit()
            print(f"[spike] run_id={run_id} status=running (committed)")
        except Exception as e:
            db.rollback()
            print(f"[FAIL] trigger_run: {type(e).__name__}: {e}")
            output_path.write_text(json.dumps({
                "ok": False,
                "stage": "trigger_run",
                "error": f"{type(e).__name__}: {e}",
                "timestamp": date_str,
            }, ensure_ascii=False, indent=2))
            return 1

    # 3) Poll status — use fresh session each poll
    print(f"\n[spike] polling every {POLL_INTERVAL_SEC}s (max {MAX_WAIT_SEC}s)...")
    final_status: str = "unknown"
    while True:
        elapsed = int(time.monotonic() - t0)
        with Session(engine) as db:
            from app.models.research_run import ResearchRun
            r = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
            if r is None:
                print(f"[FAIL] run {run_id} vanished")
                final_status = "missing"
                break
            final_status = r.status
            print(f"  [{elapsed:>4}s] status={r.status} attempt={r.attempt_count} "
                  f"tokens_in={r.llm_token_input or 0} tokens_out={r.llm_token_output or 0} "
                  f"searches={r.llm_search_count or 0}")
            if r.status in ("completed", "failed"):
                break

        if elapsed >= MAX_WAIT_SEC:
            print(f"[TIMEOUT] still {final_status} after {elapsed}s — giving up")
            break

        time.sleep(POLL_INTERVAL_SEC)

    elapsed = int(time.monotonic() - t0)

    # 4) Re-read final state with fresh session
    artifact = {
        "ok": final_status == "completed",
        "timestamp": date_str,
        "theme_name": THEME_NAME,
        "theme_id": theme_id,
        "run_id": run_id,
        "final_status": final_status,
        "elapsed_sec": elapsed,
    }

    with Session(engine) as db:
        from app.models.research_run import ResearchRun
        from sqlalchemy import text
        r = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        if r is not None:
            artifact.update({
                "error_message": r.error_message,
                "llm_provider": r.llm_provider,
                "llm_token_input": r.llm_token_input,
                "llm_token_output": r.llm_token_output,
                "llm_search_count": r.llm_search_count,
                "scope_market": r.scope_market,
                "scope_time_window": r.scope_time_window,
                "started_at": str(r.started_at) if r.started_at else None,
                "completed_at": str(r.completed_at) if r.completed_at else None,
                "failure_conditions_md": r.failure_conditions_md,
                "system_change_md": r.system_change_md,
                "next_steps_md": r.next_steps_md,
            })

            fcm = r.failure_conditions_md
            print(f"\n[spike] failure_conditions_md ({len(fcm or '')} chars):")
            if fcm:
                print("  ---")
                for line in (fcm or "").splitlines()[:30]:
                    print(f"  {line}")
                print("  ---")
            else:
                print("  (empty)")

        # 5) Capture related table counts
        counts = {}
        for table_name in [
            "research_company_universe", "research_evidence",
            "research_company_ranking", "value_chain_layers", "scarce_layers",
        ]:
            try:
                cnt = db.execute(text(
                    f"SELECT COUNT(*) FROM {table_name} WHERE research_run_id = :rid"
                ), {"rid": run_id}).scalar()
                counts[table_name] = cnt
            except Exception as e:
                counts[table_name] = f"ERR: {e}"
        artifact["child_table_counts"] = counts
        print(f"\n[spike] child table counts: {counts}")

    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str))
    print(f"\n[spike] artifact → {output_path}")
    return 0 if final_status == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
