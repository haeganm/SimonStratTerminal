"""End-to-end smoke tests for NVDA data correctness."""

import pytest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.data.fetcher import DataFetcher
from app.main import app


def test_nvda_smoke_endpoints(fake_provider):
    """End-to-end smoke test for NVDA endpoints."""
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=90)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        # 1. Health check
        health = client.get("/health")
        assert health.status_code == 200
        
        # 2. History endpoint
        history = client.get(
            f"/history?ticker={ticker}&start={start_date}&end={end_date}"
        )
        assert history.status_code == 200
        history_data = history.json()
        
        assert "data" in history_data
        assert "ticker" in history_data
        assert history_data["ticker"] == ticker.upper() or history_data["ticker"] == ticker
        
        # Verify last close is reasonable for NVDA ($100-$500 range expected)
        if history_data["data"] and len(history_data["data"]) > 0:
            last_close = history_data["data"][-1]["close"]
            assert 100.0 <= last_close <= 500.0, \
                f"NVDA last close ${last_close:.2f} should be in reasonable range ($100-$500)"
        
        # 3. Forecast endpoint
        forecast = client.get(f"/forecast?ticker={ticker}")
        assert forecast.status_code == 200
        forecast_data = forecast.json()
        
        assert "direction" in forecast_data
        assert forecast_data["direction"] in ["long", "flat", "short"]
        assert "ticker" in forecast_data
        
        # 4. Backtest endpoint
        backtest = client.get(
            f"/backtest?ticker={ticker}&start={start_date}&end={end_date}&preset=default"
        )
        assert backtest.status_code == 200
        backtest_data = backtest.json()
        
        assert "metrics" in backtest_data
        assert "equity_curve" in backtest_data
        assert "ticker" in backtest_data
        
        # Verify metrics are computed
        metrics = backtest_data["metrics"]
        assert "cagr" in metrics
        assert "sharpe" in metrics
        assert "max_drawdown" in metrics


def test_nvda_vs_aapl_cache_isolation_smoke(fake_provider, tmp_path):
    """Verify NVDA and AAPL cannot return identical last closes (cache collision check)."""
    from app.data.cache import DataCache
    from app.storage.repository import DataRepository
    
    # Use temporary database to avoid cached data from previous runs
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider, cache=cache)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        # Fetch NVDA
        nvda_response = client.get(
            f"/history?ticker=NVDA&start={start_date}&end={end_date}"
        )
        assert nvda_response.status_code == 200
        nvda_data = nvda_response.json()
        
        # Fetch AAPL
        aapl_response = client.get(
            f"/history?ticker=AAPL&start={start_date}&end={end_date}"
        )
        assert aapl_response.status_code == 200
        aapl_data = aapl_response.json()
        
        # If both have data, last closes should differ
        if nvda_data["data"] and aapl_data["data"]:
            nvda_last_close = nvda_data["data"][-1]["close"]
            aapl_last_close = aapl_data["data"][-1]["close"]
            
            # Prices should be different (>10% difference expected)
            diff_pct = abs(nvda_last_close - aapl_last_close) / min(nvda_last_close, aapl_last_close)
            assert diff_pct > 0.10, \
                f"NVDA and AAPL should have different prices: " \
                f"NVDA=${nvda_last_close:.2f}, AAPL=${aapl_last_close:.2f} " \
                f"(diff={diff_pct*100:.1f}% < 10% - possible cache collision)"


def test_nvda_signals_sorted_newest_first(fake_provider):
    """Verify signals are sorted by timestamp DESC (newest first)."""
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    ticker = "NVDA"
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        signals_response = client.get(
            f"/signals?ticker={ticker}&start={start_date}&end={end_date}"
        )
        assert signals_response.status_code == 200
        signals_data = signals_response.json()
        
        if signals_data["signals"] and len(signals_data["signals"]) > 1:
            timestamps = [s["timestamp"] for s in signals_data["signals"]]
            
            # Verify sorted DESC (newest first)
            for i in range(len(timestamps) - 1):
                assert timestamps[i] >= timestamps[i + 1], \
                    f"Signals should be sorted newest-first: {timestamps}"


def test_nvda_warnings_format(fake_provider):
    """Verify warnings are always lists (not dicts or other types)."""
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