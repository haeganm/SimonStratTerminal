"""Portfolio risk constraints."""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class RiskConstraints:
    """Risk constraints for portfolio management."""

    def __init__(
        self,
        max_leverage: float = None,
        max_drawdown: Optional[float] = None,
        max_daily_loss: Optional[float] = None,
        turnover_threshold: float = 0.1,
    ):
        """
        Initialize risk constraints.

        Args:
            max_leverage: Maximum leverage (default 1.0 = no leverage)
            max_drawdown: Maximum drawdown stop (e.g., -0.2 for 20%)
            max_daily_loss: Maximum daily loss stop (e.g., -0.05 for 5%)
            turnover_threshold: Minimum forecast change to trigger trade (0.0 to 1.0)
        """
        self.max_leverage = max_leverage or settings.max_leverage
        self.max_drawdown = max_drawdown
        self.max_daily_loss = max_daily_loss
        self.turnover_threshold = turnover_threshold

    def apply_leverage_constraint(
        self, position_size: float, current_position: float = 0.0
    ) -> float:
        """
        Apply leverage constraint.

        Args:
            position_size: Desired position size
            current_position: Current position size

        Returns:
            Constrained position size
        """
        # Simple leverage constraint: ensure |position| <= max_leverage
        max_allowed = self.max_leverage

        if abs(position_size) > max_allowed:
            logger.debug(
                f"Position size {position_size:.2f} exceeds max leverage {max_allowed:.2f}"
            )
            return max_allowed if position_size > 0 else -max_allowed

        return position_size

    def check_drawdown_stop(self, current_equity: float, peak_equity: float) -> bool:
        """
        Check if drawdown stop has been triggered.

        Args:
            current_equity: Current portfolio equity
            peak_equity: Peak portfolio equity

        Returns:
            True if drawdown stop triggered, False otherwise
        """
        if self.max_drawdown is None or peak_equity <= 0:
            return False

        drawdown = (current_equity - peak_equity) / peak_equity

        if drawdown <= self.max_drawdown:
            logger.warning(
                f"Drawdown stop triggered: {drawdown:.2%} <= {self.max_drawdown:.2%}"
            )
            return True

        return False

    def check_daily_loss_stop(
        self, daily_return: float, initial_equity: float
    ) -> bool:
        """
        Check if daily loss stop has been triggered.

        Args:
            daily_return: Daily return (e.g., -0.05 for -5%)
            initial_equity: Equity at start of day

        Returns:
            True if daily loss stop triggered, False otherwise
        """
        if self.max_daily_loss is None:
            return False

        if daily_return <= self.max_daily_loss:
            logger.warning(
                f"Daily loss stop triggered: {daily_return:.2%} <= {self.max_daily_loss:.2%}"
            )
            return True

        return False

    def should_trade(
        self, new_forecast: str, old_forecast: str, new_confidence: float, old_confidence: float
    ) -> bool:
        """
        Check if forecast change warrants a trade (turnover constraint).

        Args:
            new_forecast: New forecast direction
            old_forecast: Previous forecast direction
            new_confidence: New forecast confidence
            old_confidence: Previous forecast confidence

        Returns:
            True if should trade, False otherwise
        """
        # Always trade if direction changes
        if new_forecast != old_forecast:
            return True

        # Trade if confidence change exceeds threshold
        confidence_change = abs(new_confidence - old_confidence)
        if confidence_change >= self.turnover_threshold:
            return True

        # No trade needed
        return False
