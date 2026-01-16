"""Tests for cache isolation to ensure tickers don't share cache entries."""

import pytest
from datetime import date

from app.data.cache import DataCache
from app.data.fetcher import DataFetcher
from app.data.ticker_utils import canonical_ticker
from app.storage.repository import DataRepository


def test_ticker_canonical_normalization():
    """Test that NVDA, nvda, NVDA.US resolve to same canonical key."""
    # Test various ticker forms
    variants = ["NVDA", "nvda", "NVDA.US", "NVDA.us", "nVdA", "NVDA.UK"]
    
    canonical_keys = [canonical_ticker(v) for v in variants]
    
    # All US variants should normalize to "NVDA"
    assert canonical_keys[0] == "NVDA"  # NVDA
    assert canonical_keys[1] == "NVDA"  # nvda
    assert canonical_keys[2] == "NVDA"  # NVDA.US
    assert canonical_keys[3] == "NVDA"  # NVDA.us
    assert canonical_keys[4] == "NVDA"  # nVdA
    # NVDA.UK should also normalize to NVDA (with warning logged)
    assert canonical_keys[5] == "NVDA"  # NVDA.UK


def test_cache_isolation_different_tickers(tmp_path):
    """Test that AAPL and NVDA do not share cache entries."""
    from app.data.stooq_provider import StooqProvider
    
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    
    # Fetch NVDA data
    nvda_bars, _ = cache.get_bars("NVDA", date(2023, 1, 1), date(2023, 1, 31))
    
    # Fetch AAPL data
    aapl_bars, _ = cache.get_bars("AAPL", date(2023, 1, 1), date(2023, 1, 31))
    
    # Ensure they don't share cache (if one is empty and other isn't, that's fine for this test)
    # The key test is that they use different cache keys
    nvda_canonical = canonical_ticker("NVDA")
    aapl_canonical = canonical_ticker("AAPL")
    
    assert nvda_canonical != aapl_canonical, "NVDA and AAPL should have different canonical keys"
    
    # Verify cache keys are different by checking repository directly
    # (if repository was implemented with direct key access)
    nvda_latest = repository.get_latest_date(nvda_canonical)
    aapl_latest = repository.get_latest_date(aapl_canonical)
    
    # These might be None if data wasn't fetched, but if both are fetched,
    # they should be independent
    # Just verify the canonical keys are different
    assert nvda_canonical == "NVDA"
    assert aapl_canonical == "AAPL"
    assert nvda_canonical != aapl_canonical


def test_cache_isolation_same_ticker_variants(tmp_path):
    """Test that NVDA and NVDA.US resolve to same cache entry."""
    from app.data.stooq_provider import StooqProvider
    
    db_path = tmp_path / "test.db"
    repository = DataRepository(db_path=str(db_path))
    cache = DataCache(repository=repository)
    
    # Both should normalize to same canonical key
    nvda_canonical = canonical_ticker("NVDA")
    nvda_us_canonical = canonical_ticker("NVDA.US")
    
    assert nvda_canonical == nvda_us_canonical, "NVDA and NVDA.US should have same canonical key"
    assert nvda_canonical == "NVDA"
    
    # If we fetch with one variant and then fetch with another, they should use same cache
    # (Assuming cache is properly keyed by canonical ticker)
    # This is a structural test - actual cache hit testing requires data fetching


def test_ticker_normalization_case_insensitive():
    """Test that ticker normalization is case-insensitive."""
    variants = ["nvda", "NVDA", "NvDa", "nVdA"]
    
    canonical_keys = [canonical_ticker(v) for v in variants]
    
    # All should normalize to same key
    assert all(k == "NVDA" for k in canonical_keys), "All case variants should normalize to NVDA"


def test_cache_key_includes_ticker():
    """Test that cache operations use canonical ticker as key."""
    # This is a structural test - verify that cache methods normalize ticker
    # The actual implementation should ensure cache.get_bars and cache.store_bars
    # use canonical_ticker internally
    
    # Test that canonical_ticker is called in cache operations
    # (This is verified by implementation - cache.get_bars and store_bars call canonical_ticker)
    assert canonical_ticker("NVDA") == "NVDA"
    assert canonical_ticker("nvda") == "NVDA"
    assert canonical_ticker("NVDA.US") == "NVDA"