"""Pytest fixtures and configuration."""

import os
from datetime import date
from typing import Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest

# Ensure tests run offline by default
os.environ["DATA_PROVIDER"] = "fake"


@pytest.fixture
def fake_provider():
    """Fake provider for offline testing."""
    from app.data.provider import MarketDataProvider

    class FakeProvider(MarketDataProvider):
        def __init__(self):
            self.call_count = 0
            self.call_history = []

        @property
        def name(self) -> str:
            return "fake"

        def get_daily_bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
            self.call_count += 1
            self.call_history.append((ticker, start, end))

            # Generate deterministic fake data
            dates = pd.date_range(start, end, freq="D")
            # Remove weekends (simple approximation)
            dates = dates[dates.weekday < 5]

            if len(dates) == 0:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

            # Simple trending price - different base price per ticker for cache isolation testing
            # Use hash of ticker to generate different base prices with larger spread
            ticker_hash = abs(hash(ticker)) % 10000
            # Generate base prices with larger spread: 50 to 500, ensuring >10% difference
            base_price = 50.0 + (ticker_hash % 450)  # Base price between 50 and 500
            # Add ticker-specific multiplier to ensure significant difference
            ticker_multiplier = 1.0 + (ticker_hash % 100) / 50.0  # 1.0 to 3.0
            base_price = base_price * ticker_multiplier
            price_series = base_price + pd.Series(range(len(dates))) * 0.1

            df = pd.DataFrame({
                "date": dates,
                "open": price_series + 0.1,
                "high": price_series + 0.5,
                "low": price_series - 0.3,
                "close": price_series,
                "volume": 1000000 + pd.Series(range(len(dates))) * 1000,
            })

            return df

        def get_latest_quote(self, ticker: str) -> Optional[dict]:
            return None

    return FakeProvider()


@pytest.fixture
def sample_bars_deterministic():
    """Deterministic sample bars for reproducible tests."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    # Remove weekends
    dates = dates[dates.weekday < 5]
    dates = dates[:60]  # ~60 trading days

    prices = 100.0 + pd.Series(range(len(dates))) * 0.5

    return pd.DataFrame({
        "open": prices + 0.1,
        "high": prices + 0.5,
        "low": prices - 0.3,
        "close": prices,
        "volume": 1000000 + pd.Series(range(len(dates))) * 10000,
    }, index=dates)


@pytest.fixture
def sample_bars_with_split():
    """Sample bars with a synthetic split (price discontinuity)."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    dates = dates[dates.weekday < 5][:60]

    # Create prices Series with proper index alignment
    prices = pd.Series(100.0 + pd.Series(range(len(dates)), index=dates) * 0.5, index=dates)

    # Add a 2:1 split on day 30 (price drops 50%)
    split_day = 30
    prices.iloc[split_day:] = prices.iloc[split_day:] * 0.5

    return pd.DataFrame({
        "open": prices + 0.1,
        "high": prices + 0.5,
        "low": prices - 0.3,
        "close": prices,
        "volume": pd.Series(1000000 + pd.Series(range(len(dates)), index=dates) * 10000, index=dates),
    }, index=dates)
