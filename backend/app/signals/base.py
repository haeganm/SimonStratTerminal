"""Base signal class and result types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class SignalResult:
    """Result from a signal computation."""

    score: float  # -1 to 1 (signal strength/direction)
    confidence: float  # 0 to 1 (certainty/quality)
    name: str  # Signal name identifier
    timestamp: datetime  # Time of signal (timezone-aware UTC)
    description: Optional[str] = None  # Optional description
    reason: Optional[str] = None  # Specific reason with numeric values (e.g., "MA20 above MA50, slope=0.02")
    components: Optional[dict[str, float]] = None  # Numeric components used in calculation


class Signal:
    """Base class for trading signals."""

    def __init__(self, name: str):
        """Initialize signal with name."""
        self.name = name

    def compute(
        self, bars: pd.DataFrame, features: pd.DataFrame, current_date: pd.Timestamp
    ) -> SignalResult:
        """
        Compute signal for a given date.

        Args:
            bars: DataFrame with OHLCV data (date index)
            features: DataFrame with computed features (date index)
            current_date: Current date to compute signal for

        Returns:
            SignalResult with score, confidence, name, timestamp

        Raises:
            SignalError: If signal computation fails
        """
        raise NotImplementedError("Subclasses must implement compute()")

    def _ensure_utc_timestamp(self, dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware in UTC."""
        from datetime import timezone
        if dt.tzinfo is None:
            # Assume naive datetime is UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
