"""Watchlist endpoints — user-curated stock groups."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.watchlist import (
    WatchlistBulkAdd,
    WatchlistGroupCreate,
    WatchlistGroupResponse,
    WatchlistGroupUpdate,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistItemUpdate,
)
from app.schemas.common import AddedResponse, CodesResponse, OkResponse
from app.services import watchlist_service as svc

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("/groups", response_model=list[WatchlistGroupResponse])
def api_list_groups(db: Session = Depends(get_db)):
    if not svc.list_groups(db):
        svc.get_or_create_default_group(db)
    return [svc.group_to_response(db, g) for g in svc.list_groups(db)]


@router.post("/groups", response_model=WatchlistGroupResponse, status_code=201)
def api_create_group(payload: WatchlistGroupCreate, db: Session = Depends(get_db)):
    group = svc.create_group(db, payload.model_dump())
    return svc.group_to_response(db, group)


@router.put("/groups/{group_id}", response_model=WatchlistGroupResponse)
def api_update_group(group_id: int, payload: WatchlistGroupUpdate, db: Session = Depends(get_db)):
    group = svc.update_group(db, group_id, payload.model_dump(exclude_unset=True))
    return svc.group_to_response(db, group)


@router.delete("/groups/{group_id}", response_model=OkResponse)
def api_delete_group(group_id: int, db: Session = Depends(get_db)):
    if not svc.delete_group(db, group_id):
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    return {"ok": True}


@router.post("/groups/{group_id}/items", response_model=WatchlistItemResponse, status_code=201)
def api_add_item(group_id: int, payload: WatchlistItemCreate, db: Session = Depends(get_db)):
    item = svc.add_item(db, group_id, payload.model_dump())
    name = None
    if item.stock_code:
        from app.models.stock import Stock

        s = db.query(Stock).filter(Stock.code == item.stock_code).first()
        name = s.name if s else None
    return svc.item_to_response(item, name)


@router.post("/groups/{group_id}/items/bulk", response_model=AddedResponse)
def api_bulk_add(group_id: int, payload: WatchlistBulkAdd, db: Session = Depends(get_db)):
    if payload.group_id != group_id:
        raise HTTPException(status_code=400, detail="group_id mismatch")
    added = svc.bulk_add_items(db, group_id, payload.stock_codes)
    return {"added": added}


@router.put("/items/{item_id}", response_model=WatchlistItemResponse)
def api_update_item(item_id: int, payload: WatchlistItemUpdate, db: Session = Depends(get_db)):
    item = svc.update_item(db, item_id, payload.model_dump(exclude_unset=True))
    return svc.item_to_response(item)


@router.delete("/items/{item_id}", response_model=OkResponse)
def api_remove_item(item_id: int, db: Session = Depends(get_db)):
    if not svc.remove_item(db, item_id):
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return {"ok": True}


@router.get("/codes", response_model=CodesResponse)
def api_all_codes(db: Session = Depends(get_db)):
    """Distinct stock codes across all groups (used by scheduler/engine)."""
    return {"codes": svc.all_watched_codes(db)}
