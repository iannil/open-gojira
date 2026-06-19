"""Test data_freshness tracking + staleness gate."""
from datetime import datetime, timedelta
import pytest

from app.core.datetime_utils import now
from app.models.data_freshness import DataFreshness
from app.services.data_freshness_service import (
    record_sync_attempt, record_sync_success, record_sync_failure,
    assert_fresh_enough, DataStaleError, get_freshness_report,
)


def test_freshness_create(db_session):
    f = DataFreshness(category="valuation",
                      last_synced_at=now(),
                      last_success_at=now(),
                      last_record_count=5000)
    db_session.add(f)
    db_session.commit()
    assert f.id is not None
    assert f.category == "valuation"


def test_record_sync_attempt(db_session):
    record_sync_attempt(db_session, "valuation")
    db_session.commit()
    f = db_session.query(DataFreshness).filter_by(category="valuation").one()
    assert f.last_synced_at is not None
    assert f.last_success_at is None  # not yet success


def test_record_sync_success(db_session):
    record_sync_success(db_session, "valuation", record_count=5000)
    db_session.commit()
    f = db_session.query(DataFreshness).filter_by(category="valuation").one()
    assert f.last_synced_at is not None
    assert f.last_success_at is not None
    assert f.last_record_count == 5000


def test_record_sync_failure(db_session):
    # 先 success
    record_sync_success(db_session, "valuation", record_count=100)
    db_session.commit()
    # 再 failure
    record_sync_failure(db_session, "valuation", error="timeout")
    db_session.commit()
    f = db_session.query(DataFreshness).filter_by(category="valuation").one()
    assert f.last_synced_at is not None
    # last_success_at 仍是上次成功时间(没被覆盖)
    assert f.last_success_at is not None
    assert f.last_error == "timeout"


def test_assert_fresh_enough_pass(db_session):
    """Fresh data should pass."""
    record_sync_success(db_session, "valuation", record_count=100)
    db_session.commit()
    # 不抛
    assert_fresh_enough(db_session, "valuation", max_age_hours=24)


def test_assert_fresh_enough_stale_raises(db_session):
    """Data older than max_age should raise."""
    stale_time = now() - timedelta(hours=48)
    f = DataFreshness(category="valuation",
                      last_synced_at=stale_time,
                      last_success_at=stale_time,
                      last_record_count=100)
    db_session.add(f); db_session.commit()
    with pytest.raises(DataStaleError) as exc:
        assert_fresh_enough(db_session, "valuation", max_age_hours=24)
    assert "valuation" in str(exc.value)


def test_assert_fresh_enough_never_synced_raises(db_session):
    """Category that has never been synced should raise."""
    with pytest.raises(DataStaleError):
        assert_fresh_enough(db_session, "nonexistent_category", max_age_hours=24)


def test_assert_fresh_enough_failed_sync_only_raises(db_session):
    """If last sync failed but success was recent, may still be OK.
    But if success is stale, raise."""
    stale_success = now() - timedelta(hours=48)
    f = DataFreshness(category="valuation",
                      last_synced_at=now(),  # attempt was recent
                      last_success_at=stale_success,  # but success was 48h ago
                      last_record_count=100)
    db_session.add(f); db_session.commit()
    with pytest.raises(DataStaleError):
        assert_fresh_enough(db_session, "valuation", max_age_hours=24)


def test_assert_fresh_enough_emits_system_alert(db_session):
    """Stale data should also create a system_alert."""
    from app.services.system_alert_service import list_unresolved
    stale_time = now() - timedelta(hours=48)
    db_session.add(DataFreshness(category="valuation",
                                  last_synced_at=stale_time,
                                  last_success_at=stale_time,
                                  last_record_count=100))
    db_session.commit()
    try:
        assert_fresh_enough(db_session, "valuation", max_age_hours=24)
    except DataStaleError:
        pass
    db_session.commit()
    alerts = list_unresolved(db_session, category="data")
    assert len(alerts) >= 1
    assert any("valuation" in a.message for a in alerts)


def test_get_freshness_report(db_session):
    """Summary view of all categories."""
    record_sync_success(db_session, "valuation", record_count=100)
    record_sync_success(db_session, "kline", record_count=200)
    db_session.commit()
    report = get_freshness_report(db_session)
    assert "valuation" in report
    assert "kline" in report
    assert report["valuation"]["record_count"] == 100
