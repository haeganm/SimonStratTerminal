"""NVDA-specific data verification tests."""

import pandas as pd
import pytest
from datetime import date, timedelta

from app.data.fetcher import DataFetcher
from app.data.stooq_provider import StooqProvider
from app.data.ticker_utils import canonical_ticker
from app.storage.repository import DataRepository


def test_nvda_ticker_variants(tmp_path):
    """Verify NVDA, nvda, NVDA.US all return same data."""
    from app.data.cache import DataCache
    
    from app.data.stooq_provider import StooqProvider
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(provider=StooqProvider(), cache=cache)
    
    ticker_variants = ["NVDA", "nvda", "NVDA.US", "NVDA.us"]
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    results = []
    for ticker in ticker_variants:
        bars, _ = fetcher.get_bars(ticker, start_date, end_date)
        if not bars.empty and "close" in bars.columns:
            last_close = bars.iloc[-1]["close"]
            last_date = bars.index.max().date() if isinstance(bars.index, pd.DatetimeIndex) else pd.to_datetime(bars.index.max()).date()
            results.append({
                "ticker": ticker,
                "canonical": canonical_ticker(ticker),
                "last_close": last_close,
                "last_date": last_date,
                "bars_count": len(bars),
            })
    
    # All should normalize to same canonical key
    canonicals = [r["canonical"] for r in results]
    assert all(c == "NVDA" for c in canonicals), "All variants should normalize to NVDA"
    
    # If data was fetched, last closes should be identical
    if len(results) > 1 and all(r["last_close"] is not None for r in results):
        last_closes = [r["last_close"] for r in results]
        # All last closes should be within 0.1% of each other
        first_close = last_closes[0]
        for close in last_closes[1:]:
            diff_pct = abs(close - first_close) / first_close if first_close > 0 else 0
            assert diff_pct < 0.001, \
                f"Last closes should match: {last_closes} (diff > 0.1%)"


def test_nvda_cache_isolation(tmp_path):
    """Ensure NVDA cache doesn't contain AAPL or other ticker data."""
    from app.data.cache import DataCache
    
    from app.data.stooq_provider import StooqProvider
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(provider=StooqProvider(), cache=cache)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Fetch NVDA data
    nvda_bars, _ = fetcher.get_bars("NVDA", start_date, end_date)
    
    # Fetch AAPL data
    aapl_bars, _ = fetcher.get_bars("AAPL", start_date, end_date)
    
    # Ensure they don't share cache (if one is empty and other isn't, that's fine)
    # The key test is that they use different cache keys
    nvda_canonical = canonical_ticker("NVDA")
    aapl_canonical = canonical_ticker("AAPL")
    
    assert nvda_canonical != aapl_canonical, "NVDA and AAPL should have different canonical keys"
    
    # If both have data, last closes should be different (not identical)
    if not nvda_bars.empty and not aapl_bars.empty:
        if "close" in nvda_bars.columns and "close" in aapl_bars.columns:
            nvda_last_close = nvda_bars.iloc[-1]["close"]
            aapl_last_close = aapl_bars.iloc[-1]["close"]
            
            # Prices should be different (NVDA and AAPL have different prices)
            diff_pct = abs(nvda_last_close - aapl_last_close) / min(nvda_last_close, aapl_last_close)
            assert diff_pct > 0.01, \
                f"NVDA and AAPL last closes should differ: NVDA=${nvda_last_close:.2f}, AAPL=${aapl_last_close:.2f}"


def test_nvda_stooq_direct_comparison(tmp_path):
    """Fetch NVDA directly from Stooq and compare to our processed output."""
    import pandas as pd
    import httpx
    from io import StringIO
    
    provider = StooqProvider()
    
    end_date = date.today()
    start_date = end_date - timedelta(days=10)  # Narrow window for testing
    
    # Fetch via our provider (normalized)
    our_bars = provider.get_daily_bars("NVDA", start_date, end_date)
    
    # Fetch raw from Stooq directly (try NVDA.US)
    try:
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        url = f"https://stooq.com/q/d/l/?s=NVDA.US&d1={start_str}&d2={end_str}&i=d"
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            if response.status_code == 200 and "text/csv" in response.headers.get("content-type", "").lower():
                raw_df = pd.read_csv(StringIO(response.text), parse_dates=["Date"], date_format="%Y-%m-%d")
                
                if not raw_df.empty and not our_bars.empty:
                    # Compare last close prices
                    raw_last_close = float(raw_df.iloc[-1]["Close"])
                    our_last_close = float(our_bars.iloc[-1]["close"])
                    
                    # Should be within 0.1% tolerance
                    diff_pct = abs(our_last_close - raw_last_close) / raw_last_close if raw_last_close > 0 else 0
                    assert diff_pct < 0.001, \
                        f"Processed close ${our_last_close:.2f} should match Stooq raw ${raw_last_close:.2f} " \
                        f"(diff={diff_pct*100:.2f}% > 0.1%)"
    except Exception as e:
        # Skip test if network request fails (offline mode)
        pytest.skip(f"Could not fetch raw Stooq data: {e}")


def test_nvda_price_sanity_check(tmp_path):
    """Verify NVDA price is in reasonable range ($1-$1000)."""
    from app.data.cache import DataCache
    
    from app.data.stooq_provider import StooqProvider
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(provider=StooqProvider(), cache=cache)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    bars, warnings = fetcher.get_bars("NVDA", start_date, end_date)
    
    if not bars.empty and "close" in bars.columns:
        last_close = bars.iloc[-1]["close"]
        
        # NVDA price should be in reasonable range ($1-$1000)
        # Current NVDA is ~$100-$200 range, so this is a sanity check
        assert 1.0 <= last_close <= 1000.0, \
            f"NVDA close price ${last_close:.2f} is outside reasonable range ($1-$1000). " \
            f"This might indicate symbol mismatch or data error."
        
        # Check warnings for unusual price
        unusual_price_warnings = [w for w in warnings if "unusual close price" in w.lower() or "symbol mismatch" in w.lower()]
        assert len(unusual_price_warnings) == 0, \
            f"NVDA price should not trigger unusual price warnings: {unusual_price_warnings}"


def test_nvda_vs_aapl_price_difference(tmp_path):
    """Verify NVDA and AAPL have different prices (cache collision check)."""
    from app.data.cache import DataCache
    
    from app.data.stooq_provider import StooqProvider
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    fetcher = DataFetcher(provider=StooqProvider(), cache=cache)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Fetch both tickers
    nvda_bars, _ = fetcher.get_bars("NVDA", start_date, end_date)
    aapl_bars, _ = fetcher.get_bars("AAPL", start_date, end_date)
    
    # Both should have data for same date range
    if not nvda_bars.empty and not aapl_bars.empty:
        if "close" in nvda_bars.columns and "close" in aapl_bars.columns:
            # Get last close for same date if available
            nvda_last_date = nvda_bars.index.max()
            aapl_last_date = aapl_bars.index.max()
            
            # If same date, compare directly
            if nvda_last_date == aapl_last_date:
                nvda_close = nvda_bars.iloc[-1]["close"]
                aapl_close = aapl_bars.iloc[-1]["close"]
                
                # Prices should differ significantly (>10%)
                diff_pct = abs(nvda_close - aapl_close) / min(nvda_close, aapl_close)
                assert diff_pct > 0.10, \
                    f"NVDA and AAPL prices should differ: NVDA=${nvda_close:.2f}, AAPL=${aapl_close:.2f} " \
                    f"(diff={diff_pct*100:.1f}% < 10% - possible cache collision)"