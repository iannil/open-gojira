"""Notifications API — v2 stub.

v2 (2026-06-24): notification channels removed (v2 uses in-app only per
decision 19). Will be replaced by simpler in-app notification system.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/channels")
def list_channels() -> dict:
    """v2 stub: in-app notifications only."""
    return {"channels": [], "message": "v2: in-app notifications only"}


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
