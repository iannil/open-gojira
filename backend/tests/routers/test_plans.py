"""Tests for the plans router (CRUD + run endpoint)."""

from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

# Import models so their tables are registered on Base.metadata before
# conftest's setup_db fixture calls create_all.
import app.models  # noqa: F401  — registers all ORM tables
from app.models.strategy import Strategy
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_strategy() -> int:
    """Insert a minimal strategy row so plan_service.create passes FK checks.

    Returns the strategy id.
    """
    with TestSessionLocal() as db:
        s = Strategy(
            name="Test Strategy",
            slug="test_strategy",
            description="strategy for tests",
            kind="custom",
            rule_json='{"logic": "AND", "conditions": []}',
            is_builtin=False,
        )
        db.add(s)
        db.commit()
        return s.id


def _valid_plan_payload(strategy_id: int, **overrides) -> dict:
    """Return a valid JSON body for POST /api/plans."""
    payload = {
        "name": "My Plan",
        "slug": "my_plan",
        "description": "test plan",
        "strategy_composition": {
            "strategy_ids": [strategy_id],
            "logic": "AND",
        },
        "scan_scope": {
            "type": "all_stocks",
            "values": [],
        },
        "schedule_cron": "0 18 * * 1-5",
        "trading_rules": None,
    }
    payload.update(overrides)
    return payload


def _create_plan(client: TestClient, strategy_id: int, **overrides) -> dict:
    """Helper: create a plan via the API and return the response JSON."""
    resp = client.post("/api/plans", json=_valid_plan_payload(strategy_id, **overrides))
    assert resp.status_code == 201, f"create failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# 1. List plans — empty
# ---------------------------------------------------------------------------


class TestListPlans:
    """GET /api/plans"""

    def test_empty_list(self, client):
        resp = client.get("/api/plans")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_plan(self, client):
        sid = _insert_strategy()
        _create_plan(client, sid)

        resp = client.get("/api/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["slug"] == "my_plan"


# ---------------------------------------------------------------------------
# 2. Create plan
# ---------------------------------------------------------------------------


class TestCreatePlan:
    """POST /api/plans"""

    def test_create_plan(self, client):
        sid = _insert_strategy()
        payload = _valid_plan_payload(sid)

        resp = client.post("/api/plans", json=payload)
        assert resp.status_code == 201

        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == "My Plan"
        assert body["slug"] == "my_plan"
        assert body["description"] == "test plan"
        assert body["status"] == "active"
        assert body["is_builtin"] is False
        assert body["strategy_composition"]["strategy_ids"] == [sid]
        assert body["scan_scope"]["type"] == "all_stocks"

    def test_create_duplicate_slug_returns_409(self, client):
        sid = _insert_strategy()
        _create_plan(client, sid)

        resp = client.post("/api/plans", json=_valid_plan_payload(sid))
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_plan_with_nonexistent_strategy_returns_400(self, client):
        payload = _valid_plan_payload(strategy_id=99999)
        resp = client.post("/api/plans", json=payload)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Get plan by id
# ---------------------------------------------------------------------------


class TestGetPlan:
    """GET /api/plans/{plan_id}"""

    def test_get_existing_plan(self, client):
        sid = _insert_strategy()
        created = _create_plan(client, sid)

        resp = client.get(f"/api/plans/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["slug"] == "my_plan"
        assert resp.json()["id"] == created["id"]

    def test_get_nonexistent_plan_returns_404(self, client):
        resp = client.get("/api/plans/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Update plan
# ---------------------------------------------------------------------------


class TestUpdatePlan:
    """PUT /api/plans/{plan_id}"""

    def test_update_plan_fields(self, client):
        sid = _insert_strategy()
        created = _create_plan(client, sid)

        resp = client.put(f"/api/plans/{created['id']}", json={
            "name": "Updated Plan",
            "description": "updated desc",
            "status": "paused",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Updated Plan"
        assert body["description"] == "updated desc"
        assert body["status"] == "paused"

    def test_update_partial_only_changes_sent_fields(self, client):
        sid = _insert_strategy()
        created = _create_plan(client, sid)

        resp = client.put(f"/api/plans/{created['id']}", json={"name": "New Name"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "New Name"
        # Unchanged fields remain
        assert body["description"] == "test plan"
        assert body["status"] == "active"

    def test_update_nonexistent_plan_returns_404(self, client):
        resp = client.put("/api/plans/99999", json={"name": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Delete plan
# ---------------------------------------------------------------------------


class TestDeletePlan:
    """DELETE /api/plans/{plan_id}"""

    def test_delete_plan(self, client):
        sid = _insert_strategy()
        created = _create_plan(client, sid)

        del_resp = client.delete(f"/api/plans/{created['id']}")
        assert del_resp.status_code == 204

        # Verify it is gone
        get_resp = client.get(f"/api/plans/{created['id']}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_plan_returns_404(self, client):
        resp = client.delete("/api/plans/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Run plan (mocked)
# ---------------------------------------------------------------------------


class TestRunPlan:
    """POST /api/plans/{plan_id}/run"""

    def test_run_plan_success(self, client):
        sid = _insert_strategy()
        created = _create_plan(client, sid)

        mock_result = MagicMock()
        mock_result.plan_id = created["id"]
        mock_result.plan_name = "My Plan"
        mock_result.scanned = 50
        mock_result.passed = 5
        mock_result.removed = 1
        mock_result.new = 3
        mock_result.drafts_emitted = 0
        mock_result.errors = []

        with patch("app.services.plan_runner.run_plan", return_value=mock_result) as mock_run:
            resp = client.post(f"/api/plans/{created['id']}/run")

        assert resp.status_code == 200
        body = resp.json()
        assert body["plan_id"] == created["id"]
        assert body["scanned"] == 50
        assert body["passed"] == 5
        assert body["removed"] == 1
        assert body["new"] == 3
        mock_run.assert_called_once()

    def test_run_nonexistent_plan_returns_404(self, client):
        resp = client.post("/api/plans/99999/run")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. List candidates for plan
# ---------------------------------------------------------------------------


class TestListPlanCandidates:
    """GET /api/plans/{plan_id}/candidates"""

    def test_empty_candidates(self, client):
        sid = _insert_strategy()
        created = _create_plan(client, sid)

        resp = client.get(f"/api/plans/{created['id']}/candidates")
        assert resp.status_code == 200
        assert resp.json() == []
