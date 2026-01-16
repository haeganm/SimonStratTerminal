"""Momentum signal implementation."""

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from scipy import stats

from app.signals.base import Signal, SignalResult


class MomentumSignal(Signal):
    """Signal based on momentum features."""

    def __init__(self):
        """Initialize momentum signal."""
        super().__init__("Trend (recent price strength)")

    def compute(
        self, bars: pd.DataFrame, features: pd.DataFrame, current_date: pd.Timestamp
    ) -> SignalResult:
        """
        Compute momentum signal.

        Combines multiple momentum features into a single score.
        """
        # Get features for current date
        if current_date not in features.index:
            # Use most recent available data
            available_features = features[features.index <= current_date]
            if available_features.empty:
                return SignalResult(
                    score=0.0,
                    confidence=0.0,
                    name=self.name,
                    timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                    description="Insufficient data for momentum signal",
                )
            current_features = available_features.iloc[-1]
        else:
            current_features = features.loc[current_date]

        # Extract momentum features
        momentum_features = {}
        for feat_name in [
            "returns_5d",
            "returns_20d",
            "returns_60d",
            "ma_slope_20",
            "ma_slope_60",
            "breakout_distance",
        ]:
            if feat_name in current_features.index:
                momentum_features[feat_name] = current_features[feat_name]

        if not momentum_features:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                name=self.name,
                timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                description="Missing momentum features",
            )

        # Convert to array, handling NaN
        values = np.array([v for v in momentum_features.values() if pd.notna(v)])

        if len(values) == 0:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                name=self.name,
                timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                description="All momentum features are NaN",
            )

        # Compute score: weighted average (equal weights for now)
        # Normalize each feature to [-1, 1] range using tanh
        normalized_values = np.tanh(values * 10)  # Scale factor to emphasize extremes
        score = np.mean(normalized_values)
        score = np.clip(score, -1.0, 1.0)

        # Compute confidence based on:
        # 1. Strength of trend (absolute score)
        # 2. Consistency across features (low std = high confidence)
        abs_score = abs(score)
        consistency = 1.0 - min(np.std(normalized_values) / 2.0, 1.0)
        confidence = (abs_score * 0.7 + consistency * 0.3)
        confidence = np.clip(confidence, 0.0, 1.0)

        # Build specific reason with numeric values
        reason_parts = []
        components = {}
        
        # Add MA slope info if available
        if "ma_slope_20" in momentum_features and pd.notna(momentum_features["ma_slope_20"]):
            ma20_slope = momentum_features["ma_slope_20"]
            components["ma_slope_20"] = float(ma20_slope)
            if ma20_slope > 0.001:
                reason_parts.append(f"MA20 slope={ma20_slope:.4f}")
            elif ma20_slope < -0.001:
                reason_parts.append(f"MA20 slope={ma20_slope:.4f}")
        
        if "ma_slope_60" in momentum_features and pd.notna(momentum_features["ma_slope_60"]):
            ma60_slope = momentum_features["ma_slope_60"]
            components["ma_slope_60"] = float(ma60_slope)
            if abs(ma60_slope) > 0.001:
                reason_parts.append(f"MA60 slope={ma60_slope:.4f}")
        
        # Add breakout distance if available
        if "breakout_distance" in momentum_features and pd.notna(momentum_features["breakout_distance"]):
            breakout = momentum_features["breakout_distance"]
            components["breakout_distance"] = float(breakout)
            if abs(breakout) > 0.01:
                reason_parts.append(f"breakout_dist={breakout:.3f}")
        
        # Add returns info
        if "returns_20d" in momentum_features and pd.notna(momentum_features["returns_20d"]):
            ret20 = momentum_features["returns_20d"]
            components["returns_20d"] = float(ret20)
            if abs(ret20) > 0.01:
                reason_parts.append(f"20d_return={ret20:.3f}")
        
        if not reason_parts:
            reason = f"Based on {len(values)} momentum features"
        else:
            reason = ", ".join(reason_parts[:3])  # Limit to top 3 reasons
        
        # Description
        direction = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
        description = f"Trend signal ({direction}): Is price gaining strength vs recent history? Score={score:.2f}, based on {len(values)} features"

        return SignalResult(
            score=float(score),
            confidence=float(confidence),
            name=self.name,
            timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
            description=description,
            reason=reason,
            components=components if components else None,
        )
