"""Filter events by explicit user mutes."""

from __future__ import annotations

from app.models import AlertMute, ChangeEvent


def is_event_muted(event: ChangeEvent, mutes: list[AlertMute]) -> bool:
    for mute in mutes:
        sym_match = mute.symbol in ("*", event.symbol)
        if not sym_match:
            continue
        if mute.event_type == "*" or mute.event_type == event.event_type:
            return True
        if mute.event_type == "volume_anomaly":
            if event.event_type == "anomaly" and abs(event.feature_volume_z) >= 2:
                return True
            if event.event_type == "outlier" and abs(event.feature_volume_z) >= 2:
                return True
    return False
