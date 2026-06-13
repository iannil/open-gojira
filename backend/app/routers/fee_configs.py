"""BrokerFeeConfig API — CRUD for historical fee rates."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.broker_fee_config import BrokerFeeConfig
from app.schemas.fee_config import (
    BrokerFeeConfigCreate,
    BrokerFeeConfigResponse,
    BrokerFeeConfigUpdate,
)

router = APIRouter(prefix="/api/fee-configs", tags=["fee-configs"])


@router.get("", response_model=list[BrokerFeeConfigResponse])
def list_configs(
    broker_name: str | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
):
    """List fee configs, newest effective_from first."""
    stmt = select(BrokerFeeConfig).order_by(
        desc(BrokerFeeConfig.effective_from), desc(BrokerFeeConfig.id)
    )
    if broker_name:
        stmt = stmt.where(BrokerFeeConfig.broker_name == broker_name)
    if is_active is not None:
        stmt = stmt.where(BrokerFeeConfig.is_active == is_active)
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=BrokerFeeConfigResponse, status_code=201)
def create_config(payload: BrokerFeeConfigCreate, db: Session = Depends(get_db)):
    cfg = BrokerFeeConfig(**payload.model_dump())
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.patch("/{config_id}", response_model=BrokerFeeConfigResponse)
def update_config(
    config_id: int,
    payload: BrokerFeeConfigUpdate,
    db: Session = Depends(get_db),
):
    cfg = db.get(BrokerFeeConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Config {config_id} not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(cfg, key, value)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.delete("/{config_id}", status_code=204)
def delete_config(config_id: int, db: Session = Depends(get_db)):
    cfg = db.get(BrokerFeeConfig, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Config {config_id} not found")
    db.delete(cfg)
    db.commit()
