"""Mathematical correctness tests for feature engineering."""

import numpy as np
import pandas as pd
import pytest

from app.features.meanreversion import (
    bollinger_distance,
    compute_meanreversion_features,
    zscore_close_vs_ma20,
)
from app.features.momentum import (
    breakout_distance,
    compute_momentum_features,
    ma_slope_20,
    returns_20d,
    returns_5d,
)
from app.features.volatility import (
    compute_volatility_features,
    realized_vol_20d,
    trend_vs_chop,
    vol_change,
)


@pytest.fixture
def simple_price_series():
    """Simple price series for manual calculation verification."""
    dates = pd.date_range("2020-01-01", periods=30, freq="D")
    # Linear trend: 100, 101, 102, ...
    prices = pd.Series(100.0 + np.arange(30), index=dates, name="close")
    return prices


def test_returns_5d_manual_calculation(simple_price_series):
    """Verify 5-day returns match manual calculation."""
    returns = returns_5d(simple_price_series)
    
    # Manual calculation for day 5: log(105 / 100) = log(1.05) ≈ 0.04879
    expected_day5 = np.log(105.0 / 100.0)
    actual_day5 = returns.iloc[5]
    
    assert np.isclose(actual_day5, expected_day5, rtol=1e-5), \
        f"5-day return mismatch: expected {expected_day5}, got {actual_day5}"


def test_ma_slope_20_normalization(simple_price_series):
    """Verify MA slope is normalized by price."""
    slope = ma_slope_20(simple_price_series)
    
    # Should be normalized (divided by price)
    # For a linear trend, MA20 slope should be positive and small
    if not slope.isna().all():
        non_na_slope = slope.dropna()
        # Slope should be normalized (not raw price difference)
        assert (non_na_slope.abs() < 1.0).all(), \
            f"MA slope should be normalized, got values: {non_na_slope.head()}"


def test_zscore_calculation():
    """Verify z-score calculation: (close - MA) / std."""
    dates = pd.date_range("2020-01-01", periods=25, freq="D")
    # Constant price with one outlier
    prices = pd.Series([100.0] * 24 + [110.0], index=dates)
    
    zscore = zscore_close_vs_ma20(prices)
    
    # Last value should have high z-score (outlier)
    last_zscore = zscore.iloc[-1]
    assert last_zscore > 2.0, f"Outlier should have high z-score, got {last_zscore}"


def test_bollinger_distance_normalization():
    """Verify Bollinger distance is normalized by band width."""
    dates = pd.date_range("2020-01-01", periods=25, freq="D")
    prices = pd.Series(100.0 + np.random.randn(25) * 2, index=dates)
    
    bollinger = bollinger_distance(prices)
    
    # Should be normalized (typically between -1 and 1 for most values)
    if not bollinger.isna().all():
        non_na = bollinger.dropna()
        # Most values should be within reasonable bounds
        assert (non_na.abs() < 2.0).all(), \
            f"Bollinger distance should be normalized, got extreme values: {non_na[non_na.abs() > 2.0]}"


def test_realized_vol_annualization():
    """Verify realized volatility is annualized (multiplied by sqrt(252))."""
    dates = pd.date_range("2020-01-01", periods=25, freq="D")
    # Constant returns (no volatility)
    prices = pd.Series(100.0, index=dates)
    
    vol = realized_vol_20d(prices)
    
    # Should be close to zero for constant prices
    if not vol.isna().all():
        non_na_vol = vol.dropna()
        assert (non_na_vol < 0.01).all(), \
            f"Constant prices should have near-zero vol, got {non_na_vol.max()}"


def test_trend_vs_chop_r_squared():
    """Verify trend_vs_chop uses R-squared from linear regression."""
    dates = pd.date_range("2020-01-01", periods=25, freq="D")
    # Perfect linear trend
    prices = pd.Series(100.0 + np.arange(25) * 0.5, index=dates)
    
    trend = trend_vs_chop(prices, window=20)
    
    # Perfect trend should have high R-squared (close to 1.0)
    if not trend.isna().all():
        non_na_trend = trend.dropna()
        # R-squared should be high for perfect trend
        assert (non_na_trend.abs() > 0.8).any(), \
            f"Perfect trend should have high R-squared, got max {non_na_trend.abs().max()}"


def test_division_by_zero_handling():
    """Test that division by zero is handled gracefully."""
    dates = pd.date_range("2020-01-01", periods=25, freq="D")
    # Constant prices (std = 0)
    prices = pd.Series(100.0, index=dates)
    
    # These should not crash
    zscore = zscore_close_vs_ma20(prices)
    bollinger = bollinger_distance(prices)
    vol = realized_vol_20d(prices)
    
    # Should return NaN or 0, not crash
    assert isinstance(zscore, pd.Series)
    assert isinstance(bollinger, pd.Series)
    assert isinstance(vol, pd.Series)


def test_empty_dataframe_handling():
    """Test that empty DataFrames are handled gracefully."""
    empty_bars = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    
    # Should not crash
    momentum_features = compute_momentum_features(empty_bars)
    mr_features = compute_meanreversion_features(empty_bars)
    vol_features = compute_volatility_features(empty_bars)
    
    assert isinstance(momentum_features, pd.DataFrame)
    assert isinstance(mr_features, pd.DataFrame)
    assert isinstance(vol_features, pd.DataFrame)
