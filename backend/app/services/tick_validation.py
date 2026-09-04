"""Sanity bounds, corporate-action heuristics, and tick ordering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config import settings


@dataclass
class TickValidation:
    accepted: bool
    reject_reason: str | None = None
    is_corporate_action: bool = False
    corporate_action_type: str | None = None
    is_out_of_order: bool = False
    clamped_return_pct: float | None = None
    clamped_volume_z: float | None = None
    clamped_spread: float | None = None


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def validate_and_clamp_tick(
    return_pct: float,
    volume_z: float,
    spread: float,
    price: float,
    prior_price: float | None,
) -> TickValidation:
    """Reject or clamp garbage prints before they corrupt streaming state."""

    if price <= 0:
        return TickValidation(accepted=False, reject_reason="non_positive_price")

    if prior_price and prior_price > 0:
        ratio = price / prior_price
        if ratio < 0.5 or ratio > 2.0:
            gap_pct = abs(1 - ratio) * 100
            if gap_pct >= settings.corporate_action_gap_pct:
                action = "stock_split" if ratio < 1 else "reverse_split_or_dividend"
                return TickValidation(
                    accepted=True,
                    is_corporate_action=True,
                    corporate_action_type=action,
                    clamped_return_pct=0.0,
                    clamped_volume_z=clamp(volume_z, -settings.max_volume_z, settings.max_volume_z),
                    clamped_spread=clamp(spread, 0, settings.max_spread_pct),
                )

    if abs(return_pct) > settings.max_abs_return_pct:
        return TickValidation(accepted=False, reject_reason="return_out_of_bounds")

    if abs(volume_z) > settings.max_volume_z * 2:
        return TickValidation(accepted=False, reject_reason="volume_z_out_of_bounds")

    if spread > settings.max_spread_pct * 2:
        return TickValidation(accepted=False, reject_reason="spread_out_of_bounds")

    return TickValidation(
        accepted=True,
        clamped_return_pct=clamp(return_pct, -settings.max_abs_return_pct, settings.max_abs_return_pct),
        clamped_volume_z=clamp(volume_z, -settings.max_volume_z, settings.max_volume_z),
        clamped_spread=clamp(spread, 0, settings.max_spread_pct),
    )


def check_out_of_order(tick_at: datetime, last_tick_at: datetime | None) -> bool:
    """Late-arriving tick: arrived after we already processed a newer one."""
    if last_tick_at is None:
        return False
    return tick_at < last_tick_at
