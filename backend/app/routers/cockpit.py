"""Single aggregator endpoint that feeds the Cockpit main dashboard."""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.research_claim_variable import ResearchClaimVariable
from app.schemas.cockpit import CockpitResponse
from app.schemas.research import CockpitClaimVariablesPending
from app.services import cockpit_service

router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])


@router.get("", response_model=CockpitResponse)
def get_cockpit(db: Session = Depends(get_db)) -> CockpitResponse:
    return cockpit_service.build(db)


@router.get(
    "/claim-variables-pending",
    response_model=CockpitClaimVariablesPending,
)
def get_claim_variables_pending(db: Session = Depends(get_db)):
    """v2 Q-new: Cockpit badge — proposed count + last proposal status.

    Frontend polls this every 30s via TanStack Query refetchInterval.
    """
    proposed_rows = db.execute(
        select(ResearchClaimVariable.stock_code).where(
            ResearchClaimVariable.status == "proposed"
        )
    ).scalars().all()

    counter = Counter(proposed_rows)
    by_stock = sorted(
        ({"stock_code": code, "count": cnt} for code, cnt in counter.items()),
        key=lambda d: (-d["count"], d["stock_code"]),
    )

    # Last proposal audit row (success / partial / failed)
    last_audit = db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "research_run",
            AuditLog.event.in_([
                "claim_variable_proposed",
                "claim_variable_proposal_partial",
                "claim_variable_proposal_failed",
            ]),
        ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1)
    ).scalar_one_or_none()

    last_proposal = None
    if last_audit:
        if last_audit.event == "claim_variable_proposal_failed":
            status = "failed"
        elif last_audit.event == "claim_variable_proposal_partial":
            status = "partial"
        else:
            status = "ok"
        last_proposal = {
            "status": status,
            "run_id": int(last_audit.entity_id) if last_audit.entity_id else None,
            "at": last_audit.created_at.isoformat() if last_audit.created_at else None,
            "summary": last_audit.summary,
        }

    return CockpitClaimVariablesPending(
        count=len(proposed_rows),
        by_stock=by_stock,
        last_proposal=last_proposal,
    )
