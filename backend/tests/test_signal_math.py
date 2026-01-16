"""Mathematical correctness tests for signal computation."""

import numpy as np
import pandas as pd
import pytest

from app.signals.meanreversion_signal import MeanReversionSignal
from app.signals.momentum_signal import MomentumSignal
from app.signals.regime_signal import RegimeFilterSignal


@pytest.fixture
def sample_features_with_values():
    """Create features with known values for testing."""
    dates = pd.date_range("2020-01-01", periods=30, freq="D")
    features = pd.DataFrame(index=dates)
    
    # Add momentum features (all positive = bullish)
    features["returns_5d"] = 0.05
    features["returns_20d"] = 0.10
    features["ma_slope_20"] = 0.01
    features["breakout_distance"] = 0.15
    
    # Add mean reversion features
    features["zscore_close_vs_ma20"] = -1.5  # Oversold (buy signal)
    features["bollinger_distance"] = -0.3
    
    # Add volatility features
    features["realized_vol_20d"] = 0.25  # Moderate volatility
    features["trend_vs_chop"] = 0.6  # Strong trend
    features["vol_change"] = -0.1  # Volatility decreasing
    
    return features


@pytest.fixture
def sample_bars():
    """Create sample bars."""
    dates = pd.date_range("2020-01-01", periods=30, freq="D")
    prices = 100.0 + np.arange(30) * 0.5
    
    return pd.DataFrame({
        "open": prices + 0.1,
        "high": prices + 0.5,
        "low": prices - 0.3,
        "close": prices,
        "volume": 1000000,
    }, index=dates)


def test_momentum_signal_score_normalization(sample_bars, sample_features_with_values):
    """Verify momentum signal score is normalized to [-1, 1]."""
    signal = MomentumSignal()
    test_date = sample_bars.index[-1]
    
    result = signal.compute(sample_bars, sample_features_with_values, test_date)
    
    assert -1.0 <= result.score <= 1.0, \
        f"Score should be in [-1, 1], got {result.score}"
    assert 0.0 <= result.confidence <= 1.0, \
        f"Confidence should be in [0, 1], got {result.confidence}"


def test_momentum_signal_positive_features_positive_score(sample_bars, sample_features_with_values):
    """Verify that all positive momentum features produce positive score."""
    signal = MomentumSignal()
    test_date = sample_bars.index[-1]
    
    result = signal.compute(sample_bars, sample_features_with_values, test_date)
    
    # All features are positive, so score should be positive
    assert result.score > 0, \
        f"All positive features should produce positive score, got {result.score}"


def test_meanreversion_signal_zscore_direction(sample_bars, sample_features_with_values):
    """Verify mean reversion signal direction matches z-score."""
    signal = MeanReversionSignal()
    test_date = sample_bars.index[-1]
    
    # Negative z-score (oversold) should produce positive score (buy signal)
    result = signal.compute(sample_bars, sample_features_with_values, test_date)
    
    # z-score is -1.5 (oversold), so score should be positive (mean reversion buy)
    assert result.score > 0, \
        f"Negative z-score (oversold) should produce positive score, got {result.score}"


def test_meanreversion_signal_confidence_capping(sample_bars, sample_features_with_values):
    """Verify confidence is capped at 1.0 based on z-score."""
    signal = MeanReversionSignal()
    test_date = sample_bars.index[-1]
    
    result = signal.compute(sample_bars, sample_features_with_values, test_date)
    
    # Confidence should be: min(abs(zscore) / 3.0, 1.0)
    # For zscore = -1.5: confidence = 1.5 / 3.0 = 0.5
    expected_confidence = min(abs(-1.5) / 3.0, 1.0)
    
    assert np.isclose(result.confidence, expected_confidence, rtol=0.1), \
        f"Confidence should be ~{expected_confidence}, got {result.confidence}"


def test_regime_filter_vol_score_thresholds(sample_bars):
    """Verify regime filter vol_score thresholds are correct."""
    signal = RegimeFilterSignal()
    test_date = sample_bars.index[-1]
    
    # Test different volatility levels
    dates = pd.date_range("2020-01-01", periods=30, freq="D")
    
    # Low vol (< 0.05) with weak trend should have lower score
    features_low_vol = pd.DataFrame(index=dates)
    features_low_vol["realized_vol_20d"] = 0.03
    features_low_vol["trend_vs_chop"] = 0.1  # Weak trend
    
    result_low = signal.compute(sample_bars, features_low_vol, test_date)
    # Score combines vol_score and trend_score, so even with low vol, strong trend can raise it
    # But with both low vol and weak trend, score should be lower
    assert result_low.score < 0.8, \
        f"Low volatility with weak trend should have lower score, got {result_low.score}"
    
    # Moderate vol (0.1 to 0.5) with strong trend should have high score
    features_mod_vol = pd.DataFrame(index=dates)
    features_mod_vol["realized_vol_20d"] = 0.25
    features_mod_vol["trend_vs_chop"] = 0.6  # Strong trend
    
    result_mod = signal.compute(sample_bars, features_mod_vol, test_date)
    assert result_mod.score > 0.7, \
        f"Moderate volatility with strong trend should have high score, got {result_mod.score}"


def test_regime_filter_score_clipping(sample_bars, sample_features_with_values):
    """Verify regime filter score is clipped to [0, 1]."""
    signal = RegimeFilterSignal()
    test_date = sample_bars.index[-1]
    
    result = signal.compute(sample_bars, sample_features_with_values, test_date)
    
    assert 0.0 <= result.score <= 1.0, \
        f"Regime filter score should be in [0, 1], got {result.score}"


def test_signal_reason_field_populated(sample_bars, sample_features_with_values):
    """Verify that reason field contains numeric values."""
    signal = MomentumSignal()
    test_date = sample_bars.index[-1]
    
    result = signal.compute(sample_bars, sample_features_with_values, test_date)
    
    assert result.reason is not None, "Reason should be populated"
    assert len(result.reason) > 0, "Reason should not be empty"
    # Reason should contain numeric values or specific descriptions
    assert any(char.isdigit() for char in result.reason) or "slope" in result.reason.lower() or "return" in result.reason.lower(), \
        f"Reason should contain numeric values or specifics, got: {result.reason}"
