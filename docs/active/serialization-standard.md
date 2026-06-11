# Serialization Standard

## Rule: All ORM-to-response conversions use Pydantic schemas

### The Standard

1. **Define response models** in `backend/app/schemas/` as Pydantic `BaseModel` subclasses
2. **Service layer** returns ORM objects or Pydantic models — never raw dicts for API responses
3. **Routers** declare `response_model=XxxResponse` — FastAPI handles serialization and validation
4. **Dataclasses** crossing the API boundary should be converted to Pydantic models
5. **`.model_dump()`** (Pydantic v2) is the canonical serialization method, replacing manual `to_dict()`

### Why Pydantic-first

- **Validation**: Response shape is validated before leaving the server
- **OpenAPI docs**: Endpoints auto-document their response structure
- **Type safety**: Field mismatches between frontend and backend surface as errors, not silent bugs
- **Consistency**: One serialization pattern across the entire codebase

### Patterns to follow

#### ✅ Good: Pydantic schema with response_model

```python
# schemas/stock.py
class StockResponse(BaseModel):
    code: str
    name: Optional[str] = None
    industry: Optional[str] = None

# routers/stocks.py
@router.get("/{code}", response_model=StockResponse)
def get_stock(code: str, db: Session = Depends(get_db)):
    return stock_service.get_stock(db, code)  # Returns ORM object, FastAPI serializes
```

#### ✅ Good: Pydantic dataclass replacement

```python
# Before (dataclass with to_dict):
@dataclass
class Suggestion:
    code: str
    action: str

    def to_dict(self):
        return {"code": self.code, "action": self.action}

# After (Pydantic):
class Suggestion(BaseModel):
    code: str
    action: str

# Serialization: suggestion.model_dump() instead of suggestion.to_dict()
```

### Patterns to avoid

#### ❌ Anti-pattern: Manual dict construction in service layer

```python
# Don't do this:
def get_summary(db) -> dict:
    return {"code": "X", "value": 42}  # No validation, no type safety
```

Use a Pydantic model instead.

#### ❌ Anti-pattern: Raw dict return without response_model

```python
# Don't do this:
@router.get("/data")
def get_data():
    return {"ad_hoc": "field"}  # No contract with frontend
```

Always declare `response_model`.

#### ❌ Anti-pattern: dataclass.to_dict() for API responses

Convert to Pydantic and use `.model_dump()`.

### Migration status (2026-06-11)

All domain dataclasses converted to Pydantic:
- `RebalanceSuggestion` — Pydantic `BaseModel`, uses `.model_dump()`
- `CycleAssessment` — Pydantic `BaseModel` (kept `to_dict()` shim for backward compat)
- `DividendProjection` — Pydantic with `field_serializer` for rounding
- `HoldingDividendForecast` — Pydantic with `field_serializer` for rounding
- `ThesisAlert` — Pydantic `BaseModel`

Still using manual dict construction (acceptable for internal cockpit aggregation):
- `_serialize_*` helpers in `cockpit_service.py` — these wrap ORM-to-dict conversion
  for the cockpit aggregator. Will be replaced when cockpit endpoints migrate to
  returning Pydantic models directly.
