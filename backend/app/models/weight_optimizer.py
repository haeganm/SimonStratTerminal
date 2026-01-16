"""Walk-forward weight optimization for ensemble model."""

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from app.core.config import settings
from app.models.ensemble import EnsembleModel
from app.signals.base import SignalResult

logger = logging.getLogger(__name__)


class WeightOptimizer:
    """Optimizes ensemble weights using walk-forward regression."""

    def __init__(self, train_years: int = None, test_months: int = None):
        """
        Initialize weight optimizer.

        Args:
            train_years: Number of years for training window
            test_months: Number of months for test window
        """
        self.train_years = train_years or settings.walkforward_train_years
        self.test_months = test_months or settings.walkforward_test_months

    def optimize_weights(
        self,
        signal_history: dict[date, list[SignalResult]],
        returns: pd.Series,
        start_date: date,
        end_date: date,
    ) -> dict[str, float]:
        """
        Optimize weights using linear regression on training window.

        Args:
            signal_history: Dictionary mapping dates to lists of SignalResult
            returns: Series of future returns (indexed by date)
            start_date: Start of training window
            end_date: End of training window

        Returns:
            Dictionary mapping signal names to optimized weights
        """
        # Collect features (signal scores) and targets (future returns)
        features = []
        targets = []
        signal_names = set()

        # Get all unique signal names
        for date_key, signals in signal_history.items():
            if start_date <= date_key <= end_date:
                for signal in signals:
                    if signal.name != "Regime Filter":
                        signal_names.add(signal.name)

        signal_names = sorted(list(signal_names))

        if not signal_names:
            logger.warning("No signals found for weight optimization")
            return {}

        # Build feature matrix and target vector
        for date_key in sorted(signal_history.keys()):
            if start_date <= date_key <= end_date:
                # Get future return (e.g., 5-day forward return)
                future_date = date_key + timedelta(days=5)
                if future_date in returns.index:
                    future_return = returns.loc[future_date]

                    # Get signal scores for this date
                    signals = signal_history[date_key]
                    signal_scores = {s.name: s.score * s.confidence for s in signals}

                    # Build feature vector
                    feature_vec = [signal_scores.get(name, 0.0) for name in signal_names]
                    features.append(feature_vec)
                    targets.append(future_return)

        if len(features) < 20:  # Need minimum data points
            logger.warning(f"Insufficient data for weight optimization: {len(features)} samples")
            return {}

        # Convert to numpy arrays
        X = np.array(features)
        y = np.array(targets)

        # Remove NaN/inf
        valid_mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        X = X[valid_mask]
        y = y[valid_mask]

        if len(X) < 20:
            logger.warning(f"Insufficient valid data: {len(X)} samples")
            return {}

        # Fit linear regression
        try:
            model = LinearRegression(fit_intercept=False, positive=True)  # Positive weights
            model.fit(X, y)

            weights = {name: float(w) for name, w in zip(signal_names, model.coef_)}

            # Normalize weights to sum to 1.0
            total_weight = sum(abs(w) for w in weights.values())
            if total_weight > 0:
                weights = {k: abs(v) / total_weight for k, v in weights.items()}

            logger.info(f"Optimized weights: {weights}")

            return weights

        except Exception as e:
            logger.error(f"Error optimizing weights: {e}")
            return {}
