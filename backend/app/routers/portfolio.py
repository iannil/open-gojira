"""Portfolio (holdings) CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import OkResponse
from app.schemas.holding import (
    HoldingCreate,
    HoldingResponse,
    HoldingUpdate,
    PortfolioSummary,
    SellRequest,
)
from app.services.holding_service import (
    _holding_to_dict,
    create_holding,
    delete_holding,
    get_holding,
    get_portfolio_summary,
    list_holdings,
    sell_holding,
    update_holding,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.post("", response_model=HoldingResponse, status_code=201)
def create(payload: HoldingCreate, force: bool = False, db: Session = Depends(get_db)):
    holding = create_holding(db, payload.model_dump(), force=force)
    return _holding_to_dict(holding, db)


@router.get("/summary", response_model=PortfolioSummary)
def summary(db: Session = Depends(get_db)):
    return get_portfolio_summary(db)


@router.get("", response_model=list[HoldingResponse])
def list_all(active_only: bool = False, db: Session = Depends(get_db)):
    holdings = list_holdings(db, active_only=active_only)
    return [_holding_to_dict(h, db) for h in holdings]


@router.get("/{holding_id}", response_model=HoldingResponse)
def get(holding_id: int, db: Session = Depends(get_db)):
    holding = get_holding(db, holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail=f"Holding {holding_id} not found")
    return _holding_to_dict(holding, db)


@router.put("/{holding_id}", response_model=HoldingResponse)
def update(holding_id: int, payload: HoldingUpdate, db: Session = Depends(get_db)):
    holding = update_holding(db, holding_id, payload.model_dump(exclude_unset=True))
    if not holding:
        raise HTTPException(status_code=404, detail=f"Holding {holding_id} not found")
    return _holding_to_dict(holding, db)


@router.delete("/{holding_id}", response_model=OkResponse)
def delete(holding_id: int, db: Session = Depends(get_db)):
    ok = delete_holding(db, holding_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Holding {holding_id} not found")
    return {"ok": True}


@router.post("/{holding_id}/sell", response_model=HoldingResponse)
def sell(holding_id: int, payload: SellRequest, db: Session = Depends(get_db)):
    holding = sell_holding(
        db,
        holding_id,
        sell_date=payload.sell_date,
        sell_price=payload.sell_price,
        sell_thesis=payload.sell_thesis,
    )
    if not holding:
        raise HTTPException(status_code=404, detail=f"Holding {holding_id} not found")
    return _holding_to_dict(holding, db)
