"""Market data: Finnhub (live) → yfinance → demo fallback chain."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

import httpx

from app.config import settings
from app.services.trading_calendar import expected_market_quiet

logger = logging.getLogger(__name__)

LIVE_SOURCES = frozenset({"finnhub", "yfinance"})

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)


@dataclass
class QuoteData:
    symbol: str
    price: float
    change_pct: float
    volume: float
    high: float
    low: float
    open_price: float
    source: str
    tick_at: datetime
    fetched_at: datetime
    is_stale: bool
    trading_status: str = "active"
    recent_split_ratio: float | None = None


class MarketDataService:
    def __init__(self) -> None:
        self._cache: dict[str, QuoteData] = {}
        self._last_success: dict[str, datetime] = {}
        self._demo_ticks: dict[str, int] = {}
        self._finnhub_disabled_until: datetime | None = None
        self._yfinance_disabled_until: datetime | None = None
        self._finnhub_notice_logged = False
        self._yfinance_notice_logged = False
        self._active_source: str = "demo"
        self._lock = Lock()
        self._volume_cache: dict[str, tuple[float, datetime]] = {}

    def fetch_quote(self, symbol: str) -> QuoteData | None:
        sym = symbol.upper()
        provider = settings.market_data_provider.lower()

        with self._lock:
            cached = self._cache.get(sym)
            if cached and cached.source in LIVE_SOURCES:
                if datetime.utcnow() - cached.fetched_at < timedelta(seconds=30):
                    return cached

        if provider == "demo":
            return self._demo_quote(sym)

        if provider in ("auto", "finnhub") and self._should_try_finnhub():
            quote = self._fetch_finnhub(sym)
            if quote:
                return self._store_live(sym, quote)

        if provider in ("auto", "yfinance", "finnhub") and self._should_try_yfinance(provider):
            quote = self._fetch_yfinance(sym)
            if quote:
                with self._lock:
                    self._yfinance_disabled_until = None
                return self._store_live(sym, quote)
            self._record_yfinance_failure()

        with self._lock:
            cached = self._cache.get(sym)
        return self._handle_missing(sym, cached)

    def _store_live(self, sym: str, quote: QuoteData) -> QuoteData:
        with self._lock:
            self._cache[sym] = quote
            self._last_success[sym] = datetime.utcnow()
            self._active_source = quote.source
        return quote

    def _should_try_finnhub(self) -> bool:
        if not settings.finnhub_api_key:
            return False
        with self._lock:
            if self._finnhub_disabled_until and datetime.utcnow() < self._finnhub_disabled_until:
                return False
        return True

    def _should_try_yfinance(self, provider: str) -> bool:
        if provider == "finnhub":
            return False
        if provider == "yfinance":
            return True
        with self._lock:
            if self._yfinance_disabled_until and datetime.utcnow() < self._yfinance_disabled_until:
                return False
        return True

    def _record_finnhub_failure(self) -> None:
        with self._lock:
            self._finnhub_disabled_until = datetime.utcnow() + timedelta(
                minutes=settings.finnhub_retry_minutes
            )
            if not self._finnhub_notice_logged:
                logger.warning(
                    "Finnhub request failed — falling back for %s minutes. Check FINNHUB_API_KEY.",
                    settings.finnhub_retry_minutes,
                )
                self._finnhub_notice_logged = True

    def _record_yfinance_failure(self) -> None:
        with self._lock:
            self._yfinance_disabled_until = datetime.utcnow() + timedelta(
                minutes=settings.yfinance_retry_minutes
            )
            if not self._yfinance_notice_logged:
                logger.warning(
                    "Yahoo Finance unavailable — falling back for %s minutes.",
                    settings.yfinance_retry_minutes,
                )
                self._yfinance_notice_logged = True

    def _fetch_finnhub(self, sym: str) -> QuoteData | None:
        """https://finnhub.io/docs/api/quote"""
        try:
            resp = httpx.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": sym, "token": settings.finnhub_api_key},
                timeout=10.0,
            )
            if resp.status_code != 200:
                self._record_finnhub_failure()
                return None

            data = resp.json()
            price = float(data.get("c") or 0)
            if price <= 0:
                self._record_finnhub_failure()
                return None

            change_pct = float(data.get("dp") or 0)
            prev_close = float(data.get("pc") or 0)
            if change_pct == 0 and prev_close > 0:
                change_pct = ((price - prev_close) / prev_close) * 100

            ts = data.get("t")
            tick_at = (
                datetime.utcfromtimestamp(ts)
                if ts
                else datetime.utcnow()
            )

            with self._lock:
                self._finnhub_disabled_until = None

            volume = self._finnhub_daily_volume(sym)

            return QuoteData(
                symbol=sym,
                price=price,
                change_pct=change_pct,
                volume=volume,
                high=float(data.get("h") or price),
                low=float(data.get("l") or price),
                open_price=float(data.get("o") or price),
                source="finnhub",
                tick_at=tick_at,
                fetched_at=datetime.utcnow(),
                is_stale=False,
                trading_status="active",
            )
        except Exception:
            self._record_finnhub_failure()
            return None

    def _finnhub_daily_volume(self, sym: str) -> float:
        """Finnhub /quote has no volume — fetch latest daily candle (cached 5 min)."""
        with self._lock:
            cached = self._volume_cache.get(sym)
            if cached and datetime.utcnow() - cached[1] < timedelta(minutes=5):
                return cached[0]

        try:
            now = int(datetime.utcnow().timestamp())
            resp = httpx.get(
                "https://finnhub.io/api/v1/stock/candle",
                params={
                    "symbol": sym,
                    "resolution": "D",
                    "from": now - 86400 * 5,
                    "to": now,
                    "token": settings.finnhub_api_key,
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                return 0.0
            data = resp.json()
            if data.get("s") != "ok" or not data.get("v"):
                return 0.0
            volume = float(data["v"][-1])
            with self._lock:
                self._volume_cache[sym] = (volume, datetime.utcnow())
            return volume
        except Exception:
            return 0.0

    def _fetch_yfinance(self, sym: str) -> QuoteData | None:
        try:
            import yfinance as yf
        except ImportError:
            return None

        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d", interval="1d", auto_adjust=True)
            if hist is None or hist.empty:
                hist = yf.download(
                    sym,
                    period="5d",
                    interval="1d",
                    progress=False,
                    threads=False,
                    auto_adjust=True,
                )
            if hist is None or hist.empty:
                return None

            latest = hist.iloc[-1]
            prev_close = float(hist.iloc[-2]["Close"]) if len(hist) > 1 else float(latest["Open"])
            try:
                price = float(ticker.fast_info.get("last_price") or latest["Close"])
            except Exception:
                price = float(latest["Close"])

            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
            tick_at = datetime.utcnow()
            if hasattr(latest.name, "to_pydatetime"):
                tick_at = latest.name.to_pydatetime().replace(tzinfo=None)

            return QuoteData(
                symbol=sym,
                price=price,
                change_pct=change_pct,
                volume=float(latest.get("Volume", 0)),
                high=float(latest["High"]),
                low=float(latest["Low"]),
                open_price=float(latest["Open"]),
                source="yfinance",
                tick_at=tick_at,
                fetched_at=datetime.utcnow(),
                is_stale=False,
                trading_status="active",
                recent_split_ratio=self._detect_recent_split(ticker),
            )
        except Exception:
            return None

    def _detect_recent_split(self, ticker) -> float | None:
        try:
            splits = ticker.splits
            if splits is None or splits.empty:
                return None
            recent = splits.tail(1)
            if recent.empty:
                return None
            split_date = recent.index[-1]
            if (datetime.utcnow() - split_date.to_pydatetime().replace(tzinfo=None)).days <= 3:
                return float(recent.iloc[-1])
        except Exception:
            pass
        return None

    def _handle_missing(self, sym: str, cached: QuoteData | None) -> QuoteData:
        now = datetime.utcnow()
        with self._lock:
            last_ok = self._last_success.get(sym)
            if last_ok and expected_market_quiet(now) and cached and cached.source in LIVE_SOURCES:
                stale = cached
                stale.is_stale = True
                return stale
            if (
                last_ok
                and (now - last_ok) > timedelta(minutes=settings.halt_no_tick_minutes)
                and not expected_market_quiet(now)
                and cached
            ):
                halted = cached
                halted.trading_status = "halted"
                halted.is_stale = True
                return halted
            if cached and cached.source in LIVE_SOURCES:
                stale = cached
                stale.is_stale = True
                return stale
        quote = self._demo_quote(sym)
        with self._lock:
            self._active_source = "demo"
        return quote

    def _demo_quote(self, symbol: str) -> QuoteData:
        import math
        import random
        import time

        sym = symbol.upper()
        with self._lock:
            n = self._demo_ticks.get(sym, 0)
            self._demo_ticks[sym] = n + 1

        seed = sum(ord(c) for c in sym)
        t = time.time() / 10 + n * 0.41
        jitter = random.uniform(-0.8, 0.8)
        noise = math.sin(t + seed) * 2.5 + math.cos(t * 0.7 + seed) * 1.5 + jitter
        base = 50 + (seed % 200)
        price = base * (1 + noise / 100)
        change_pct = noise
        volume_mult = 1 + abs(math.sin(t * 1.3 + seed)) * 0.8
        now = datetime.utcnow()
        return QuoteData(
            symbol=sym,
            price=float(price),
            change_pct=float(change_pct),
            volume=float((1_000_000 + seed * 1000) * volume_mult),
            high=float(price * 1.02),
            low=float(price * 0.98),
            open_price=float(price * (1 - change_pct / 200)),
            source="demo",
            tick_at=now,
            fetched_at=now,
            is_stale=False,
            trading_status="active",
        )

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteData]:
        return [q for sym in symbols if (q := self.fetch_quote(sym)) is not None]

    def active_provider(self) -> str:
        if settings.market_data_provider.lower() == "demo":
            return "demo"
        with self._lock:
            return self._active_source
