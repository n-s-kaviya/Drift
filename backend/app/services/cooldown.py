"""Event cooldown / hysteresis to prevent alert chattering."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.config import settings
from app.models import Instrument

COOLDOWN_MINUTES_BY_TYPE: dict[str, int] = {
    "price_move": settings.price_move_cooldown_minutes,
    "regime_shift": settings.event_cooldown_minutes,
    "outlier": settings.event_cooldown_minutes,
    "anomaly": settings.event_cooldown_minutes,
    "volume_anomaly": settings.volume_anomaly_cooldown_minutes,
    "corporate_action": settings.event_cooldown_minutes,
    "trading_halted": settings.event_cooldown_minutes,
}


def cooldown_for(event_type: str) -> timedelta:
    minutes = COOLDOWN_MINUTES_BY_TYPE.get(event_type, settings.event_cooldown_minutes)
    return timedelta(minutes=minutes)


def _last_fired_at(instrument: Instrument, event_type: str) -> datetime | None:
    raw = (instrument.last_event_times or {}).get(event_type)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(raw)


def should_suppress_event(
    instrument: Instrument,
    event_type: str,
    severity: float,
    now: datetime | None = None,
) -> bool:
    """Don't re-fire the same event type within cooldown unless magnitude jumps."""
    now = now or datetime.utcnow()
    last = _last_fired_at(instrument, event_type)
    if last is None:
        return False

    elapsed = now - last
    if elapsed >= cooldown_for(event_type):
        return False

    return True


def record_event_fired(instrument: Instrument, event_type: str, now: datetime | None = None) -> None:
    fired_at = now or datetime.utcnow()
    times = dict(instrument.last_event_times or {})
    times[event_type] = fired_at.isoformat()
    instrument.last_event_times = times
