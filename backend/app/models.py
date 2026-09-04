from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import FEATURE_SCHEMA_VERSION
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_visit_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    watchlist_items: Mapped[list["WatchlistItem"]] = relationship(back_populates="user")
    feedback: Mapped[list["AlertFeedback"]] = relationship(back_populates="user")
    mutes: Mapped[list["AlertMute"]] = relationship(back_populates="user")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="watchlist_items")


class Instrument(Base):
    """Per-symbol cluster state with optimistic locking and schema versioning."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    feature_schema_version: Mapped[int] = mapped_column(Integer, default=FEATURE_SCHEMA_VERSION)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    algo: Mapped[str] = mapped_column(String(32), default="dbstream")
    state_json: Mapped[str] = mapped_column(Text, default="")
    last_cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # event_type -> ISO-8601 UTC timestamp; each type has its own cooldown window
    last_event_times: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    trading_status: Mapped[str] = mapped_column(String(32), default="active")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    price: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    open_price: Mapped[float] = mapped_column(Float)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    is_out_of_order: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(64), default="yfinance")
    tick_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[float] = mapped_column(Float, default=0.5)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_return: Mapped[float] = mapped_column(Float)
    feature_volatility: Mapped[float] = mapped_column(Float)
    feature_volume_z: Mapped[float] = mapped_column(Float)
    feature_spread: Mapped[float] = mapped_column(Float)
    detection_method: Mapped[str] = mapped_column(String(32), default="dbstream")
    is_stale_context: Mapped[bool] = mapped_column(Boolean, default=False)
    is_out_of_order: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AlertFeedback(Base):
    __tablename__ = "alert_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("change_events.id"), index=True)
    engaged: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="feedback")


class AlertMute(Base):
    """Explicit user preference to hide certain alert types per symbol."""

    __tablename__ = "alert_mutes"
    __table_args__ = (UniqueConstraint("user_id", "symbol", "event_type", name="uq_user_symbol_event_mute"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="mutes")
