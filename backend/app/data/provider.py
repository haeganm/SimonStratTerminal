"""Market data provider interface."""

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

import pandas as pd


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> pd.DataFrame:
        """
        Retrieve daily OHLCV bars for a ticker.

        Args:
            ticker: Stock ticker symbol
            start: Start date (inclusive)
            end: End date (inclusive)

        Returns:
            DataFrame with columns: date, open, high, low, close, volume
            Date should be a column, not index

        Raises:
            DataProviderError: If data retrieval fails
        """
        pass

    @abstractmethod
    def get_latest_quote(self, ticker: str) -> Optional[dict]:
        """
        Get latest quote for a ticker (best-effort, may be delayed).

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with quote data or None if unavailable
            Should include: price, timestamp, is_delayed, staleness_seconds

        Raises:
            DataProviderError: If quote retrieval fails
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass
