"""US equity trading calendar — weekends and common NYSE holidays."""

from __future__ import annotations

from datetime import date, datetime, timedelta

# NYSE full-day closures (extend as needed)
NYSE_HOLIDAYS: set[date] = {
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def previous_trading_day(d: date) -> date:
    cur = d - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def calendar_gap_days(tick_date: date, prior_tick_date: date) -> int:
    """Trading days between two tick dates (exclusive of tick_date)."""
    if tick_date <= prior_tick_date:
        return 0
    gap = 0
    cur = prior_tick_date + timedelta(days=1)
    while cur < tick_date:
        if is_trading_day(cur):
            gap += 1
        cur += timedelta(days=1)
    return gap


def is_weekend_or_holiday_gap(tick_at: datetime, prior_tick_at: datetime | None) -> bool:
    """True when gap spans a weekend/holiday — reopen tick, not an anomaly."""
    if prior_tick_at is None:
        return False
    tick_d = tick_at.date()
    prior_d = prior_tick_at.date()
    if tick_d == prior_d:
        return False
    gap_days = calendar_gap_days(tick_d, prior_d)
    return gap_days >= 1 and (not is_trading_day(prior_d) or not is_trading_day(tick_d) or (tick_d - prior_d).days > 1)


def expected_market_quiet(now: datetime | None = None) -> bool:
    """Market is closed right now (weekend/holiday or outside regular hours)."""
    now = now or datetime.utcnow()
    d = now.date()
    if not is_trading_day(d):
        return True
    # Rough US regular session 14:30–21:00 UTC (9:30–16:00 ET)
    minutes = now.hour * 60 + now.minute
    return minutes < 14 * 60 + 30 or minutes >= 21 * 60
