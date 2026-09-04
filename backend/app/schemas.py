from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime
    last_visit_at: datetime | None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    notes: str | None = None


class WatchlistItemOut(BaseModel):
    id: int
    symbol: str
    notes: str | None
    added_at: datetime

    class Config:
        from_attributes = True


class MarketQuoteOut(BaseModel):
    symbol: str
    price: float
    change_pct: float
    volume: float
    high: float
    low: float
    open_price: float
    is_stale: bool
    source: str
    fetched_at: datetime
    trading_status: str = "active"
    trust_label: str = ""
    abnormality_score: float = 0.0
    abnormality_label: str = "Within normal"


class ChangeEventOut(BaseModel):
    id: int
    symbol: str
    event_type: str
    title: str
    summary: str
    why_plain: str = ""
    severity: float
    cluster_id: int | None
    prev_cluster_id: int | None
    detection_method: str
    is_stale_context: bool
    is_out_of_order: bool = False
    created_at: datetime
    relevance_score: float | None = None
    user_engaged: bool | None = None
    personalization_forced: bool = False
    is_muted_type: bool = False
    is_new: bool = False

    class Config:
        from_attributes = True


class FeedItemOut(BaseModel):
    kind: Literal["single", "bundle"]
    bundle_id: str | None = None
    title: str
    summary: str
    why_plain: str | None = None
    events: list[ChangeEventOut]
    created_at: datetime


class FeedbackCreate(BaseModel):
    event_id: int
    engaged: bool


class AlertMuteCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    event_type: str = Field(min_length=1, max_length=64)


class AlertMuteOut(BaseModel):
    id: int
    symbol: str
    event_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardOut(BaseModel):
    last_visit_at: datetime | None
    feed: list[FeedItemOut]
    watchlist: list[WatchlistItemOut]
    quotes: list[MarketQuoteOut]
    mutes: list[AlertMuteOut]
    unread_event_count: int
    in_bootstrap_phase: bool = False
    quotes_updated_at: datetime | None = None


class HealthOut(BaseModel):
    status: str
    symbols_tracked: int
    clustering_algo: str
    market_data_provider: str
    market_data_active: str


class PriceBarOut(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    class Config:
        from_attributes = True


class FundamentalsOut(BaseModel):
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    dividend_yield: float | None = None
    pe_ratio: float | None = None
    profit_margin: float | None = None
    beta: float | None = None
    market_cap: float | None = None
    revenue_growth: float | None = None
    source: str

    class Config:
        from_attributes = True


class StockDetailsOut(BaseModel):
    symbol: str
    history: list[PriceBarOut]
    fundamentals: FundamentalsOut


class SymbolSearchResultOut(BaseModel):
    symbol: str
    name: str
    type: str | None = None
