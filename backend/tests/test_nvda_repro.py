"""Deterministic repro test for NVDA vs AAPL data correctness."""

import pandas as pd
import pytest
from datetime import date, timedelta

from app.data.fetcher import DataFetcher
from app.data.cache import DataCache
from app.data.ticker_utils import canonical_ticker
from app.storage.repository import DataRepository


def test_nvda_vs_aapl_deterministic_repro(tmp_path):
    """
    Deterministic repro: Fetch AAPL + NVDA same window, compare results.
    
    This test verifies:
    - last_close differs between tickers (>10% difference)
    - last_date matches (both should have same latest trading day)
    - bar counts are similar (within 10% for same window)
    - cache keys are different (canonical ticker isolation)
    """
    from app.data.stooq_provider import StooqProvider
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(provider=StooqProvider(), cache=cache)
    
    # Use same date window for both tickers
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Fetch NVDA data
    nvda_bars, nvda_warnings = fetcher.get_bars("NVDA", start_date, end_date)
    
    # Fetch AAPL data
    aapl_bars, aapl_warnings = fetcher.get_bars("AAPL", start_date, end_date)
    
    # Verify canonical tickers are different
    nvda_canonical = canonical_ticker("NVDA")
    aapl_canonical = canonical_ticker("AAPL")
    assert nvda_canonical != aapl_canonical, \
        f"Cache keys should differ: NVDA={nvda_canonical}, AAPL={aapl_canonical}"
    
    # Both should have data
    assert not nvda_bars.empty, f"NVDA should have data, got empty bars. Warnings: {nvda_warnings}"
    assert not aapl_bars.empty, f"AAPL should have data, got empty bars. Warnings: {aapl_warnings}"
    
    # Verify required columns exist
    required_cols = ["open", "high", "low", "close", "volume"]
    for col in required_cols:
        assert col in nvda_bars.columns, f"NVDA missing column: {col}"
        assert col in aapl_bars.columns, f"AAPL missing column: {col}"
    
    # Get last close prices
    nvda_last_close = float(nvda_bars.iloc[-1]["close"])
    aapl_last_close = float(aapl_bars.iloc[-1]["close"])
    
    # Get last dates
    if isinstance(nvda_bars.index, pd.DatetimeIndex):
        nvda_last_date = nvda_bars.index.max().date()
    else:
        nvda_last_date = pd.to_datetime(nvda_bars.index.max()).date()
    
    if isinstance(aapl_bars.index, pd.DatetimeIndex):
        aapl_last_date = aapl_bars.index.max().date()
    else:
        aapl_last_date = pd.to_datetime(aapl_bars.index.max()).date()
    
    # Assert: last_date matches (both should have same latest trading day)
    assert nvda_last_date == aapl_last_date, \
        f"Last dates should match: NVDA={nvda_last_date}, AAPL={aapl_last_date}"
    
    # Assert: last_close differs between tickers (>10% difference)
    diff_pct = abs(nvda_last_close - aapl_last_close) / min(nvda_last_close, aapl_last_close)
    assert diff_pct > 0.10, \
        f"NVDA and AAPL prices should differ by >10%: " \
        f"NVDA=${nvda_last_close:.2f}, AAPL=${aapl_last_close:.2f}, diff={diff_pct*100:.1f}%"
    
    # Assert: bar counts are similar (within 10% for same window)
    nvda_count = len(nvda_bars)
    aapl_count = len(aapl_bars)
    count_diff_pct = abs(nvda_count - aapl_count) / max(nvda_count, aapl_count)
    assert count_diff_pct < 0.10, \
        f"Bar counts should be similar (within 10%): NVDA={nvda_count}, AAPL={aapl_count}, diff={count_diff_pct*100:.1f}%"
    
    # Verify prices are in reasonable ranges
    assert 1.0 <= nvda_last_close <= 1000.0, \
        f"NVDA price ${nvda_last_close:.2f} outside reasonable range ($1-$1000)"
    assert 1.0 <= aapl_last_close <= 1000.0, \
        f"AAPL price ${aapl_last_close:.2f} outside reasonable range ($1-$1000)"
    
    # Verify no unusual price warnings
    nvda_price_warnings = [w for w in nvda_warnings if "unusual" in w.lower() or "symbol mismatch" in w.lower()]
    aapl_price_warnings = [w for w in aapl_warnings if "unusual" in w.lower() or "symbol mismatch" in w.lower()]
    
    assert len(nvda_price_warnings) == 0, \
        f"NVDA should not have price warnings: {nvda_price_warnings}"
    assert len(aapl_price_warnings) == 0, \
        f"AAPL should not have price warnings: {aapl_price_warnings}"
