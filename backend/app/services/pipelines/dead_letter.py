"""Dead letter queue — persistent storage for failed sync items with retry support."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.models.pipeline import DeadLetterRecord
from app.services.pipelines.base import ErrorType

logger = logging.getLogger(__name__)


class DeadLetterQueue:
    """Manages failed sync records for later retry or analysis."""

    @staticmethod
    def push(
        db: Session,
        pipeline_run_id: str,
        pipeline_type: str,
        stock_code: str,
        error_type: ErrorType,
        error_message: str,
        payload: dict | None = None,
        max_retries: int = 3,
    ) -> DeadLetterRecord:
        record = DeadLetterRecord(
            pipeline_run_id=pipeline_run_id,
            pipeline_type=pipeline_type,
            stock_code=stock_code,
            error_type=error_type.value,
            error_message=error_message[:2000] if error_message else None,
            payload=json.dumps(payload) if payload else None,
            max_retries=max_retries,
            status="pending",
        )
        db.add(record)
        db.commit()
        return record

    @staticmethod
    def get_pending(
        db: Session,
        pipeline_type: str | None = None,
        limit: int = 100,
    ) -> list[DeadLetterRecord]:
        q = db.query(DeadLetterRecord).filter(
            DeadLetterRecord.status.in_(["pending", "retrying"]),
            DeadLetterRecord.retry_count < DeadLetterRecord.max_retries,
        )
        if pipeline_type:
            q = q.filter(DeadLetterRecord.pipeline_type == pipeline_type)
        return q.order_by(DeadLetterRecord.created_at.asc()).limit(limit).all()

    @staticmethod
    def get_exhausted(
        db: Session,
        pipeline_type: str | None = None,
        limit: int = 100,
    ) -> list[DeadLetterRecord]:
        q = db.query(DeadLetterRecord).filter(DeadLetterRecord.status == "exhausted")
        if pipeline_type:
            q = q.filter(DeadLetterRecord.pipeline_type == pipeline_type)
        return q.order_by(DeadLetterRecord.created_at.desc()).limit(limit).all()

    @staticmethod
    def mark_retrying(db: Session, record_id: int) -> None:
        r = db.get(DeadLetterRecord, record_id)
        if r:
            r.retry_count += 1
            r.last_retry_at = utcnow()
            if r.retry_count >= r.max_retries:
                r.status = "exhausted"
            else:
                r.status = "retrying"
            db.commit()

    @staticmethod
    def mark_resolved(db: Session, record_id: int) -> None:
        r = db.get(DeadLetterRecord, record_id)
        if r:
            r.status = "resolved"
            db.commit()

    @staticmethod
    def mark_retry_attempt(db: Session, record: DeadLetterRecord, success: bool) -> None:
        if success:
            record.status = "resolved"
        else:
            record.retry_count += 1
            record.last_retry_at = utcnow()
            if record.retry_count >= record.max_retries:
                record.status = "exhausted"
            else:
                record.status = "pending"
        db.commit()

    @staticmethod
    def get_stats(db: Session, pipeline_type: str | None = None) -> dict:
        q = db.query(DeadLetterRecord)
        if pipeline_type:
            q = q.filter(DeadLetterRecord.pipeline_type == pipeline_type)
        records = q.all()
        return {
            "total": len(records),
            "pending": sum(1 for r in records if r.status == "pending"),
            "retrying": sum(1 for r in records if r.status == "retrying"),
            "exhausted": sum(1 for r in records if r.status == "exhausted"),
            "resolved": sum(1 for r in records if r.status == "resolved"),
        }
