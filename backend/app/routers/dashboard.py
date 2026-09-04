from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AlertFeedback, AlertMute, ChangeEvent, Instrument, User, WatchlistItem
from app.schemas import (
    AlertMuteOut,
    ChangeEventOut,
    DashboardOut,
    FeedItemOut,
    FeedbackCreate,
    MarketQuoteOut,
)
from app.services.abnormality import abnormality_score
from app.services.alert_bundling import bundle_events
from app.services.event_copy import plain_english_title, plain_english_why
from app.services.event_ranking import is_bootstrap_phase, rank_events_for_user
from app.services.mute_filter import is_event_muted
from app.config import settings
from app.services.pipeline import pipeline
from app.services.trust_label import format_trust_label

from app.services.feed_filter import collapse_superseded_events, filter_feed_event_types

router = APIRouter(prefix="/api", tags=["dashboard"])


def _added_at_by_symbol(items: list[WatchlistItem]) -> dict[str, datetime]:
    return {item.symbol: item.added_at for item in items}


def _is_new_event(event: ChangeEvent, user: User, added_at: datetime | None) -> bool:
    if user.last_visit_at is None:
        return False
    since = max(user.last_visit_at, added_at) if added_at else user.last_visit_at
    return event.created_at > since


def _fetch_feed_events(db: Session, symbols: list[str]) -> list[ChangeEvent]:
    if not symbols:
        return []

    lookback = datetime.utcnow() - timedelta(hours=settings.feed_lookback_hours)
    return (
        db.query(ChangeEvent)
        .filter(
            ChangeEvent.symbol.in_(symbols),
            ChangeEvent.created_at > lookback,
        )
        .order_by(ChangeEvent.created_at.desc())
        .limit(100)
        .all()
    )


def _event_to_out(
    e: ChangeEvent,
    instrument: Instrument | None,
    feedback_map: dict[int, bool],
    score: float,
    forced: bool,
    muted: bool,
    is_new: bool,
) -> ChangeEventOut:
    return ChangeEventOut(
        id=e.id,
        symbol=e.symbol,
        event_type=e.event_type,
        title=plain_english_title(e),
        summary=e.summary,
        why_plain=plain_english_why(e, instrument),
        severity=e.severity,
        cluster_id=e.cluster_id,
        prev_cluster_id=e.prev_cluster_id,
        detection_method=e.detection_method,
        is_stale_context=e.is_stale_context,
        is_out_of_order=e.is_out_of_order,
        created_at=e.created_at,
        relevance_score=round(score, 3),
        user_engaged=feedback_map.get(e.id),
        personalization_forced=forced,
        is_muted_type=muted,
        is_new=is_new,
    )


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    light: bool = Query(False, description="Skip ML pipeline — refresh quotes only"),
):
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id).all()
    symbols = [i.symbol for i in items]

    if symbols and not light:
        pipeline.process_symbols(db, symbols)

    quotes: list[MarketQuoteOut] = []
    for sym in symbols:
        q = pipeline.market.fetch_quote(sym)
        if not q:
            continue
        fv = pipeline.features.compute(
            symbol=q.symbol,
            price=q.price,
            volume=q.volume,
            high=q.high,
            low=q.low,
            open_price=q.open_price,
            fetched_at=q.fetched_at,
            is_stale=q.is_stale,
        )
        abn_score, abn_label = abnormality_score(fv)
        quotes.append(
            MarketQuoteOut(
                symbol=q.symbol,
                price=q.price,
                change_pct=q.change_pct,
                volume=q.volume,
                high=q.high,
                low=q.low,
                open_price=q.open_price,
                is_stale=q.is_stale,
                source=q.source,
                fetched_at=q.fetched_at,
                trading_status=q.trading_status,
                trust_label=format_trust_label(q.source, q.is_stale, q.fetched_at, q.trading_status),
                abnormality_score=abn_score,
                abnormality_label=abn_label,
            )
        )

    since = user.last_visit_at
    added_map = _added_at_by_symbol(items)
    raw_events = _fetch_feed_events(db, symbols)
    mutes = db.query(AlertMute).filter(AlertMute.user_id == user.id).all()
    events = [e for e in raw_events if not is_event_muted(e, mutes)]
    events = filter_feed_event_types(events)
    events = collapse_superseded_events(events)

    feedback_rows = db.query(AlertFeedback).filter(AlertFeedback.user_id == user.id).all()
    feedback_map = {f.event_id: f.engaged for f in feedback_rows}
    feedback_count = len(feedback_rows)

    ranked = rank_events_for_user(user, events, pipeline.personalization, feedback_count)

    instruments = {
        i.symbol: i for i in db.query(Instrument).filter(Instrument.symbol.in_(symbols)).all()
    } if symbols else {}

    event_out: list[ChangeEventOut] = []
    for e, score, forced in ranked[:50]:
        inst = instruments.get(e.symbol)
        event_out.append(
            _event_to_out(
                e,
                inst,
                feedback_map,
                score,
                forced,
                is_event_muted(e, mutes),
                _is_new_event(e, user, added_map.get(e.symbol)),
            )
        )

    bundled = bundle_events(event_out)
    feed = [FeedItemOut(**item) for item in bundled]

    unread = sum(1 for e in event_out if e.is_new)

    return DashboardOut(
        last_visit_at=since,
        feed=feed,
        watchlist=items,
        quotes=quotes,
        mutes=[AlertMuteOut.model_validate(m) for m in mutes],
        unread_event_count=unread,
        in_bootstrap_phase=is_bootstrap_phase(user, feedback_count),
        quotes_updated_at=datetime.utcnow(),
    )


@router.get("/events", response_model=list[ChangeEventOut])
def list_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id).all()
    if not items:
        return []
    symbols = [i.symbol for i in items]
    events = (
        db.query(ChangeEvent)
        .filter(ChangeEvent.symbol.in_(symbols))
        .order_by(ChangeEvent.created_at.desc())
        .limit(100)
        .all()
    )
    instruments = {i.symbol: i for i in db.query(Instrument).filter(Instrument.symbol.in_(symbols)).all()}
    return [
        ChangeEventOut(
            id=e.id,
            symbol=e.symbol,
            event_type=e.event_type,
            title=plain_english_title(e),
            summary=e.summary,
            why_plain=plain_english_why(e, instruments.get(e.symbol)),
            severity=e.severity,
            cluster_id=e.cluster_id,
            prev_cluster_id=e.prev_cluster_id,
            detection_method=e.detection_method,
            is_stale_context=e.is_stale_context,
            is_out_of_order=e.is_out_of_order,
            created_at=e.created_at,
            relevance_score=round(pipeline.personalization.score(user.id, e), 3),
        )
        for e in events
    ]


@router.post("/visit", status_code=200)
def mark_visit(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.last_visit_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/feedback", status_code=201)
def submit_feedback(
    payload: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = db.get(ChangeEvent, payload.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    existing = (
        db.query(AlertFeedback)
        .filter(AlertFeedback.user_id == user.id, AlertFeedback.event_id == payload.event_id)
        .first()
    )
    if existing:
        existing.engaged = payload.engaged
    else:
        db.add(AlertFeedback(user_id=user.id, event_id=payload.event_id, engaged=payload.engaged))

    pipeline.personalization.learn(user.id, event, payload.engaged)
    db.commit()
    return {"ok": True}


@router.delete("/feedback/{event_id}", status_code=204)
def clear_feedback(
    event_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(AlertFeedback)
        .filter(AlertFeedback.user_id == user.id, AlertFeedback.event_id == event_id)
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
