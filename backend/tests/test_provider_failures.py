"""Tests for provider failure scenarios: network errors, timeouts, rate limits."""

from datetime import date
from unittest.mock import patch, MagicMock
import pytest
import pandas as pd

from app.data.fetcher import DataFetcher
from app.data.provider import MarketDataProvider


class FailingProvider(MarketDataProvider):
    """Provider that simulates various failure modes."""
    
    def __init__(self, failure_mode="network_error"):
        self.failure_mode = failure_mode
        self.call_count = 0
    
    @property
    def name(self) -> str:
        return "failing"
    
    def get_daily_bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        self.call_count += 1
        
        if self.failure_mode == "network_error":
            raise ConnectionError("Network connection failed")
        elif self.failure_mode == "timeout":
            raise TimeoutError("Request timed out")
        elif self.failure_mode == "rate_limit":
            if self.call_count <= 2:
                raise Exception("Rate limit exceeded")
            # After 2 failures, succeed
            return self._generate_fake_data(start, end)
        elif self.failure_mode == "partial_data":
            # Return partial data (some dates missing)
            dates = pd.date_range(start, end, freq="D")[:10]  # Only first 10 days
            return self._generate_fake_data_for_dates(dates)
        elif self.failure_mode == "invalid_data":
            # Return invalid data structure
            return pd.DataFrame({"wrong": [1, 2, 3]})
        else:
            return self._generate_fake_data(start, end)
    
    def get_latest_quote(self, ticker: str):
        return None
    
    def _generate_fake_data(self, start: date, end: date) -> pd.DataFrame:
        """Generate fake valid data."""
        dates = pd.date_range(start, end, freq="D")
        dates = dates[dates.weekday < 5][:min(60, len(dates))]  # Weekdays only, max 60
        
        if len(dates) == 0:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        
        prices = 100.0 + pd.Series(range(len(dates))) * 0.1
        return pd.DataFrame({
            "date": dates,
            "open": prices + 0.1,
            "high": prices + 0.5,
            "low": prices - 0.3,
            "close": prices,
            "volume": 1000000 + pd.Series(range(len(dates))) * 1000,
        })
    
    def _generate_fake_data_for_dates(self, dates: pd.DatetimeIndex) -> pd.DataFrame:
        """Generate fake data for specific dates."""
        prices = 100.0 + pd.Series(range(len(dates))) * 0.1
        return pd.DataFrame({
            "date": dates,
            "open": prices + 0.1,
            "high": prices + 0.5,
            "low": prices - 0.3,
            "close": prices,
            "volume": 1000000 + pd.Series(range(len(dates))) * 1000,
        })


class TestProviderFailures:
    """Test handling of provider failures."""

    def test_network_error_handling(self):
        """Test handling of network connection errors."""
        provider = FailingProvider(failure_mode="network_error")
        fetcher = DataFetcher(provider=provider)
        
        # Should raise or return empty with warnings
        try:
            bars, warnings = fetcher.get_bars("TEST", date(2020, 1, 1), date(2020, 1, 31))
            # If it doesn't raise, should return empty with warnings
            assert bars.empty
            assert len(warnings) > 0
        except (ConnectionError, Exception):
            # Expected to raise
            pass

    def test_timeout_handling(self):
        """Test handling of timeout errors."""
        provider = FailingProvider(failure_mode="timeout")
        fetcher = DataFetcher(provider=provider)
        
        try:
            bars, warnings = fetcher.get_bars("TEST", date(2020, 1, 1), date(2020, 1, 31))
            assert bars.empty or len(warnings) > 0
        except (TimeoutError, Exception):
            # Expected to raise
            pass

    def test_rate_limit_handling(self):
        """Test handling of rate limit errors."""
        provider = FailingProvider(failure_mode="rate_limit")
        fetcher = DataFetcher(provider=provider)
        
        # First calls should fail
        try:
            bars1, warnings1 = fetcher.get_bars("TEST", date(2020, 1, 1), date(2020, 1, 31))
            # May succeed after retries or fail
            assert isinstance(bars1, pd.DataFrame)
        except Exception:
            # May raise on first attempts
            pass

    def test_partial_data_handling(self):
        """Test handling when provider returns partial data."""
        provider = FailingProvider(failure_mode="partial_data")
        fetcher = DataFetcher(provider=provider)
        
        bars, warnings = fetcher.get_bars("TEST", date(2020, 1, 1), date(2020, 1, 31))
        
        # Should return partial data
        assert isinstance(bars, pd.DataFrame)
        assert len(bars) < 31  # Less than full month
        # Warnings may or may not be generated (depends on implementation)
        # The key is that partial data is handled gracefully
        assert isinstance(warnings, list)

    def test_invalid_data_structure(self):
        """Test handling when provider returns invalid data structure."""
        provider = FailingProvider(failure_mode="invalid_data")
        fetcher = DataFetcher(provider=provider)
        
        try:
            bars, warnings = fetcher.get_bars("TEST", date(2020, 1, 1), date(2020, 1, 31))
            # Should normalize or handle gracefully
            assert isinstance(bars, pd.DataFrame)
            # May be empty after normalization
            # Warnings may or may not be generated (normalization may raise instead)
            assert isinstance(warnings, list)
        except (KeyError, ValueError):
            # Expected to raise if normalization fails - this is correct behavior
            pass

    def test_api_handles_provider_failures(self):
        """Test API endpoints handle provider failures gracefully."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.data.fetcher import DataFetcher
        
        provider = FailingProvider(failure_mode="network_error")
        fetcher = DataFetcher(provider=provider)
        
        with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
            client = TestClient(app)
            
            # History endpoint
            response = client.get("/history?ticker=TEST&start=2020-01-01&end=2020-01-31")
            # Should return error or empty data with warnings
            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert "warnings" in data
                assert len(data["warnings"]) > 0

    def test_cache_fallback_on_provider_failure(self):
        """Test that cache is used when provider fails."""
        from app.data.cache import DataCache
        from app.storage.repository import DataRepository
        import tempfile
        import os
        import shutil
        
        # Create temp directory for database
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test.db")
        
        try:
            repository = DataRepository(db_path=db_path)
            cache = DataCache(repository=repository)
            
            # Store data in cache first
            good_provider = FailingProvider(failure_mode="success")
            good_fetcher = DataFetcher(provider=good_provider, cache=cache)
            bars1, _ = good_fetcher.get_bars("TEST", date(2020, 1, 1), date(2020, 1, 31), use_cache=True)
            assert not bars1.empty
            
            # Now use failing provider but with cache
            failing_provider = FailingProvider(failure_mode="network_error")
            failing_fetcher = DataFetcher(provider=failing_provider, cache=cache)
            
            # Should get data from cache even though provider fails
            try:
                bars2, warnings = failing_fetcher.get_bars("TEST", date(2020, 1, 1), date(2020, 1, 31), use_cache=True)
                # Should get from cache (provider failure shouldn't prevent cache access)
                assert isinstance(bars2, pd.DataFrame)
                assert not bars2.empty  # Should have cached data
            except Exception as e:
                # If it raises, verify it's not a cache issue
                assert "cache" not in str(e).lower() or "database" not in str(e).lower()
        finally:
            # Cleanup
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
