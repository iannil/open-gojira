"""Test system_alerts model + service."""
from datetime import datetime
import pytest

from app.models.system_alert import SystemAlert
from app.services.system_alert_service import (
    create_alert, list_alerts, list_unresolved, resolve_alert,
    get_critical_unresolved_count,
)


def test_alert_create(db_session):
    a = SystemAlert(
        severity="critical",
        category="data",
        message="Lixinger API连续失败",
        detail_json={"endpoint": "/cn/company", "consecutive_failures": 5},
    )
    db_session.add(a)
    db_session.commit()
    assert a.id is not None
    assert a.created_at is not None
    assert a.resolved_at is None


def test_severity_values(db_session):
    for sev in ("info", "warning", "critical"):
        db_session.add(SystemAlert(
            severity=sev, category="api", message=f"test {sev}",
        ))
    db_session.commit()
    assert db_session.query(SystemAlert).count() == 3


def test_category_values(db_session):
    for cat in ("data", "scheduler", "api", "db", "token"):
        db_session.add(SystemAlert(
            severity="warning", category=cat, message=f"test {cat}",
        ))
    db_session.commit()
    assert db_session.query(SystemAlert).count() == 5


def test_create_alert_service(db_session):
    a = create_alert(
        db_session,
        severity="warning",
        category="data",
        message="valuation data 24h stale",
        detail={"category": "valuation", "age_hours": 26},
    )
    db_session.commit()
    assert a.id is not None
    assert a.severity == "warning"
    assert a.detail_json["age_hours"] == 26


def test_list_alerts_ordered_by_created_desc(db_session):
    import time
    a1 = create_alert(db_session, severity="info", category="data", message="first")
    db_session.flush()
    a2 = create_alert(db_session, severity="info", category="data", message="second")
    db_session.commit()
    alerts = list_alerts(db_session, limit=10)
    assert len(alerts) == 2
    # newest first
    assert alerts[0].id == a2.id


def test_list_alerts_filter_by_severity(db_session):
    create_alert(db_session, severity="critical", category="api", message="c1")
    create_alert(db_session, severity="info", category="api", message="i1")
    db_session.commit()
    critical_only = list_alerts(db_session, severity="critical")
    assert len(critical_only) == 1
    assert critical_only[0].severity == "critical"


def test_list_unresolved(db_session):
    a1 = create_alert(db_session, severity="warning", category="data", message="a1")
    a2 = create_alert(db_session, severity="warning", category="data", message="a2")
    db_session.commit()
    # resolve a1
    resolve_alert(db_session, a1.id, resolved_by="tester")
    db_session.commit()
    unresolved = list_unresolved(db_session)
    assert len(unresolved) == 1
    assert unresolved[0].id == a2.id


def test_resolve_alert_sets_timestamp(db_session):
    a = create_alert(db_session, severity="info", category="api", message="x")
    db_session.commit()
    assert a.resolved_at is None
    resolved = resolve_alert(db_session, a.id, resolved_by="user")
    db_session.commit()
    assert resolved.resolved_at is not None
    assert resolved.resolved_by == "user"


def test_resolve_alert_idempotent(db_session):
    """Resolving already-resolved returns the same row."""
    a = create_alert(db_session, severity="info", category="api", message="x")
    db_session.commit()
    first = resolve_alert(db_session, a.id, resolved_by="u1")
    db_session.commit()
    second = resolve_alert(db_session, a.id, resolved_by="u2")
    db_session.commit()
    assert first.resolved_at == second.resolved_at
    assert second.resolved_by == "u1"  # 不覆盖


def test_get_critical_unresolved_count(db_session):
    create_alert(db_session, severity="critical", category="api", message="c1")
    create_alert(db_session, severity="critical", category="data", message="c2")
    create_alert(db_session, severity="warning", category="api", message="w1")
    a = create_alert(db_session, severity="critical", category="api", message="c3")
    db_session.commit()
    resolve_alert(db_session, a.id)
    db_session.commit()
    count = get_critical_unresolved_count(db_session)
    assert count == 2


def test_alert_resolve_by_filter(db_session):
    """Resolve all critical alerts matching a category."""
    create_alert(db_session, severity="critical", category="data", message="d1")
    create_alert(db_session, severity="critical", category="data", message="d2")
    create_alert(db_session, severity="critical", category="api", message="a1")
    db_session.commit()
    from app.services.system_alert_service import resolve_matching
    count = resolve_matching(db_session, severity="critical", category="data",
                              resolved_by="auto")
    db_session.commit()
    assert count == 2
    # api alert still unresolved
    assert get_critical_unresolved_count(db_session) == 1


def test_detail_json_nullable(db_session):
    """detail_json is optional."""
    a = SystemAlert(severity="info", category="api", message="no detail")
    db_session.add(a)
    db_session.commit()
    assert a.detail_json is None
