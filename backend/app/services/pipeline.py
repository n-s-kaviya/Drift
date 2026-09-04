"""Orchestrates ingestion → regime detection → event store."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.config import FEATURE_SCHEMA_VERSION, settings
from app.models import ChangeEvent, Instrument, MarketSnapshot
from app.services.cooldown import record_event_fired, should_suppress_event
from app.services.ingestion import RollingFeatureEngine
from app.services.market_data import MarketDataService, QuoteData
from app.services.personalization import PersonalizationEngine
from app.services.regime import RegimeDetector
from app.services.tick_validation import check_out_of_order, validate_and_clamp_tick
from app.services.trading_calendar import is_weekend_or_holiday_gap


class PipelineService:
    def __init__(self) -> None:
        self.market = MarketDataService()
        self.features = RollingFeatureEngine()
        self.regime = RegimeDetector()
        self.personalization = PersonalizationEngine()
        self._loaded = False

    def load_persisted_models(self, db: Session) -> None:
        if self._loaded:
            return
        for row in db.query(Instrument).all():
            if row.feature_schema_version != FEATURE_SCHEMA_VERSION:
                continue
            self.regime.import_state(row.symbol, row.state_json, row.last_cluster_id, row.observation_count)
        self._loaded = True

    def _lock_instrument(self, db: Session, symbol: str) -> Instrument:
        """Row-level lock to prevent lost updates on concurrent ingestion."""
        sym = symbol.upper()
        row = (
            db.query(Instrument)
            .filter(Instrument.symbol == sym)
            .with_for_update()
            .first()
        )
        if row is None:
            row = Instrument(symbol=sym, algo=settings.regime_clustering_algo)
            db.add(row)
            db.flush()
            row = (
                db.query(Instrument)
                .filter(Instrument.symbol == sym)
                .with_for_update()
                .one()
            )
        if row.feature_schema_version != FEATURE_SCHEMA_VERSION:
            row.state_json = ""
            row.observation_count = 0
            row.last_cluster_id = None
            row.feature_schema_version = FEATURE_SCHEMA_VERSION
        return row

    def _persist_regime(self, db: Session, instrument: Instrument, expected_version: int) -> None:
        state = self.regime.export_state(instrument.symbol)
        if instrument.state_version != expected_version:
            db.rollback()
            raise RuntimeError(f"Optimistic lock conflict on {instrument.symbol}")

        instrument.algo = state["algo"]
        instrument.state_json = state.get("state_hex") or ""
        instrument.last_cluster_id = state.get("last_cluster_id")
        instrument.observation_count = state.get("observation_count", 0)
        instrument.state_version = expected_version + 1
        instrument.updated_at = datetime.utcnow()

    def process_symbol(self, db: Session, symbol: str) -> ChangeEvent | None:
        quote = self.market.fetch_quote(symbol)
        if quote is None:
            return None

        instrument = self._lock_instrument(db, symbol)
        version_at_read = instrument.state_version
        prev_price = instrument.last_price

        if instrument.state_json and instrument.observation_count > 0:
            self.regime.import_state(
                instrument.symbol,
                instrument.state_json,
                instrument.last_cluster_id,
                instrument.observation_count,
            )

        is_ooo = check_out_of_order(quote.tick_at, instrument.last_tick_at)
        weekend_gap = is_weekend_or_holiday_gap(quote.tick_at, instrument.last_tick_at)

        if quote.trading_status == "active":
            instrument.trading_status = "active"

        if quote.trading_status == "halted":
            return self._emit_halt_event(db, instrument, quote, version_at_read)

        snapshot = MarketSnapshot(
            symbol=quote.symbol,
            price=quote.price,
            change_pct=quote.change_pct,
            volume=quote.volume,
            high=quote.high,
            low=quote.low,
            open_price=quote.open_price,
            is_stale=quote.is_stale,
            is_out_of_order=is_ooo,
            source=quote.source,
            tick_at=quote.tick_at,
            fetched_at=quote.fetched_at,
        )
        db.add(snapshot)

        if is_ooo:
            instrument.last_processed_at = datetime.utcnow()
            self._persist_regime(db, instrument, version_at_read)
            db.commit()
            return None

        if quote.recent_split_ratio or self._price_gap_corporate_action(quote, instrument):
            return self._emit_corporate_action(db, instrument, quote, version_at_read)

        fv = self.features.compute(
            symbol=quote.symbol,
            price=quote.price,
            volume=quote.volume,
            high=quote.high,
            low=quote.low,
            open_price=quote.open_price,
            fetched_at=quote.fetched_at,
            is_stale=quote.is_stale,
        )

        validation = validate_and_clamp_tick(
            fv.return_pct, fv.volume_z, fv.spread, quote.price, instrument.last_price
        )
        if not validation.accepted:
            instrument.last_processed_at = datetime.utcnow()
            instrument.last_tick_at = quote.tick_at
            instrument.last_price = quote.price
            self._persist_regime(db, instrument, version_at_read)
            db.commit()
            return None

        if validation.clamped_return_pct is not None:
            fv.return_pct = validation.clamped_return_pct
        if validation.clamped_volume_z is not None:
            fv.volume_z = validation.clamped_volume_z
        if validation.clamped_spread is not None:
            fv.spread = validation.clamped_spread

        if validation.is_corporate_action:
            return self._emit_corporate_action(
                db, instrument, quote, version_at_read, validation.corporate_action_type
            )

        if weekend_gap:
            instrument.last_tick_at = quote.tick_at
            instrument.last_price = quote.price
            instrument.last_processed_at = datetime.utcnow()
            self.regime.evaluate(fv)
            self._persist_regime(db, instrument, version_at_read)
            db.commit()
            return None

        result = self.regime.evaluate(fv)
        instrument.last_tick_at = quote.tick_at
        instrument.last_price = quote.price
        instrument.last_processed_at = datetime.utcnow()
        self._persist_regime(db, instrument, version_at_read)

        obs_count = self.regime.observation_count(instrument.symbol)
        primary: ChangeEvent | None = None

        if result.is_change and obs_count >= settings.min_observations_before_events:
            event_type = result.event_type or "unknown"
            if not should_suppress_event(instrument, event_type, result.severity):
                primary = self._build_change_event(quote, result, fv)
                db.add(primary)
                record_event_fired(instrument, event_type)

        volume_event: ChangeEvent | None = None
        if result.event_type != "volume_anomaly":
            volume_event = self._maybe_emit_volume_anomaly(
                db, instrument, quote, fv, obs_count
            )

        if primary or volume_event:
            db.commit()
            if primary:
                db.refresh(primary)
            return primary or volume_event

        price_event = self._maybe_emit_price_move(db, instrument, quote, fv, prev_price)
        if price_event:
            db.commit()
            db.refresh(price_event)
            return price_event

        db.commit()
        return None

    def _build_change_event(self, quote: QuoteData, result, fv) -> ChangeEvent:
        return ChangeEvent(
            symbol=quote.symbol,
            event_type=result.event_type or "unknown",
            title=result.title or f"{quote.symbol} changed",
            summary=result.summary or "",
            severity=result.severity,
            cluster_id=result.cluster_id,
            prev_cluster_id=result.prev_cluster_id,
            feature_return=fv.return_pct,
            feature_volatility=fv.volatility,
            feature_volume_z=fv.volume_z,
            feature_spread=fv.spread,
            detection_method=result.detection_method,
            is_stale_context=fv.is_stale,
            is_out_of_order=False,
        )

    def _maybe_emit_price_move(
        self,
        db: Session,
        instrument: Instrument,
        quote: QuoteData,
        fv,
        prev_price: float | None,
    ) -> ChangeEvent | None:
        """Surface meaningful tick-to-tick moves — what users see in the price table."""
        event_type = "price_move"
        if should_suppress_event(instrument, event_type, 0.5):
            return None

        move_pct = quote.change_pct
        if prev_price and prev_price > 0:
            tick_move = (quote.price - prev_price) / prev_price * 100
            if abs(tick_move) >= abs(move_pct):
                move_pct = tick_move

        if abs(move_pct) < settings.price_move_threshold_pct:
            return None

        severity = min(1.0, max(0.35, abs(move_pct) / 2.5))
        direction = "up" if move_pct > 0 else "down"
        stale_note = " (demo/simulated data)" if quote.source in ("mock", "demo") else ""

        event = ChangeEvent(
            symbol=quote.symbol,
            event_type=event_type,
            title=f"{quote.symbol} moved {move_pct:+.2f}%",
            summary=(
                f"Price moved {direction} {abs(move_pct):.2f}% since last check "
                f"(${quote.price:.2f} now).{stale_note}"
            ),
            severity=severity,
            cluster_id=instrument.last_cluster_id,
            prev_cluster_id=None,
            feature_return=fv.return_pct,
            feature_volatility=fv.volatility,
            feature_volume_z=fv.volume_z,
            feature_spread=fv.spread,
            detection_method="price_move",
            is_stale_context=quote.source in ("mock", "demo"),
            is_out_of_order=False,
        )
        db.add(event)
        record_event_fired(instrument, event_type)
        return event

    def _maybe_emit_volume_anomaly(
        self,
        db: Session,
        instrument: Instrument,
        quote: QuoteData,
        fv,
        obs_count: int,
    ) -> ChangeEvent | None:
        """Surface unusual volume separately from regime shifts."""
        event_type = "volume_anomaly"
        if obs_count < settings.min_observations_before_events:
            return None
        if quote.volume <= 0:
            return None
        if abs(fv.volume_z) < settings.volume_anomaly_threshold_z:
            return None
        if should_suppress_event(instrument, event_type, abs(fv.volume_z) / 4):
            return None

        severity = min(1.0, max(0.4, abs(fv.volume_z) / 4))
        event = ChangeEvent(
            symbol=quote.symbol,
            event_type=event_type,
            title=f"{quote.symbol} unusual volume (z={fv.volume_z:+.1f})",
            summary=(
                f"Trading volume is {abs(fv.volume_z):.1f} standard deviations from "
                f"this stock's recent average."
            ),
            severity=severity,
            cluster_id=instrument.last_cluster_id,
            prev_cluster_id=None,
            feature_return=fv.return_pct,
            feature_volatility=fv.volatility,
            feature_volume_z=fv.volume_z,
            feature_spread=fv.spread,
            detection_method="volume_z",
            is_stale_context=quote.is_stale,
            is_out_of_order=False,
        )
        db.add(event)
        record_event_fired(instrument, event_type)
        return event

    def _price_gap_corporate_action(self, quote: QuoteData, instrument: Instrument) -> bool:
        if instrument.last_price is None or instrument.last_price <= 0:
            return False
        ratio = quote.price / instrument.last_price
        return ratio < 0.55 or ratio > 1.8

    def _emit_corporate_action(
        self,
        db: Session,
        instrument: Instrument,
        quote: QuoteData,
        version: int,
        action_type: str | None = None,
    ) -> ChangeEvent | None:
        action = action_type or ("stock_split" if quote.recent_split_ratio else "price_gap")
        title = f"{quote.symbol}: corporate action detected ({action.replace('_', ' ')})"
        summary = (
            "Large overnight price gap consistent with a split, reverse split, or dividend adjustment. "
            "Not treated as a regime shift — adjust holdings before interpreting alerts."
        )
        if quote.recent_split_ratio:
            summary += f" Recent split ratio: {quote.recent_split_ratio}:1."

        event = ChangeEvent(
            symbol=quote.symbol,
            event_type="corporate_action",
            title=title,
            summary=summary,
            severity=0.9,
            cluster_id=None,
            prev_cluster_id=instrument.last_cluster_id,
            feature_return=0.0,
            feature_volatility=0.0,
            feature_volume_z=0.0,
            feature_spread=0.0,
            detection_method="corporate_action",
            is_stale_context=quote.is_stale,
        )
        instrument.last_price = quote.price
        instrument.last_tick_at = quote.tick_at
        instrument.last_processed_at = datetime.utcnow()
        self._persist_regime(db, instrument, version)
        db.add(event)
        record_event_fired(instrument, "corporate_action")
        db.commit()
        db.refresh(event)
        return event

    def _emit_halt_event(
        self,
        db: Session,
        instrument: Instrument,
        quote: QuoteData,
        version: int,
    ) -> ChangeEvent | None:
        if instrument.trading_status == "halted":
            db.commit()
            return None

        event = ChangeEvent(
            symbol=quote.symbol,
            event_type="trading_halted",
            title=f"{quote.symbol}: trading halted or no new ticks",
            summary=(
                "No fresh market data during regular hours. Last price may be stale — "
                "this is not the same as 'no change'."
            ),
            severity=0.85,
            cluster_id=None,
            prev_cluster_id=None,
            feature_return=0.0,
            feature_volatility=0.0,
            feature_volume_z=0.0,
            feature_spread=0.0,
            detection_method="halt_detection",
            is_stale_context=True,
        )
        instrument.trading_status = "halted"
        instrument.last_processed_at = datetime.utcnow()
        self._persist_regime(db, instrument, version)
        db.add(event)
        record_event_fired(instrument, "trading_halted")
        db.commit()
        db.refresh(event)
        return event

    def process_symbols(self, db: Session, symbols: list[str]) -> list[ChangeEvent]:
        self.load_persisted_models(db)
        events: list[ChangeEvent] = []
        for sym in set(s.upper() for s in symbols):
            try:
                event = self.process_symbol(db, sym)
                if event:
                    events.append(event)
            except RuntimeError:
                db.rollback()
                continue
        return events


pipeline = PipelineService()
