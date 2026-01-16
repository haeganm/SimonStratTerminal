"""Data caching layer with validation."""

import logging
from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd

from app.core.config import settings
from app.core.exceptions import CacheError
from app.data.ticker_utils import canonical_ticker
from app.storage.repository import DataRepository

logger = logging.getLogger(__name__)


class DataCache:
    """Cache for market data with validation and deduplication."""

    def __init__(self, repository: Optional[DataRepository] = None):
        """Initialize cache with repository."""
        self.repository = repository or DataRepository()

    def get_bars(
        self, ticker: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """
        Get bars from cache (ticker should be canonical).

        Args:
            ticker: Stock ticker symbol (canonical form)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            DataFrame with date index and OHLCV columns
        """
        # Ensure ticker is canonical
        canonical = canonical_ticker(ticker)
        
        # Debug logging: log cache key construction
        cache_key = f"{canonical}:{self.repository.__class__.__name__}:unadjusted"  # Cache key format
        if settings.debug_mode:
            logger.debug(
                f"[DEBUG] DataCache.get_bars: CACHE_LOOKUP "
                f"input_ticker={ticker}, canonical_ticker={canonical}, "
                f"cache_key={cache_key}, start_date={start_date}, end_date={end_date}"
            )
        import json
        from pathlib import Path
        from datetime import datetime
        debug_log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
        try:
            log_entry = {
                "timestamp": int(datetime.now().timestamp() * 1000),
                "location": "cache.get_bars:entry",
                "message": "get_bars called",
                "data": {"ticker": ticker, "start": str(start_date), "end": str(end_date)},
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "B",
            }
            with open(debug_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass
        
        try:
            bars = self.repository.get_bars(canonical, start_date, end_date)
            
            # Debug logging: log cache hit/miss with metadata
            if settings.debug_mode:
                cache_status = "hit" if not bars.empty else "miss"
                if not bars.empty:
                    if isinstance(bars.index, pd.DatetimeIndex):
                        first_date = bars.index.min().date()
                        last_date = bars.index.max().date()
                    else:
                        first_date = pd.to_datetime(bars.index.min()).date()
                        last_date = pd.to_datetime(bars.index.max()).date()
                    last_close = float(bars.iloc[-1]["close"]) if "close" in bars.columns else None
                    logger.debug(
                        f"[DEBUG] DataCache.get_bars: CACHE_{cache_status.upper()} "
                        f"ticker={canonical}, bars_count={len(bars)}, "
                        f"first_date={first_date}, last_date={last_date}, last_close={last_close}"
                    )
                else:
                    logger.debug(
                        f"[DEBUG] DataCache.get_bars: CACHE_{cache_status.upper()} "
                        f"ticker={canonical}, bars_empty=True"
                    )
            
            try:
                log_entry = {
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "location": "cache.get_bars:after_repo",
                    "message": "Repository returned data",
                    "data": {"ticker": canonical, "bars_empty": bars.empty, "bars_count": len(bars) if not bars.empty else 0},
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                }
                with open(debug_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except Exception:
                pass
            
            return bars
        except Exception as e:
            logger.error(f"Error retrieving bars from cache: {e}")
            raise CacheError(f"Failed to retrieve cached data: {e}") from e

    def store_bars(
        self, ticker: str, bars: pd.DataFrame, source: str = "stooq"
    ) -> list[str]:
        """
        Store bars in cache with validation (ticker should be canonical).

        Args:
            ticker: Stock ticker symbol (canonical form)
            bars: DataFrame with OHLCV data (either with 'date' column or DatetimeIndex)
            source: Data source identifier

        Returns:
            List of validation warnings
        """
        # Ensure ticker is canonical
        canonical = canonical_ticker(ticker)
        
        # Debug logging
        if settings.debug_mode:
            logger.debug(
                f"[DEBUG] DataCache.store_bars: "
                f"input_ticker={ticker}, canonical_ticker={canonical}, "
                f"bars_count={len(bars)}, source={source}"
            )
        
        if bars.empty:
            logger.warning(f"Attempted to store empty bars for {canonical}")
            return []

        try:
            # Normalize bars: ensure 'date' column exists
            bars_normalized = bars.copy()
            
            # If 'date' column is missing, check if index is datetime-like
            if "date" not in bars_normalized.columns:
                if isinstance(bars_normalized.index, (pd.DatetimeIndex, pd.PeriodIndex)):
                    # Reset index and rename to 'date'
                    bars_normalized = bars_normalized.reset_index()
                    # The index column might have a different name, rename it to 'date'
                    if bars_normalized.index.name or len(bars_normalized.columns) > 0:
                        # Find the datetime column (usually the first one after reset_index)
                        date_col = None
                        for col in bars_normalized.columns:
                            if pd.api.types.is_datetime64_any_dtype(bars_normalized[col]):
                                date_col = col
                                break
                        if date_col:
                            bars_normalized = bars_normalized.rename(columns={date_col: "date"})
                        elif len(bars_normalized.columns) > 0:
                            # Assume first column is date if no datetime column found
                            first_col = bars_normalized.columns[0]
                            bars_normalized = bars_normalized.rename(columns={first_col: "date"})
                else:
                    raise CacheError(f"Missing 'date' column and index is not datetime-like for {ticker}")
            
            # Ensure date is datetime type
            bars_normalized["date"] = pd.to_datetime(bars_normalized["date"])
            
            # Sort by date and drop duplicates
            bars_normalized = bars_normalized.sort_values("date")
            bars_normalized = bars_normalized.drop_duplicates(subset=["date"], keep="last")
            
            # Validate before storing
            warnings = self.repository.validate_bars(canonical, bars_normalized)

            # Store bars using canonical ticker
            self.repository.store_bars(canonical, bars_normalized, source)

            if warnings:
                logger.warning(f"Validation warnings for {canonical}: {warnings}")
            
            # Debug logging: log cache store success
            if settings.debug_mode:
                logger.debug(
                    f"[DEBUG] DataCache.store_bars: "
                    f"ticker={canonical}, stored_bars={len(bars_normalized)}, "
                    f"warnings_count={len(warnings)}"
                )

            return warnings
        except Exception as e:
            logger.error(f"Error storing bars in cache: {e}")
            raise CacheError(f"Failed to store data in cache: {e}") from e

    def get_latest_date(self, ticker: str) -> Optional[date]:
        """Get the latest cached date for a ticker (ticker should be canonical)."""
        canonical = canonical_ticker(ticker)
        try:
            return self.repository.get_latest_date(canonical)
        except Exception as e:
            logger.error(f"Error getting latest date: {e}")
            return None

    def needs_refresh(self, ticker: str, max_age_days: int = 1) -> bool:
        """
        Check if cached data needs refresh (ticker should be canonical).

        Args:
            ticker: Stock ticker symbol (canonical form)
            max_age_days: Maximum age of cached data in days

        Returns:
            True if data needs refresh
        """
        canonical = canonical_ticker(ticker)
        latest_date = self.get_latest_date(canonical)
        if latest_date is None:
            return True

        age = (date.today() - latest_date).days
        return age > max_age_days

    def get_cached_date_range(
        self, ticker: str, requested_start: date, requested_end: date
    ) -> tuple[Optional[date], Optional[date]]:
        """
        Determine what date range is already cached (ticker should be canonical).

        Returns:
            Tuple of (cached_start, cached_end) or (None, None) if no cache
        """
        canonical = canonical_ticker(ticker)
        latest_date = self.get_latest_date(canonical)
        if latest_date is None:
            return (None, None)

        # For simplicity, we only track latest date
        # In a full implementation, we'd track min/max dates
        # For now, assume we have data up to latest_date
        if latest_date >= requested_end:
            return (requested_start, requested_end)
        elif latest_date >= requested_start:
            return (requested_start, latest_date)
        else:
            return (None, None)
