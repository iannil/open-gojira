"""Tests for thesis_variable_proposal_service (Phase 2 #9 阶段 B v2)."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models.research_claim import ResearchClaim
from app.models.research_claim_variable import ResearchClaimVariable
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.stock import Stock
from app.services import thesis_variable_proposal_service as svc


# ── Helpers ────────────────────────────────────────────────────────────


def _make_run(db, theme_name: str = "test theme") -> ResearchRun:
    theme = ResearchTheme(name=theme_name, market="A_SHARE")
    db.add(theme)
    db.flush()
    run = ResearchRun(
        research_theme_id=theme.id,
        status="completed",
        scope_market="A_SHARE",
        triggered_by="manual",
        llm_provider="glm-test",
        started_at=__import__("datetime").datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    return run


def _make_claim(
    db, run_id: int, *, signal: str, stock_codes: list[str],
    type_: str = "failure_condition", subject: str = "x", outcome: str = "y",
) -> ResearchClaim:
    c = ResearchClaim(
        research_run_id=run_id,
        type=type_,
        position=0,
        subject=subject,
        predicate="test",
        signal=signal,
        outcome=outcome,
        stock_codes_json=json.dumps(stock_codes),
    )
    db.add(c)
    db.flush()
    return c


def _make_stock(db, code: str) -> Stock:
    s = Stock(code=code, name=f"name-{code}")
    db.add(s)
    db.flush()
    return s


def _mock_response(*, proposals: list[dict], skipped: list[int] | None = None):
    """Build a fake GLM response with submit_claim_variables tool_call."""
    args = {"proposals": proposals}
    if skipped is not None:
        args["skipped_claim_ids"] = skipped
    fn = SimpleNamespace(name="submit_claim_variables", arguments=json.dumps(args))
    msg = SimpleNamespace(
        tool_calls=[SimpleNamespace(function=fn)],
        content=None,
    )
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=200)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


# ── propose_for_run ────────────────────────────────────────────────────


class TestProposeForRun:
    def test_persists_proposals(self, db_session):
        db = db_session
        run = _make_run(db)
        claim = _make_claim(db, run.id, signal="净息差<1.3%", stock_codes=["601398"])
        _make_stock(db, "601398")

        proposals = [{
            "claim_id": claim.id, "stock_code": "601398",
            "variable_name": "净息差", "threshold_critical": 1.3,
            "breach_when": "lt", "source": "financial:NIM", "unit": "%",
            "window_periods": 2,
        }]
        fake_resp = _mock_response(proposals=proposals, skipped=[])

        with patch.object(svc, "get_zhipu_client") as mock_client:
            mock_client.return_value._client.chat.completions.create.return_value = fake_resp
            result = svc.propose_for_run(db, run.id)

        assert result.proposed_count == 1
        rows = db.query(ResearchClaimVariable).all()
        assert len(rows) == 1
        r = rows[0]
        assert r.stock_code == "601398"
        assert r.variable_name == "净息差"
        assert r.threshold_critical == 1.3
        assert r.breach_when == "lt"
        assert r.source == "financial:NIM"
        assert r.window_periods == 2
        assert r.status == "proposed"

    def test_dedup_skips_existing_proposed(self, db_session):
        """v2 Q-new: business-level dedup — same (stock, var, source) already proposed."""
        db = db_session
        run = _make_run(db)
        claim = _make_claim(db, run.id, signal="净息差<1.3%", stock_codes=["601398"])
        _make_stock(db, "601398")
        # Pre-existing proposed row
        db.add(ResearchClaimVariable(
            research_claim_id=claim.id, stock_code="601398",
            variable_name="净息差", threshold_critical=1.3,
            breach_when="lt", source="financial:NIM", unit="%",
            window_periods=2, status="proposed",
        ))
        db.flush()

        proposals = [{
            "claim_id": claim.id, "stock_code": "601398",
            "variable_name": "净息差", "threshold_critical": 1.3,
            "breach_when": "lt", "source": "financial:NIM",
        }]
        with patch.object(svc, "get_zhipu_client") as mock_client:
            mock_client.return_value._client.chat.completions.create.return_value = _mock_response(proposals=proposals)
            result = svc.propose_for_run(db, run.id)

        assert result.proposed_count == 0
        assert result.deduped_count == 1
        # Still one row (no duplicate)
        assert db.query(ResearchClaimVariable).count() == 1

    def test_dedup_skips_existing_active(self, db_session):
        """Already-active var blocks re-propose."""
        db = db_session
        run = _make_run(db)
        claim = _make_claim(db, run.id, signal="净息差<1.3%", stock_codes=["601398"])
        _make_stock(db, "601398")
        db.add(ResearchClaimVariable(
            research_claim_id=claim.id, stock_code="601398",
            variable_name="净息差", threshold_critical=1.3,
            breach_when="lt", source="financial:NIM",
            status="active",
        ))
        db.flush()

        proposals = [{
            "claim_id": claim.id, "stock_code": "601398",
            "variable_name": "净息差", "threshold_critical": 1.3,
            "breach_when": "lt", "source": "financial:NIM",
        }]
        with patch.object(svc, "get_zhipu_client") as mock_client:
            mock_client.return_value._client.chat.completions.create.return_value = _mock_response(proposals=proposals)
            result = svc.propose_for_run(db, run.id)

        assert result.proposed_count == 0
        assert result.deduped_count == 1

    def test_rejected_does_not_block_repropose(self, db_session):
        """v2: rejected status allows re-propose (user changed mind)."""
        db = db_session
        run = _make_run(db)
        claim = _make_claim(db, run.id, signal="净息差<1.3%", stock_codes=["601398"])
        _make_stock(db, "601398")
        db.add(ResearchClaimVariable(
            research_claim_id=claim.id, stock_code="601398",
            variable_name="净息差", threshold_critical=1.3,
            breach_when="lt", source="financial:NIM",
            status="rejected",
        ))
        db.flush()

        proposals = [{
            "claim_id": claim.id, "stock_code": "601398",
            "variable_name": "净息差", "threshold_critical": 1.3,
            "breach_when": "lt", "source": "financial:NIM",
        }]
        with patch.object(svc, "get_zhipu_client") as mock_client:
            mock_client.return_value._client.chat.completions.create.return_value = _mock_response(proposals=proposals)
            result = svc.propose_for_run(db, run.id)

        assert result.proposed_count == 1
        # Now 2 rows: rejected + new proposed
        assert db.query(ResearchClaimVariable).count() == 2

    def test_invalid_source_logs_failure(self, db_session):
        """v2 Q3-A: LLM-picked source not in shortlist → fail this proposal."""
        db = db_session
        run = _make_run(db)
        claim = _make_claim(db, run.id, signal="x<1", stock_codes=["601398"])
        _make_stock(db, "601398")

        proposals = [{
            "claim_id": claim.id, "stock_code": "601398",
            "variable_name": "x", "threshold_critical": 1.0,
            "breach_when": "lt", "source": "financial:BOGUS",  # invalid
        }]
        with patch.object(svc, "get_zhipu_client") as mock_client:
            mock_client.return_value._client.chat.completions.create.return_value = _mock_response(proposals=proposals)
            result = svc.propose_for_run(db, run.id)

        assert result.proposed_count == 0
        assert result.failed_count == 1
        assert claim.id in result.failed_claim_ids

    def test_no_claims_emits_zero(self, db_session):
        db = db_session
        run = _make_run(db)
        # No claims attached
        with patch.object(svc, "get_zhipu_client") as mock_client:
            result = svc.propose_for_run(db, run.id)
            # Should not even call LLM
            mock_client.assert_not_called()
        assert result.total_claims == 0
        assert result.proposed_count == 0
