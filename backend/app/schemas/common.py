"""Common response schemas shared across endpoints."""


from pydantic import BaseModel


class OkResponse(BaseModel):
    """Simple success response."""
    ok: bool = True


class CountResponse(BaseModel):
    """Response with a single count field."""
    count: int


class AckedResponse(BaseModel):
    """Response for bulk ack operations."""
    acked: int


class AddedResponse(BaseModel):
    """Response for bulk add operations."""
    added: list[str] = []


class CodesResponse(BaseModel):
    """Response returning stock codes."""
    codes: list[str] = []


class StatusResponse(BaseModel):
    """Response with a status string."""
    status: str


class SyncDividendResponse(BaseModel):
    """Response for dividend sync."""
    stock_code: str
    inserted: int
