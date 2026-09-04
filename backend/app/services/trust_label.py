"""Human-readable data trust labels from source + staleness."""

from __future__ import annotations

from datetime import datetime


SOURCE_LABELS = {
    "finnhub": "Finnhub",
    "yfinance": "Yahoo Finance",
    "demo": "simulated demo feed",
}


def format_trust_label(source: str, is_stale: bool, fetched_at: datetime, trading_status: str) -> str:
    time_str = fetched_at.strftime("%H:%M UTC")
    src = SOURCE_LABELS.get(source, source)

    if trading_status == "halted":
        return f"As of {time_str}, trading halted — last known price may be outdated."

    if source == "demo":
        return f"As of {time_str}, simulated demo data (not a live exchange feed)."

    if is_stale:
        return f"As of {time_str}, delayed feed — fallback source ({src})."

    return f"As of {time_str}, live via {src}."
