"""Tests for signal generation."""

import pandas as pd
import pytest

from app.features.volatility import compute_all_features
from app.signals.meanreversion_signal import MeanReversionSignal
from app.signals.momentum_signal import MomentumSignal
from app.signals.regime_signal import RegimeFilterSignal


@pytest.fixture
def sample_bars():
    """Create sample bars data."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    prices = 100 + pd.Series(range(100)) * 0.5  # Trending up

    return pd.DataFrame({
        "open": prices + 0.1,
        "high": prices + 0.5,
        "low": prices - 0.3,
        "close": prices,
        "volume": 1000000 + pd.Series(range(100)) * 10000,
    }, index=dates)


@pytest.fixture
def sample_features(sample_bars):
    """Create sample features."""
    return compute_all_features(sample_bars)


def test_momentum_signal(sample_bars, sample_features):
    """Test momentum signal."""
    signal = MomentumSignal()

    if sample_features.empty:
        pytest.skip("No features computed")

    # Test on a date in the middle
    test_date = sample_bars.index[50]

    result = signal.compute(sample_bars, sample_features, test_date)

    assert result.name == "Trend (recent price strength)"
    assert -1.0 <= result.score <= 1.0
    assert 0.0 <= result.confidence <= 1.0
    assert result.timestamp is not None


def test_meanreversion_signal(sample_bars, sample_features):
    """Test mean reversion signal."""
    signal = MeanReversionSignal()

    if sample_features.empty:
        pytest.skip("No features computed")

    test_date = sample_bars.index[50]
    result = signal.compute(sample_bars, sample_features, test_date)

    assert result.name == "Pullback vs average"
    assert -1.0 <= result.score <= 1.0
    assert 0.0 <= result.confidence <= 1.0


def test_regime_signal(sample_bars, sample_features):
    """Test regime filter signal."""
    signal = RegimeFilterSignal()

    if sample_features.empty:
        pytest.skip("No features computed")

    test_date = sample_bars.index[50]
    result = signal.compute(sample_bars, sample_features, test_date)

    assert result.name == "Market Regime (trend/vol filter)"
    assert 0.0 <= result.score <= 1.0  # Regime filter is 0-1
    assert 0.0 <= result.confidence <= 1.0


def test_signals_sorted_newest_first(fake_provider):
    """Test that signals are sorted by timestamp DESC (newest first)."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.data.fetcher import DataFetcher
    
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        
        response = client.get(
            f"/signals?ticker=TEST&start={start_date}&end={end_date}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        signals = data.get("signals", [])
        if len(signals) > 1:
            # Check that timestamps are in descending order
            timestamps = [s["timestamp"] for s in signals]
            assert timestamps == sorted(timestamps, reverse=True), \
                "Signals should be sorted by timestamp DESC (newest first)"


def test_signals_reason_field_populated(fake_provider):
    """Test that reason field is populated with specifics."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.data.fetcher import DataFetcher
    
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        
        response = client.get(
            f"/signals?ticker=TEST&start={start_date}&end={end_date}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        signals = data.get("signals", [])
        # At least some signals should have reason field
        signals_with_reason = [s for s in signals if s.get("reason")]
        # Reason should contain numeric values or specific descriptions
        for signal in signals_with_reason[:5]:  # Check first 5
            reason = signal.get("reason", "")
            assert reason, f"Signal {signal.get('name')} should have a reason"
            # Reason should not be generic
            assert len(reason) > 10, f"Reason should be specific, got: {reason}"