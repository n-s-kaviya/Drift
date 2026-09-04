"""Rolling feature computation and staleness tagging."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from app.config import settings


@dataclass
class FeatureVector:
    symbol: str
    return_pct: float
    volatility: float
    volume_z: float
    spread: float
    price: float
    volume: float
    is_stale: bool
    fetched_at: datetime

    def as_array(self) -> list[float]:
        return [self.return_pct, self.volatility, self.volume_z, self.spread]


class RollingFeatureEngine:
    """Maintains per-symbol rolling windows for feature extraction."""

    def __init__(self, window: int = 20) -> None:
        self.window = window
        self._returns: dict[str, deque[float]] = {}
        self._volumes: dict[str, deque[float]] = {}
        self._last_fetch: dict[str, datetime] = {}

    def compute(
        self,
        symbol: str,
        price: float,
        volume: float,
        high: float,
        low: float,
        open_price: float,
        fetched_at: datetime,
        is_stale: bool,
    ) -> FeatureVector:
        sym = symbol.upper()
        returns = self._returns.setdefault(sym, deque(maxlen=self.window))
        volumes = self._volumes.setdefault(sym, deque(maxlen=self.window))

        prev_price = price / (1 + 0.0001) if not returns else price
        if returns:
            prev_price = price / (1 + returns[-1] / 100) if returns[-1] != -100 else price

        return_pct = ((price - open_price) / open_price * 100) if open_price else 0.0
        if len(returns) >= 1:
            last_close_proxy = price / (1 + return_pct / 100) if return_pct != -100 else price
            return_pct = ((price - last_close_proxy) / last_close_proxy * 100) if last_close_proxy else 0.0

        returns.append(return_pct)
        volumes.append(volume)

        vol_arr = np.array(returns)
        volatility = float(np.std(vol_arr)) if len(vol_arr) > 1 else 0.1

        vol_arr_full = np.array(volumes)
        vol_mean = float(np.mean(vol_arr_full)) if len(vol_arr_full) else volume
        vol_std = float(np.std(vol_arr_full)) if len(vol_arr_full) > 1 else 1.0
        volume_z = (volume - vol_mean) / vol_std if vol_std > 0 else 0.0

        spread = ((high - low) / price * 100) if price > 0 else 0.0

        self._last_fetch[sym] = fetched_at
        stale = is_stale or self._is_stale(fetched_at)

        return FeatureVector(
            symbol=sym,
            return_pct=return_pct,
            volatility=volatility,
            volume_z=volume_z,
            spread=spread,
            price=price,
            volume=volume,
            is_stale=stale,
            fetched_at=fetched_at,
        )

    def _is_stale(self, fetched_at: datetime) -> bool:
        age = datetime.utcnow() - fetched_at
        return age > timedelta(seconds=settings.stale_data_threshold_seconds)
