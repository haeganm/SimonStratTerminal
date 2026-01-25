"""Edge case tests: empty data, NaN, extreme values, etc."""

from datetime import date
import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import BacktestEngine
from app.data.normalize import normalize_ohlcv
from app.features.volatility import compute_all_features
from app.models.ensemble import EnsembleModel
from app.portfolio.sizing import compute_position_size
from app.signals.base import SignalResult
from app.signals.momentum_signal import MomentumSignal
from app.signals.meanreversion_signal import MeanReversionSignal
from app.signals.regime_signal import RegimeFilterSignal


class TestEmptyData:
    """Test handling of empty data."""

    def test_empty_dataframe_normalization(self):
        """Test normalization handles empty DataFrame."""
        empty_df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        normalized = normalize_ohlcv(empty_df)
        assert normalized.empty or len(normalized) == 0

    def test_single_bar_data(self):
        """Test handling of single bar (insufficient data)."""
        single_bar = pd.DataFrame({
            "date": [pd.Timestamp("2020-01-01")],
            "open": [100.0],
            "high": [105.0],
            "low": [95.0],
            "close": [102.0],
            "volume": [1000000],
        })
        
        normalized = normalize_ohlcv(single_bar)
        assert len(normalized) == 1
        
        # Features should handle gracefully
        features = compute_all_features(normalized.set_index("date"))
        # May be empty or have NaN values, but shouldn't crash
        assert isinstance(features, pd.DataFrame)

    def test_no_bars_for_ticker(self):
        """Test API handles ticker with no data."""
        from fastapi.testclient import TestClient
        from app.main import app
        from tests.conftest import fake_provider
        from unittest.mock import patch
        from app.data.fetcher import DataFetcher
        
        # Create provider that returns empty data
        class EmptyProvider:
            @property
            def name(self):
                return "empty"
            
            def get_daily_bars(self, ticker, start, end):
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            
            def get_latest_quote(self, ticker):
                return None
        
        empty_provider = EmptyProvider()
        fetcher = DataFetcher(provider=empty_provider)
        
        with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
            client = TestClient(app)
            response = client.get("/history?ticker=EMPTY&start=2020-01-01&end=2020-01-31")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 0
            assert len(data["warnings"]) > 0  # Should warn about no data


class TestNaNHandling:
    """Test handling of NaN values."""

    def test_nan_in_price_data(self):
        """Test handling of NaN in price columns."""
        bars_with_nan = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "open": [100.0, np.nan, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
            "high": [105.0] * 10,
            "low": [95.0] * 10,
            "close": [102.0, np.nan, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
            "volume": [1000000] * 10,
        })
        
        # Normalization should handle NaN
        normalized = normalize_ohlcv(bars_with_nan)
        # Should either drop NaN rows or fill them
        assert isinstance(normalized, pd.DataFrame)
        
        # Features should handle NaN gracefully
        if not normalized.empty:
            features = compute_all_features(normalized.set_index("date"))
            assert isinstance(features, pd.DataFrame)

    def test_all_nan_data(self):
        """Test handling when all data is NaN."""
        all_nan = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "open": [np.nan] * 10,
            "high": [np.nan] * 10,
            "low": [np.nan] * 10,
            "close": [np.nan] * 10,
            "volume": [np.nan] * 10,
        })
        
        normalized = normalize_ohlcv(all_nan)
        # Should handle gracefully (may be empty or have NaN)
        assert isinstance(normalized, pd.DataFrame)

    def test_nan_in_features(self):
        """Test signals handle NaN in features gracefully."""
        # Create bars
        dates = pd.date_range("2020-01-01", periods=100, freq="D")
        prices = 100 + pd.Series(range(100)) * 0.5
        bars = pd.DataFrame({
            "open": prices + 0.1,
            "high": prices + 0.5,
            "low": prices - 0.3,
            "close": prices,
            "volume": 1000000 + pd.Series(range(100)) * 10000,
        }, index=dates)
        
        # Create features with some NaN
        features = compute_all_features(bars)
        # Inject some NaN
        features.loc[features.index[50], "returns_20d"] = np.nan
        
        # Signals should handle NaN gracefully
        momentum = MomentumSignal()
        result = momentum.compute(bars, features, features.index[-1])
        # Should return valid result (may have low confidence)
        assert isinstance(result, SignalResult)
        assert not np.isnan(result.score) or result.score == 0.0


class TestExtremeValues:
    """Test handling of extreme values."""

    def test_zero_prices(self):
        """Test handling of zero prices."""
        zero_price_bars = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "open": [0.0] * 10,
            "high": [0.0] * 10,
            "low": [0.0] * 10,
            "close": [0.0] * 10,
            "volume": [1000000] * 10,
        })
        
        normalized = normalize_ohlcv(zero_price_bars)
        assert isinstance(normalized, pd.DataFrame)
        
        # Features should handle zero prices (may produce inf or NaN)
        if not normalized.empty:
            features = compute_all_features(normalized.set_index("date"))
            assert isinstance(features, pd.DataFrame)

    def test_negative_prices(self):
        """Test handling of negative prices (invalid but should not crash)."""
        negative_bars = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "open": [-100.0] * 10,
            "high": [-95.0] * 10,
            "low": [-105.0] * 10,
            "close": [-100.0] * 10,
            "volume": [1000000] * 10,
        })
        
        normalized = normalize_ohlcv(negative_bars)
        assert isinstance(normalized, pd.DataFrame)
        # Should handle gracefully (may warn or reject)

    def test_very_large_prices(self):
        """Test handling of very large price values."""
        large_bars = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "open": [1e10] * 10,  # $10 billion
            "high": [1e10] * 10,
            "low": [1e10] * 10,
            "close": [1e10] * 10,
            "volume": [1000000] * 10,
        })
        
        normalized = normalize_ohlcv(large_bars)
        assert isinstance(normalized, pd.DataFrame)
        
        # Features should handle large values
        if not normalized.empty:
            features = compute_all_features(normalized.set_index("date"))
            assert isinstance(features, pd.DataFrame)

    def test_extreme_volatility(self):
        """Test position sizing with extreme volatility values."""
        # Very high volatility
        size_high_vol = compute_position_size(
            "long", 0.8, 10.0, target_volatility=0.01  # 1000% daily vol (extreme)
        )
        assert 0.0 <= size_high_vol <= 1.0
        
        # Very low volatility
        size_low_vol = compute_position_size(
            "long", 0.8, 1e-10, target_volatility=0.01  # Near zero vol
        )
        assert 0.0 <= size_low_vol <= 1.0
        # Should be capped by vol_floor

    def test_extreme_confidence(self):
        """Test ensemble with extreme confidence values."""
        ensemble = EnsembleModel(threshold=0.1)
        
        # Signal with confidence = 0.0
        signal_zero_conf = SignalResult(
            score=0.5,
            confidence=0.0,
            name="Momentum",
            timestamp=pd.Timestamp.now(tz="UTC"),
            description="Zero confidence",
        )
        forecast = ensemble.combine([signal_zero_conf])
        assert 0.0 <= forecast.confidence <= 1.0
        
        # Signal with very high score but low confidence
        signal_high_score_low_conf = SignalResult(
            score=1.0,
            confidence=0.01,
            name="Momentum",
            timestamp=pd.Timestamp.now(tz="UTC"),
            description="High score, low conf",
        )
        forecast2 = ensemble.combine([signal_high_score_low_conf])
        # Direction should still be long (based on score)
        assert forecast2.direction == "long"
        # But confidence should be low
        assert forecast2.confidence < 0.5


class TestMissingColumns:
    """Test handling of missing columns."""

    def test_missing_price_columns(self):
        """Test normalization with missing price columns."""
        incomplete_bars = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "open": range(100, 110),
            # Missing: high, low, close
            "volume": [1000000] * 10,
        })
        
        # Should handle gracefully (may raise error or fill with defaults)
        try:
            normalized = normalize_ohlcv(incomplete_bars)
            # If it doesn't raise, should handle missing columns
            assert isinstance(normalized, pd.DataFrame)
        except (KeyError, ValueError):
            # Expected to fail - missing required columns
            pass

    def test_missing_date_column(self):
        """Test normalization without date column."""
        no_date_bars = pd.DataFrame({
            "open": range(100, 110),
            "high": range(105, 115),
            "low": range(95, 105),
            "close": range(102, 112),
            "volume": [1000000] * 10,
        })
        
        # Should raise ValueError for missing date column
        with pytest.raises(ValueError, match="Missing required columns"):
            normalize_ohlcv(no_date_bars)


class TestDateEdgeCases:
    """Test date-related edge cases."""

    def test_date_range_no_trading_days(self):
        """Test date range with no trading days (weekends only)."""
        # Weekend-only range
        from fastapi.testclient import TestClient
        from app.main import app
        from tests.conftest import fake_provider
        from unittest.mock import patch
        from app.data.fetcher import DataFetcher
        
        class WeekendProvider:
            @property
            def name(self):
                return "weekend"
            
            def get_daily_bars(self, ticker, start, end):
                # Return empty (no trading on weekends)
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            
            def get_latest_quote(self, ticker):
                return None
        
        provider = WeekendProvider()
        fetcher = DataFetcher(provider=provider)
        
        with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
            client = TestClient(app)
            # Request weekend dates
            response = client.get("/history?ticker=TEST&start=2024-01-06&end=2024-01-07")  # Sat-Sun
            assert response.status_code == 200
            data = response.json()
            # Should return empty data with warning
            assert len(data["data"]) == 0
            assert len(data["warnings"]) > 0

    def test_invalid_date_range(self):
        """Test invalid date ranges."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        # Start after end
        response = client.get("/history?ticker=AAPL&start=2020-01-31&end=2020-01-01")
        assert response.status_code == 400
        
        # Same start and end
        response = client.get("/history?ticker=AAPL&start=2020-01-01&end=2020-01-01")
        assert response.status_code == 400

    def test_future_dates(self):
        """Test handling of future dates."""
        from fastapi.testclient import TestClient
        from app.main import app
        from tests.conftest import fake_provider
        from unittest.mock import patch
        from app.data.fetcher import DataFetcher
        
        with patch("app.api.routes.get_data_fetcher", return_value=DataFetcher(provider=fake_provider)):
            client = TestClient(app)
            # Request future dates
            from datetime import date, timedelta
            future_start = (date.today() + timedelta(days=365)).isoformat()
            future_end = (date.today() + timedelta(days=400)).isoformat()
            
            response = client.get(f"/history?ticker=TEST&start={future_start}&end={future_end}")
            assert response.status_code == 200
            data = response.json()
            # Should clamp to latest available and warn
            assert "warnings" in data
            assert len(data["warnings"]) > 0
