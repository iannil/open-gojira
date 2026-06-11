from typing import Optional

from pydantic import BaseModel


RULE_TYPES = (
    "dividend_ex_date_near",
    "financial_report_released",
    "stop_profit",
)


class AlertRuleCreate(BaseModel):
    rule_type: str
    stock_code: Optional[str] = None
    params: dict = {}
    enabled: bool = True
    note: Optional[str] = None


class AlertRuleUpdate(BaseModel):
    params: Optional[dict] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None


class AlertRuleResponse(BaseModel):
    id: int
    rule_type: str
    stock_code: Optional[str] = None
    params: dict
    enabled: bool
    note: Optional[str] = None
    created_at: Optional[str] = None
    last_evaluated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertEventResponse(BaseModel):
    id: int
    rule_id: int
    stock_code: Optional[str] = None
    rule_type: str
    title: str
    detail: Optional[str] = None
    payload: dict
    severity: str
    fired_at: Optional[str] = None
    acked: bool
    acked_at: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertEvaluateResponse(BaseModel):
    evaluated_rules: int
    new_events: int
