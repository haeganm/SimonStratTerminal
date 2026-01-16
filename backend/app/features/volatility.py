"""Volatility and regime feature extractors."""

import logging

import numpy as np
import pandas as pd
from scipy import stats

from app.core.config import settings

logger = logging.getLogger(__name__)


def realized_vol_20d(close: pd.Series) -> pd.Series:
    """20-day rolling realized volatility (annualized)."""
    returns = close.pct_change(fill_method=None)
    vol = returns.rolling(window=20).std() * np.sqrt(252)  # Annualized
    return vol


def vol_change(close: pd.Series, short_window: int = 10, long_window: int = 20) -> pd.Series:
    """Change in volatility (short-term vs long-term)."""
    returns = close.pct_change(fill_method=None)
    vol_short = returns.rolling(window=short_window).std()
    vol_long = returns.rolling(window=long_window).std()
    vol_change_pct = (vol_short - vol_long) / vol_long
    return vol_change_pct


def trend_vs_chop(close: pd.Series, window: int = 20) -> pd.Series:
    """
    Trend strength proxy using R-squared of linear trend.

    Returns:
        Series where:
        - Values close to 1: strong trend
        - Values close to 0: choppy/no trend
    """
    trend_strength = pd.Series(index=close.index, dtype=float)

    for i in range(window, len(close)):
        window_close = close.iloc[i - window : i]
        if len(window_close) < window:
            continue

        # Fit linear trend
        x = np.arange(len(window_close))
        y = window_close.values

        if len(np.unique(y)) < 2:  # Not enough variation
            trend_strength.iloc[i] = 0.0
            continue

        slope, intercept, r_value, _, _ = stats.linregress(x, y)
        r_squared = r_value ** 2

        # Direction: positive for uptrend, negative for downtrend
        direction = 1 if slope > 0 else -1
        trend_strength.iloc[i] = r_squared * direction

    return trend_strength


def compute_volatility_features(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all volatility/regime features.

    Args:
        bars: DataFrame with date index and 'close' column

    Returns:
        DataFrame with date index and volatility feature columns
    """
    if bars.empty or "close" not in bars.columns:
        return pd.DataFrame()

    close = bars["close"]

    # Debug logging: log volatility calculation steps
    if settings.debug_mode:
        returns = close.pct_change(fill_method=None)
        rolling_std_daily = returns.rolling(window=20).std()
        vol_annualized = rolling_std_daily * np.sqrt(252)
        
        if not vol_annualized.empty:
            last_vol = vol_annualized.iloc[-1]
            last_vol_pct = last_vol * 100 if not pd.isna(last_vol) else None
            
            # Log sample of returns and volatility
            sample_returns = returns.dropna().head(5).tolist() if len(returns.dropna()) > 0 else []
            sample_std_daily = rolling_std_daily.dropna().head(5).tolist() if len(rolling_std_daily.dropna()) > 0 else []
            
            vol_pct_str = f"{last_vol_pct:.2f}%" if last_vol_pct is not None else "None"
            logger.debug(
                f"[DEBUG] compute_volatility_features: "
                f"bars_count={len(bars)}, "
                f"sample_returns={sample_returns}, "
                f"sample_std_daily={sample_std_daily}, "
                f"last_vol_annualized={last_vol:.6f}, "
                f"last_vol_percent={vol_pct_str}"
            )

    features = pd.DataFrame(index=bars.index)
    features["realized_vol_20d"] = realized_vol_20d(close)
    features["vol_change"] = vol_change(close)
    features["trend_vs_chop"] = trend_vs_chop(close)

    return features


def compute_all_features(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all features (momentum, mean reversion, volatility).

    Args:
        bars: DataFrame with date index and OHLCV columns

    Returns:
        DataFrame with date index and all feature columns
    """
    from app.features.momentum import compute_momentum_features
    from app.features.meanreversion import compute_meanreversion_features

    all_features = pd.DataFrame(index=bars.index)

    # Momentum features
    momentum_features = compute_momentum_features(bars)
    if not momentum_features.empty:
        all_features = pd.concat([all_features, momentum_features], axis=1)

    # Mean reversion features
    mr_features = compute_meanreversion_features(bars)
    if not mr_features.empty:
        all_features = pd.concat([all_features, mr_features], axis=1)

    # Volatility features
    vol_features = compute_volatility_features(bars)
    if not vol_features.empty:
        all_features = pd.concat([all_features, vol_features], axis=1)

    return all_features
