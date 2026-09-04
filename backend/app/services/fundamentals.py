"""Stock history and fundamental metrics via yfinance."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

HISTORY_CACHE_TTL = timedelta(hours=1)
FUNDAMENTALS_CACHE_TTL = timedelta(hours=24)

PERIOD_MAP = {
    "1w": ("5d", "1d"),
    "1m": ("1mo", "1d"),
    "3m": ("3mo", "1d"),
    "6m": ("6mo", "1d"),
    "1y": ("1y", "1d"),
}


@dataclass
class PriceBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class FundamentalsData:
    symbol: str
    company_name: str | None
    sector: str | None
    industry: str | None
    roe: float | None
    debt_to_equity: float | None
    dividend_yield: float | None
    pe_ratio: float | None
    profit_margin: float | None
    beta: float | None
    market_cap: float | None
    revenue_growth: float | None
    source: str


class FundamentalsService:
    def __init__(self) -> None:
        self._history_cache: dict[str, tuple[list[PriceBar], datetime]] = {}
        self._fundamentals_cache: dict[str, tuple[FundamentalsData, datetime]] = {}
        self._lock = Lock()

    def fetch_history(self, symbol: str, period: str = "1m") -> list[PriceBar]:
        sym = symbol.upper()
        cache_key = f"{sym}:{period}"
        with self._lock:
            cached = self._history_cache.get(cache_key)
            if cached and datetime.utcnow() - cached[1] < HISTORY_CACHE_TTL:
                return cached[0]

        bars = self._fetch_yfinance_history(sym, period)
        if not bars:
            bars = self._demo_history(sym, period)

        with self._lock:
            self._history_cache[cache_key] = (bars, datetime.utcnow())
        return bars

    def fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        sym = symbol.upper()
        with self._lock:
            cached = self._fundamentals_cache.get(sym)
            if cached and datetime.utcnow() - cached[1] < FUNDAMENTALS_CACHE_TTL:
                return cached[0]

        data = self._fetch_yfinance_fundamentals(sym)
        if data is None:
            data = self._demo_fundamentals(sym)

        with self._lock:
            self._fundamentals_cache[sym] = (data, datetime.utcnow())
        return data

    def _fetch_yfinance_history(self, sym: str, period: str) -> list[PriceBar]:
        yf_period, interval = PERIOD_MAP.get(period, PERIOD_MAP["1m"])
        try:
            import yfinance as yf
        except ImportError:
            return []

        try:
            hist = yf.Ticker(sym).history(period=yf_period, interval=interval, auto_adjust=True)
            if hist is None or hist.empty:
                return []
            bars: list[PriceBar] = []
            for idx, row in hist.iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                bars.append(
                    PriceBar(
                        date=date_str,
                        open=round(float(row["Open"]), 2),
                        high=round(float(row["High"]), 2),
                        low=round(float(row["Low"]), 2),
                        close=round(float(row["Close"]), 2),
                        volume=float(row.get("Volume", 0)),
                    )
                )
            return bars
        except Exception:
            logger.exception("yfinance history failed for %s", sym)
            return []

    def _fetch_yfinance_fundamentals(self, sym: str) -> FundamentalsData | None:
        try:
            import yfinance as yf
        except ImportError:
            return None

        try:
            info = yf.Ticker(sym).info or {}
            if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
                return None

            roe = info.get("returnOnEquity")
            if roe is not None:
                roe = round(float(roe) * 100, 2)

            div_yield = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
            if div_yield is not None:
                div_yield = round(float(div_yield) * 100, 2)

            profit_margin = info.get("profitMargins")
            if profit_margin is not None:
                profit_margin = round(float(profit_margin) * 100, 2)

            revenue_growth = info.get("revenueGrowth")
            if revenue_growth is not None:
                revenue_growth = round(float(revenue_growth) * 100, 2)

            return FundamentalsData(
                symbol=sym,
                company_name=info.get("longName") or info.get("shortName"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                roe=roe,
                debt_to_equity=round(float(info["debtToEquity"]), 2) if info.get("debtToEquity") is not None else None,
                dividend_yield=div_yield,
                pe_ratio=round(float(info["trailingPE"]), 2) if info.get("trailingPE") is not None else None,
                profit_margin=profit_margin,
                beta=round(float(info["beta"]), 2) if info.get("beta") is not None else None,
                market_cap=float(info["marketCap"]) if info.get("marketCap") is not None else None,
                revenue_growth=revenue_growth,
                source="yfinance",
            )
        except Exception:
            logger.exception("yfinance fundamentals failed for %s", sym)
            return None

    def _demo_history(self, sym: str, period: str) -> list[PriceBar]:
        days = {"1w": 5, "1m": 22, "3m": 66, "6m": 132, "1y": 252}.get(period, 22)
        seed = sum(ord(c) for c in sym)
        base = 50 + (seed % 200)
        bars: list[PriceBar] = []
        price = base
        for i in range(days):
            t = time.time() / 86400 + i * 0.3 + seed
            delta = math.sin(t) * 1.5 + math.cos(t * 0.5) * 0.8
            price = max(1, price * (1 + delta / 100))
            d = (datetime.utcnow() - timedelta(days=days - i)).strftime("%Y-%m-%d")
            bars.append(
                PriceBar(
                    date=d,
                    open=round(price * 0.995, 2),
                    high=round(price * 1.01, 2),
                    low=round(price * 0.99, 2),
                    close=round(price, 2),
                    volume=float(1_000_000 + seed * 100 + i * 5000),
                )
            )
        return bars

    def _demo_fundamentals(self, sym: str) -> FundamentalsData:
        seed = sum(ord(c) for c in sym)
        return FundamentalsData(
            symbol=sym,
            company_name=f"{sym} Inc. (demo)",
            sector="Technology" if seed % 3 == 0 else "Financial Services",
            industry="Software" if seed % 2 == 0 else "Diversified",
            roe=round(8 + (seed % 25), 2),
            debt_to_equity=round(0.3 + (seed % 80) / 10, 2),
            dividend_yield=round((seed % 40) / 10, 2),
            pe_ratio=round(12 + (seed % 30), 2),
            profit_margin=round(5 + (seed % 20), 2),
            beta=round(0.8 + (seed % 12) / 10, 2),
            market_cap=float((seed + 50) * 1_000_000_000),
            revenue_growth=round(-5 + (seed % 30), 2),
            source="demo",
        )


fundamentals_service = FundamentalsService()
