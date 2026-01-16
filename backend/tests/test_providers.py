"""Tests for data providers."""

from datetime import date

import pandas as pd
import pytest

from app.data.normalize import normalize_ohlcv
from app.data.stooq_provider import StooqProvider


def test_normalize_ohlcv():
    """Test OHLCV normalization."""
    # Create sample data with various column name formats
    df = pd.DataFrame({
        "Date": pd.date_range("2020-01-01", periods=10),
        "Open": range(100, 110),
        "High": range(105, 115),
        "Low": range(95, 105),
        "Close": range(102, 112),
        "Volume": range(1000000, 1000010),
    })

    normalized = normalize_ohlcv(df)

    assert "date" in normalized.columns
    assert "open" in normalized.columns
    assert "high" in normalized.columns
    assert "low" in normalized.columns
    assert "close" in normalized.columns
    assert "volume" in normalized.columns

    assert len(normalized) == 10
    assert normalized["date"].dtype.name.startswith("datetime")


def test_stooq_provider_init():
    """Test StooqProvider initialization."""
    provider = StooqProvider()
    assert provider.name == "stooq"


@pytest.mark.skip(reason="Requires network access - test manually")
def test_stooq_provider_fetch():
    """Test StooqProvider data fetching (requires network)."""
    provider = StooqProvider()

    # Test with a known ticker
    start_date = date(2020, 1, 1)
    end_date = date(2020, 12, 31)

    bars = provider.get_daily_bars("AAPL.us", start_date, end_date)

    assert not bars.empty
    assert "date" in bars.columns
    assert "open" in bars.columns
    assert "close" in bars.columns
