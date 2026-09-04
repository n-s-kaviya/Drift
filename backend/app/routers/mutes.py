from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AlertMute, ChangeEvent, User
from app.schemas import AlertMuteCreate, AlertMuteOut
from app.services.pipeline import pipeline

router = APIRouter(prefix="/api/mutes", tags=["mutes"])


@router.get("", response_model=list[AlertMuteOut])
def list_mutes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(AlertMute).filter(AlertMute.user_id == user.id).order_by(AlertMute.created_at.desc()).all()


@router.post("", response_model=AlertMuteOut, status_code=201)
def create_mute(
    payload: AlertMuteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    symbol = payload.symbol.upper().strip()
    event_type = payload.event_type.strip().lower()
    existing = (
        db.query(AlertMute)
        .filter(
            AlertMute.user_id == user.id,
            AlertMute.symbol == symbol,
            AlertMute.event_type == event_type,
        )
        .first()
    )
    if existing:
        return existing
    mute = AlertMute(user_id=user.id, symbol=symbol, event_type=event_type)
    db.add(mute)
    db.commit()
    db.refresh(mute)

    # Explicit negative signal for personalization (cleaner than implicit dismiss)
    recent = (
        db.query(ChangeEvent)
        .filter(ChangeEvent.symbol == symbol)
        .order_by(ChangeEvent.created_at.desc())
        .first()
    ) if symbol != "*" else (
        db.query(ChangeEvent).order_by(ChangeEvent.created_at.desc()).first()
    )
    if recent:
        pipeline.personalization.learn(user.id, recent, engaged=False)

    return mute


@router.delete("/{mute_id}", status_code=204)
def delete_mute(
    mute_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Idempotent — safe if the client retries after a successful delete."""
    mute = db.get(AlertMute, mute_id)
    if mute is None or mute.user_id != user.id:
        return
    db.delete(mute)
    db.commit()
