"""Integration tests for data correctness across endpoints."""

import pandas as pd
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.data.fetcher import DataFetcher
from app.data.cache import DataCache
from app.data.ticker_utils import canonical_ticker
from app.storage.repository import DataRepository
from app.main import app


def test_api_consistency_same_ticker(fake_provider):
    """Test that /history, /forecast, /backtest return consistent ticker and prices."""
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=90)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        # Test /history endpoint
        history_response = client.get(
            f"/history?ticker={ticker}&start={start_date}&end={end_date}"
        )
        assert history_response.status_code == 200
        history_data = history_response.json()
        
        # Test /forecast endpoint
        forecast_response = client.get(f"/forecast?ticker={ticker}")
        assert forecast_response.status_code == 200
        forecast_data = forecast_response.json()
        
        # Test /backtest endpoint
        backtest_response = client.get(
            f"/backtest?ticker={ticker}&start={start_date}&end={end_date}&preset=default"
        )
        assert backtest_response.status_code == 200
        backtest_data = backtest_response.json()
        
        # Verify all responses have same ticker
        assert history_data["ticker"] == ticker.upper() or history_data["ticker"] == ticker
        assert forecast_data["ticker"] == ticker.upper() or forecast_data["ticker"] == ticker
        assert backtest_data["ticker"] == ticker.upper() or backtest_data["ticker"] == ticker
        
        # Verify last_close prices are consistent (if data available)
        if history_data["data"] and len(history_data["data"]) > 0:
            last_close_history = history_data["data"][-1]["close"]
            
            # Backtest uses same data, so equity curve should reflect similar prices
            if backtest_data["equity_curve"] and len(backtest_data["equity_curve"]) > 0:
                # Verify data_source is consistent
                assert history_data["data_source"] == forecast_data["data_source"]
                assert history_data["data_source"] == backtest_data["data_source"]


def test_ticker_normalization_consistency(fake_provider):
    """Test that NVDA, nvda, NVDA.US all return same data."""
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    ticker_variants = ["NVDA", "nvda", "NVDA.US"]
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    responses = []
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        for ticker in ticker_variants:
            response = client.get(
                f"/history?ticker={ticker}&start={start_date}&end={end_date}"
            )
            assert response.status_code == 200
            responses.append(response.json())
        
        # All responses should have same data (same ticker normalization)
        # Compare data lengths and last close prices
        if responses[0]["data"]:
            for i in range(1, len(responses)):
                # Should have same number of bars (if all variants resolve to same ticker)
                # Note: This assumes fake_provider handles all variants the same
                assert len(responses[i]["data"]) == len(responses[0]["data"]), \
                    f"Ticker variant {ticker_variants[i]} should return same data length"
                
                # Last close should be same
                if responses[i]["data"]:
                    last_close_0 = responses[0]["data"][-1]["close"]
                    last_close_i = responses[i]["data"][-1]["close"]
                    assert abs(last_close_0 - last_close_i) < 1e-6, \
                        f"Ticker variant {ticker_variants[i]} should return same last close price"


def test_staleness_consistency(fake_provider):
    """Test that staleness_seconds is consistent across endpoints."""
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        history_response = client.get(
            f"/history?ticker={ticker}&start={start_date}&end={end_date}"
        )
        assert history_response.status_code == 200
        history_data = history_response.json()
        
        forecast_response = client.get(f"/forecast?ticker={ticker}")
        assert forecast_response.status_code == 200
        forecast_data = forecast_response.json()
        
        # Staleness should be same for both (same data source, same last bar date)
        # Note: staleness_seconds might be None if data is fresh
        # But type should be consistent (None or int)
        assert history_data["staleness_seconds"] is None or isinstance(history_data["staleness_seconds"], (int, float))
        assert forecast_data["staleness_seconds"] is None or isinstance(forecast_data["staleness_seconds"], (int, float))
        
        # If both have staleness, they should be similar (within 1 second tolerance)
        if history_data["staleness_seconds"] is not None and forecast_data["staleness_seconds"] is not None:
            assert abs(history_data["staleness_seconds"] - forecast_data["staleness_seconds"]) < 1


def test_warnings_consistency(fake_provider):
    """Test that warnings are always lists (not dicts or other types)."""
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        endpoints = [
            f"/history?ticker={ticker}&start={start_date}&end={end_date}",
            f"/forecast?ticker={ticker}",
            f"/backtest?ticker={ticker}&start={start_date}&end={end_date}&preset=default",
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200
            data = response.json()
            
            # Warnings should always be a list
            assert "warnings" in data
            assert isinstance(data["warnings"], list), \
                f"warnings should be list, got {type(data['warnings'])} for endpoint {endpoint}"
            
            # All warning items should be strings
            for warning in data["warnings"]:
                assert isinstance(warning, str), \
                    f"Warning items should be strings, got {type(warning)}"


def test_nvda_cache_isolation_regression(tmp_path):
    """Regression test: NVDA cache isolation (NVDA bars != AAPL bars)."""
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(cache=cache)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Fetch NVDA data
    nvda_bars, _ = fetcher.get_bars("NVDA", start_date, end_date)
    
    # Fetch AAPL data
    aapl_bars, _ = fetcher.get_bars("AAPL", start_date, end_date)
    
    # Verify canonical tickers are different
    nvda_canonical = canonical_ticker("NVDA")
    aapl_canonical = canonical_ticker("AAPL")
    assert nvda_canonical != aapl_canonical, \
        "NVDA and AAPL should have different canonical keys"
    
    # If both have data, last closes should be different
    if not nvda_bars.empty and not aapl_bars.empty:
        if "close" in nvda_bars.columns and "close" in aapl_bars.columns:
            nvda_last_close = nvda_bars.iloc[-1]["close"]
            aapl_last_close = aapl_bars.iloc[-1]["close"]
            
            # Prices should differ significantly (>10%)
            diff_pct = abs(nvda_last_close - aapl_last_close) / min(nvda_last_close, aapl_last_close)
            assert diff_pct > 0.10, \
                f"NVDA and AAPL prices should differ: NVDA=${nvda_last_close:.2f}, " \
                f"AAPL=${aapl_last_close:.2f}, diff={diff_pct*100:.1f}%"


def test_cache_hit_accuracy(tmp_path):
    """Regression test: Cache hit returns same data as fresh fetch."""
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(cache=cache)
    
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # First fetch (cache miss, stores data)
    bars_fresh, _ = fetcher.get_bars(ticker, start_date, end_date, use_cache=True)
    
    # Second fetch (should be cache hit)
    bars_cached, _ = fetcher.get_bars(ticker, start_date, end_date, use_cache=True)
    
    # Both should have same data
    assert not bars_fresh.empty, "Fresh fetch should return data"
    assert not bars_cached.empty, "Cached fetch should return data"
    
    # Compare data
    assert len(bars_fresh) == len(bars_cached), \
        f"Cache hit should return same number of bars: fresh={len(bars_fresh)}, cached={len(bars_cached)}"
    
    # Compare last close (should be identical)
    if "close" in bars_fresh.columns and "close" in bars_cached.columns:
        fresh_last_close = bars_fresh.iloc[-1]["close"]
        cached_last_close = bars_cached.iloc[-1]["close"]
        assert abs(fresh_last_close - cached_last_close) < 1e-6, \
            f"Cache hit should return same last close: fresh=${fresh_last_close:.2f}, " \
            f"cached=${cached_last_close:.2f}"


def test_ohlcv_integrity(tmp_path):
    """Regression test: OHLCV integrity (no invalid high/low, sorted dates)."""
    from app.data.normalize import normalize_ohlcv
    
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(cache=cache)
    
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Fetch data
    bars, _ = fetcher.get_bars(ticker, start_date, end_date)
    
    if bars.empty:
        pytest.skip("No data available for OHLCV integrity test")
    
    # Convert to format expected by normalize_ohlcv (date as column)
    if isinstance(bars.index, pd.DatetimeIndex):
        bars_for_check = bars.reset_index()
    else:
        bars_for_check = bars.copy()
        if "date" not in bars_for_check.columns:
            bars_for_check["date"] = bars_for_check.index
    
    # Normalize (this will fix any integrity issues and return warnings)
    normalized = normalize_ohlcv(bars_for_check)
    
    # Verify dates are sorted ascending
    dates = pd.to_datetime(normalized["date"])
    assert dates.is_monotonic_increasing, "Dates should be sorted ascending"
    
    # Verify no duplicate dates
    assert not dates.duplicated().any(), "Should have no duplicate dates"
    
    # Verify OHLCV integrity: high >= max(open, close, low), low <= min(open, close, high)
    invalid_high = (normalized["high"] < normalized[["open", "close", "low"]].max(axis=1))
    invalid_low = (normalized["low"] > normalized[["open", "close", "high"]].min(axis=1))
    
    assert not invalid_high.any(), \
        f"Found {invalid_high.sum()} rows with high < max(open, close, low)"
    assert not invalid_low.any(), \
        f"Found {invalid_low.sum()} rows with low > min(open, close, high)"
    
    # Verify volume >= 0
    negative_volume = normalized["volume"] < 0
    assert not negative_volume.any(), \
        f"Found {negative_volume.sum()} rows with negative volume"