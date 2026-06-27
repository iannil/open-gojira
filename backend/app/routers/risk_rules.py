"""Holding risk rules API — v2 stub.

v2 (decision 19): holding risk-rules (stop-loss/take-profit) removed per
redesign. Will be re-added when feature is redesigned. Currently returns
empty array for list endpoint and 404 for individual operations.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/risk-rules", tags=["risk-rules"])


@router.get("", response_model=list)
def list_rules() -> list:
    """v2 stub: no risk rules in v2 yet."""
    return []


@router.get("/{code}", response_model=dict | None)
def get_rule(code: str) -> None:
    """v2 stub: individual risk rule not available."""
    return None


@router.post("", status_code=201)
def create_rule() -> dict:
    """v2 stub: risk rules not available."""
    return {"message": "v2: risk rules not available"}


@router.patch("/{rule_id}")
def update_rule(rule_id: int) -> dict:
    """v2 stub: risk rules not available."""
    return {"message": "v2: risk rules not available"}


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int) -> None:
    """v2 stub: risk rules not available."""
    return None
