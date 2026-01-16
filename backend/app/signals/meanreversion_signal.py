"""Mean reversion signal implementation."""

import numpy as np
import pandas as pd
from datetime import datetime, timezone

from app.signals.base import Signal, SignalResult


class MeanReversionSignal(Signal):
    """Signal based on mean reversion features."""

    def __init__(self):
        """Initialize mean reversion signal."""
        super().__init__("Pullback vs average")

    def compute(
        self, bars: pd.DataFrame, features: pd.DataFrame, current_date: pd.Timestamp
    ) -> SignalResult:
        """
        Compute mean reversion signal.

        Negative z-score indicates oversold (buy signal).
        Positive z-score indicates overbought (sell signal).
        """
        # Get features for current date
        if current_date not in features.index:
            available_features = features[features.index <= current_date]
            if available_features.empty:
                return SignalResult(
                    score=0.0,
                    confidence=0.0,
                    name=self.name,
                    timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                    description="Insufficient data for mean reversion signal",
                )
            current_features = available_features.iloc[-1]
        else:
            current_features = features.loc[current_date]

        # Primary feature: z-score vs MA20
        zscore = None
        if "zscore_close_vs_ma20" in current_features.index:
            zscore_val = current_features["zscore_close_vs_ma20"]
            if pd.notna(zscore_val):
                zscore = zscore_val

        if zscore is None:
            # Fallback to Bollinger distance
            if "bollinger_distance" in current_features.index:
                bollinger = current_features["bollinger_distance"]
                if pd.notna(bollinger):
                    # Convert Bollinger distance to z-score-like metric
                    zscore = bollinger * 2.0  # Approximate conversion

        if zscore is None:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                name=self.name,
                timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                description="Missing mean reversion features",
            )

        # Score: negative of z-score (mean reversion assumption)
        # High z-score (overbought) -> negative score (sell signal)
        # Low z-score (oversold) -> positive score (buy signal)
        score = -zscore

        # Normalize to [-1, 1] using tanh
        score = np.tanh(score / 2.0)  # Divide by 2 to make it less extreme
        score = np.clip(score, -1.0, 1.0)

        # Confidence: absolute z-score, capped at 1.0
        confidence = min(abs(zscore) / 3.0, 1.0)  # z-score of 3 = max confidence

        # Add reversal features if available
        reversal_contrib = 0.0
        reversal_count = 0

        if "reversal_1d" in current_features.index:
            rev1 = current_features["reversal_1d"]
            if pd.notna(rev1):
                reversal_contrib += rev1
                reversal_count += 1

        if "reversal_3d" in current_features.index:
            rev3 = current_features["reversal_3d"]
            if pd.notna(rev3):
                reversal_contrib += rev3
                reversal_count += 1

        if reversal_count > 0:
            reversal_avg = reversal_contrib / reversal_count
            # Adjust score slightly based on reversal signals
            score = 0.7 * score + 0.3 * np.tanh(reversal_avg * 10)
            score = np.clip(score, -1.0, 1.0)

        # Build specific reason with numeric values
        reason_parts = []
        components = {}
        
        # Primary z-score
        if "zscore_close_vs_ma20" in current_features.index:
            zscore_val = current_features["zscore_close_vs_ma20"]
            if pd.notna(zscore_val):
                components["zscore_close_vs_ma20"] = float(zscore_val)
                reason_parts.append(f"zscore={zscore_val:.2f} vs MA20")
        
        # Bollinger distance if used
        if "bollinger_distance" in current_features.index:
            bollinger = current_features["bollinger_distance"]
            if pd.notna(bollinger) and abs(bollinger) > 0.1:
                components["bollinger_distance"] = float(bollinger)
                reason_parts.append(f"Bollinger_dist={bollinger:.3f}")
        
        if not reason_parts:
            reason = f"zscore={zscore:.2f}"
        else:
            reason = ", ".join(reason_parts)
        
        # Description
        zscore_str = f"z-score={zscore:.2f}"
        if zscore > 1.0:
            regime = "overbought (sell signal)"
        elif zscore < -1.0:
            regime = "oversold (buy signal)"
        else:
            regime = "neutral"
        description = f"Reversion signal ({regime}): Is price stretched away from its typical range? {zscore_str}, score={score:.2f}"

        return SignalResult(
            score=float(score),
            confidence=float(confidence),
            name=self.name,
            timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
            description=description,
            reason=reason,
            components=components if components else None,
        )
