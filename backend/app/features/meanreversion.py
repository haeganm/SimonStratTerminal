"""Mean reversion feature extractors."""

import numpy as np
import pandas as pd


def zscore_close_vs_ma20(close: pd.Series) -> pd.Series:
    """Z-score of close price vs 20-day moving average."""
    ma20 = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std()
    zscore = (close - ma20) / std20
    return zscore


def bollinger_distance(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.Series:
    """
    Distance from Bollinger Bands (normalized).

    Returns:
        Series where:
        - Positive values: above upper band (overbought)
        - Negative values: below lower band (oversold)
        - Zero: at middle band (MA)
    """
    ma = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()

    upper_band = ma + (num_std * std)
    lower_band = ma - (num_std * std)

    # Distance from middle band, normalized by band width
    band_width = upper_band - lower_band
    distance = (close - ma) / band_width

    return distance


def reversal_1d(close: pd.Series) -> pd.Series:
    """
    1-day reversal feature (negative autocorrelation).

    Returns:
        Negative of 1-day return (mean reversion signal)
    """
    returns = close.pct_change(fill_method=None)
    reversal = -returns  # Negative autocorrelation
    return reversal


def reversal_3d(close: pd.Series) -> pd.Series:
    """
    3-day reversal feature (negative autocorrelation).

    Returns:
        Negative of 3-day return (mean reversion signal)
    """
    returns_3d = (close / close.shift(3)) - 1
    reversal = -returns_3d
    return reversal


def compute_meanreversion_features(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all mean reversion features.

    Args:
        bars: DataFrame with date index and 'close' column

    Returns:
        DataFrame with date index and mean reversion feature columns
    """
    if bars.empty or "close" not in bars.columns:
        return pd.DataFrame()

    close = bars["close"]

    features = pd.DataFrame(index=bars.index)
    features["zscore_close_vs_ma20"] = zscore_close_vs_ma20(close)
    features["bollinger_distance"] = bollinger_distance(close)
    features["reversal_1d"] = reversal_1d(close)
    features["reversal_3d"] = reversal_3d(close)

    return features
