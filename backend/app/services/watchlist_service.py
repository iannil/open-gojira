"""Watchlist service — user-curated stock groups."""

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.watchlist import WatchlistGroup, WatchlistItem

logger = logging.getLogger(__name__)

DEFAULT_GROUP_NAME = "默认关注"


def get_or_create_default_group(db: Session) -> WatchlistGroup:
    group = db.query(WatchlistGroup).filter(WatchlistGroup.name == DEFAULT_GROUP_NAME).first()
    if group:
        return group
    group = WatchlistGroup(name=DEFAULT_GROUP_NAME, description="系统默认关注分组", sort_order=0)
    db.add(group)
    db.flush()
    db.refresh(group)
    return group


def list_groups(db: Session) -> list[WatchlistGroup]:
    return (
        db.query(WatchlistGroup)
        .order_by(WatchlistGroup.sort_order.asc(), WatchlistGroup.id.asc())
        .all()
    )


def create_group(db: Session, data: dict) -> WatchlistGroup:
    existing = db.query(WatchlistGroup).filter(WatchlistGroup.name == data["name"]).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Group {data['name']!r} already exists")
    group = WatchlistGroup(
        name=data["name"],
        description=data.get("description"),
        sort_order=data.get("sort_order", 0),
    )
    db.add(group)
    db.flush()
    db.refresh(group)
    return group


def update_group(db: Session, group_id: int, data: dict) -> WatchlistGroup:
    group = db.query(WatchlistGroup).filter(WatchlistGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    for key in ("name", "description", "sort_order"):
        if data.get(key) is not None:
            setattr(group, key, data[key])
    db.flush()
    db.refresh(group)
    return group


def delete_group(db: Session, group_id: int) -> bool:
    group = db.query(WatchlistGroup).filter(WatchlistGroup.id == group_id).first()
    if not group:
        return False
    db.delete(group)
    db.flush()
    return True


def _verify_stock(db: Session, stock_code: str) -> None:
    if not db.query(Stock).filter(Stock.code == stock_code).first():
        raise HTTPException(status_code=404, detail=f"Stock {stock_code} not found")


def add_item(db: Session, group_id: int, data: dict) -> WatchlistItem:
    if not db.query(WatchlistGroup).filter(WatchlistGroup.id == group_id).first():
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    _verify_stock(db, data["stock_code"])
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.group_id == group_id, WatchlistItem.stock_code == data["stock_code"])
        .first()
    )
    if existing:
        return existing
    item = WatchlistItem(
        group_id=group_id,
        stock_code=data["stock_code"],
        note=data.get("note"),
    )
    db.add(item)
    db.flush()
    db.refresh(item)
    return item


def bulk_add_items(db: Session, group_id: int, stock_codes: list[str]) -> int:
    if not db.query(WatchlistGroup).filter(WatchlistGroup.id == group_id).first():
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    existing_codes = {
        row[0]
        for row in db.query(WatchlistItem.stock_code).filter(WatchlistItem.group_id == group_id).all()
    }
    valid_codes = {
        row[0]
        for row in db.query(Stock.code).filter(Stock.code.in_(stock_codes)).all()
    }
    added = 0
    for code in stock_codes:
        if code in existing_codes or code not in valid_codes:
            continue
        db.add(WatchlistItem(group_id=group_id, stock_code=code))
        added += 1
    db.flush()
    return added


def update_item(db: Session, item_id: int, data: dict) -> WatchlistItem:
    item = db.query(WatchlistItem).filter(WatchlistItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    # Use sentinel-aware update so clients can clear thresholds with explicit null.
    for key in ("note",):
        if key in data:
            setattr(item, key, data[key])
    db.flush()
    db.refresh(item)
    return item


def remove_item(db: Session, item_id: int) -> bool:
    item = db.query(WatchlistItem).filter(WatchlistItem.id == item_id).first()
    if not item:
        return False
    db.delete(item)
    db.flush()
    return True


def all_watched_codes(db: Session) -> list[str]:
    """Return distinct stock codes across all watchlist groups."""
    rows = db.query(WatchlistItem.stock_code).distinct().all()
    return [r[0] for r in rows]


def item_to_response(item: WatchlistItem, stock_name: Optional[str] = None) -> dict:
    return {
        "id": item.id,
        "group_id": item.group_id,
        "stock_code": item.stock_code,
        "stock_name": stock_name,
        "note": item.note,
        "added_at": str(item.added_at) if item.added_at else None,
    }


def group_to_response(db: Session, group: WatchlistGroup) -> dict:
    codes = [it.stock_code for it in group.items]
    name_map = (
        {row[0]: row[1] for row in db.query(Stock.code, Stock.name).filter(Stock.code.in_(codes)).all()}
        if codes
        else {}
    )
    items = [item_to_response(it, name_map.get(it.stock_code)) for it in group.items]
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "sort_order": group.sort_order,
        "items": items,
        "created_at": str(group.created_at) if group.created_at else None,
    }
