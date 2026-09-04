"""Rank and filter events with bootstrap + epsilon-greedy personalization."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.config import settings
from app.models import ChangeEvent, User
from app.services.personalization import PersonalizationEngine


def is_bootstrap_phase(user: User, feedback_count: int) -> bool:
    age = datetime.utcnow() - user.created_at
    return age < timedelta(days=settings.personalization_bootstrap_days) or feedback_count < 5


def rank_events_for_user(
    user: User,
    events: list[ChangeEvent],
    personalization: PersonalizationEngine,
    feedback_count: int,
) -> list[tuple[ChangeEvent, float, bool]]:
    """
    Returns (event, relevance_score, forced_explore).
    Bootstrap: always include top-N by raw severity.
    Mature: epsilon-greedy surfaces low-score events 10% of the time.
    """
    if not events:
        return []

    scored: list[tuple[ChangeEvent, float]] = [
        (e, personalization.score(user.id, e)) for e in events
    ]

    bootstrap = is_bootstrap_phase(user, feedback_count)
    top_by_magnitude = sorted(events, key=lambda e: e.severity, reverse=True)[
        : settings.bootstrap_top_n_by_magnitude
    ]
    top_ids = {e.id for e in top_by_magnitude}

    result: list[tuple[ChangeEvent, float, bool]] = []
    seen: set[int] = set()

    if bootstrap:
        for e in top_by_magnitude:
            score = next(s for ev, s in scored if ev.id == e.id)
            result.append((e, score, True))
            seen.add(e.id)

    remaining = [(e, s) for e, s in sorted(scored, key=lambda x: x[1], reverse=True) if e.id not in seen]

    for e, score in remaining:
        explore = False
        if not bootstrap and random.random() < settings.epsilon_greedy_rate:
            explore = True
        result.append((e, score, explore))
        seen.add(e.id)

    # Re-sort: forced items first in bootstrap, then by score
    if bootstrap:
        forced = [r for r in result if r[2]]
        rest = sorted([r for r in result if not r[2]], key=lambda x: x[1], reverse=True)
        return forced + rest

    return sorted(result, key=lambda x: (x[2], x[1]), reverse=True)
