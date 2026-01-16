"""Feature and signal caching for performance optimization."""

import hashlib
import logging
from datetime import timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class FeatureCache:
    """In-memory cache for computed features and signals."""

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize feature cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 1 hour)
        """
        self.cache: dict[str, tuple[pd.DataFrame, float]] = {}
        self.ttl_seconds = ttl_seconds

    def _make_key(self, ticker: str, start_date: str, end_date: str, preset: str = "default") -> str:
        """Generate cache key from parameters."""
        key_str = f"{ticker}:{start_date}:{end_date}:{preset}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get_features(self, ticker: str, start_date: str, end_date: str, preset: str = "default") -> Optional[pd.DataFrame]:
        """
        Get cached features if available and not expired.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)
            preset: Strategy preset name

        Returns:
            Cached features DataFrame or None if not found/expired
        """
        import time
        key = self._make_key(ticker, start_date, end_date, preset)
        
        if key in self.cache:
            features, timestamp = self.cache[key]
            age = time.time() - timestamp
            
            if age < self.ttl_seconds:
                logger.debug(f"Cache hit for features: {ticker} {start_date} to {end_date}")
                return features.copy()
            else:
                # Expired - remove from cache
                del self.cache[key]
                logger.debug(f"Cache expired for: {ticker} {start_date} to {end_date}")
        
        return None

    def set_features(self, ticker: str, start_date: str, end_date: str, features: pd.DataFrame, preset: str = "default") -> None:
        """
        Store features in cache.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)
            features: Features DataFrame to cache
            preset: Strategy preset name
        """
        import time
        key = self._make_key(ticker, start_date, end_date, preset)
        self.cache[key] = (features.copy(), time.time())
        logger.debug(f"Cached features: {ticker} {start_date} to {end_date}")

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        logger.debug("Feature cache cleared")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "ttl_seconds": self.ttl_seconds,
        }


# Global feature cache instance
_feature_cache: Optional[FeatureCache] = None


def get_feature_cache() -> FeatureCache:
    """Get global feature cache instance."""
    global _feature_cache
    if _feature_cache is None:
        _feature_cache = FeatureCache()
    return _feature_cache
