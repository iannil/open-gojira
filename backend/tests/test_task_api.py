"""Tests for Task REST API via TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.routers.task import set_engine
from app.services.task.engine import TaskEngine
from app.services.task.registry import get_registry, task as _task


@pytest.fixture(autouse=True)
def _setup_task_env():
    """Per-test: register test task + sync DB + start/stop engine."""
    # Register test tasks
    @_task(name="api_test_task", cron="0 0 * * *", timeout=60, tags=["test"])
    def dummy(ctx):
        return {"ok": True}

    # Sync to DB
    registry = get_registry()
    db = SessionLocal()
    try:
        registry.sync_to_db(db)
        db.commit()
    finally:
        db.close()

    # Start a minimal engine for this test
    engine = TaskEngine(tick_interval=999, cron_check_interval=999)
    engine.start()
    set_engine(engine)

    yield

    engine.shutdown(wait=True, timeout=1)


class TestTaskAPI:
    """Tests for /api/tasks endpoints."""

    def test_list_tasks(self, client: TestClient):
        """GET /api/tasks returns task list."""
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        ids = [t["task_id"] for t in data]
        assert "api_test_task" in ids

    def test_get_task(self, client: TestClient):
        """GET /api/tasks/{task_id} returns task detail."""
        resp = client.get("/api/tasks/api_test_task")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "api_test_task"
        assert data["timeout_seconds"] == 60
        assert data["tags"] == ["test"]

    def test_get_task_not_found(self, client: TestClient):
        """GET /api/tasks/nonexistent returns 404."""
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    def test_trigger_task(self, client: TestClient):
        """POST /api/tasks/{task_id}/trigger creates a queued run."""
        resp = client.post("/api/tasks/api_test_task/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "api_test_task"
        assert data["status"] == "queued"
        assert data["run_id"] > 0

    def test_trigger_task_not_found(self, client: TestClient):
        """POST /api/tasks/nonexistent/trigger returns 400."""
        resp = client.post("/api/tasks/nonexistent/trigger")
        assert resp.status_code == 400

    def test_pause_resume_task(self, client: TestClient):
        """POST /api/tasks/{task_id}/pause disables; /resume enables."""
        resp = client.post("/api/tasks/api_test_task/pause")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        resp = client.post("/api/tasks/api_test_task/resume")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_update_task(self, client: TestClient):
        """PUT /api/tasks/{task_id} updates task config."""
        resp = client.put(
            "/api/tasks/api_test_task",
            json={"timeout_seconds": 999, "description": "Updated desc"},
        )
        assert resp.status_code == 200
        assert resp.json()["timeout_seconds"] == 999
        assert resp.json()["description"] == "Updated desc"

    def test_list_task_runs(self, client: TestClient):
        """GET /api/tasks/runs/list returns run list."""
        client.post("/api/tasks/api_test_task/trigger")

        resp = client.get("/api/tasks/runs/list")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["task_id"] == "api_test_task"

    def test_get_task_run(self, client: TestClient):
        """GET /api/tasks/runs/{run_id} returns run detail."""
        trigger_resp = client.post("/api/tasks/api_test_task/trigger")
        run_id = trigger_resp.json()["run_id"]

        resp = client.get(f"/api/tasks/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run_id
        assert data["task_id"] == "api_test_task"

    def test_cancel_task_run(self, client: TestClient):
        """POST /api/tasks/runs/{run_id}/cancel cancels a queued run."""
        trigger_resp = client.post("/api/tasks/api_test_task/trigger")
        run_id = trigger_resp.json()["run_id"]

        resp = client.post(f"/api/tasks/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_retry_task_run(self, client: TestClient):
        """POST /api/tasks/runs/{run_id}/retry creates a new queued run."""
        trigger_resp = client.post("/api/tasks/api_test_task/trigger")
        run_id = trigger_resp.json()["run_id"]

        resp = client.post(f"/api/tasks/runs/{run_id}/retry")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"

    def test_health_endpoint(self, client: TestClient):
        """GET /api/tasks/health returns engine status."""
        resp = client.get("/api/tasks/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine_running"] is True
