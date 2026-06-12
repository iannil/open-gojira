"""Test data_sanity_service — field validation for Lixinger records."""
import pytest
import math

from app.services.data_sanity_service import (
    validate_record, validate_batch, SANITY_RULES,
    is_valid_record, get_violations_summary,
)


def test_valid_record_passes():
    """All fields in valid ranges → empty violations list."""
    record = {
        "pe_ttm": 25.0,
        "pb": 3.5,
        "dyr": 0.045,
        "sp": 100.0,
        "mc": 1000000000,
    }
    assert validate_record(record) == []


def test_pe_too_high_violation():
    record = {"pe_ttm": 1500.0}
    violations = validate_record(record)
    assert len(violations) == 1
    assert "pe_ttm" in violations[0]


def test_pe_negative_violation():
    """PE can be negative (loss-making companies) but sanity rule may flag."""
    record = {"pe_ttm": -50.0}
    violations = validate_record(record)
    assert any("pe_ttm" in v for v in violations)


def test_pb_zero_violation():
    record = {"pb": 0.0}
    violations = validate_record(record)
    assert any("pb" in v for v in violations)


def test_dyr_too_high_violation():
    """DYR > 30% is suspicious (likely data error)."""
    record = {"dyr": 0.45}
    violations = validate_record(record)
    assert any("dyr" in v for v in violations)


def test_dyr_zero_allowed():
    """DYR=0 is normal (no dividend)."""
    record = {"dyr": 0.0}
    assert validate_record(record) == []


def test_sp_must_be_positive():
    record = {"sp": -5.0}
    violations = validate_record(record)
    assert any("sp" in v for v in violations)


def test_sp_zero_violation():
    record = {"sp": 0.0}
    violations = validate_record(record)
    assert any("sp" in v for v in violations)


def test_nan_value_violation():
    record = {"pe_ttm": float("nan")}
    violations = validate_record(record)
    assert any("pe_ttm" in v for v in violations)


def test_none_value_skipped():
    """Missing field is OK (not all records have all fields)."""
    record = {"pe_ttm": None, "sp": 100.0}
    # pe_ttm=None 不参与校验,sp=100 OK
    assert validate_record(record) == []


def test_is_valid_record_helper():
    assert is_valid_record({"sp": 100.0}) is True
    assert is_valid_record({"sp": -1.0}) is False


def test_validate_batch_partitions():
    """Batch returns (valid, invalid) split."""
    records = [
        {"sp": 100.0, "pe_ttm": 20.0},
        {"sp": -5.0},  # bad
        {"sp": 50.0, "pe_ttm": 10000.0},  # pe bad
        {"sp": 200.0},  # ok
    ]
    valid, invalid = validate_batch(records)
    assert len(valid) == 2
    assert len(invalid) == 2


def test_validate_batch_with_metadata():
    """Invalid records include the violations for tracing."""
    records = [
        {"stockCode": "600519", "sp": 100.0},
        {"stockCode": "BAD001", "sp": -1.0},
    ]
    valid, invalid = validate_batch(records, id_field="stockCode")
    assert len(valid) == 1
    assert len(invalid) == 1
    invalid_rec = invalid[0]
    assert invalid_rec["record"]["stockCode"] == "BAD001"
    assert "violations" in invalid_rec
    assert len(invalid_rec["violations"]) > 0


def test_get_violations_summary():
    """Aggregate stats for logging / alerts."""
    records = [
        {"sp": -1.0, "pe_ttm": 5000.0},  # 2 violations
        {"sp": -2.0},  # 1 violation
        {"sp": 100.0},  # ok
    ]
    valid, invalid = validate_batch(records)
    summary = get_violations_summary(invalid)
    assert summary["total_records"] == 2
    assert summary["total_violations"] == 3
    assert "sp" in summary["by_field"]
    assert summary["by_field"]["sp"] == 2
    assert summary["by_field"]["pe_ttm"] == 1


def test_unknown_field_ignored():
    """Fields not in SANITY_RULES are not validated."""
    record = {"unknown_field": -999999, "sp": 100.0}
    assert validate_record(record) == []
