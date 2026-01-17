"""Data fetcher with cache integration."""

import logging
from datetime import date
from typing import Optional

import pandas as pd

from app.core.config import settings
from app.data.cache import DataCache
from app.data.provider import MarketDataProvider
from app.data.stooq_provider import StooqProvider
from app.data.ticker_utils import canonical_ticker

logger = logging.getLogger(__name__)


class DataFetcher:
    """Fetches data from providers with caching."""

    def __init__(
        self,
        provider: Optional[MarketDataProvider] = None,
        cache: Optional[DataCache] = None,
    ):
        """Initialize fetcher with provider and cache."""
        self.provider = provider or self._get_default_provider()
        self.cache = cache or DataCache()
        # Track original ticker for provider queries (to avoid double normalization)
        self._ticker_mapping: dict[str, str] = {}  # canonical -> original

    def _get_default_provider(self) -> MarketDataProvider:
        """Get default provider based on settings."""
        provider_name = settings.data_provider.lower()

        if provider_name == "stooq":
            return StooqProvider()
        else:
            raise ValueError(f"Unknown data provider: {provider_name}")

    def get_latest_available_date(self, ticker: str) -> date | None:
        """
        Get the latest available bar date for a ticker.
        
        Optimized to check cache first before making expensive provider calls.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Latest available date or None if no data found
        """
        # Normalize ticker to canonical form
        canonical = canonical_ticker(ticker)
        
        # First, try to get latest date from cache (cheap operation)
        latest_cached_date = self.cache.get_latest_date(canonical)
        if latest_cached_date is not None:
            # Check if cached date is recent (within last 5 days)
            # If so, we can trust it without fetching
            age_days = (date.today() - latest_cached_date).days
            if age_days <= 5:
                return latest_cached_date
            # If cached date is old, we'll fetch to check for newer data
        
        # If no cache or cache is stale, try to get recent data from cache first
        end_date = date.today()
        start_date = date(end_date.year - 1, end_date.month, end_date.day)
        
        bars, _ = self.get_bars(ticker, start_date, end_date, use_cache=True)
        
        if bars.empty:
            # Try fetching a wider range (but still use cache if available)
            start_date = date(end_date.year - 5, end_date.month, end_date.day)
            bars, _ = self.get_bars(ticker, start_date, end_date, use_cache=True)
        
        if bars.empty:
            return latest_cached_date  # Return cached date if available, else None
        
        # Get latest date from fetched bars
        if isinstance(bars.index, pd.DatetimeIndex):
            latest_date = bars.index.max().date()
        else:
            latest_date = pd.to_datetime(bars.index.max()).date()
        
        return latest_date

    def get_bars(
        self, ticker: str, start_date: date, end_date: date, use_cache: bool = True
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Get bars with cache-first strategy.

        Args:
            ticker: Stock ticker symbol (original format, e.g., "NVDA" or "NVDA.US")
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            use_cache: Whether to use cache

        Returns:
            Tuple of (DataFrame with bars, list of warnings)
        """
        # Normalize ticker to canonical form for consistent caching
        canonical = canonical_ticker(ticker)
        
        # Store mapping: canonical -> original (for provider queries)
        # Use first-seen original ticker for this canonical form
        if canonical not in self._ticker_mapping:
            self._ticker_mapping[canonical] = ticker
        
        # Debug logging: log ticker normalization and cache key
        if settings.debug_mode:
            cache_key = f"{canonical}:{self.provider.name}:unadjusted"
            logger.debug(
                f"[DEBUG] DataFetcher.get_bars: "
                f"requested_ticker={ticker}, canonical_ticker={canonical}, "
                f"provider_symbol={self._ticker_mapping.get(canonical, ticker)}, "
                f"cache_key={cache_key}, "
                f"start_date={start_date}, end_date={end_date}, use_cache={use_cache}"
            )
        
        warnings = []

        if use_cache:
            # Check cache first using canonical ticker
            cached_bars = self.cache.get_bars(canonical, start_date, end_date)
            
            # Debug logging: log cache lookup
            if settings.debug_mode:
                logger.debug(
                    f"[DEBUG] DataFetcher.get_bars: "
                    f"cache_lookup: ticker={canonical}, "
                    f"cached_bars_empty={cached_bars.empty}, "
                    f"cached_bars_count={len(cached_bars)}"
                )

            if not cached_bars.empty:
                # Check if we have all requested data
                # cached_bars should have date index from repository
                if isinstance(cached_bars.index, pd.DatetimeIndex):
                    cached_start = cached_bars.index.min().date()
                    cached_end = cached_bars.index.max().date()
                else:
                    # Fallback if index is not datetime
                    cached_start = pd.to_datetime(cached_bars.index.min()).date()
                    cached_end = pd.to_datetime(cached_bars.index.max()).date()

                # Check if cache needs refresh (stale >1 day old and requesting recent data)
                needs_refresh = False
                if self.cache.needs_refresh(canonical, max_age_days=1):
                    # Only auto-refresh if requesting recent data (within last 30 days)
                    days_since_end = (date.today() - end_date).days
                    if days_since_end <= 30:
                        needs_refresh = True
                        if settings.debug_mode:
                            logger.debug(
                                f"[DEBUG] DataFetcher.get_bars: AUTO_REFRESH_TRIGGERED "
                                f"ticker={canonical}, cached_end={cached_end}, "
                                f"requested_end={end_date}, cache_stale=True"
                            )

                # Check if we have all requested data and cache is fresh
                if cached_start <= start_date and cached_end >= end_date and not needs_refresh:
                    logger.debug(
                        f"Returning {len(cached_bars)} bars from cache for {canonical}"
                    )
                    if settings.debug_mode:
                        logger.debug(
                            f"[DEBUG] DataFetcher.get_bars: "
                            f"cache_hit: ticker={canonical}, "
                            f"cached_range=[{cached_start}, {cached_end}], "
                            f"requested_range=[{start_date}, {end_date}]"
                        )
                    return cached_bars, warnings

                # Auto-refresh: if cache is stale and requesting recent data, refresh last 30 days
                if needs_refresh:
                    refresh_start = date.today() - pd.Timedelta(days=30)
                    if refresh_start < cached_end:
                        refresh_start = self._next_trading_day(cached_end)
                    if refresh_start <= date.today():
                        logger.info(
                            f"Auto-refreshing stale cache for {canonical}: {refresh_start} to {date.today()}"
                        )
                        original_ticker = self._ticker_mapping.get(canonical, ticker)
                        # Respect rate limiting: wait 1 second between requests
                        import time
                        time.sleep(1)  # Rate limit: 1 req/sec for Stooq
                        fetched_bars, fetch_warnings = self._fetch_and_cache(
                            original_ticker, canonical, refresh_start, date.today()
                        )
                        warnings.extend(fetch_warnings)
                        if not fetched_bars.empty:
                            # Combine cached and refreshed data
                            cached_bars_reset = cached_bars.reset_index()
                            fetched_bars_reset = fetched_bars.reset_index()
                            combined = pd.concat([cached_bars_reset, fetched_bars_reset])
                            combined = combined.drop_duplicates(subset=["date"], keep="last")
                            combined = combined.set_index("date").sort_index()
                            cached_bars = combined
                            # Update cached_end after refresh
                            if isinstance(combined.index, pd.DatetimeIndex):
                                cached_end = combined.index.max().date()
                            else:
                                cached_end = pd.to_datetime(combined.index.max()).date()

                # Partial cache hit - fetch missing ranges
                if cached_end < end_date:
                    # Fetch missing recent data
                    fetch_start = date(
                        cached_end.year,
                        cached_end.month,
                        cached_end.day,
                    )
                    fetch_start = self._next_trading_day(fetch_start)
                    if fetch_start <= end_date:
                        logger.info(
                            f"Fetching missing data for {canonical}: {fetch_start} to {end_date}"
                        )
                        # Pass original ticker to provider, canonical to cache
                        original_ticker = self._ticker_mapping.get(canonical, ticker)
                        # Respect rate limiting: wait 1 second between requests
                        import time
                        time.sleep(1)  # Rate limit: 1 req/sec for Stooq
                        fetched_bars, fetch_warnings = self._fetch_and_cache(
                            original_ticker, canonical, fetch_start, end_date
                        )
                        warnings.extend(fetch_warnings)

                        # Combine cached and fetched data
                        if not fetched_bars.empty:
                            # Reset index to combine
                            cached_bars_reset = cached_bars.reset_index()
                            fetched_bars_reset = fetched_bars.reset_index()
                            combined = pd.concat([cached_bars_reset, fetched_bars_reset])
                            combined = combined.drop_duplicates(subset=["date"], keep="last")
                            combined = combined.set_index("date").sort_index()
                            cached_bars = combined

            else:
                # No cache - fetch everything
                logger.info(
                    f"No cache found for {canonical}, fetching {start_date} to {end_date}"
                )
                # Pass original ticker to provider, canonical to cache
                original_ticker = self._ticker_mapping.get(canonical, ticker)
                cached_bars, fetch_warnings = self._fetch_and_cache(
                    original_ticker, canonical, start_date, end_date
                )
                warnings.extend(fetch_warnings)

        else:
            # Bypass cache - fetch directly
            logger.info(f"Bypassing cache, fetching {canonical}")
            # Pass original ticker to provider, canonical to cache
            original_ticker = self._ticker_mapping.get(canonical, ticker)
            cached_bars, fetch_warnings = self._fetch_and_cache(
                original_ticker, canonical, start_date, end_date
            )
            warnings.extend(fetch_warnings)

        # Filter to requested date range
        if not cached_bars.empty:
            cached_bars = cached_bars.loc[
                (cached_bars.index.date >= start_date)
                & (cached_bars.index.date <= end_date)
            ]
        
        # Debug logging: log final bars metadata
        if settings.debug_mode and not cached_bars.empty:
            if isinstance(cached_bars.index, pd.DatetimeIndex):
                first_date = cached_bars.index.min().date()
                last_date = cached_bars.index.max().date()
            else:
                first_date = pd.to_datetime(cached_bars.index.min()).date()
                last_date = pd.to_datetime(cached_bars.index.max()).date()
            
            last_close = float(cached_bars.iloc[-1]["close"]) if "close" in cached_bars.columns else None
            
            logger.debug(
                f"[DEBUG] DataFetcher.get_bars: FINAL_RESULT "
                f"ticker={canonical}, bars_count={len(cached_bars)}, "
                f"first_date={first_date}, last_date={last_date}, "
                f"last_close={last_close}, warnings_count={len(warnings)}"
            )

        return cached_bars, warnings

    def _fetch_and_cache(
        self, original_ticker: str, canonical_ticker: str, start_date: date, end_date: date
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Fetch data from provider and store in cache.
        
        Args:
            original_ticker: Original ticker format (for provider query, e.g., "NVDA.US")
            canonical_ticker: Canonical ticker format (for cache storage, e.g., "NVDA")
            start_date: Start date
            end_date: End date
        """
        # Debug logging
        if settings.debug_mode:
            logger.debug(
                f"[DEBUG] DataFetcher._fetch_and_cache: "
                f"original_ticker={original_ticker}, canonical_ticker={canonical_ticker}, "
                f"start_date={start_date}, end_date={end_date}, provider={self.provider.name}"
            )
        try:
            # Fetch from provider using original ticker (provider handles normalization)
            bars = self.provider.get_daily_bars(original_ticker, start_date, end_date)
            
            if settings.debug_mode:
                logger.debug(
                    f"[DEBUG] DataFetcher._fetch_and_cache: PROVIDER_CALL "
                    f"original_ticker={original_ticker}, provider={self.provider.name}, "
                    f"bars_returned={len(bars) if not bars.empty else 0}, bars_empty={bars.empty}"
                )

            if bars.empty:
                return pd.DataFrame(), []

            # Store in cache using canonical ticker (for consistent cache keys)
            warnings = self.cache.store_bars(canonical_ticker, bars, source=self.provider.name)
            
            if settings.debug_mode:
                logger.debug(
                    f"[DEBUG] DataFetcher._fetch_and_cache: CACHE_STORE "
                    f"canonical_ticker={canonical_ticker}, warnings_count={len(warnings)}"
                )

            # Convert to index format for return (fetcher expects date index)
            if "date" in bars.columns:
                bars = bars.set_index("date").sort_index()
            elif not isinstance(bars.index, pd.DatetimeIndex):
                # If already has date index, ensure it's DatetimeIndex
                if bars.index.name == "date" or (hasattr(bars.index, "dtype") and str(bars.index.dtype).startswith("datetime")):
                    bars.index = pd.to_datetime(bars.index)
            
            # Debug logging: log provider response metadata
            if settings.debug_mode and not bars.empty:
                if isinstance(bars.index, pd.DatetimeIndex):
                    first_date = bars.index.min().date()
                    last_date = bars.index.max().date()
                else:
                    first_date = pd.to_datetime(bars.index.min()).date()
                    last_date = pd.to_datetime(bars.index.max()).date()
                
                last_close = float(bars.iloc[-1]["close"]) if "close" in bars.columns else None
                first_close = float(bars.iloc[0]["close"]) if "close" in bars.columns and len(bars) > 0 else None
                
                logger.debug(
                    f"[DEBUG] DataFetcher._fetch_and_cache: PROVIDER_RESPONSE "
                    f"original_ticker={original_ticker}, canonical_ticker={canonical_ticker}, "
                    f"provider={self.provider.name}, bars_count={len(bars)}, "
                    f"first_date={first_date}, last_date={last_date}, "
                    f"first_close={first_close}, last_close={last_close}, "
                    f"adjustment_status=unadjusted (Stooq CSV)"
                )

            return bars, warnings

        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            if settings.debug_mode:
                logger.debug(
                    f"[DEBUG] DataFetcher._fetch_and_cache: ERROR "
                    f"original_ticker={original_ticker}, canonical_ticker={canonical_ticker}, "
                    f"error_type={type(e).__name__}, error_msg={str(e)}"
                )
            return pd.DataFrame(), [f"Failed to fetch data: {str(e)}"]

    def _next_trading_day(self, d: date) -> date:
        """Get next trading day (simplified - just add 1 day)."""
        # In a real implementation, we'd check for weekends/holidays
        # For now, just add 1 day
        from datetime import timedelta

        return d + timedelta(days=1)
