"""Stooq data provider implementation."""

import logging
import time
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlencode

import httpx
import pandas as pd

from app.core.config import settings
from app.core.exceptions import DataProviderError
from app.data.normalize import normalize_ohlcv
from app.data.provider import MarketDataProvider

logger = logging.getLogger(__name__)


class StooqProvider(MarketDataProvider):
    """Provider for historical data from Stooq (CSV download)."""

    BASE_URL = "https://stooq.com/q/d/l/"
    _last_request_time: float = 0

    @property
    def name(self) -> str:
        """Provider name."""
        return "stooq"

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        min_interval = settings.stooq_rate_limit_seconds
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _normalize_ticker(self, ticker: str) -> list[str]:
        """
        Generate ticker candidates to try (case-insensitive normalization).
        
        For US stocks, prioritizes .US suffix to ensure correct symbol resolution.
        
        Args:
            ticker: Input ticker (e.g., "NVDA", "nvda", "NVDA.US", "NVDA.us")
            
        Returns:
            List of ticker candidates to try in order (NVDA.US prioritized for US stocks)
        """
        # Normalize to uppercase and strip whitespace
        ticker = ticker.strip().upper()
        
        candidates = []
        
        # Check if this is a known US ticker (load from symbols_us.csv if available)
        known_us_tickers = self._get_known_us_tickers()
        
        # If already has a dot, try as-is first
        if "." in ticker:
            candidates.append(ticker)
            # Also try with .US if it has a different suffix
            if not ticker.endswith(".US"):
                base = ticker.split(".")[0]
                candidates.append(f"{base}.US")
        else:
            # No dot - for known US tickers, prioritize .US suffix
            base_ticker = ticker
            if known_us_tickers and base_ticker in known_us_tickers:
                # Known US ticker: try .US first, then as-is
                candidates.append(f"{base_ticker}.US")
                candidates.append(base_ticker)
            else:
                # Unknown ticker: try as-is first, then .US
                candidates.append(base_ticker)
                candidates.append(f"{base_ticker}.US")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for cand in candidates:
            if cand not in seen:
                seen.add(cand)
                unique_candidates.append(cand)
        
        return unique_candidates
    
    def _get_known_us_tickers(self) -> set[str]:
        """Get set of known US ticker symbols from symbols_us.csv (cached)."""
        import csv
        from pathlib import Path
        
        # Cache for known US tickers
        if not hasattr(self, '_known_us_tickers_cache'):
            self._known_us_tickers_cache = None
            
            try:
                symbols_path = Path(__file__).parent.parent.parent.parent / "data" / "symbols_us.csv"
                if symbols_path.exists():
                    known_tickers = set()
                    with open(symbols_path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            symbol = row.get("symbol", "").strip().upper()
                            if symbol:
                                known_tickers.add(symbol)
                    self._known_us_tickers_cache = known_tickers
                    logger.debug(f"Loaded {len(known_tickers)} known US tickers from symbols_us.csv")
            except Exception as e:
                logger.warning(f"Could not load known US tickers: {e}")
                self._known_us_tickers_cache = set()
        
        return self._known_us_tickers_cache or set()

    def get_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> pd.DataFrame:
        """
        Download daily bars from Stooq.

        Args:
            ticker: Stock ticker symbol (accepts NVDA, nvda, NVDA.US, NVDA.us, etc.)
            start: Start date
            end: End date

        Returns:
            DataFrame with columns: date, open, high, low, close, volume

        Raises:
            DataProviderError: If download or parsing fails for all ticker candidates
        """
        # Apply rate limiting
        self._rate_limit()

        # Get ticker candidates to try
        ticker_candidates = self._normalize_ticker(ticker)
        
        # Debug logging: log ticker normalization path
        if settings.debug_mode:
            logger.debug(
                f"[DEBUG] StooqProvider.get_daily_bars: TICKER_NORMALIZATION "
                f"input_ticker={ticker}, candidates={ticker_candidates}, "
                f"provider=stooq"
            )
        
        last_error = None
        
        for candidate in ticker_candidates:
            try:
                result = self._fetch_bars_for_ticker(candidate, start, end)
                # Debug logging: log which candidate succeeded
                if settings.debug_mode:
                    logger.debug(
                        f"[DEBUG] StooqProvider.get_daily_bars: SUCCESS "
                        f"input_ticker={ticker}, successful_candidate={candidate}, "
                        f"provider_symbol_queried={candidate}"
                    )
                return result
            except DataProviderError as e:
                last_error = e
                logger.debug(f"Failed to fetch {candidate}: {e}")
                if settings.debug_mode:
                    logger.debug(
                        f"[DEBUG] StooqProvider.get_daily_bars: "
                        f"candidate={candidate} failed: {e}"
                    )
                continue
            except Exception as e:
                last_error = DataProviderError(f"Unexpected error fetching {candidate}: {e}")
                logger.debug(f"Unexpected error fetching {candidate}: {e}")
                continue
        
        # All candidates failed
        if len(ticker_candidates) > 1:
            raise DataProviderError(
                f"Ticker not found. Tried: {', '.join(ticker_candidates)}. "
                f"Try adding .us suffix (e.g., {ticker_candidates[0]}.us)"
            )
        else:
            raise DataProviderError(
                f"Ticker not found: {ticker_candidates[0]}. "
                f"Try adding .us suffix (e.g., {ticker_candidates[0]}.us)"
            )

    def _fetch_bars_for_ticker(
        self, ticker: str, start: date, end: date
    ) -> pd.DataFrame:
        """
        Fetch bars for a specific ticker (internal method).
        
        Args:
            ticker: Ticker symbol (already normalized)
            start: Start date
            end: End date
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
            
        Raises:
            DataProviderError: If fetch fails
        """

        # Format dates for Stooq API
        # Stooq expects dates in format: YYYYMMDD
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        # Build URL
        params = {
            "s": ticker,
            "d1": start_str,
            "d2": end_str,
            "i": "d",  # daily bars
        }
        url = f"{self.BASE_URL}?{urlencode(params)}"

        logger.info(f"Fetching data from Stooq: {ticker} from {start} to {end}")
        
        # Debug logging: log exact ticker sent to Stooq API
        if settings.debug_mode:
            logger.debug(
                f"[DEBUG] StooqProvider._fetch_bars_for_ticker: "
                f"ticker={ticker}, start={start}, end={end}, url={url}"
            )

        # Download CSV
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)

            if response.status_code != 200:
                raise DataProviderError(
                    f"Stooq API returned status {response.status_code}: {response.text}"
                )

            # Check if response is CSV (Stooq sometimes returns HTML on errors)
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise DataProviderError(
                    f"Stooq returned HTML instead of CSV. Possible ticker not found: {ticker}"
                )

            # Parse CSV
            # Stooq CSV format: Date,Open,High,Low,Close,Volume
            # Read from response content
            from io import StringIO
            df = pd.read_csv(
                StringIO(response.text),
                parse_dates=["Date"],
                date_format="%Y-%m-%d",
            )

            if df.empty:
                raise DataProviderError(f"No data returned from Stooq for {ticker}")

            # Normalize to standard format
            df_normalized = normalize_ohlcv(df)

            # Validate response: check if bars count is suspiciously low
            expected_days = (end - start).days
            bars_count = len(df_normalized)
            
            if bars_count < expected_days * 0.5:  # Less than 50% of expected days
                logger.warning(
                    f"Suspiciously low bar count for {ticker}: "
                    f"got {bars_count} bars, expected ~{expected_days} days. "
                    f"This might indicate wrong symbol or missing data."
                )
            
            # Verify we got reasonable amount of data
            if bars_count == 0:
                raise DataProviderError(f"No data returned from Stooq for {ticker} after normalization")
            
            logger.info(
                f"Successfully fetched {len(df_normalized)} bars for {ticker} "
                f"(expected ~{expected_days} days)"
            )
            
            # Debug logging: log first/last bar dates and close prices
            if settings.debug_mode and not df_normalized.empty:
                first_date = df_normalized.iloc[0]["date"] if "date" in df_normalized.columns else df_normalized.index[0]
                last_date = df_normalized.iloc[-1]["date"] if "date" in df_normalized.columns else df_normalized.index[-1]
                first_close = df_normalized.iloc[0]["close"] if "close" in df_normalized.columns else None
                last_close = df_normalized.iloc[-1]["close"] if "close" in df_normalized.columns else None
                
                logger.debug(
                    f"[DEBUG] StooqProvider._fetch_bars_for_ticker: "
                    f"ticker={ticker}, bars_returned={len(df_normalized)}, "
                    f"first_date={first_date}, first_close={first_close}, "
                    f"last_date={last_date}, last_close={last_close}, "
                    f"expected_days={expected_days}"
                )

            return df_normalized

    def get_latest_quote(self, ticker: str) -> Optional[dict]:
        """
        Get latest quote (not available for free Stooq CSV endpoint).

        Stooq CSV endpoint is historical only. This returns None to indicate
        that real-time quotes are not available.

        Args:
            ticker: Stock ticker symbol

        Returns:
            None (real-time quotes not available via free CSV endpoint)
        """
        # Stooq CSV endpoint doesn't provide real-time quotes
        # Return None to indicate data is not available
        logger.debug(f"Real-time quotes not available for Stooq provider")
        return None
