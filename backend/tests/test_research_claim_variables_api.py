"""API tests for /api/research/claim-variables endpoints (Phase 2 #9 阶段 B v2)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.models.research_claim import ResearchClaim
from app.models.research_claim_variable import ResearchClaimVariable
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.stock import Stock


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_COUNTER = [0]


def _seed_cv(db, *, status: str = "proposed", stock_code: str = "601398",
              variable_name: str = "净息差", breach_when: str = "lt",
              threshold: float = 1.3, window: int | None = 2,
              source: str = "financial:NIM") -> ResearchClaimVariable:
    _COUNTER[0] += 1
    theme = ResearchTheme(name=f"t-{_COUNTER[0]}", market="A_SHARE")
    db.add(theme); db.flush()
    run = ResearchRun(
        research_theme_id=theme.id, status="completed",
        scope_market="A_SHARE", triggered_by="manual", llm_provider="t",
        started_at=_utcnow_naive(),
    )
    db.add(run); db.flush()
    claim = ResearchClaim(
        research_run_id=run.id, type="failure_condition", position=0,
        subject="x", predicate="y", signal="NIM<1.3", outcome="z",
        stock_codes_json=json.dumps([stock_code]),
    )
    db.add(claim); db.flush()
    if not db.get(Stock, stock_code):
        db.add(Stock(code=stock_code, name="x"))
        db.flush()
    cv = ResearchClaimVariable(
        research_claim_id=claim.id, stock_code=stock_code,
        variable_name=variable_name, threshold_critical=threshold,
        breach_when=breach_when, source=source, unit="%",
        window_periods=window, status=status,
    )
    db.add(cv); db.flush()
    return cv


# ── list ───────────────────────────────────────────────────────────────


class TestList:
    def test_list_groups_by_status(self, db_session, client):
        _seed_cv(db_session, status="proposed", stock_code="A")
        _seed_cv(db_session, status="active", stock_code="B")
        _seed_cv(db_session, status="rejected", stock_code="C")
        db_session.commit()

        r = client.get("/api/research/claim-variables")
        assert r.status_code == 200
        data = r.json()
        assert len(data["proposed"]) == 1
        assert len(data["active"]) == 1
        assert len(data["rejected"]) == 1

    def test_list_filter_by_stock(self, db_session, client):
        _seed_cv(db_session, stock_code="A")
        _seed_cv(db_session, stock_code="B")
        db_session.commit()

        r = client.get("/api/research/claim-variables", params={"stock_code": "A"})
        assert r.status_code == 200
        data = r.json()
        total = len(data["proposed"]) + len(data["active"]) + len(data["rejected"])
        assert total == 1


# ── approve ────────────────────────────────────────────────────────────


class TestApprove:
    def test_proposed_to_active(self, db_session, client):
        cv = _seed_cv(db_session, status="proposed")
        db_session.commit()

        r = client.post(f"/api/research/claim-variables/{cv.id}/approve", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "active"
        assert body["reviewed_by"] == "user"
        assert body["reviewed_at"] is not None

    def test_approve_with_overrides(self, db_session, client):
        cv = _seed_cv(db_session, status="proposed", threshold=1.3)
        db_session.commit()

        r = client.post(
            f"/api/research/claim-variables/{cv.id}/approve",
            json={"threshold_critical": 1.5, "window_periods": 3, "note": "tighten"},
        )
        assert r.status_code == 200
        assert r.json()["threshold_critical"] == 1.5
        assert r.json()["window_periods"] == 3

    def test_approve_rejected_returns_409(self, db_session, client):
        cv = _seed_cv(db_session, status="rejected")
        db_session.commit()
        r = client.post(f"/api/research/claim-variables/{cv.id}/approve", json={})
        assert r.status_code == 409

    def test_approve_active_returns_409(self, db_session, client):
        cv = _seed_cv(db_session, status="active")
        db_session.commit()
        r = client.post(f"/api/research/claim-variables/{cv.id}/approve", json={})
        assert r.status_code == 409

    def test_approve_404(self, client):
        r = client.post("/api/research/claim-variables/9999/approve", json={})
        assert r.status_code == 404


# ── reject ─────────────────────────────────────────────────────────────


class TestReject:
    def test_proposed_to_rejected(self, db_session, client):
        cv = _seed_cv(db_session, status="proposed")
        db_session.commit()
        r = client.post(
            f"/api/research/claim-variables/{cv.id}/reject",
            json={"note": "noisy"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "rejected"
        assert body["review_note"] == "noisy"

    def test_reject_already_rejected_409(self, db_session, client):
        cv = _seed_cv(db_session, status="rejected")
        db_session.commit()
        r = client.post(f"/api/research/claim-variables/{cv.id}/reject", json={})
        assert r.status_code == 409


# ── patch ──────────────────────────────────────────────────────────────


class TestPatch:
    def test_patch_active_threshold(self, db_session, client):
        cv = _seed_cv(db_session, status="active", threshold=1.3)
        db_session.commit()
        r = client.patch(
            f"/api/research/claim-variables/{cv.id}",
            json={"threshold_critical": 1.5},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["updated_fields"] == ["threshold_critical"]
        assert body["before"]["threshold_critical"] == 1.3
        assert body["after"]["threshold_critical"] == 1.5

    def test_patch_resets_last_alerted_at(self, db_session, client):
        """v2: editing resets dedup so new threshold takes effect immediately."""
        from datetime import timedelta
        cv = _seed_cv(db_session, status="active")
        cv.last_alerted_at = _utcnow_naive() - timedelta(hours=2)
        db_session.commit()
        client.patch(
            f"/api/research/claim-variables/{cv.id}",
            json={"threshold_critical": 1.5},
        )
        db_session.refresh(cv)
        assert cv.last_alerted_at is None

    def test_patch_proposed_returns_409(self, db_session, client):
        cv = _seed_cv(db_session, status="proposed")
        db_session.commit()
        r = client.patch(
            f"/api/research/claim-variables/{cv.id}",
            json={"threshold_critical": 1.5},
        )
        assert r.status_code == 409

    def test_patch_no_fields_returns_400(self, db_session, client):
        cv = _seed_cv(db_session, status="active")
        db_session.commit()
        r = client.patch(f"/api/research/claim-variables/{cv.id}", json={})
        assert r.status_code == 400


# ── cockpit pending ────────────────────────────────────────────────────


class TestCockpitPending:
    def test_returns_count_and_by_stock(self, db_session, client):
        _seed_cv(db_session, status="proposed", stock_code="A")
        _seed_cv(db_session, status="proposed", stock_code="A")
        _seed_cv(db_session, status="proposed", stock_code="B")
        _seed_cv(db_session, status="active", stock_code="C")  # not counted
        db_session.commit()

        r = client.get("/api/cockpit/claim-variables-pending")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 3
        by_stock = {d["stock_code"]: d["count"] for d in data["by_stock"]}
        assert by_stock["A"] == 2
        assert by_stock["B"] == 1
        assert "C" not in by_stock
