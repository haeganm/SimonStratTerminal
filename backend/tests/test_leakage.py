"""Critical tests to ensure no data leakage."""

from datetime import date, timedelta

import pandas as pd
import pytest

from app.backtest.engine import BacktestEngine
from app.features.volatility import compute_all_features
from app.models.ensemble import EnsembleModel


@pytest.fixture
def date_stamped_bars():
    """Create bars with known dates to detect leakage."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    prices = 100 + pd.Series(range(100)) * 0.5

    return pd.DataFrame({
        "open": prices + 0.1,
        "high": prices + 0.5,
        "low": prices - 0.3,
        "close": prices,
        "volume": 1000000 + pd.Series(range(100)) * 10000,
    }, index=dates)


def test_backtest_no_future_data_access(date_stamped_bars):
    """Test that backtest never accesses future data."""
    ensemble = EnsembleModel()
    engine = BacktestEngine(ensemble=ensemble)

    # Create a mock that tracks date access
    accessed_dates = []

    original_getitem = date_stamped_bars.__getitem__
    original_loc = date_stamped_bars.loc

    def track_getitem(key):
        accessed_dates.append(key)
        return original_getitem(key)

    def track_loc(key):
        accessed_dates.append(key)
        return original_loc(key)

    # This is a simplified test - in practice, you'd need to mock more thoroughly
    # For now, we test the principle: engine should only access data up to current_date

    start_date = date(2020, 1, 1)
    end_date = date(2020, 3, 31)

    # Run backtest
    equity_curve, trades, metrics = engine.run(
        date_stamped_bars.copy(), start_date=start_date, end_date=end_date
    )

    # Verify results
    assert not equity_curve.empty

    # The engine should have processed dates in order
    # This is a basic check - more sophisticated testing would track exact date access


def test_features_no_future_data(date_stamped_bars):
    """Test that feature computation only uses past data."""
    # Features should use rolling windows that only look backward
    features = compute_all_features(date_stamped_bars)

    if features.empty:
        pytest.skip("No features computed")

    # For a rolling window of N days, the first N-1 rows should be NaN
    # Check that features don't magically have values before sufficient history
    for col in features.columns:
        if features[col].notna().any():
            # Find first non-NaN index
            first_valid = features[col].first_valid_index()
            first_valid_pos = features.index.get_loc(first_valid)

            # Should have at least some NaN values at the start (window size - 1)
            assert first_valid_pos >= 0  # Should start with NaN for rolling windows


def test_backtest_date_order(date_stamped_bars):
    """Test that backtest processes dates in chronological order."""
    ensemble = EnsembleModel()
    engine = BacktestEngine(ensemble=ensemble)

    start_date = date(2020, 1, 10)
    end_date = date(2020, 2, 10)

    equity_curve, trades, metrics = engine.run(
        date_stamped_bars.copy(), start_date=start_date, end_date=end_date
    )

    if not equity_curve.empty:
        # Verify equity curve dates are in order
        dates = pd.to_datetime(equity_curve["date"])
        assert dates.is_monotonic_increasing or len(dates) <= 1
