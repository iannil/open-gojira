"""Checkpoint manager — persistent sync progress for resume-after-crash."""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.models.pipeline import PipelineCheckpoint


class CheckpointManager:
    """Reads and writes per-stock sync checkpoints."""

    @staticmethod
    def get(db: Session, pipeline_type: str, stock_code: str) -> PipelineCheckpoint | None:
        return (
            db.query(PipelineCheckpoint)
            .filter(
                PipelineCheckpoint.pipeline_type == pipeline_type,
                PipelineCheckpoint.stock_code == stock_code,
            )
            .first()
        )

    @staticmethod
    def get_last_date(db: Session, pipeline_type: str, stock_code: str) -> date | None:
        cp = CheckpointManager.get(db, pipeline_type, stock_code)
        return cp.last_sync_date if cp else None

    @staticmethod
    def save(
        db: Session,
        pipeline_type: str,
        stock_code: str,
        last_sync_date: date,
        sync_version: int = 0,
    ) -> PipelineCheckpoint:
        cp = CheckpointManager.get(db, pipeline_type, stock_code)
        if cp:
            cp.last_sync_date = last_sync_date
            cp.sync_version = sync_version
            cp.updated_at = utcnow()
        else:
            cp = PipelineCheckpoint(
                pipeline_type=pipeline_type,
                stock_code=stock_code,
                last_sync_date=last_sync_date,
                sync_version=sync_version,
            )
            db.add(cp)
        db.commit()
        return cp

    @staticmethod
    def get_pending_codes(
        db: Session, pipeline_type: str, all_codes: list[str]
    ) -> list[str]:
        """Return codes that have no checkpoint yet (never synced)."""
        synced = {
            r[0]
            for r in db.query(PipelineCheckpoint.stock_code)
            .filter(PipelineCheckpoint.pipeline_type == pipeline_type)
            .all()
        }
        return [c for c in all_codes if c not in synced]

    @staticmethod
    def reset(db: Session, pipeline_type: str, stock_code: str | None = None) -> int:
        """Reset checkpoints. If stock_code is None, reset all for the type."""
        q = db.query(PipelineCheckpoint).filter(
            PipelineCheckpoint.pipeline_type == pipeline_type
        )
        if stock_code:
            q = q.filter(PipelineCheckpoint.stock_code == stock_code)
        count = q.delete(synchronize_session="fetch")
        db.commit()
        return count
