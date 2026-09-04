"""Per-user online personalization with Hoeffding tree."""

from __future__ import annotations

import pickle
from typing import Any

from river import tree

from app.models import ChangeEvent


class PersonalizationEngine:
    """
    Lightweight per-user classifier predicting whether a user will engage
    with a regime-change alert. Updates one sample at a time — no retraining.
    """

    def __init__(self) -> None:
        self._models: dict[int, tree.HoeffdingTreeClassifier] = {}

    def _get_model(self, user_id: int) -> tree.HoeffdingTreeClassifier:
        if user_id not in self._models:
            self._models[user_id] = tree.HoeffdingTreeClassifier(
                grace_period=20,
                delta=1e-5,
                tau=0.05,
                leaf_prediction="nba",
            )
        return self._models[user_id]

    def _features(self, event: ChangeEvent) -> dict[str, float | int]:
        hour = event.created_at.hour
        return {
            "severity": event.severity,
            "abs_return": abs(event.feature_return),
            "volatility": event.feature_volatility,
            "volume_z": abs(event.feature_volume_z),
            "spread": event.feature_spread,
            "hour": hour,
            "is_regime_shift": 1 if event.event_type == "regime_shift" else 0,
            "is_outlier": 1 if event.event_type == "outlier" else 0,
            "is_anomaly": 1 if event.event_type == "anomaly" else 0,
        }

    def score(self, user_id: int, event: ChangeEvent) -> float:
        model = self._get_model(user_id)
        x = self._features(event)
        try:
            proba = model.predict_proba_one(x)
            if not proba:
                return event.severity
            return float(proba.get(True, proba.get(1, event.severity)))
        except Exception:
            return event.severity

    def learn(self, user_id: int, event: ChangeEvent, engaged: bool) -> None:
        model = self._get_model(user_id)
        x = self._features(event)
        model.learn_one(x, engaged)

    def export_state(self, user_id: int) -> str | None:
        model = self._models.get(user_id)
        if model is None:
            return None
        try:
            return pickle.dumps(model).hex()
        except Exception:
            return None

    def import_state(self, user_id: int, state_hex: str) -> None:
        try:
            self._models[user_id] = pickle.loads(bytes.fromhex(state_hex))
        except Exception:
            self._models[user_id] = self._get_model(user_id)
