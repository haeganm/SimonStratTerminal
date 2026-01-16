"""Regime filter signal implementation."""

import numpy as np
import pandas as pd
from datetime import datetime, timezone

from app.signals.base import Signal, SignalResult


class RegimeFilterSignal(Signal):
    """
    Regime filter signal.

    Acts as a gate/scaler based on volatility regime and trend clarity.
    Returns score of 1.0 when regime is favorable, 0.0 when unfavorable.
    Confidence reflects regime clarity.
    """

    def __init__(self):
        """Initialize regime filter signal."""
        super().__init__("Market Regime (trend/vol filter)")

    def compute(
        self, bars: pd.DataFrame, features: pd.DataFrame, current_date: pd.Timestamp
    ) -> SignalResult:
        """
        Compute regime filter signal.

        Favorable regimes:
        - Moderate volatility (not too high, not too low)
        - Clear trend (high trend_vs_chop)

        Unfavorable regimes:
        - Extreme volatility (very high or very low)
        - Choppy/no trend (low trend_vs_chop)
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
                    description="Insufficient data for regime filter",
                )
            current_features = available_features.iloc[-1]
        else:
            current_features = features.loc[current_date]

        # Get volatility and trend features
        vol = None
        if "realized_vol_20d" in current_features.index:
            vol_val = current_features["realized_vol_20d"]
            if pd.notna(vol_val):
                vol = vol_val

        trend_strength = None
        if "trend_vs_chop" in current_features.index:
            trend_val = current_features["trend_vs_chop"]
            if pd.notna(trend_val):
                trend_strength = abs(trend_val)  # Absolute trend strength

        vol_change = None
        if "vol_change" in current_features.index:
            vol_change_val = current_features["vol_change"]
            if pd.notna(vol_change_val):
                vol_change = vol_change_val

        if vol is None and trend_strength is None:
            return SignalResult(
                score=0.5,  # Neutral/default
                confidence=0.0,
                name=self.name,
                timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                description="Missing regime features",
            )

        # Volatility regime scoring
        # Favorable: moderate volatility (0.1 to 0.5 annualized)
        vol_score = 1.0
        if vol is not None:
            if vol < 0.05:  # Too low volatility (stagnant)
                vol_score = 0.3
            elif vol > 0.8:  # Too high volatility (crisis/unstable)
                vol_score = 0.2
            elif 0.1 <= vol <= 0.5:  # Sweet spot
                vol_score = 1.0
            else:
                vol_score = 0.6  # Acceptable but not ideal

        # Trend strength scoring
        # Favorable: clear trend (high absolute trend_vs_chop)
        trend_score = 1.0
        if trend_strength is not None:
            # Normalize to [0, 1] where 0.5+ R-squared = good
            trend_score = min(trend_strength * 2.0, 1.0)  # R-squared of 0.5 = score of 1.0

        # Volatility change scoring
        # Favorable: decreasing volatility (stability)
        vol_change_score = 1.0
        if vol_change is not None:
            if vol_change < -0.2:  # Volatility decreasing significantly
                vol_change_score = 1.2  # Bonus
            elif vol_change > 0.3:  # Volatility increasing significantly
                vol_change_score = 0.5  # Penalty

        # Combine scores
        scores = [vol_score, trend_score, vol_change_score]
        valid_scores = [s for s in scores if s is not None]
        if not valid_scores:
            final_score = 0.5
        else:
            final_score = np.mean(valid_scores)
            final_score = np.clip(final_score, 0.0, 1.0)  # Clip to [0, 1]

        # Confidence: how clear is the regime?
        # High confidence when features agree (vol is moderate AND trend is clear)
        confidence = 0.5  # Base confidence
        if vol is not None and trend_strength is not None:
            # High confidence when both vol and trend are favorable
            if 0.15 <= vol <= 0.4 and trend_strength > 0.3:
                confidence = 0.9
            elif vol_score < 0.4 or trend_score < 0.3:
                confidence = 0.3
            else:
                confidence = 0.6

        # Description
        regime_desc = []
        if vol is not None:
            if vol < 0.1:
                regime_desc.append("low vol")
            elif vol > 0.6:
                regime_desc.append("high vol")
            else:
                regime_desc.append("moderate vol")
        if trend_strength is not None:
            if trend_strength > 0.5:
                regime_desc.append("strong trend")
            elif trend_strength < 0.2:
                regime_desc.append("choppy")
            else:
                regime_desc.append("weak trend")

        # Build specific reason with numeric values
        reason_parts = []
        components = {}
        
        if vol is not None:
            components["realized_vol_20d"] = float(vol)
            reason_parts.append(f"vol={vol:.3f}")
        
        if trend_strength is not None:
            components["trend_vs_chop"] = float(trend_strength)
            reason_parts.append(f"trend_strength={trend_strength:.3f}")
        
        if vol_change is not None:
            components["vol_change"] = float(vol_change)
            if vol_change < -0.1:
                reason_parts.append("vol_decreasing")
            elif vol_change > 0.1:
                reason_parts.append("vol_increasing")
        
        if not reason_parts:
            reason = f"regime_score={final_score:.2f}"
        else:
            reason = ", ".join(reason_parts)
        
        regime_str = ", ".join(regime_desc) if regime_desc else "unknown"
        description = f"Market Regime ({regime_str}): Is the market environment favorable for taking risk? Score={final_score:.2f}"

        return SignalResult(
            score=float(final_score),
            confidence=float(confidence),
            name=self.name,
            timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
            description=description,
            reason=reason,
            components=components if components else None,
        )
