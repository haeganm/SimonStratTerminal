"""Ensemble model for combining signals."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.signals.base import SignalResult


@dataclass
class Forecast:
    """Trading forecast from ensemble model."""

    direction: str  # 'long', 'flat', 'short'
    confidence: float  # 0.0 to 1.0
    suggested_position_size: Optional[float] = None  # 0.0 to 1.0 (fraction of portfolio)
    explanation: Optional[dict] = None  # Top contributors, regime filter, etc.


class EnsembleModel:
    """Ensemble model that combines multiple signals with weights."""

    def __init__(
        self,
        signal_weights: Optional[dict[str, float]] = None,
        regime_weight: float = 0.3,
        threshold: float = 0.1,
    ):
        """
        Initialize ensemble model.

        Args:
            signal_weights: Dictionary mapping signal names to weights (default: equal weights)
            regime_weight: Weight for regime filter (acts as scaler/multiplier)
            threshold: Minimum weighted score to take a position (default: 0.1)
        """
        self.signal_weights = signal_weights or {}
        self.regime_weight = regime_weight
        self.threshold = threshold

    def combine(self, signals: list[SignalResult]) -> Forecast:
        """
        Combine signals into a single forecast.

        Args:
            signals: List of SignalResult objects

        Returns:
            Forecast with direction, confidence, position size, explanation
        """
        if not signals:
            return Forecast(
                direction="flat",
                confidence=0.0,
                explanation={"top_contributors": [], "regime_filter": "No signals available"},
            )

        # Separate regime filter from trading signals
        trading_signals = []
        regime_signal = None

        for signal in signals:
            if signal.name == "Regime Filter":
                regime_signal = signal
            else:
                trading_signals.append(signal)

        # Get weights for trading signals (default: equal weights)
        if not self.signal_weights:
            # Equal weights
            num_signals = len(trading_signals)
            if num_signals > 0:
                weight_per_signal = 1.0 / num_signals
                weights = {s.name: weight_per_signal for s in trading_signals}
            else:
                weights = {}
        else:
            weights = self.signal_weights.copy()
            # Normalize weights
            total_weight = sum(weights.values())
            if total_weight > 0:
                weights = {k: v / total_weight for k, v in weights.items()}

        # Compute weighted sum of signal scores
        weighted_sum = 0.0
        contributors = []

        for signal in trading_signals:
            weight = weights.get(signal.name, 0.0)
            contribution = weight * signal.score * signal.confidence
            weighted_sum += contribution
            contributors.append(
                {
                    "signal": signal.name,
                    "contribution": contribution,
                    "score": signal.score,
                    "confidence": signal.confidence,
                }
            )

        # Apply regime filter as scaler
        regime_multiplier = 1.0
        regime_description = "Unknown regime"

        if regime_signal:
            # Regime filter acts as confidence multiplier
            # High regime score (1.0) = no penalty
            # Low regime score (0.0) = reduce confidence significantly
            regime_multiplier = regime_signal.score  # Already in [0, 1]
            regime_description = regime_signal.description or "Unknown regime"

            # Also adjust weighted sum slightly based on regime
            if regime_multiplier < 0.5:
                weighted_sum *= 0.5  # Penalty for unfavorable regime

        # Determine direction
        if weighted_sum > self.threshold:
            direction = "long"
        elif weighted_sum < -self.threshold:
            direction = "short"
        else:
            direction = "flat"

        # Compute confidence
        # Base confidence: weighted average of signal confidences
        if trading_signals:
            base_confidence = sum(s.confidence * weights.get(s.name, 0.0) for s in trading_signals)
        else:
            base_confidence = 0.0

        # Apply regime multiplier
        confidence = base_confidence * (0.7 + 0.3 * regime_multiplier)
        confidence = min(confidence, 1.0)
        confidence = max(confidence, 0.0)

        # Position size suggestion (proportional to confidence and magnitude)
        if direction != "flat":
            magnitude = abs(weighted_sum)
            suggested_position_size = min(confidence * magnitude, 1.0)
        else:
            suggested_position_size = 0.0

        # Sort contributors by absolute contribution
        contributors_sorted = sorted(
            contributors, key=lambda x: abs(x["contribution"]), reverse=True
        )

        # Format top contributors for explanation
        top_contributors = [
            {"signal": c["signal"], "contribution": c["contribution"]}
            for c in contributors_sorted[:5]
        ]

        explanation = {
            "top_contributors": top_contributors,
            "regime_filter": regime_description,
        }

        return Forecast(
            direction=direction,
            confidence=confidence,
            suggested_position_size=suggested_position_size,
            explanation=explanation,
        )

    def update_weights(self, new_weights: dict[str, float]) -> None:
        """
        Update signal weights.

        Args:
            new_weights: Dictionary mapping signal names to new weights
        """
        self.signal_weights.update(new_weights)

    def set_threshold(self, threshold: float) -> None:
        """
        Set minimum threshold for taking positions.

        Args:
            threshold: Minimum weighted score (0.0 to 1.0)
        """
        self.threshold = threshold
