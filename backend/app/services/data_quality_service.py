"""Data quality service — computes completeness, gaps, anomalies, and validation rates."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.models.dividend import DividendRecord
from app.models.financial import FinancialStatement
from app.models.pipeline import DeadLetterRecord, PipelineRun
from app.models.price_kline import PriceKline
from app.models.valuation import ValuationSnapshot
from app.schemas.data_quality import (
    DataQualityResponse,
    DataTypeQuality,
    DataTypeQualityDetails,
)

logger = logging.getLogger(__name__)

# Freshness thresholds (days)
_FRESHNESS_THRESHOLDS: dict[str, int] = {
    "valuations": 1,
    "klines": 3,
    "financials": 90,
    "dividends": 365,
}

_STALE_THRESHOLDS: dict[str, int] = {
    "valuations": 7,
    "klines": 7,
    "financials": 180,
    "dividends": 730,
}

# Map pipeline_type to (model, date_column attribute name, stock_code column)
_DATA_TYPE_CONFIG: dict[str, dict] = {
    "valuations": {
        "model": ValuationSnapshot,
        "date_col": "date",
        "code_col": "stock_code",
    },
    "klines": {
        "model": PriceKline,
        "date_col": "date",
        "code_col": "stock_code",
    },
    "financials": {
        "model": FinancialStatement,
        "date_col": "report_date",
        "code_col": "stock_code",
    },
    "dividends": {
        "model": DividendRecord,
        "date_col": "ex_date",
        "code_col": "stock_code",
    },
}


def _get_pool_codes(db: Session) -> set[str]:
    """Get all watched + held stock codes."""
    from app.services.data_management_service import get_watched_stock_codes
    return get_watched_stock_codes(db)


def _compute_freshness(latest_date: date | None, dtype: str) -> str:
    if latest_date is None:
        return "missing"
    today = utcnow().date()
    days_diff = (today - latest_date).days
    if days_diff <= _FRESHNESS_THRESHOLDS.get(dtype, 365):
        return "fresh"
    if days_diff <= _STALE_THRESHOLDS.get(dtype, 730):
        return "stale"
    return "missing"


def _detect_gaps(db: Session, model, date_col: str, code_col: str, pool_codes: set[str]) -> int:
    """Count per-stock trading-day gaps using SQL aggregation.

    For each pool stock, count how many of the union-of-all-trading-dates
    are missing from that stock.  gap = sum_stocks(total_dates - stock_dates).
    """
    if not pool_codes:
        return 0

    col = getattr(model, date_col)
    code = getattr(model, code_col)

    # Total distinct trading dates across the entire pool
    total_dates = (
        db.query(sa_func.count(sa_func.distinct(col)))
        .filter(code.in_(pool_codes))
        .scalar()
    ) or 0

    if total_dates == 0:
        return 0

    # Per-stock date count
    per_stock = (
        db.query(code.label("c"), sa_func.count(sa_func.distinct(col)).label("cnt"))
        .filter(code.in_(pool_codes))
        .group_by(code)
        .all()
    )

    total_gap = sum(total_dates - row.cnt for row in per_stock)
    return max(total_gap, 0)


def _get_anomaly_count(db: Session, pipeline_type: str) -> int:
    """Count DATA_ANOMALY type errors from dead letter queue."""
    return db.query(DeadLetterRecord).filter(
        DeadLetterRecord.pipeline_type == pipeline_type,
        DeadLetterRecord.error_type == "DATA_ANOMALY",
    ).count()


def _get_validation_pass_rate(db: Session, pipeline_type: str) -> float:
    """Compute validation pass rate from recent pipeline runs."""
    runs = db.query(PipelineRun).filter(
        PipelineRun.pipeline_type == pipeline_type,
        PipelineRun.status.in_(["completed", "completed_with_errors", "failed"]),
    ).order_by(PipelineRun.created_at.desc()).limit(5).all()

    if not runs:
        return 0.0

    total_items = sum(r.total_items for r in runs)
    completed_items = sum(r.completed_items for r in runs)

    if total_items == 0:
        return 0.0

    return round(completed_items / total_items, 4)


def compute_quality(db: Session) -> DataQualityResponse:
    """Compute comprehensive data quality metrics."""
    pool_codes = _get_pool_codes(db)
    total_stocks = len(pool_codes)

    if total_stocks == 0:
        return DataQualityResponse(
            overall_score=0,
            data_types={},
            recommendations=["股票池为空，请先添加股票"],
        )

    data_types: dict[str, DataTypeQuality] = {}
    scores: list[float] = []
    recommendations: list[str] = []

    for dtype, cfg in _DATA_TYPE_CONFIG.items():
        model = cfg["model"]
        date_col = cfg["date_col"]
        code_col = cfg["code_col"]
        col = getattr(model, date_col)
        code = getattr(model, code_col)

        # Basic stats
        row = db.query(
            sa_func.count(model.id).label("records"),
            sa_func.count(sa_func.distinct(code)).label("covered"),
            sa_func.max(col).label("latest"),
            sa_func.min(col).label("earliest"),
        ).filter(code.in_(pool_codes)).first()

        covered = row.covered or 0 if row else 0
        latest_raw = row.latest if row else None
        earliest_raw = row.earliest if row else None

        latest_date = None
        if latest_raw:
            latest_date = latest_raw if isinstance(latest_raw, date) else latest_raw.date()

        earliest_date = None
        if earliest_raw:
            earliest_date = earliest_raw if isinstance(earliest_raw, date) else earliest_raw.date()

        # Completeness rate
        completeness_rate = round(covered / total_stocks, 4) if total_stocks > 0 else 0.0

        # Freshness
        freshness = _compute_freshness(latest_date, dtype)

        # Gap detection (only for time-series types)
        gap_count = 0
        if dtype in ("valuations", "klines") and covered > 0:
            gap_count = _detect_gaps(db, model, date_col, code_col, pool_codes)

        # Anomaly count
        anomaly_count = _get_anomaly_count(db, dtype)

        # Validation pass rate
        validation_pass_rate = _get_validation_pass_rate(db, dtype)

        # Quality score for this data type (0-100)
        type_score = completeness_rate * 40
        type_score += (1.0 if freshness == "fresh" else 0.5 if freshness == "stale" else 0.0) * 30
        type_score += min(validation_pass_rate, 1.0) * 20
        type_score += max(0.0, 1.0 - (gap_count / max(total_stocks * 5, 1))) * 10
        scores.append(type_score)

        data_types[dtype] = DataTypeQuality(
            completeness_rate=completeness_rate,
            freshness=freshness,
            gap_count=gap_count,
            anomaly_count=anomaly_count,
            validation_pass_rate=validation_pass_rate,
            details=DataTypeQualityDetails(
                total_stocks=total_stocks,
                covered_stocks=covered,
                latest_date=str(latest_date) if latest_date else None,
                earliest_date=str(earliest_date) if earliest_date else None,
            ),
        )

        # Generate recommendations
        if completeness_rate < 1.0:
            missing_count = total_stocks - covered
            label = {"valuations": "估值", "financials": "财报", "klines": "K线", "dividends": "分红"}[dtype]
            recommendations.append(f"{missing_count} 只股票缺少{label}数据，建议同步")

        if freshness == "stale":
            label = {"valuations": "估值", "financials": "财报", "klines": "K线", "dividends": "分红"}[dtype]
            recommendations.append(f"{label}数据较旧，建议更新")

        if freshness == "missing":
            label = {"valuations": "估值", "financials": "财报", "klines": "K线", "dividends": "分红"}[dtype]
            recommendations.append(f"{label}数据缺失，请立即同步")

        if gap_count > total_stocks:
            label = {"valuations": "估值", "financials": "财报", "klines": "K线", "dividends": "分红"}[dtype]
            recommendations.append(f"{label}数据存在 {gap_count} 个交易日缺口，建议补齐")

        if anomaly_count > 0:
            label = {"valuations": "估值", "financials": "财报", "klines": "K线", "dividends": "分红"}[dtype]
            recommendations.append(f"{label}数据有 {anomaly_count} 条异常记录")

    overall_score = int(sum(scores) / len(scores)) if scores else 0

    return DataQualityResponse(
        overall_score=overall_score,
        data_types=data_types,
        recommendations=recommendations,
    )
