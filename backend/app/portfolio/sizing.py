"""Position sizing using volatility targeting."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)


def compute_position_size(
    forecast_direction: str,
    forecast_confidence: float,
    realized_volatility: float,
    target_volatility: Optional[float] = None,
    max_position_size: Optional[float] = None,
) -> float:
    """
    Compute position size using volatility targeting.

    Args:
        forecast_direction: 'long', 'flat', or 'short'
        forecast_confidence: Confidence in forecast (0.0 to 1.0)
        realized_volatility: Realized volatility of the asset (annualized)
        target_volatility: Target portfolio volatility (default from settings)
        max_position_size: Maximum position size as fraction of portfolio (default from settings)

    Returns:
        Position size as fraction of portfolio (0.0 to 1.0)
    """
    if forecast_direction == "flat":
        return 0.0

    target_vol = target_volatility or settings.target_volatility
    max_size = max_position_size or settings.max_position_size

    if realized_volatility <= 0:
        logger.warning("Realized volatility is non-positive, using default position size")
        return forecast_confidence * 0.5  # Conservative default

    # Volatility targeting: position_size = target_vol / realized_vol
    vol_targeted_size = target_vol / realized_volatility

    # Scale by confidence
    confidence_scaled_size = vol_targeted_size * forecast_confidence

    # Cap at maximum position size
    position_size = min(confidence_scaled_size, max_size)

    # Ensure non-negative
    position_size = max(position_size, 0.0)

    return float(position_size)
