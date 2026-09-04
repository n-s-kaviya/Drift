"""Compute how unusual current behavior is vs a stock's own rolling history."""

from __future__ import annotations

from app.services.ingestion import FeatureVector


def abnormality_score(fv: FeatureVector) -> tuple[float, str]:
    """
    Distance from this stock's own normal (not a universal % threshold).
    Returns score 0–1 and a short label.
    """
    ret_sigma = abs(fv.return_pct) / max(fv.volatility, 0.08)
    vol_component = min(1.0, abs(fv.volume_z) / 3.0)
    spread_component = min(1.0, abs(fv.spread) / max(fv.volatility * 3, 0.5))

    raw = (ret_sigma * 0.5 + vol_component * 0.3 + spread_component * 0.2) / 2.5
    score = min(1.0, max(0.0, raw))

    if score < 0.25:
        label = "Within normal"
    elif score < 0.5:
        label = "Mildly unusual"
    elif score < 0.75:
        label = "Notably unusual"
    else:
        label = "Highly unusual"

    return round(score, 3), label
