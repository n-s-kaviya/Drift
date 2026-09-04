from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, WatchlistItem
from app.schemas import WatchlistItemCreate, WatchlistItemOut

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemOut])
def list_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id).order_by(WatchlistItem.added_at).all()


@router.post("", response_model=WatchlistItemOut, status_code=201)
def add_to_watchlist(
    payload: WatchlistItemCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    symbol = payload.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol required")
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user.id, WatchlistItem.symbol == symbol)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Symbol already in watchlist")
    item = WatchlistItem(user_id=user.id, symbol=symbol, notes=payload.notes)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def remove_from_watchlist(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(WatchlistItem, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
