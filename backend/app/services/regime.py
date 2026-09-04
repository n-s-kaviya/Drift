"""Per-instrument streaming regime detection using DBSTREAM / STREAMKMeans."""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from typing import Any

from river import cluster

from app.config import settings
from app.services.ingestion import FeatureVector


@dataclass
class RegimeResult:
    is_change: bool
    event_type: str | None
    title: str | None
    summary: str | None
    severity: float
    cluster_id: int | None
    prev_cluster_id: int | None
    detection_method: str


class RegimeDetector:
    """
    Global per-instrument regime model.

    We use DBSTREAM over CluStream because CluStream's micro-cluster merging is
    O(M²) per merge event. DenStream's predict_one recomputes DBSCAN over all
    micro-clusters on every call. DBSTREAM and STREAMKMeans are more defensible
    for repeated 'has this stock shifted?' checks.
    """

    WARMUP_OBSERVATIONS = settings.min_observations_before_events

    def __init__(self, algo: str | None = None) -> None:
        self.algo = algo or settings.regime_clustering_algo
        self._models: dict[str, Any] = {}
        self._last_cluster: dict[str, int | None] = {}
        self._obs_count: dict[str, int] = {}

    def _create_model(self) -> Any:
        if self.algo == "streamkmeans":
            return cluster.STREAMKMeans(
                chunk_size=50,
                n_clusters=settings.streamkmeans_k,
                halflife=0.5,
                sigma=1.5,
                seed=42,
            )
        if self.algo == "dbstream":
            return cluster.DBSTREAM(
                clustering_threshold=settings.dbstream_epsilon,
                fading_factor=0.01,
                cleanup_interval=4,
                intersection_factor=settings.dbstream_mu,
                minimum_weight=1.0,
            )
        return None

    def _get_model(self, symbol: str) -> Any:
        sym = symbol.upper()
        if sym not in self._models:
            self._models[sym] = self._create_model()
            self._last_cluster.setdefault(sym, None)
            self._obs_count.setdefault(sym, 0)
        return self._models[sym]

    def evaluate(self, features: FeatureVector) -> RegimeResult:
        sym = features.symbol
        self._obs_count[sym] = self._obs_count.get(sym, 0) + 1
        x = dict(zip(["return", "volatility", "volume_z", "spread"], features.as_array()))

        fallback = self._fallback_check(features)
        if self.algo == "fallback" or self._models.get(sym) is None and self.algo not in ("dbstream", "streamkmeans"):
            return fallback

        model = self._get_model(sym)
        prev = self._last_cluster.get(sym)

        try:
            model.learn_one(x)
            pred = model.predict_one(x)
        except Exception:
            return fallback

        cluster_id = int(pred) if pred is not None else None
        self._last_cluster[sym] = cluster_id

        if self._obs_count[sym] < self.WARMUP_OBSERVATIONS:
            return RegimeResult(
                is_change=False,
                event_type=None,
                title=None,
                summary=None,
                severity=0.0,
                cluster_id=cluster_id,
                prev_cluster_id=prev,
                detection_method=self.algo,
            )

        if fallback.is_change and fallback.severity >= 0.7:
            return fallback

        if prev is not None and cluster_id is not None and cluster_id != prev:
            severity = min(1.0, 0.5 + abs(features.return_pct) / 10)
            return RegimeResult(
                is_change=True,
                event_type="regime_shift",
                title=f"{sym} behavior regime shifted",
                summary=(
                    f"Moved from cluster {prev} to {cluster_id}. "
                    f"Return {features.return_pct:+.2f}%, vol {features.volatility:.2f}, "
                    f"volume z={features.volume_z:+.1f}."
                ),
                severity=severity,
                cluster_id=cluster_id,
                prev_cluster_id=prev,
                detection_method=self.algo,
            )

        if cluster_id is None and self._obs_count[sym] >= self.WARMUP_OBSERVATIONS:
            return RegimeResult(
                is_change=True,
                event_type="outlier",
                title=f"{sym} outside established regimes",
                summary=(
                    f"Latest observation doesn't fit known patterns. "
                    f"Return {features.return_pct:+.2f}%, volume z={features.volume_z:+.1f}."
                ),
                severity=min(1.0, 0.6 + abs(features.volume_z) / 5),
                cluster_id=None,
                prev_cluster_id=prev,
                detection_method=self.algo,
            )

        return RegimeResult(
            is_change=False,
            event_type=None,
            title=None,
            summary=None,
            severity=0.0,
            cluster_id=cluster_id,
            prev_cluster_id=prev,
            detection_method=self.algo,
        )

    def _fallback_check(self, features: FeatureVector) -> RegimeResult:
        """Z-score / volume anomaly fallback — reliable MVP baseline."""
        z_thresh = settings.zscore_fallback_threshold
        triggers: list[str] = []
        severity = 0.0

        if abs(features.return_pct) > z_thresh * max(features.volatility, 0.5):
            triggers.append(f"unusual return ({features.return_pct:+.2f}%)")
            severity = max(severity, min(1.0, abs(features.return_pct) / 5))

        if abs(features.volume_z) > z_thresh:
            triggers.append(f"volume spike (z={features.volume_z:+.1f})")
            severity = max(severity, min(1.0, abs(features.volume_z) / 4))

        if abs(features.spread) > z_thresh * 2:
            triggers.append(f"wide spread ({features.spread:.2f}%)")
            severity = max(severity, 0.5)

        if not triggers:
            return RegimeResult(
                is_change=False,
                event_type=None,
                title=None,
                summary=None,
                severity=0.0,
                cluster_id=self._last_cluster.get(features.symbol),
                prev_cluster_id=None,
                detection_method="fallback",
            )

        sym = features.symbol
        event_type = "anomaly"
        if triggers and triggers[0].startswith("volume"):
            event_type = "volume_anomaly"

        return RegimeResult(
            is_change=True,
            event_type=event_type,
            title=f"{sym}: {triggers[0]}",
            summary="; ".join(triggers) + f" (fallback z-score detection).",
            severity=severity,
            cluster_id=self._last_cluster.get(sym),
            prev_cluster_id=None,
            detection_method="fallback",
        )

    def export_state(self, symbol: str) -> dict[str, Any]:
        sym = symbol.upper()
        model = self._models.get(sym)
        state = None
        if model is not None:
            try:
                state = pickle.dumps(model).hex()
            except Exception:
                state = None
        return {
            "symbol": sym,
            "algo": self.algo,
            "state_hex": state,
            "last_cluster_id": self._last_cluster.get(sym),
            "observation_count": self._obs_count.get(sym, 0),
        }

    def import_state(self, symbol: str, state_hex: str | None, last_cluster: int | None, count: int) -> None:
        sym = symbol.upper()
        self._last_cluster[sym] = last_cluster
        self._obs_count[sym] = count
        if state_hex:
            try:
                self._models[sym] = pickle.loads(bytes.fromhex(state_hex))
            except Exception:
                self._models[sym] = self._create_model()
        else:
            self._models[sym] = self._create_model()

    def observation_count(self, symbol: str) -> int:
        return self._obs_count.get(symbol.upper(), 0)

    def tracked_symbols(self) -> list[str]:
        return list(self._models.keys())
