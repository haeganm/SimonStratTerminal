"""Walk-forward backtest evaluation."""

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import BacktestMetrics, compute_metrics
from app.core.config import settings
from app.models.ensemble import EnsembleModel
from app.models.weight_optimizer import WeightOptimizer
from app.signals.base import SignalResult

logger = logging.getLogger(__name__)


class WalkForwardEvaluator:
    """Walk-forward backtest evaluator."""

    def __init__(
        self,
        train_years: Optional[int] = None,
        test_months: Optional[int] = None,
        step_months: Optional[int] = None,
    ):
        """
        Initialize walk-forward evaluator.

        Args:
            train_years: Number of years for training window
            test_months: Number of months for test window
            step_months: Step size in months
        """
        self.train_years = train_years or settings.walkforward_train_years
        self.test_months = test_months or settings.walkforward_test_months
        self.step_months = step_months or settings.walkforward_step_months

    def evaluate(
        self, bars: pd.DataFrame, start_date: date, end_date: date
    ) -> tuple[list[BacktestMetrics], pd.DataFrame, pd.DataFrame]:
        """
        Run walk-forward evaluation.

        Args:
            bars: DataFrame with OHLCV data
            start_date: Start of evaluation period
            end_date: End of evaluation period

        Returns:
            Tuple of (list of metrics per test window, combined equity curve, combined trades)
        """
        all_equity_curves = []
        all_trades = []
        all_metrics = []

        # Generate windows
        windows = self._generate_windows(start_date, end_date)

        logger.info(f"Walk-forward evaluation: {len(windows)} windows")

        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            logger.info(
                f"Window {i+1}/{len(windows)}: Train {train_start} to {train_end}, "
                f"Test {test_start} to {test_end}"
            )

            # Get training and test data
            train_bars = bars[
                (bars.index.date >= train_start) & (bars.index.date <= train_end)
            ]
            test_bars = bars[
                (bars.index.date >= test_start) & (bars.index.date <= test_end)
            ]

            if train_bars.empty or test_bars.empty:
                logger.warning(f"Skipping window {i+1}: insufficient data")
                continue

            # Optimize weights on training data
            optimizer = WeightOptimizer()
            # For now, use default weights (full optimization requires signal history)
            # In full implementation, we'd collect signal history during training backtest
            ensemble = EnsembleModel()

            # Run backtest on test window
            engine = BacktestEngine(ensemble=ensemble)
            equity_curve, trades, metrics = engine.run(
                bars, start_date=test_start, end_date=test_end
            )

            all_equity_curves.append(equity_curve)
            all_trades.append(trades)
            all_metrics.append(metrics)

        # Combine results
        combined_equity = pd.concat(all_equity_curves, ignore_index=True).drop_duplicates(
            subset=["date"], keep="last"
        ).sort_values("date")
        combined_trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()

        return all_metrics, combined_equity, combined_trades

    def _generate_windows(
        self, start_date: date, end_date: date
    ) -> list[tuple[date, date, date, date]]:
        """Generate train/test windows."""
        windows = []

        current_date = start_date

        while current_date < end_date:
            # Training window: train_years before test
            train_start = current_date - timedelta(days=self.train_years * 365)
            train_end = current_date - timedelta(days=1)

            # Test window: test_months from current_date
            test_start = current_date
            test_end = min(
                current_date + timedelta(days=self.test_months * 30), end_date
            )

            if test_start < end_date:
                windows.append((train_start, train_end, test_start, test_end))

            # Step forward
            current_date += timedelta(days=self.step_months * 30)

        return windows
