# 基础数据管理功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the existing DataSyncPage into two independent pages: "数据管理" (data management with stock pool CRUD, data sync, cleanup) and "定时任务" (scheduler job management).

**Architecture:** New backend router + service layer aggregate existing sync services. Frontend splits into two lazy-loaded page components. Stock pool management reuses watchlist service. Data cleanup adds new service methods over existing models.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, React 19, Ant Design, TypeScript

---

## Task 1: Backend — Data Management Schemas

**Files:**
- Create: `backend/app/schemas/data_management.py`

- [ ] **Step 1: Create the schema file**

```python
"""Schemas for data management endpoints."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Stock search & pool ──────────────────────────────────────────────────

class StockSearchResult(BaseModel):
    code: str
    name: str
    industry: Optional[str] = None
    listed_date: Optional[str] = None


class StockPoolAddRequest(BaseModel):
    stock_codes: list[str] = Field(..., min_length=1)


class StockPoolRemoveRequest(BaseModel):
    stock_codes: list[str] = Field(..., min_length=1)


class StockPoolItem(BaseModel):
    code: str
    name: str
    industry: Optional[str] = None
    tier: Optional[str] = None
    security_theme: Optional[str] = None
    added_at: Optional[str] = None
    data_completeness: "DataCompleteness"


class DataCompleteness(BaseModel):
    has_valuation: bool = False
    has_financial: bool = False
    has_kline: bool = False
    has_dividend: bool = False


# ── Data status overview ─────────────────────────────────────────────────

class DataStatusOverview(BaseModel):
    valuations: "DataTypeStatus"
    financials: "DataTypeStatus"
    klines: "DataTypeStatus"
    dividends: "DataTypeStatus"


class DataTypeStatus(BaseModel):
    total_records: int = 0
    stock_count: int = 0
    latest_date: Optional[str] = None
    earliest_date: Optional[str] = None


# ── Sync trigger ─────────────────────────────────────────────────────────

class SyncTriggerRequest(BaseModel):
    stock_codes: Optional[list[str]] = None  # None = all watched stocks
    years: int = 5


class SyncTriggerResponse(BaseModel):
    task_id: str
    data_type: str
    stock_count: int
    message: str


class SyncTaskStatus(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed
    progress: int = 0  # percentage
    total: int = 0
    completed_items: int = 0
    message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


# ── Data cleanup ─────────────────────────────────────────────────────────

class CleanupRequest(BaseModel):
    stock_codes: Optional[list[str]] = None  # None = all
    before_date: Optional[str] = None
    after_date: Optional[str] = None


class CleanupPreview(BaseModel):
    data_type: str
    record_count: int
    date_range: Optional[str] = None


class CleanupResult(BaseModel):
    data_type: str
    deleted_count: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/data_management.py
git commit -m "feat: add data management schemas"
```

---

## Task 2: Backend — Data Management Service

**Files:**
- Create: `backend/app/services/data_management_service.py`

- [ ] **Step 1: Create the service file**

```python
"""Data management service — aggregates existing sync services."""

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.dividend import DividendRecord
from app.models.financial import FinancialStatement
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.models.watchlist import WatchlistItem

logger = logging.getLogger(__name__)

# In-memory task tracking for sync operations
_sync_tasks: dict[str, dict] = {}


def get_watched_stock_codes(db: Session) -> set[str]:
    """Get all watched + held stock codes."""
    from app.models.holding import Holding
    held = {r[0] for r in db.query(Holding.stock_code).filter(Holding.sell_date.is_(None)).all()}
    watched = {r[0] for r in db.query(WatchlistItem.stock_code).distinct().all()}
    return held | watched


def list_stock_pool(db: Session) -> list[dict]:
    """List all stocks in the pool with data completeness info."""
    all_codes = get_watched_stock_codes(db)
    if not all_codes:
        return []

    stocks = db.query(Stock).filter(Stock.code.in_(all_codes)).all()
    stock_map = {s.code: s for s in stocks}

    # Batch query completeness
    val_codes = {r[0] for r in db.query(ValuationSnapshot.stock_code).filter(
        ValuationSnapshot.stock_code.in_(all_codes)
    ).distinct().all()}

    fin_codes = {r[0] for r in db.query(FinancialStatement.stock_code).filter(
        FinancialStatement.stock_code.in_(all_codes)
    ).distinct().all()}

    kline_codes = {r[0] for r in db.query(PriceKline.stock_code).filter(
        PriceKline.stock_code.in_(all_codes)
    ).distinct().all()}

    div_codes = {r[0] for r in db.query(DividendRecord.stock_code).filter(
        DividendRecord.stock_code.in_(all_codes)
    ).distinct().all()}

    # Watchlist added_at
    added_at_map = {}
    items = db.query(WatchlistItem).filter(WatchlistItem.stock_code.in_(all_codes)).all()
    for item in items:
        if item.stock_code not in added_at_map or (item.added_at and added_at_map.get(item.stock_code) is None):
            added_at_map[item.stock_code] = str(item.added_at) if item.added_at else None

    result = []
    for code in sorted(all_codes):
        s = stock_map.get(code)
        if not s:
            continue
        result.append({
            "code": code,
            "name": s.name,
            "industry": s.industry,
            "tier": s.tier,
            "security_theme": s.security_theme,
            "added_at": added_at_map.get(code),
            "data_completeness": {
                "has_valuation": code in val_codes,
                "has_financial": code in fin_codes,
                "has_kline": code in kline_codes,
                "has_dividend": code in div_codes,
            },
        })
    return result


def search_stocks(db: Session, keyword: str) -> list[dict]:
    """Search stocks by code or name."""
    if not keyword or len(keyword.strip()) < 1:
        return []
    kw = keyword.strip()
    query = db.query(Stock).filter(
        (Stock.code.ilike(f"%{kw}%")) | (Stock.name.ilike(f"%{kw}%"))
    ).limit(20)
    return [
        {
            "code": s.code,
            "name": s.name,
            "industry": s.industry,
            "listed_date": str(s.listed_date) if s.listed_date else None,
        }
        for s in query.all()
    ]


def add_to_pool(db: Session, stock_codes: list[str]) -> int:
    """Add stocks to the default watchlist group."""
    from app.services import watchlist_service as svc
    group = svc.get_or_create_default_group(db)
    return svc.bulk_add_items(db, group.id, stock_codes)


def remove_from_pool(db: Session, stock_codes: list[str]) -> int:
    """Remove stocks from all watchlist groups."""
    items = db.query(WatchlistItem).filter(
        WatchlistItem.stock_code.in_(stock_codes)
    ).all()
    count = len(items)
    for item in items:
        db.delete(item)
    db.commit()
    return count


def get_data_status(db: Session) -> dict:
    """Get aggregated data status for all data types."""
    watched_codes = get_watched_stock_codes(db)
    all_codes = watched_codes if watched_codes else set()

    def _status(model, date_col, code_filter=None) -> dict:
        q = db.query(
            sa_func.count(model.id).label("total"),
            sa_func.count(sa_func.distinct(getattr(model, "stock_code", None))).label("stocks"),
            sa_func.max(date_col).label("latest"),
            sa_func.min(date_col).label("earliest"),
        )
        if code_filter and all_codes:
            q = q.filter(getattr(model, "stock_code").in_(all_codes))
        row = q.first()
        return {
            "total_records": row.total or 0,
            "stock_count": row.stocks or 0,
            "latest_date": str(row.latest) if row.latest else None,
            "earliest_date": str(row.earliest) if row.earliest else None,
        }

    return {
        "valuations": _status(ValuationSnapshot, ValuationSnapshot.date, True),
        "financials": _status(FinancialStatement, FinancialStatement.report_date, True),
        "klines": _status(PriceKline, PriceKline.date, True),
        "dividends": _status(DividendRecord, DividendRecord.ex_date, True),
    }


def trigger_sync(db: Session, data_type: str, stock_codes: list[str] | None = None, years: int = 5) -> dict:
    """Trigger a sync operation. Returns task info immediately."""
    codes = stock_codes or list(get_watched_stock_codes(db))
    if not codes:
        raise ValueError("No stocks to sync")

    task_id = str(uuid.uuid4())[:8]
    task = {
        "task_id": task_id,
        "data_type": data_type,
        "status": "pending",
        "progress": 0,
        "total": len(codes),
        "completed_items": 0,
        "message": "Queued",
        "started_at": None,
        "finished_at": None,
        "stock_codes": codes,
        "years": years,
    }
    _sync_tasks[task_id] = task

    # Execute synchronously for now (simple approach)
    _execute_sync(db, task_id, data_type, codes, years)

    return {
        "task_id": task_id,
        "data_type": data_type,
        "stock_count": len(codes),
        "message": f"Syncing {len(codes)} stocks for {data_type}",
    }


def _execute_sync(db: Session, task_id: str, data_type: str, codes: list[str], years: int):
    """Execute the actual sync operation."""
    task = _sync_tasks[task_id]
    task["status"] = "running"
    task["started_at"] = datetime.utcnow().isoformat()
    errors = []

    for i, code in enumerate(codes):
        try:
            if data_type == "financials":
                from app.services.financial_service import fetch_and_store_financials
                fetch_and_store_financials(db, code, years=years)
            elif data_type == "klines":
                from app.services.kline_service import get_klines
                end = date.today()
                start = end - timedelta(days=years * 365)
                get_klines(db, code, start=start, end=end)
            elif data_type == "dividends":
                from app.services.dividend_service import fetch_and_store_from_lixinger
                fetch_and_store_from_lixinger(db, code)
            elif data_type == "valuations":
                from app.services.lixinger_client import get_lixinger_client
                client = get_lixinger_client()
                from app.services.data_service import fetch_stock_info
                info = fetch_stock_info(code)
                if info:
                    stock = db.query(Stock).filter(Stock.code == code).first()
                    if stock:
                        pass  # Valuation snapshots are handled by daily_snapshot job
        except Exception as e:
            logger.warning("Sync failed for %s/%s: %s", data_type, code, e)
            errors.append(f"{code}: {e}")

        task["completed_items"] = i + 1
        task["progress"] = int((i + 1) / len(codes) * 100)

    task["status"] = "completed" if not errors else "completed_with_errors"
    task["finished_at"] = datetime.utcnow().isoformat()
    task["message"] = f"Done. {len(errors)} errors." if errors else "Completed"


def get_sync_status(task_id: str) -> dict | None:
    """Get sync task status."""
    task = _sync_tasks.get(task_id)
    if not task:
        return None
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "progress": task["progress"],
        "total": task["total"],
        "completed_items": task["completed_items"],
        "message": task["message"],
        "started_at": task["started_at"],
        "finished_at": task["finished_at"],
    }


def preview_cleanup(db: Session, data_type: str, before_date: str | None = None, after_date: str | None = None, stock_codes: list[str] | None = None) -> dict:
    """Preview how many records would be deleted."""
    model_map = {
        "valuations": (ValuationSnapshot, ValuationSnapshot.date),
        "financials": (FinancialStatement, FinancialStatement.report_date),
        "klines": (PriceKline, PriceKline.date),
        "dividends": (DividendRecord, DividendRecord.ex_date),
    }
    if data_type not in model_map:
        raise ValueError(f"Unknown data type: {data_type}")

    model, date_col = model_map[data_type]
    q = db.query(sa_func.count(model.id))

    if stock_codes:
        q = q.filter(model.stock_code.in_(stock_codes))
    if before_date:
        q = q.filter(date_col < before_date)
    if after_date:
        q = q.filter(date_col > after_date)

    count = q.scalar() or 0
    return {
        "data_type": data_type,
        "record_count": count,
    }


def execute_cleanup(db: Session, data_type: str, before_date: str | None = None, after_date: str | None = None, stock_codes: list[str] | None = None) -> dict:
    """Delete records by criteria."""
    model_map = {
        "valuations": (ValuationSnapshot, ValuationSnapshot.date),
        "financials": (FinancialStatement, FinancialStatement.report_date),
        "klines": (PriceKline, PriceKline.date),
        "dividends": (DividendRecord, DividendRecord.ex_date),
    }
    if data_type not in model_map:
        raise ValueError(f"Unknown data type: {data_type}")

    model, date_col = model_map[data_type]
    q = db.query(model)

    if stock_codes:
        q = q.filter(model.stock_code.in_(stock_codes))
    if before_date:
        q = q.filter(date_col < before_date)
    if after_date:
        q = q.filter(date_col > after_date)

    count = q.delete(synchronize_session="fetch")
    db.commit()
    return {
        "data_type": data_type,
        "deleted_count": count,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/data_management_service.py
git commit -m "feat: add data management service"
```

---

## Task 3: Backend — Data Management Router

**Files:**
- Create: `backend/app/routers/data_management.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the router file**

```python
"""Data management endpoints — stock pool, sync, cleanup."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.data_management import (
    CleanupPreview,
    CleanupRequest,
    CleanupResult,
    DataStatusOverview,
    StockPoolAddRequest,
    StockPoolItem,
    StockPoolRemoveRequest,
    StockSearchResult,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from app.services import data_management_service as svc

router = APIRouter(prefix="/api/data-management", tags=["data-management"])


# ── Stock Pool ───────────────────────────────────────────────────────────

@router.get("/universe", response_model=list[StockPoolItem])
def list_universe(db: Session = Depends(get_db)):
    return svc.list_stock_pool(db)


@router.post("/universe/search", response_model=list[StockSearchResult])
def search_stocks(keyword: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return svc.search_stocks(db, keyword)


@router.post("/universe/add")
def add_to_pool(payload: StockPoolAddRequest, db: Session = Depends(get_db)):
    added = svc.add_to_pool(db, payload.stock_codes)
    return {"added": added}


@router.post("/universe/batch-remove")
def batch_remove(payload: StockPoolRemoveRequest, db: Session = Depends(get_db)):
    removed = svc.remove_from_pool(db, payload.stock_codes)
    return {"removed": removed}


# ── Data Status ──────────────────────────────────────────────────────────

@router.get("/status", response_model=DataStatusOverview)
def get_status(db: Session = Depends(get_db)):
    return svc.get_data_status(db)


# ── Sync ─────────────────────────────────────────────────────────────────

@router.post("/sync/{data_type}", response_model=SyncTriggerResponse)
def trigger_sync(data_type: str, payload: SyncTriggerRequest, db: Session = Depends(get_db)):
    valid_types = {"valuations", "financials", "klines", "dividends"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Must be one of: {valid_types}")
    try:
        return svc.trigger_sync(db, data_type, payload.stock_codes, payload.years)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sync/{task_id}/status")
def get_sync_status(task_id: str):
    result = svc.get_sync_status(task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return result


# ── Cleanup ──────────────────────────────────────────────────────────────

@router.get("/cleanup/{data_type}/preview", response_model=CleanupPreview)
def preview_cleanup(
    data_type: str,
    before_date: str | None = None,
    after_date: str | None = None,
    stock_codes: list[str] | None = Query(None),
    db: Session = Depends(get_db),
):
    valid_types = {"valuations", "financials", "klines", "dividends"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Must be one of: {valid_types}")
    return svc.preview_cleanup(db, data_type, before_date, after_date, stock_codes)


@router.post("/cleanup/{data_type}", response_model=CleanupResult)
def execute_cleanup(data_type: str, payload: CleanupRequest, db: Session = Depends(get_db)):
    valid_types = {"valuations", "financials", "klines", "dividends"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Must be one of: {valid_types}")
    return svc.execute_cleanup(db, data_type, payload.before_date, payload.after_date, payload.stock_codes)
```

- [ ] **Step 2: Register router in main.py**

Add import for the new router in `backend/app/main.py`:

In the import block (line ~21-29), add `data_management` to the imports:
```python
from app.routers import (
    alerts, audit_log, cashflow_goal, candidates as candidates_router,
    cockpit as cockpit_router, dividend,
    data_management,
    drafts as drafts_router, financial, health, market,
    ...
```

In the route registration section (after line ~148), add:
```python
app.include_router(data_management.router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/data_management.py backend/app/main.py
git commit -m "feat: add data management router and register in main"
```

---

## Task 4: Frontend — Type Definitions & API Client

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add type definitions to types.ts**

Append to the end of `frontend/src/api/types.ts`:

```typescript
// ── Data Management ──────────────────────────────────────────────────────

export interface DataCompleteness {
  has_valuation: boolean;
  has_financial: boolean;
  has_kline: boolean;
  has_dividend: boolean;
}

export interface StockPoolItem {
  code: string;
  name: string;
  industry: string | null;
  tier: string | null;
  security_theme: string | null;
  added_at: string | null;
  data_completeness: DataCompleteness;
}

export interface StockSearchResult {
  code: string;
  name: string;
  industry: string | null;
  listed_date: string | null;
}

export interface DataTypeStatus {
  total_records: number;
  stock_count: number;
  latest_date: string | null;
  earliest_date: string | null;
}

export interface DataStatusOverview {
  valuations: DataTypeStatus;
  financials: DataTypeStatus;
  klines: DataTypeStatus;
  dividends: DataTypeStatus;
}

export interface SyncTriggerResponse {
  task_id: string;
  data_type: string;
  stock_count: number;
  message: string;
}

export interface SyncTaskStatus {
  task_id: string;
  status: string;
  progress: number;
  total: number;
  completed_items: number;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CleanupPreview {
  data_type: string;
  record_count: number;
  date_range: string | null;
}

export interface CleanupResult {
  data_type: string;
  deleted_count: number;
}
```

- [ ] **Step 2: Add API functions to client.ts**

First, add the new type imports to the import block at the top of `client.ts`. Add these to the existing import from `./types`:
```typescript
  CleanupPreview,
  CleanupResult,
  DataStatusOverview,
  StockPoolItem,
  StockSearchResult,
  SyncTaskStatus,
  SyncTriggerResponse,
```

Then append these API functions to the end of `client.ts`:

```typescript
// ── Data Management ──────────────────────────────────────────────────────

export async function fetchStockPool(): Promise<StockPoolItem[]> {
  const res = await apiClient.get<StockPoolItem[]>('/data-management/universe');
  return res.data;
}

export async function searchStocks(keyword: string): Promise<StockSearchResult[]> {
  const res = await apiClient.post<StockSearchResult[]>('/data-management/universe/search', null, {
    params: { keyword },
  });
  return res.data;
}

export async function addToStockPool(stockCodes: string[]): Promise<{ added: number }> {
  const res = await apiClient.post<{ added: number }>('/data-management/universe/add', {
    stock_codes: stockCodes,
  });
  return res.data;
}

export async function removeFromStockPool(stockCodes: string[]): Promise<{ removed: number }> {
  const res = await apiClient.post<{ removed: number }>('/data-management/universe/batch-remove', {
    stock_codes: stockCodes,
  });
  return res.data;
}

export async function fetchDataStatus(): Promise<DataStatusOverview> {
  const res = await apiClient.get<DataStatusOverview>('/data-management/status');
  return res.data;
}

export async function triggerDataSync(
  dataType: string,
  stockCodes?: string[],
  years?: number,
): Promise<SyncTriggerResponse> {
  const res = await apiClient.post<SyncTriggerResponse>(`/data-management/sync/${dataType}`, {
    stock_codes: stockCodes ?? null,
    years: years ?? 5,
  });
  return res.data;
}

export async function fetchSyncTaskStatus(taskId: string): Promise<SyncTaskStatus> {
  const res = await apiClient.get<SyncTaskStatus>(`/data-management/sync/${taskId}/status`);
  return res.data;
}

export async function previewCleanup(
  dataType: string,
  params?: { before_date?: string; after_date?: string; stock_codes?: string[] },
): Promise<CleanupPreview> {
  const res = await apiClient.get<CleanupPreview>(`/data-management/cleanup/${dataType}/preview`, {
    params,
  });
  return res.data;
}

export async function executeCleanup(
  dataType: string,
  params?: { before_date?: string; after_date?: string; stock_codes?: string[] },
): Promise<CleanupResult> {
  const res = await apiClient.post<CleanupResult>(`/data-management/cleanup/${dataType}`, {
    stock_codes: params?.stock_codes ?? null,
    before_date: params?.before_date ?? null,
    after_date: params?.after_date ?? null,
  });
  return res.data;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts
git commit -m "feat: add data management types and API client functions"
```

---

## Task 5: Frontend — Scheduler Page (migrate from DataSyncPage)

**Files:**
- Create: `frontend/src/pages/SchedulerPage.tsx`

- [ ] **Step 1: Create SchedulerPage**

Extract the "任务管理" and "执行日志" tabs from DataSyncPage into a standalone component:

```tsx
import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Input,
  message,
  Popconfirm,
  Switch,
  Table,
  Tabs,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  PlayCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

import {
  listJobExecutions,
  listSchedulerJobs,
  triggerSchedulerJob,
  updateSchedulerJob,
} from '../api/client';
import type {
  JobExecutionResponse,
  SchedulerJobResponse,
} from '../api/types';

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(t: string | null): string {
  if (!t) return '-';
  return dayjs(t).format('YYYY-MM-DD HH:mm:ss');
}

function parseCronHuman(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return cron;
  const [min, hour, dom, mon, dow] = parts;

  const dowMap: Record<string, string> = {
    '0': '周日', '1': '周一', '2': '周二', '3': '周三',
    '4': '周四', '5': '周五', '6': '周六', '7': '周日',
    '1-5': '工作日',
  };

  const monMap: Record<string, string> = {
    '1': '1月', '2': '2月', '3': '3月', '4': '4月',
    '5': '5月', '6': '6月', '7': '7月', '8': '8月',
    '9': '9月', '10': '10月', '11': '11月', '12': '12月',
    '3,4,8,10': '季报月(3,4,8,10)',
    '1,4,7,10': '季初月(1,4,7,10)',
  };

  const timeStr = `${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;

  if (dom === '*' && mon === '*') {
    if (dow !== '*') {
      return `${dowMap[dow] || `星期${dow}`} ${timeStr}`;
    }
    return `每天 ${timeStr}`;
  }

  if (dom !== '*' && dow === '*') {
    const monStr = mon !== '*' ? (monMap[mon] || `${mon}月`) : '';
    let domStr = dom;
    if (dom === '1') domStr = '每月1日';
    else if (dom === '5') domStr = '每月5日';
    else if (dom.includes('-')) domStr = `${dom}日`;
    return `${monStr} ${domStr} ${timeStr}`.trim();
  }

  return cron;
}

export default function SchedulerPage() {
  const [jobs, setJobs] = useState<SchedulerJobResponse[]>([]);
  const [executions, setExecutions] = useState<JobExecutionResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [execLoading, setExecLoading] = useState(false);
  const [editingJob, setEditingJob] = useState<string | null>(null);
  const [editCron, setEditCron] = useState('');
  const [triggering, setTriggering] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSchedulerJobs();
      setJobs(data);
    } catch {
      message.error('获取任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchExecutions = useCallback(async () => {
    setExecLoading(true);
    try {
      const data = await listJobExecutions(undefined, 100);
      setExecutions(data);
    } catch {
      message.error('获取执行日志失败');
    } finally {
      setExecLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    fetchExecutions();
  }, [fetchJobs, fetchExecutions]);

  const handleToggle = async (jobId: string, enabled: boolean) => {
    try {
      await updateSchedulerJob(jobId, { enabled });
      message.success(enabled ? '已启用' : '已停用');
      fetchJobs();
    } catch {
      message.error('更新失败');
    }
  };

  const handleCronSave = async (jobId: string) => {
    try {
      await updateSchedulerJob(jobId, { cron_expr: editCron });
      message.success('Cron 已更新');
      setEditingJob(null);
      fetchJobs();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Cron 格式无效';
      message.error(msg);
    }
  };

  const handleTrigger = async (jobId: string) => {
    setTriggering(jobId);
    try {
      await triggerSchedulerJob(jobId);
      message.success('执行完成');
      fetchJobs();
      fetchExecutions();
    } catch {
      message.error('执行失败');
    } finally {
      setTriggering(null);
    }
  };

  const jobColumns: ColumnsType<SchedulerJobResponse> = [
    {
      title: '任务 ID',
      dataIndex: 'job_id',
      width: 200,
      render: (v: string) => <code style={{ fontSize: 13 }}>{v}</code>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: '调度规则',
      dataIndex: 'cron_expr',
      width: 240,
      render: (cron: string, record: SchedulerJobResponse) => {
        if (editingJob === record.job_id) {
          return (
            <Input.Search
              size="small"
              value={editCron}
              onChange={(e) => setEditCron(e.target.value)}
              enterButton="保存"
              onSearch={() => handleCronSave(record.job_id)}
              onBlur={() => setEditingJob(null)}
              style={{ width: 220 }}
              placeholder="0 17 * * 1-5"
            />
          );
        }
        return (
          <span
            onClick={() => {
              setEditingJob(record.job_id);
              setEditCron(cron);
            }}
            style={{ cursor: 'pointer', borderBottom: '1px dashed var(--gray-300)' }}
            title="点击编辑"
          >
            <code>{cron}</code>
            <span style={{ color: 'var(--gray-400)', fontSize: 12, marginLeft: 8 }}>
              ({parseCronHuman(cron)})
            </span>
          </span>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: (enabled: boolean, record: SchedulerJobResponse) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(v) => handleToggle(record.job_id, v)}
        />
      ),
    },
    {
      title: '上次执行',
      width: 180,
      render: (_: unknown, record: SchedulerJobResponse) => (
        <span>
          {record.last_run_status === 'success' && (
            <CheckCircleOutlined style={{ color: 'var(--green-600)', marginRight: 4 }} />
          )}
          {record.last_run_status === 'failed' && (
            <ExclamationCircleOutlined style={{ color: 'var(--red-600)', marginRight: 4 }} />
          )}
          {formatTime(record.last_run_at)}
          {record.last_duration_ms != null && (
            <span style={{ color: 'var(--gray-400)', fontSize: 12, marginLeft: 4 }}>
              ({formatDuration(record.last_duration_ms)})
            </span>
          )}
        </span>
      ),
    },
    {
      title: '下次执行',
      dataIndex: 'next_run_time',
      width: 170,
      render: (v: string | null, record: SchedulerJobResponse) =>
        record.enabled ? formatTime(v) : <span style={{ color: 'var(--gray-400)' }}>-</span>,
    },
    {
      title: '操作',
      width: 100,
      render: (_: unknown, record: SchedulerJobResponse) => (
        <Popconfirm
          title={`确认手动执行 ${record.job_id}?`}
          onConfirm={() => handleTrigger(record.job_id)}
        >
          <Button
            type="link"
            size="small"
            icon={<PlayCircleOutlined />}
            loading={triggering === record.job_id}
          >
            执行
          </Button>
        </Popconfirm>
      ),
    },
  ];

  const statusIconMap: Record<string, React.ReactNode> = {
    success: <CheckCircleOutlined />,
    failed: <ExclamationCircleOutlined />,
    running: <SyncOutlined spin />,
  };

  const execColumns: ColumnsType<JobExecutionResponse> = [
    {
      title: '任务',
      dataIndex: 'job_id',
      width: 180,
      render: (v: string) => <code style={{ fontSize: 13 }}>{v}</code>,
      filters: [...new Set(executions.map((e) => e.job_id))].map((j) => ({
        text: j,
        value: j,
      })),
      onFilter: (value, record) => record.job_id === value,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => (
        <Tag
          icon={statusIconMap[s]}
          color={s === 'success' ? 'success' : s === 'failed' ? 'error' : 'processing'}
        >
          {s === 'success' ? '成功' : s === 'failed' ? '失败' : '运行中'}
        </Tag>
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      width: 170,
      render: (v: string | null) => formatTime(v),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 80,
      render: (v: number | null) => formatDuration(v),
    },
    {
      title: '结果',
      dataIndex: 'result_summary',
      ellipsis: true,
      render: (v: string | null) =>
        v ? (
          <span style={{ color: 'var(--gray-600)', fontSize: 12 }}>{v.slice(0, 120)}</span>
        ) : (
          '-'
        ),
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (v: string | null) =>
        v ? <span style={{ color: 'var(--red-600)', fontSize: 12 }}>{v}</span> : '-',
    },
  ];

  const enabledCount = jobs.filter((j) => j.enabled).length;

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400 }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          <ClockCircleOutlined style={{ marginRight: 8 }} />
          定时任务
        </h2>
        <span style={{ color: 'var(--gray-500)', fontSize: 13 }}>
          共 {jobs.length} 个任务，{enabledCount} 个启用
        </span>
      </div>

      <Tabs
        defaultActiveKey="jobs"
        items={[
          {
            key: 'jobs',
            label: '任务管理',
            children: (
              <Table<SchedulerJobResponse>
                rowKey="job_id"
                columns={jobColumns}
                dataSource={jobs}
                loading={loading}
                pagination={false}
                size="middle"
              />
            ),
          },
          {
            key: 'executions',
            label: '执行日志',
            children: (
              <Table<JobExecutionResponse>
                rowKey="id"
                columns={execColumns}
                dataSource={executions}
                loading={execLoading}
                pagination={{ pageSize: 20, showSizeChanger: false }}
                size="middle"
              />
            ),
          },
        ]}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/SchedulerPage.tsx
git commit -m "feat: create SchedulerPage from DataSyncPage migration"
```

---

## Task 6: Frontend — Data Management Page

**Files:**
- Create: `frontend/src/pages/DataManagementPage.tsx`

- [ ] **Step 1: Create DataManagementPage**

```tsx
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  Col,
  DatePicker,
  message,
  Modal,
  Popconfirm,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Input,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloudSyncOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  LineChartOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

import {
  addToStockPool,
  executeCleanup,
  fetchDataStatus,
  fetchStockPool,
  previewCleanup,
  removeFromStockPool,
  searchStocks,
  triggerDataSync,
} from '../api/client';
import type {
  DataStatusOverview,
  StockPoolItem,
  StockSearchResult,
} from '../api/types';

export default function DataManagementPage() {
  // ── State ──────────────────────────────────────────────────────────────
  const [pool, setPool] = useState<StockPoolItem[]>([]);
  const [status, setStatus] = useState<DataStatusOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);

  // Sync modal
  const [syncModalType, setSyncModalType] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  // Cleanup modal
  const [cleanupModalType, setCleanupModalType] = useState<string | null>(null);
  const [cleanupDateRange, setCleanupDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [cleanupPreviewCount, setCleanupPreviewCount] = useState<number | null>(null);
  const [cleaning, setCleaning] = useState(false);

  // ── Data fetching ──────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [poolData, statusData] = await Promise.all([
        fetchStockPool().catch(() => []),
        fetchDataStatus().catch(() => null),
      ]);
      setPool(poolData);
      setStatus(statusData);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Stock pool actions ─────────────────────────────────────────────────

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    setSearching(true);
    try {
      const results = await searchStocks(searchKeyword.trim());
      setSearchResults(results);
    } catch {
      message.error('搜索失败');
    } finally {
      setSearching(false);
    }
  };

  const handleAddStock = async (code: string) => {
    try {
      const res = await addToStockPool([code]);
      message.success(`已添加 ${res.added} 只股票`);
      setSearchResults((prev) => prev.filter((s) => s.code !== code));
      loadData();
    } catch {
      message.error('添加失败');
    }
  };

  const handleRemoveStocks = async (codes: string[]) => {
    try {
      const res = await removeFromStockPool(codes);
      message.success(`已移除 ${res.removed} 只股票`);
      setSelectedRowKeys([]);
      loadData();
    } catch {
      message.error('移除失败');
    }
  };

  // ── Sync actions ───────────────────────────────────────────────────────

  const handleSync = async (dataType: string) => {
    setSyncing(true);
    try {
      const res = await triggerDataSync(dataType);
      message.success(`已触发 ${dataType} 同步，${res.stock_count} 只股票`);
      setSyncModalType(null);
      loadData();
    } catch {
      message.error('同步失败');
    } finally {
      setSyncing(false);
    }
  };

  // ── Cleanup actions ────────────────────────────────────────────────────

  const handleCleanupPreview = async (dataType: string) => {
    if (!cleanupDateRange?.[0] && !cleanupDateRange?.[1]) {
      setCleanupPreviewCount(null);
      return;
    }
    try {
      const params: Record<string, string> = {};
      if (cleanupDateRange?.[0]) params.before_date = cleanupDateRange[1]!.format('YYYY-MM-DD');
      if (cleanupDateRange?.[1]) params.after_date = cleanupDateRange[0]!.format('YYYY-MM-DD');
      const res = await previewCleanup(dataType, params);
      setCleanupPreviewCount(res.record_count);
    } catch {
      setCleanupPreviewCount(null);
    }
  };

  const handleCleanupExecute = async (dataType: string) => {
    setCleaning(true);
    try {
      const params: Record<string, string | string[] | undefined> = {};
      if (cleanupDateRange?.[0]) params.after_date = cleanupDateRange[0]!.format('YYYY-MM-DD');
      if (cleanupDateRange?.[1]) params.before_date = cleanupDateRange[1]!.format('YYYY-MM-DD');
      const res = await executeCleanup(dataType, params);
      message.success(`已清理 ${res.deleted_count} 条记录`);
      setCleanupModalType(null);
      setCleanupDateRange(null);
      setCleanupPreviewCount(null);
      loadData();
    } catch {
      message.error('清理失败');
    } finally {
      setCleaning(false);
    }
  };

  // ── Stock pool columns ─────────────────────────────────────────────────

  const poolColumns: ColumnsType<StockPoolItem> = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 100,
      render: (v: string) => (
        <a onClick={() => window.location.hash = `/stock/${v}`} style={{ fontFamily: 'monospace' }}>{v}</a>
      ),
    },
    { title: '名称', dataIndex: 'name', width: 100 },
    { title: '行业', dataIndex: 'industry', width: 100, ellipsis: true },
    {
      title: '等级',
      dataIndex: 'tier',
      width: 70,
      render: (v: string | null) => v ? <Tag>{v}</Tag> : '-',
    },
    {
      title: '数据完整度',
      width: 200,
      render: (_: unknown, record: StockPoolItem) => {
        const c = record.data_completeness;
        return (
          <Space size={4}>
            <Tooltip title="估值">
              {c.has_valuation ? <CheckCircleOutlined style={{ color: 'var(--green-600)' }} /> : <CloseCircleOutlined style={{ color: 'var(--gray-300)' }} />}
            </Tooltip>
            <Tooltip title="财报">
              {c.has_financial ? <CheckCircleOutlined style={{ color: 'var(--green-600)' }} /> : <CloseCircleOutlined style={{ color: 'var(--gray-300)' }} />}
            </Tooltip>
            <Tooltip title="K线">
              {c.has_kline ? <CheckCircleOutlined style={{ color: 'var(--green-600)' }} /> : <CloseCircleOutlined style={{ color: 'var(--gray-300)' }} />}
            </Tooltip>
            <Tooltip title="分红">
              {c.has_dividend ? <CheckCircleOutlined style={{ color: 'var(--green-600)' }} /> : <CloseCircleOutlined style={{ color: 'var(--gray-300)' }} />}
            </Tooltip>
          </Space>
        );
      },
    },
    {
      title: '添加时间',
      dataIndex: 'added_at',
      width: 120,
      render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD') : '-',
    },
  ];

  // ── Data type card helper ──────────────────────────────────────────────

  const renderDataCard = (
    title: string,
    icon: React.ReactNode,
    dataType: string,
    stat: { total_records: number; stock_count: number; latest_date: string | null; earliest_date: string | null } | undefined,
  ) => (
    <Card
      title={<span>{icon}<span style={{ marginLeft: 8 }}>{title}</span></span>}
      size="small"
      style={{ height: '100%' }}
      extra={
        <Space>
          <Button
            size="small"
            icon={<CloudSyncOutlined />}
            onClick={() => setSyncModalType(dataType)}
          >
            同步
          </Button>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => setCleanupModalType(dataType)}
          >
            清理
          </Button>
        </Space>
      }
    >
      <Row gutter={16}>
        <Col span={8}>
          <Statistic title="记录数" value={stat?.total_records ?? 0} />
        </Col>
        <Col span={8}>
          <Statistic title="覆盖股票" value={stat?.stock_count ?? 0} suffix="只" />
        </Col>
        <Col span={8}>
          <div style={{ fontSize: 12, color: 'var(--gray-500)' }}>
            <div>最近: {stat?.latest_date ? dayjs(stat.latest_date).format('YYYY-MM-DD') : '-'}</div>
            <div>最早: {stat?.earliest_date ? dayjs(stat.earliest_date).format('YYYY-MM-DD') : '-'}</div>
          </div>
        </Col>
      </Row>
    </Card>
  );

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400 }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          <DatabaseOutlined style={{ marginRight: 8 }} />
          基础数据管理
        </h2>
        <span style={{ color: 'var(--gray-500)', fontSize: 13 }}>
          管理股票池、同步数据、清理历史记录
        </span>
      </div>

      {/* ── Stock Pool ────────────────────────────────────────────────── */}
      <Card
        title="股票池"
        size="small"
        style={{ marginBottom: 20 }}
        extra={
          <Space>
            {selectedRowKeys.length > 0 && (
              <Popconfirm
                title={`确认移除 ${selectedRowKeys.length} 只股票?`}
                onConfirm={() => handleRemoveStocks(selectedRowKeys)}
              >
                <Button size="small" danger icon={<DeleteOutlined />}>
                  批量移除 ({selectedRowKeys.length})
                </Button>
              </Popconfirm>
            )}
          </Space>
        }
      >
        <div style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
          <Input.Search
            placeholder="搜索股票代码/名称"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            onSearch={handleSearch}
            enterButton={<><SearchOutlined /> 搜索</>}
            loading={searching}
            style={{ width: 300 }}
          />
        </div>

        {/* Search results */}
        {searchResults.length > 0 && (
          <div style={{ marginBottom: 12, padding: 8, background: 'var(--gray-50)', borderRadius: 4 }}>
            <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>搜索结果（点击添加到股票池）</div>
            <Space wrap>
              {searchResults.map((s) => (
                <Tag
                  key={s.code}
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleAddStock(s.code)}
                >
                  <PlusOutlined /> {s.code} {s.name}
                </Tag>
              ))}
            </Space>
          </div>
        )}

        <Table<StockPoolItem>
          rowKey="code"
          columns={poolColumns}
          dataSource={pool}
          loading={loading}
          size="small"
          pagination={false}
          scroll={{ y: 300 }}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as string[]),
          }}
        />
      </Card>

      {/* ── Data Cards ───────────────────────────────────────────────── */}
      <Row gutter={16}>
        <Col span={12}>
          {renderDataCard('估值快照', <LineChartOutlined />, 'valuations', status?.valuations)}
        </Col>
        <Col span={12}>
          {renderDataCard('财报数据', <DatabaseOutlined />, 'financials', status?.financials)}
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          {renderDataCard('K线数据', <LineChartOutlined />, 'klines', status?.klines)}
        </Col>
        <Col span={12}>
          {renderDataCard('分红数据', <DatabaseOutlined />, 'dividends', status?.dividends)}
        </Col>
      </Row>

      {/* ── Sync Modal ──────────────────────────────────────────────── */}
      <Modal
        title={`同步${syncModalType === 'valuations' ? '估值' : syncModalType === 'financials' ? '财报' : syncModalType === 'klines' ? 'K线' : '分红'}数据`}
        open={syncModalType !== null}
        onCancel={() => setSyncModalType(null)}
        onOk={() => syncModalType && handleSync(syncModalType)}
        confirmLoading={syncing}
        okText="开始同步"
      >
        <p>将对所有股票池中的股票执行{syncModalType === 'valuations' ? '估值快照' : syncModalType === 'financials' ? '财报' : syncModalType === 'klines' ? 'K线' : '分红'}数据同步。</p>
        <p>当前股票池共 <strong>{pool.length}</strong> 只股票。</p>
      </Modal>

      {/* ── Cleanup Modal ───────────────────────────────────────────── */}
      <Modal
        title={`清理${cleanupModalType === 'valuations' ? '估值' : cleanupModalType === 'financials' ? '财报' : cleanupModalType === 'klines' ? 'K线' : '分红'}数据`}
        open={cleanupModalType !== null}
        onCancel={() => {
          setCleanupModalType(null);
          setCleanupDateRange(null);
          setCleanupPreviewCount(null);
        }}
        onOk={() => cleanupModalType && handleCleanupExecute(cleanupModalType)}
        confirmLoading={cleaning}
        okText={`确认清理${cleanupPreviewCount != null ? ` (${cleanupPreviewCount} 条)` : ''}`}
      >
        <p>选择要清理的时间范围：</p>
        <DatePicker.RangePicker
          style={{ width: '100%', marginBottom: 12 }}
          onChange={(dates) => {
            setCleanupDateRange(dates as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null);
            setCleanupPreviewCount(null);
          }}
        />
        {cleanupDateRange && cleanupModalType && (
          <Button
            size="small"
            onClick={() => handleCleanupPreview(cleanupModalType)}
            style={{ marginBottom: 12 }}
          >
            预览清理数量
          </Button>
        )}
        {cleanupPreviewCount != null && (
          <p>将清理 <strong>{cleanupPreviewCount}</strong> 条记录。</p>
        )}
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/DataManagementPage.tsx
git commit -m "feat: create DataManagementPage with stock pool, sync, cleanup"
```

---

## Task 7: Frontend — Update Routes & Navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Delete: `frontend/src/pages/DataSyncPage.tsx`

- [ ] **Step 1: Update App.tsx**

Replace the DataSyncPage lazy import with the two new pages:

Change line 14:
```typescript
const DataSyncPage = lazy(() => import('./pages/DataSyncPage'));
```
to:
```typescript
const DataManagementPage = lazy(() => import('./pages/DataManagementPage'));
const SchedulerPage = lazy(() => import('./pages/SchedulerPage'));
```

Change line 82:
```typescript
<Route path="data-sync" element={<DataSyncPage />} />
```
to:
```typescript
<Route path="data-management" element={<DataManagementPage />} />
<Route path="scheduler" element={<SchedulerPage />} />
```

- [ ] **Step 2: Update Layout.tsx navigation**

Replace the SyncOutlined import with additional icons. Add `DatabaseOutlined` and `ClockCircleOutlined` to the imports from `@ant-design/icons` (ClockCircleOutlined is not currently imported; SyncOutlined is).

In the NAV_GROUPS array, replace the '系统' group (line 33-38):
```typescript
  {
    label: '系统',
    items: [
      { key: '/data-sync', label: '数据同步', labelEn: 'Data Sync', icon: <SyncOutlined /> },
    ],
  },
```
with:
```typescript
  {
    label: '系统',
    items: [
      { key: '/data-management', label: '数据管理', labelEn: 'Data Management', icon: <DatabaseOutlined /> },
      { key: '/scheduler', label: '定时任务', labelEn: 'Scheduler', icon: <ClockCircleOutlined /> },
    ],
  },
```

Update the icon imports at the top of Layout.tsx — add `ClockCircleOutlined` and `DatabaseOutlined`, remove `SyncOutlined` if no longer used.

- [ ] **Step 3: Delete old DataSyncPage**

```bash
rm frontend/src/pages/DataSyncPage.tsx
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx
git rm frontend/src/pages/DataSyncPage.tsx
git commit -m "feat: split DataSyncPage into DataManagement + Scheduler, update navigation"
```

---

## Task 8: Verify & Smoke Test

**Files:** None

- [ ] **Step 1: Run backend tests**

```bash
cd /Users/rong.zhu/Code/gojira/backend && source .venv/bin/activate && pytest -x -q 2>&1 | tail -20
```

Expected: All existing tests pass. No test regressions from the new router/service additions.

- [ ] **Step 2: Start backend and verify API**

```bash
cd /Users/rong.zhu/Code/gojira/backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 3001 &
```

Then verify the new endpoint:
```bash
curl -s http://localhost:3001/api/data-management/status | python3 -m json.tool
```

Expected: JSON response with valuations, financials, klines, dividends status objects.

- [ ] **Step 3: Start frontend and verify**

```bash
cd /Users/rong.zhu/Code/gojira/frontend && npm run build 2>&1 | tail -10
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: Fix any issues found**

Address any test failures, build errors, or runtime issues discovered during verification.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A && git commit -m "fix: address issues from verification"
```
