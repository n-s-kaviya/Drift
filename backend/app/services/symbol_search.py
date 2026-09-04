"""Global stock symbol search via Finnhub with relevance ranking."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=10)


@dataclass
class SymbolSearchHit:
    symbol: str
    name: str
    type: str | None = None


class SymbolSearchService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[list[SymbolSearchHit], datetime]] = {}
        self._lock = Lock()

    def search(self, query: str, limit: int = 20) -> list[SymbolSearchHit]:
        q = query.strip()
        if not q:
            return []

        cache_key = f"{q.lower()}:{limit}"
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and datetime.utcnow() - cached[1] < CACHE_TTL:
                return cached[0]

        hits: list[SymbolSearchHit] = []
        hits.extend(self._finnhub_search(q))

        # Short ticker-style queries: also try NSE/BSE suffixes and exact symbol.
        if _looks_like_ticker(q):
            upper = q.upper()
            extras = [upper]
            if "." not in upper:
                extras.extend([f"{upper}.NS", f"{upper}.BO"])
            for attempt in extras:
                if attempt.lower() != q.lower():
                    hits.extend(self._finnhub_search(attempt))

        ranked = _rank_hits(q, hits, limit)

        with self._lock:
            self._cache[cache_key] = (ranked, datetime.utcnow())
        return ranked

    def _finnhub_search(self, query: str) -> list[SymbolSearchHit]:
        if not settings.finnhub_api_key:
            return []
        try:
            resp = httpx.get(
                "https://finnhub.io/api/v1/search",
                params={"q": query, "token": settings.finnhub_api_key},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results: list[SymbolSearchHit] = []
            for item in data.get("result") or []:
                sym = (item.get("symbol") or item.get("displaySymbol") or "").strip()
                name = (item.get("description") or sym).strip()
                if sym:
                    results.append(SymbolSearchHit(symbol=sym, name=name, type=item.get("type")))
            return results
        except Exception:
            logger.exception("Finnhub symbol search failed for %r", query)
            return []


def _looks_like_ticker(query: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9.\-]{1,12}", query))


def _rank_hits(query: str, hits: list[SymbolSearchHit], limit: int) -> list[SymbolSearchHit]:
    q_lower = query.lower()
    q_words = [w for w in re.split(r"\s+", q_lower) if w]

    def score(hit: SymbolSearchHit) -> float:
        sym = hit.symbol.lower()
        name = hit.name.lower()
        s = 0.0

        if sym == q_lower:
            s += 100
        base_sym = sym.split(".")[0]
        if base_sym == q_lower:
            s += 85
            if sym.endswith(".ns"):
                s += 55
            elif sym.endswith(".bo"):
                s += 35
        if sym.replace(".", "") == q_lower.replace(".", ""):
            s += 90
        if sym.startswith(q_lower):
            s += 70
        if q_lower in name:
            s += 60
        if all(w in name for w in q_words):
            s += 50
        if any(w in sym for w in q_words):
            s += 30

        # Prefer NSE listings for short Indian-style queries without a dot.
        if "." not in q_lower and len(q_lower) <= 6:
            if sym.endswith(".ns"):
                s += 10
            if sym.endswith(".bo"):
                s += 5

        # For short queries, prefer Indian listings over other exchanges sharing the same prefix.
        if len(q_lower) <= 6 and "." not in q_lower:
            if sym.endswith((".kl", ".to", ".de", ".du", ".f", ".ne", ".sw", ".be", ".hm", ".mu", ".sg")):
                s -= 35

        return s

    seen: set[str] = set()
    unique: list[SymbolSearchHit] = []
    for hit in sorted(hits, key=score, reverse=True):
        key = hit.symbol.upper()
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)

    return unique[:limit]


symbol_search_service = SymbolSearchService()
