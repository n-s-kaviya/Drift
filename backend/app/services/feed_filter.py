"""Trim and dedupe events before they reach the dashboard feed."""

from __future__ import annotations

from app.models import ChangeEvent

# Shown in the alert feed. price_move included for meaningful moves (deduped per symbol).
FEED_EVENT_TYPES = frozenset(
    {
        "regime_shift",
        "volume_anomaly",
        "anomaly",
        "outlier",
        "price_move",
    }
)


def filter_feed_event_types(events: list[ChangeEvent]) -> list[ChangeEvent]:
    return [e for e in events if e.event_type in FEED_EVENT_TYPES]


def collapse_superseded_events(events: list[ChangeEvent]) -> list[ChangeEvent]:
    """Keep only the latest alert per symbol + event type (drops stale repeats)."""
    latest: dict[tuple[str, str], ChangeEvent] = {}
    for event in events:
        key = (event.symbol.upper(), event.event_type)
        current = latest.get(key)
        if current is None or event.created_at > current.created_at:
            latest[key] = event
    return sorted(latest.values(), key=lambda e: e.created_at, reverse=True)
