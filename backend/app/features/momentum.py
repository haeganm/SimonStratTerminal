"""Momentum feature extractors."""

import numpy as np
import pandas as pd


def returns_5d(close: pd.Series) -> pd.Series:
    """5-day log returns."""
    return np.log(close / close.shift(5))


def returns_20d(close: pd.Series) -> pd.Series:
    """20-day log returns."""
    return np.log(close / close.shift(20))


def returns_60d(close: pd.Series) -> pd.Series:
    """60-day log returns."""
    return np.log(close / close.shift(60))


def ma_slope_20(close: pd.Series) -> pd.Series:
    """Slope of 20-day moving average (normalized by price)."""
    ma20 = close.rolling(window=20).mean()
    slope = ma20.diff(5) / close  # 5-day change in MA, normalized by price
    return slope


def ma_slope_60(close: pd.Series) -> pd.Series:
    """Slope of 60-day moving average (normalized by price)."""
    ma60 = close.rolling(window=60).mean()
    slope = ma60.diff(10) / close  # 10-day change in MA, normalized by price
    return slope


def breakout_distance(close: pd.Series, window: int = 20) -> pd.Series:
    """
    Distance to the nearest rolling breakout boundary (high/low) over `window`.
    Uses ONLY past data via rolling(). Vectorized (no DataFrame.apply).
    Output is signed:
      - positive => closer to / above rolling low (distance from low)
      - negative => closer to / below rolling high (distance from high)
    """
    close = pd.Series(close).astype(float)

    rolling_high = close.rolling(window=window, min_periods=window).max()
    rolling_low = close.rolling(window=window, min_periods=window).min()

    rolling_high = rolling_high.replace(0.0, np.nan)
    rolling_low = rolling_low.replace(0.0, np.nan)

    dist_from_high = (close - rolling_high) / rolling_high
    dist_from_low = (close - rolling_low) / rolling_low

    out = np.where(dist_from_low.abs() < dist_from_high.abs(), dist_from_low, dist_from_high)
    return pd.Series(out, index=close.index, name="breakout_distance")


def compute_momentum_features(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all momentum features.

    Args:
        bars: DataFrame with date index and 'close' column

    Returns:
        DataFrame with date index and momentum feature columns
    """
    if bars.empty or "close" not in bars.columns:
        return pd.DataFrame()

    close = bars["close"]

    features = pd.DataFrame(index=bars.index)
    features["returns_5d"] = returns_5d(close)
    features["returns_20d"] = returns_20d(close)
    features["returns_60d"] = returns_60d(close)
    features["ma_slope_20"] = ma_slope_20(close)
    features["ma_slope_60"] = ma_slope_60(close)
    features["breakout_distance"] = breakout_distance(close)

    return features
