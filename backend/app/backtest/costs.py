"""Transaction cost model."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)


class TransactionCostModel:
    """Model for transaction costs including fees and slippage."""

    def __init__(
        self,
        fixed_bps: Optional[float] = None,
        slippage_factor: Optional[float] = None,
    ):
        """
        Initialize transaction cost model.

        Args:
            fixed_bps: Fixed cost in basis points (e.g., 5.0 for 5 bps)
            slippage_factor: Slippage multiplier (e.g., 0.001)
        """
        self.fixed_bps = fixed_bps or settings.transaction_cost_bps
        self.slippage_factor = slippage_factor or settings.slippage_factor

    def compute_cost(
        self,
        trade_size: float,  # Dollar value of trade
        price: float,
        volume: float,  # Trading volume on this day
        volatility: Optional[float] = None,
    ) -> float:
        """
        Compute total transaction cost (fees + slippage).

        Args:
            trade_size: Dollar value of trade (absolute value)
            price: Execution price
            volume: Trading volume for the day
            volatility: Annualized volatility (optional, for slippage)

        Returns:
            Total cost in dollars
        """
        if trade_size <= 0 or price <= 0:
            return 0.0

        # Fixed cost (basis points)
        fixed_cost = trade_size * (self.fixed_bps / 10000.0)

        # Slippage model: k * vol * sqrt(trade_size / volume)
        slippage_cost = 0.0
        if volatility is not None and volume > 0:
            # Volatility in price terms (not annualized)
            vol_price = volatility * price
            # Slippage proportional to volatility and trade size relative to volume
            trade_ratio = trade_size / (volume * price)
            slippage_cost = self.slippage_factor * vol_price * np.sqrt(trade_ratio) * trade_size

        total_cost = fixed_cost + slippage_cost

        return float(total_cost)

    def compute_cost_bps(
        self,
        trade_size: float,
        price: float,
        volume: float,
        volatility: Optional[float] = None,
    ) -> float:
        """
        Compute transaction cost as basis points.

        Args:
            trade_size: Dollar value of trade
            price: Execution price
            volume: Trading volume
            volatility: Annualized volatility

        Returns:
            Cost in basis points
        """
        cost_dollars = self.compute_cost(trade_size, price, volume, volatility)
        cost_bps = (cost_dollars / trade_size) * 10000.0 if trade_size > 0 else 0.0
        return float(cost_bps)
