"""Test CorpAction model."""
from datetime import date
import pytest

from app.models.corp_action import CorpAction


def test_corp_action_create_cash_dividend(db_session):
    a = CorpAction(
        stock_code="600519",
        ex_date=date(2026, 7, 15),
        action_type="cash_dividend",
        params_json={"per_share": 25.0, "record_date": "2026-07-14"},
        source="lixinger",
    )
    db_session.add(a)
    db_session.commit()
    assert a.id is not None
    assert a.processed_at is None
    assert a.applied_trade_id is None


def test_action_type_values(db_session):
    """All supported action types."""
    for i, action_type in enumerate([
        "cash_dividend", "stock_dividend", "capitalization",
        "rights_issue", "delist", "merger", "code_change",
    ]):
        db_session.add(CorpAction(
            stock_code="600519",
            ex_date=date(2026, 1, 1),
            action_type=action_type,
            params_json={"test": i},
            source="manual",
        ))
    db_session.commit()
    assert db_session.query(CorpAction).count() == 7


def test_params_json_storage(db_session):
    """JSON field round-trip."""
    params = {
        "per_10_shares": 5,
        "cash_per_10": 25.0,
        "record_date": "2026-07-14",
        "payment_date": "2026-07-15",
    }
    a = CorpAction(
        stock_code="600519",
        ex_date=date(2026, 7, 15),
        action_type="stock_dividend",
        params_json=params,
        source="lixinger",
    )
    db_session.add(a); db_session.commit()
    refreshed = db_session.get(CorpAction, a.id)
    assert refreshed.params_json == params


def test_processed_at_set_after_processing(db_session):
    a = CorpAction(
        stock_code="600519",
        ex_date=date(2026, 7, 15),
        action_type="cash_dividend",
        params_json={"per_share": 1.0},
        source="lixinger",
    )
    db_session.add(a); db_session.commit()
    assert a.processed_at is None
    a.processed_at = __import__("datetime").datetime.utcnow()
    a.applied_trade_id = 42
    db_session.commit()
    refreshed = db_session.get(CorpAction, a.id)
    assert refreshed.processed_at is not None
    assert refreshed.applied_trade_id == 42


def test_unique_constraint_prevents_duplicates(db_session):
    """Same stock + ex_date + action_type + source should be unique."""
    a1 = CorpAction(
        stock_code="600519",
        ex_date=date(2026, 7, 15),
        action_type="cash_dividend",
        params_json={"per_share": 25.0},
        source="lixinger",
    )
    db_session.add(a1); db_session.commit()
    a2 = CorpAction(
        stock_code="600519",
        ex_date=date(2026, 7, 15),
        action_type="cash_dividend",
        params_json={"per_share": 25.0},
        source="lixinger",
    )
    db_session.add(a2)
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()


def test_indexed_by_ex_date(db_session):
    """ex_date should be indexed (range scan for daily processing)."""
    from app.models.corp_action import CorpAction as CA
    table = CA.__table__
    assert table.c.ex_date.index


def test_indexed_by_processed_at(db_session):
    """processed_at index for finding unprocessed (IS NULL)."""
    from app.models.corp_action import CorpAction as CA
    table = CA.__table__
    assert table.c.processed_at.index
