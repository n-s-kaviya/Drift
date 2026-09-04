"""Template-generated plain-English explanations for change events."""

from __future__ import annotations

from app.models import ChangeEvent, Instrument


def _price_direction(ret: float) -> str:
    if ret > 0.05:
        return "up"
    if ret < -0.05:
        return "down"
    return "flat"


def _volume_phrase(vol_z: float) -> str | None:
    if vol_z >= 2.5:
        return "much heavier trading than usual"
    if vol_z >= 1.5:
        return "higher-than-usual trading volume"
    if vol_z <= -1.5:
        return "lighter trading than usual"
    return None


def plain_english_title(event: ChangeEvent) -> str:
    """One-line headline a new user can understand at a glance."""
    sym = event.symbol
    ret = event.feature_return
    vol_z = event.feature_volume_z
    direction = _price_direction(ret)

    if event.event_type == "regime_shift":
        vol_note = _volume_phrase(vol_z)
        if abs(ret) >= 0.3:
            base = f"{sym} is trading differently — price {direction} {abs(ret):.1f}%"
            return f"{base} with {vol_note}" if vol_note else base
        if vol_note:
            return f"{sym} is trading differently with {vol_note}"
        return f"{sym} is behaving differently than its recent pattern"

    if event.event_type == "price_move":
        word = "rose" if ret > 0 else "fell" if ret < 0 else "held steady"
        return f"{sym} {word} {abs(ret):.1f}% since the last update"

    if event.event_type == "volume_anomaly":
        return f"{sym} is seeing unusually high trading activity"

    if event.event_type == "outlier":
        return f"{sym} had an unusual price move that doesn't match recent patterns"

    if event.event_type == "anomaly":
        if abs(vol_z) >= 2:
            return f"{sym} is seeing unusually high trading volume"
        return f"{sym} showed unusual price or volume activity"

    if event.event_type == "corporate_action":
        return f"{sym} had a large overnight price change (likely a split or dividend)"

    if event.event_type == "trading_halted":
        return f"{sym} trading appears paused — price may be outdated"

    return event.title


def plain_english_why(event: ChangeEvent, instrument: Instrument | None = None) -> str:
    """Short supporting line with a bit more context."""
    ret = event.feature_return
    vol_z = event.feature_volume_z
    volatility = event.feature_volatility

    if event.event_type == "regime_shift":
        parts: list[str] = []
        if abs(ret) >= 0.1:
            word = "rose" if ret > 0 else "fell" if ret < 0 else "stayed flat"
            parts.append(f"Price {word} {abs(ret):.1f}%")
        if abs(vol_z) >= 1.5:
            parts.append("volume is well above this stock's recent average")
        elif abs(vol_z) >= 1.0:
            parts.append("volume is a bit higher than usual")
        if parts:
            return " and ".join(parts).capitalize() + " — the stock's trading pattern just changed."
        return "The way this stock has been trading recently just shifted."

    if event.event_type == "price_move":
        return (
            f"Price moved {ret:+.1f}% — "
            f"{'a bigger move than usual' if abs(ret) > max(volatility, 0.5) else 'a noticeable move'} "
            f"for this stock."
        )

    if event.event_type == "outlier":
        vol_note = _volume_phrase(vol_z)
        base = f"Latest price change ({ret:+.1f}%) doesn't fit this stock's recent behavior."
        return f"{base} {vol_note.capitalize()}." if vol_note else base

    if event.event_type == "anomaly":
        if abs(vol_z) >= 2:
            return f"Trading volume spiked while price moved {ret:+.1f}%."
        return f"Unusual activity detected: price {ret:+.1f}%, volume above normal."

    if event.event_type == "volume_anomaly":
        return (
            f"Many more shares traded than usual (price {ret:+.1f}%) — "
            "often a sign of news or heavy investor interest."
        )

    if event.event_type == "corporate_action":
        return (
            "A large overnight gap often means a stock split, reverse split, or dividend — "
            "not a normal market move."
        )

    if event.event_type == "trading_halted":
        return "No new price updates during market hours — the last price may not reflect current trading."

    return event.summary


def bundle_title(symbols: list[str]) -> str:
    count = len(symbols)
    if count == 2:
        return f"{symbols[0]} and {symbols[1]} moved together"
    return f"{count} of your stocks moved around the same time"


def bundle_summary(symbols: list[str], window_minutes: int) -> str:
    listed = ", ".join(symbols[:4])
    extra = f" and {len(symbols) - 4} more" if len(symbols) > 4 else ""
    return (
        f"{listed}{extra} all shifted within {window_minutes} minutes — "
        "this often happens during broad market moves."
    )


def bundle_why_plain() -> str:
    return "Several watchlist stocks changed at once, which usually points to a sector or market-wide event."
