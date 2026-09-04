"""Group correlated regime shifts into bundled alerts."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from app.schemas import ChangeEventOut

from app.services.event_copy import bundle_summary, bundle_title, bundle_why_plain

BUNDLE_WINDOW_MINUTES = 20


def _cluster_by_time(events: list[ChangeEventOut], window_minutes: int) -> list[list[ChangeEventOut]]:
    if not events:
        return []

    ordered = sorted(events, key=lambda e: e.created_at)
    clusters: list[list[ChangeEventOut]] = [[ordered[0]]]
    for event in ordered[1:]:
        gap = (event.created_at - clusters[-1][-1].created_at).total_seconds()
        if gap <= window_minutes * 60:
            clusters[-1].append(event)
        else:
            clusters.append([event])
    return clusters


def bundle_events(events: list[ChangeEventOut]) -> list[dict]:
    if not events:
        return []

    regime = [e for e in events if e.event_type == "regime_shift"]
    used: set[int] = set()
    feed: list[dict] = []

    for cluster in _cluster_by_time(regime, BUNDLE_WINDOW_MINUTES):
        if len(cluster) < 2:
            continue
        for event in cluster:
            used.add(event.id)
        symbols = sorted({e.symbol for e in cluster})
        feed.append(
            {
                "kind": "bundle",
                "bundle_id": str(uuid4()),
                "title": bundle_title(symbols),
                "summary": bundle_summary(symbols, BUNDLE_WINDOW_MINUTES),
                "why_plain": bundle_why_plain(),
                "events": sorted(cluster, key=lambda e: e.created_at, reverse=True),
                "created_at": max(e.created_at for e in cluster),
            }
        )

    for ev in events:
        if ev.id in used:
            continue
        feed.append(
            {
                "kind": "single",
                "bundle_id": None,
                "title": ev.title,
                "summary": ev.summary,
                "why_plain": ev.why_plain,
                "events": [ev],
                "created_at": ev.created_at,
            }
        )

    feed.sort(key=lambda x: x["created_at"], reverse=True)
    return feed
