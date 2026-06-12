"""Test Lixinger client resilience — retry + circuit breaker + alerting."""
from unittest.mock import patch, MagicMock

import pytest
import httpx
from tenacity import wait_none

from app.services.lixinger_client import LixingerClient, LixingerError, CircuitOpenError


def _make_client() -> LixingerClient:
    """Client with no-op retry wait so tests run fast."""
    c = LixingerClient(token="fake")
    c._retry_wait = wait_none()
    return c


def _make_response(status_code=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.json.return_value = json_data or {}
    return r


def test_transient_request_error_retried_then_succeeds():
    """Network error 2 times then success → should succeed (not raise)."""
    client = _make_client()

    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] < 3:
            raise httpx.RequestError("network down", request=MagicMock())
        return _make_response(json_data={"code": 1, "data": [{"x": 1}]})

    with patch.object(client._client, "post", side_effect=side_effect):
        data = client._post("/test", {"a": 1})

    assert data == [{"x": 1}]
    assert call_count[0] == 3  # 2 retries + 1 success


def test_all_retries_exhausted_raises():
    """3 attempts all fail → LixingerError."""
    client = _make_client()

    with patch.object(
        client._client,
        "post",
        side_effect=httpx.RequestError("dead", request=MagicMock()),
    ):
        with pytest.raises(LixingerError):
            client._post("/test", {"a": 1})


def test_5xx_retried_4xx_not():
    """5xx errors retried; 4xx errors fail fast (no retry)."""
    client = _make_client()

    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        # Return a 500 response — _post_with_retry converts this into a
        # _TransientServerError which tenacity retries.
        return _make_response(status_code=500, text="server error")

    with patch.object(client._client, "post", side_effect=side_effect):
        with pytest.raises(LixingerError):
            client._post("/test", {"a": 1})
    # Should have retried (3 attempts)
    assert call_count[0] == 3

    # 4xx: should not retry — _post_with_retry returns the response as-is,
    # and _post's raise_for_status() surfaces it as HTTPStatusError.
    client2 = _make_client()
    call_count[0] = 0

    def side_effect_4xx(*args, **kwargs):
        call_count[0] += 1
        r = MagicMock()
        r.status_code = 403
        r.text = "forbidden"
        r.request = MagicMock()
        # raise_for_status() will raise this on 4xx
        def raise_for_status():
            raise httpx.HTTPStatusError("forbidden", request=r.request, response=r)
        r.raise_for_status.side_effect = raise_for_status
        return r

    with patch.object(client2._client, "post", side_effect=side_effect_4xx):
        with pytest.raises(LixingerError):
            client2._post("/test", {"a": 1})
    assert call_count[0] == 1  # no retry


def test_business_code_error_not_retried():
    """Lixinger code != 1 is a business error, no retry."""
    client = _make_client()

    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        return _make_response(json_data={"code": 0, "message": "token expired"})

    with patch.object(client._client, "post", side_effect=side_effect):
        with pytest.raises(LixingerError):
            client._post("/test", {"a": 1})
    assert call_count[0] == 1  # no retry on business error


def test_circuit_opens_after_consecutive_failures():
    """After 5 consecutive failures, circuit opens; further calls fast-fail."""
    client = _make_client()

    def side_effect(*args, **kwargs):
        raise httpx.RequestError("down", request=MagicMock())

    with patch.object(client._client, "post", side_effect=side_effect):
        # First 5 attempts use all retries each (3 attempts each = 15 total)
        for _ in range(5):
            with pytest.raises(LixingerError):
                client._post("/test", {"a": 1})

    # Circuit should now be open. Next call should fail-fast without HTTP.
    call_count_after = [0]

    def count_post(*args, **kwargs):
        call_count_after[0] += 1
        return _make_response(json_data={"code": 1, "data": []})

    with patch.object(client._client, "post", side_effect=count_post):
        with pytest.raises(LixingerError) as exc:
            client._post("/test", {"a": 1})
        assert "circuit" in str(exc.value).lower() or "open" in str(exc.value).lower()
    assert call_count_after[0] == 0  # no HTTP call made


def test_circuit_emits_critical_system_alert():
    """When circuit opens, a critical system_alert is created."""
    client = _make_client()

    def side_effect(*args, **kwargs):
        raise httpx.RequestError("down", request=MagicMock())

    from app.services import system_alert_service

    alerts_created = []

    def fake_create(db, **kwargs):
        alerts_created.append(kwargs)
        return MagicMock()

    with patch.object(client._client, "post", side_effect=side_effect), \
         patch.object(system_alert_service, "create_alert", fake_create):
        for _ in range(5):
            with pytest.raises(LixingerError):
                client._post("/test", {"a": 1})

    # At least one alert should have been emitted for circuit opening
    assert len(alerts_created) > 0
    last = alerts_created[-1]
    assert last.get("severity") == "critical"
    assert last.get("category") == "api"


def test_token_quota_business_error_emits_alert():
    """When Lixinger returns token/quota/limit error, emit critical alert."""
    client = _make_client()

    from app.services import system_alert_service

    alerts_created = []

    def fake_create(db, **kwargs):
        alerts_created.append(kwargs)
        return MagicMock()

    with patch.object(
        client._client,
        "post",
        side_effect=lambda *a, **k: _make_response(
            json_data={"code": 0, "message": "token expired, please renew"}
        ),
    ), patch.object(system_alert_service, "create_alert", fake_create):
        with pytest.raises(LixingerError):
            client._post("/test", {"a": 1})

    assert len(alerts_created) == 1
    alert = alerts_created[0]
    assert alert.get("severity") == "critical"
    assert alert.get("category") == "token"


def test_successful_call_resets_failure_count():
    """A successful call resets the consecutive failure counter.

    We bypass retry (mock _post_with_retry) so we can deterministically
    control success/failure per _post call without tenacity's retry loop
    muddying the call_count.
    """
    client = _make_client()

    # First 4 _post calls fail, 5th succeeds, then 4 more failures should NOT
    # open the circuit (because the success reset the counter).
    outcomes = [
        httpx.RequestError("down", request=MagicMock()),  # failure 1
        httpx.RequestError("down", request=MagicMock()),  # failure 2
        httpx.RequestError("down", request=MagicMock()),  # failure 3
        httpx.RequestError("down", request=MagicMock()),  # failure 4
        _make_response(json_data={"code": 1, "data": []}),  # success → resets
        httpx.RequestError("down", request=MagicMock()),  # failure 5 (post-reset: count 1)
        httpx.RequestError("down", request=MagicMock()),  # failure 6 (count 2)
        httpx.RequestError("down", request=MagicMock()),  # failure 7 (count 3)
        httpx.RequestError("down", request=MagicMock()),  # failure 8 (count 4)
    ]

    def fake_post_with_retry(url, body):
        item = outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    with patch.object(client, "_post_with_retry", side_effect=fake_post_with_retry):
        # First 4 calls fail
        for _ in range(4):
            with pytest.raises(LixingerError):
                client._post("/test", {"a": 1})
        # 5th call succeeds (resets counter)
        assert client._post("/test", {"a": 1}) == []
        # 4 more failures: count goes 1,2,3,4 — below threshold of 5
        for _ in range(4):
            with pytest.raises(LixingerError) as exc:
                client._post("/test", {"a": 1})
            # Should be regular LixingerError, NOT CircuitOpenError
            assert not isinstance(exc.value, CircuitOpenError)
        # Final state: failure_count is 4, not enough to open
