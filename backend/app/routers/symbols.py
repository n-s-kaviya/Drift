from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.models import User, WatchlistItem
from app.schemas import FundamentalsOut, PriceBarOut, StockDetailsOut, SymbolSearchResultOut
from app.database import get_db
from sqlalchemy.orm import Session

from app.services.fundamentals import fundamentals_service
from app.services.symbol_search import symbol_search_service

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


def _user_has_symbol(user: User, db: Session, symbol: str) -> bool:
    return (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user.id, WatchlistItem.symbol == symbol.upper())
        .first()
        is not None
    )


@router.get("/search", response_model=list[SymbolSearchResultOut])
def search_symbols(
    q: str = Query(..., min_length=1, max_length=64, description="Company name or ticker"),
    user: User = Depends(get_current_user),
):
    del user  # auth required; search is per-session not per-user data
    hits = symbol_search_service.search(q, limit=24)
    return [SymbolSearchResultOut(symbol=h.symbol, name=h.name, type=h.type) for h in hits]


@router.get("/{symbol}/details", response_model=StockDetailsOut)
def get_stock_details(
    symbol: str,
    period: str = Query("1m", pattern="^(1w|1m|3m|6m|1y)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sym = symbol.upper().strip()
    if not _user_has_symbol(user, db, sym):
        raise HTTPException(status_code=403, detail="Add this symbol to your watchlist first")

    history = fundamentals_service.fetch_history(sym, period)
    fundamentals = fundamentals_service.fetch_fundamentals(sym)

    return StockDetailsOut(
        symbol=sym,
        history=[PriceBarOut.model_validate(b, from_attributes=True) for b in history],
        fundamentals=FundamentalsOut.model_validate(fundamentals, from_attributes=True),
    )
