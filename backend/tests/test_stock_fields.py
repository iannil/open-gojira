"""Test new Stock trading-status fields and stocks_sync population.

S1.1 adds four columns sourced from Lixinger /cn/company:
- listing_status (8-value enum: normally_listed / delisting_risk_warning /
  special_treatment / delisting_transitional_period / ipo_suspension /
  issued_but_not_listed / issue_failure / unauthorized)
- exchange (sh / sz / bj)
- fs_table_type (non_financial / bank / security / insurance / other_financial)
- ipo_date (Date)

These replace the planned derived fields (board / is_st / is_suspended) with
the raw source values, which are more reliable than inferring from code prefix
or name matching.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.stock import Stock
from app.services.stocks_sync_service import sync_stocks_from_lixinger


# ---------------------------------------------------------------------------
# Fixtures — local in-memory SQLite (matches test_holding_service convention)
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create an in-memory SQLite session with all tables."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    import app.models  # noqa: F401 — register all ORM tables
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_stock_has_listing_status_field(db_session):
    """All four new fields should persist and round-trip."""
    s = Stock(
        code="600519",
        name="贵州茅台",
        listing_status="normally_listed",
        exchange="sh",
        fs_table_type="non_financial",
        ipo_date=date(2001, 8, 27),
    )
    db_session.add(s)
    db_session.commit()
    refreshed = db_session.get(Stock, "600519")
    assert refreshed.listing_status == "normally_listed"
    assert refreshed.exchange == "sh"
    assert refreshed.fs_table_type == "non_financial"
    assert refreshed.ipo_date == date(2001, 8, 27)


def test_listing_status_enum_values_accepted(db_session):
    """All 8 statuses observed in S0.6 spike should be storable verbatim."""
    statuses = [
        "normally_listed",
        "delisting_risk_warning",
        "special_treatment",
        "delisting_transitional_period",
        "ipo_suspension",
        "issued_but_not_listed",
        "issue_failure",
        "unauthorized",
    ]
    for i, status in enumerate(statuses):
        db_session.add(
            Stock(
                code=f"90000{i}",
                name=f"Test {i}",
                listing_status=status,
                exchange="sh",
                fs_table_type="non_financial",
                ipo_date=date(2020, 1, 1),
            )
        )
    db_session.commit()
    assert db_session.query(Stock).count() == len(statuses)


def test_sync_stocks_populates_new_fields(db_session, monkeypatch):
    """sync_stocks_from_lixinger should switch to get_company_list_all and
    populate listing_status / exchange / fs_table_type / ipo_date."""
    fake_data = [
        {
            "stockCode": "600519",
            "name": "贵州茅台",
            "exchange": "sh",
            "listingStatus": "normally_listed",
            "fsTableType": "non_financial",
            "ipoDate": "2001-08-27",
        },
        {
            "stockCode": "300750",
            "name": "宁德时代",
            "exchange": "sz",
            "listingStatus": "normally_listed",
            "fsTableType": "non_financial",
            "ipoDate": "2018-06-11",
        },
        {
            "stockCode": "688981",
            "name": "中芯国际",
            "exchange": "sh",
            "listingStatus": "normally_listed",
            "fsTableType": "non_financial",
            "ipoDate": "2020-07-16",
        },
    ]

    fake_client = MagicMock()
    fake_client.get_company_list_all.return_value = fake_data
    # Industry sync phase should not blow up; return empty so phase 2 is a no-op.
    fake_client.get_industry_list.return_value = []

    result = sync_stocks_from_lixinger(db_session, client=fake_client)

    # The sync must call get_company_list_all (the auto-paginating path).
    fake_client.get_company_list_all.assert_called_once()
    # And must NOT fall back to the capped get_company_list.
    fake_client.get_company_list.assert_not_called()

    assert result.total_fetched == 3
    assert result.inserted == 3

    mao_tai = db_session.get(Stock, "600519")
    assert mao_tai is not None
    assert mao_tai.listing_status == "normally_listed"
    assert mao_tai.exchange == "sh"
    assert mao_tai.fs_table_type == "non_financial"
    assert mao_tai.ipo_date == date(2001, 8, 27)

    catl = db_session.get(Stock, "300750")
    assert catl.listing_status == "normally_listed"
    assert catl.exchange == "sz"


def test_sync_stocks_updates_existing_stock_new_fields(db_session, monkeypatch):
    """An existing stock should have its new fields backfilled on re-sync."""
    db_session.add(Stock(code="600519", name="贵州茅台"))
    db_session.commit()

    fake_client = MagicMock()
    fake_client.get_company_list_all.return_value = [
        {
            "stockCode": "600519",
            "name": "贵州茅台",
            "exchange": "sh",
            "listingStatus": "normally_listed",
            "fsTableType": "non_financial",
            "ipoDate": "2001-08-27",
        }
    ]
    fake_client.get_industry_list.return_value = []

    result = sync_stocks_from_lixinger(db_session, client=fake_client)

    assert result.inserted == 0
    assert result.updated == 1
    refreshed = db_session.get(Stock, "600519")
    assert refreshed.exchange == "sh"
    assert refreshed.listing_status == "normally_listed"
    assert refreshed.ipo_date == date(2001, 8, 27)


def test_sync_stocks_handles_malformed_ipo_date(db_session, monkeypatch):
    """Bad ipoDate strings should not crash the sync; field falls back to None."""
    fake_client = MagicMock()
    fake_client.get_company_list_all.return_value = [
        {
            "stockCode": "000001",
            "name": "平安银行",
            "exchange": "sz",
            "listingStatus": "normally_listed",
            "fsTableType": "bank",
            "ipoDate": "not-a-date",
        }
    ]
    fake_client.get_industry_list.return_value = []

    sync_stocks_from_lixinger(db_session, client=fake_client)

    stock = db_session.get(Stock, "000001")
    assert stock.ipo_date is None
    # Other fields still populate.
    assert stock.exchange == "sz"
    assert stock.fs_table_type == "bank"
