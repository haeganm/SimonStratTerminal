"""Backtest engine (leakage-safe)."""

import logging
from datetime import date
from typing import Optional

import pandas as pd

from app.backtest.costs import TransactionCostModel
from app.backtest.metrics import BacktestMetrics, compute_metrics
from app.core.config import settings
from app.core.exceptions import BacktestError
from app.features.volatility import compute_all_features
from app.models.ensemble import EnsembleModel, Forecast
from app.portfolio.constraints import RiskConstraints
from app.portfolio.sizing import compute_position_size
from app.signals.base import SignalResult
from app.signals.meanreversion_signal import MeanReversionSignal
from app.signals.momentum_signal import MomentumSignal
from app.signals.regime_signal import RegimeFilterSignal

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Leakage-safe backtest engine."""

    def __init__(
        self,
        ensemble: Optional[EnsembleModel] = None,
        constraints: Optional[RiskConstraints] = None,
        cost_model: Optional[TransactionCostModel] = None,
        initial_capital: float = 100000.0,
    ):
        """
        Initialize backtest engine.

        Args:
            ensemble: Ensemble model for forecasts
            constraints: Risk constraints
            cost_model: Transaction cost model
            initial_capital: Starting capital in dollars
        """
        self.ensemble = ensemble or EnsembleModel()
        self.constraints = constraints or RiskConstraints()
        self.cost_model = cost_model or TransactionCostModel()
        self.initial_capital = initial_capital

        # Initialize signals
        self.signals = [
            MomentumSignal(),
            MeanReversionSignal(),
            RegimeFilterSignal(),
        ]

    def run(
        self,
        bars: pd.DataFrame,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, BacktestMetrics]:
        """
        Run backtest (leakage-safe: only uses data up to current date).

        Args:
            bars: DataFrame with OHLCV data (date index)
            start_date: Start date (optional, defaults to first date in bars)
            end_date: End date (optional, defaults to last date in bars)

        Returns:
            Tuple of (equity_curve DataFrame, trades DataFrame, metrics)
        """
        if bars.empty:
            raise BacktestError("Empty bars data provided")

        # Filter date range
        if start_date:
            bars = bars[bars.index.date >= start_date]
        if end_date:
            bars = bars[bars.index.date <= end_date]

        if bars.empty:
            raise BacktestError("No data in specified date range")

        # Ensure date index
        if not isinstance(bars.index, pd.DatetimeIndex):
            bars.index = pd.to_datetime(bars.index)

        dates = sorted(bars.index)

        # Initialize state
        cash = self.initial_capital
        position = 0.0  # Number of shares (positive = long, negative = short)
        entry_value = 0.0  # Total cost basis for current position (absolute value)
        entry_price = 0.0  # Average entry price for current position (entry_value / abs(position))
        equity_history = []
        trades_history = []
        peak_equity = self.initial_capital

        # Track previous forecast for turnover constraint
        prev_forecast = "flat"
        prev_confidence = 0.0

        logger.info(f"Starting backtest from {dates[0].date()} to {dates[-1].date()}")

        for i, current_date in enumerate(dates):
            # CRITICAL: Only use data up to current date (leakage prevention)
            available_bars = bars.loc[bars.index <= current_date]

            if len(available_bars) < 60:  # Need minimum data for features
                # Skip early dates with insufficient data
                current_price = available_bars.iloc[-1]["close"]
                current_equity = cash + position * current_price
                equity_history.append(
                    {
                        "date": current_date.date(),
                        "equity": current_equity,
                        "drawdown": (current_equity - peak_equity) / peak_equity
                        if peak_equity > 0
                        else 0.0,
                    }
                )
                continue

            # Get current bar data
            current_bar = available_bars.loc[current_date]
            current_price = current_bar["close"]
            current_volume = current_bar["volume"]

            # Compute features (using only past data)
            features = compute_all_features(available_bars)

            if features.empty or current_date not in features.index:
                # Use most recent available features
                available_features = features[features.index <= current_date]
                if available_features.empty:
                    current_features = pd.DataFrame()
                else:
                    current_features = available_features.iloc[-1:].to_frame().T
                    current_features.index = [current_date]
            else:
                current_features = features.loc[[current_date]]

            if current_features.empty:
                # No features available - skip
                current_equity = cash + position * current_price
                equity_history.append(
                    {
                        "date": current_date.date(),
                        "equity": current_equity,
                        "drawdown": (current_equity - peak_equity) / peak_equity
                        if peak_equity > 0
                        else 0.0,
                    }
                )
                continue

            # Generate signals (only using current date features)
            signal_results = []
            for signal in self.signals:
                try:
                    result = signal.compute(available_bars, features, current_date)
                    signal_results.append(result)
                except Exception as e:
                    logger.warning(f"Error computing signal {signal.name} on {current_date}: {e}")

            if not signal_results:
                # No signals - skip
                current_equity = cash + position * current_price
                equity_history.append(
                    {
                        "date": current_date.date(),
                        "equity": current_equity,
                        "drawdown": (current_equity - peak_equity) / peak_equity
                        if peak_equity > 0
                        else 0.0,
                    }
                )
                continue

            # Get forecast from ensemble
            forecast = self.ensemble.combine(signal_results)

            # Check risk constraints
            if self.constraints.check_drawdown_stop(
                cash + position * current_price, peak_equity
            ):
                # Stop trading due to drawdown
                break

            # Compute position size
            realized_vol = available_bars["close"].pct_change(fill_method=None).rolling(20).std().iloc[-1] * (252 ** 0.5)
            if pd.isna(realized_vol) or realized_vol <= 0:
                realized_vol = 0.2  # Default volatility

            position_size_pct = compute_position_size(
                forecast.direction,
                forecast.confidence,
                realized_vol,
            )

            # Apply leverage constraint
            position_size_pct = self.constraints.apply_leverage_constraint(
                position_size_pct, position / (cash + position * current_price) if (cash + position * current_price) > 0 else 0.0
            )

            # Determine desired position
            current_equity = cash + position * current_price
            if current_equity <= 0:
                # Out of money
                break

            desired_position_value = current_equity * position_size_pct
            desired_shares = desired_position_value / current_price if current_price > 0 else 0.0

            # Apply direction
            if forecast.direction == "short":
                desired_shares = -abs(desired_shares)
            elif forecast.direction == "long":
                desired_shares = abs(desired_shares)
            else:  # flat
                desired_shares = 0.0

            # Check turnover constraint
            should_trade = self.constraints.should_trade(
                forecast.direction,
                prev_forecast,
                forecast.confidence,
                prev_confidence,
            )

            # Execute trade if needed
            trade_shares = desired_shares - position
            trade_value = abs(trade_shares * current_price)

            # Calculate P&L if position is changing
            trade_pnl = 0.0
            
            if abs(trade_shares) > 1e-6 and should_trade:
                # Compute realized P&L based on position change
                # Track old position for P&L calculation
                old_position = position
                old_entry_price = entry_price if abs(position) > 1e-6 else 0.0
                
                # Case 1: Opening new position (position == 0)
                if abs(position) < 1e-6:
                    # No existing position - opening new position
                    trade_pnl = 0.0  # No P&L on entry
                    if trade_shares > 0:  # Opening long
                        entry_value = trade_shares * current_price
                        entry_price = current_price
                    else:  # Opening short
                        entry_value = abs(trade_shares) * current_price
                        entry_price = current_price
                # Case 2: Adding to existing position (same direction)
                elif (position > 0 and trade_shares > 0) or (position < 0 and trade_shares < 0):
                    # Adding to position - no realized P&L, but update entry price (weighted average)
                    additional_cost = abs(trade_shares) * current_price
                    entry_value += additional_cost
                    # Recalculate average entry price
                    new_position_size = abs(position) + abs(trade_shares)
                    entry_price = entry_value / new_position_size if new_position_size > 0 else current_price
                    trade_pnl = 0.0  # No realized P&L when adding
                # Case 3: Closing or reducing position (opposite direction or reducing)
                elif (position > 0 and trade_shares < 0) or (position < 0 and trade_shares > 0):
                    # Closing or reducing position - compute realized P&L
                    shares_closed = min(abs(position), abs(trade_shares))
                    
                    if position > 0:  # Closing long position
                        # Selling shares at current_price, entered at entry_price
                        trade_pnl = (current_price - entry_price) * shares_closed
                    else:  # Closing short position
                        # Buying back shares at current_price, sold at entry_price
                        trade_pnl = (entry_price - current_price) * shares_closed
                    
                    # Update entry_value and entry_price if partial close
                    if abs(trade_shares) < abs(position):
                        # Partial close - reduce entry_value proportionally
                        remaining_ratio = (abs(position) - shares_closed) / abs(position)
                        entry_value = entry_value * remaining_ratio
                        # entry_price stays the same (it's the average for remaining shares)
                        # But we need to recalc it for the remaining position size
                        remaining_shares = abs(position) - shares_closed
                        entry_price = entry_value / remaining_shares if remaining_shares > 0 else 0.0
                    else:
                        # Full close - reset entry values
                        entry_value = 0.0
                        entry_price = 0.0
                # Case 4: Reversing position (going from long to short or vice versa)
                elif (position > 0 and desired_shares < 0) or (position < 0 and desired_shares > 0):
                    # First close existing position, then open new in opposite direction
                    # Close existing position
                    if position > 0:  # Closing long, opening short
                        trade_pnl = (current_price - entry_price) * abs(position)
                    else:  # Closing short, opening long
                        trade_pnl = (entry_price - current_price) * abs(position)
                    
                    # New position uses current price as entry
                    entry_value = abs(desired_shares) * current_price
                    entry_price = current_price
                
                # Apply transaction costs
                cost = self.cost_model.compute_cost(
                    trade_value, current_price, current_volume, realized_vol
                )

                # Update position and cash
                if trade_shares > 0:  # Buy
                    cash -= (trade_shares * current_price + cost)
                    action = "buy"
                    # Update entry price for new longs (if opening new or reversing)
                    if abs(position) < 1e-6 or (position < 0 and desired_shares > 0):
                        entry_price = current_price
                else:  # Sell
                    cash -= (trade_shares * current_price - cost)  # Negative trade_shares, so this adds cash
                    action = "sell"
                    # Update entry price for new shorts (if opening new or reversing)
                    if abs(position) < 1e-6 or (position > 0 and desired_shares < 0):
                        entry_price = current_price

                # Update position
                position = desired_shares
                
                # Ensure entry_price and entry_value are consistent
                if abs(position) > 1e-6:
                    if abs(entry_price) < 1e-6:
                        entry_price = current_price
                    if abs(entry_value) < 1e-6:
                        entry_value = abs(position) * entry_price
                    # Recalculate entry_price from entry_value to ensure consistency
                    entry_price = entry_value / abs(position) if abs(position) > 1e-6 else 0.0
                else:
                    # Position is zero - reset entry values
                    entry_value = 0.0
                    entry_price = 0.0

                # Record trade with computed P&L
                trades_history.append(
                    {
                        "date": current_date.date(),
                        "action": action,
                        "quantity": abs(trade_shares),
                        "price": current_price,
                        "pnl": trade_pnl,  # Realized P&L computed above
                        "position_after": position,
                    }
                )
                
                # Debug logging for P&L calculation
                if settings.debug_mode and abs(trade_pnl) > 1e-6:
                    logger.debug(
                        f"[DEBUG] BacktestEngine: P&L calculated: "
                        f"date={current_date.date()}, action={action}, "
                        f"old_position={old_position:.2f}, new_position={position:.2f}, "
                        f"entry_price={entry_price:.2f}, trade_price={current_price:.2f}, "
                        f"pnl={trade_pnl:.2f}"
                    )
            else:
                action = "hold"

            # Update previous forecast
            prev_forecast = forecast.direction
            prev_confidence = forecast.confidence

            # Compute current equity
            current_equity = cash + position * current_price
            if current_equity > peak_equity:
                peak_equity = current_equity

            # Record equity
            equity_history.append(
                {
                    "date": current_date.date(),
                    "equity": current_equity,
                    "drawdown": (current_equity - peak_equity) / peak_equity
                    if peak_equity > 0
                    else 0.0,
                }
            )

        # Final unrealized P&L for open position at end of backtest
        # Note: We don't add this as a trade record since P&L should only reflect realized gains/losses
        # Unrealized P&L is already reflected in the final equity value
        if abs(position) > 1e-6 and abs(entry_price) > 1e-6:
            final_price = bars.iloc[-1]["close"]
            if position > 0:  # Long position
                unrealized_pnl = (final_price - entry_price) * position
            else:  # Short position
                unrealized_pnl = (entry_price - final_price) * abs(position)
            
            if settings.debug_mode:
                logger.debug(
                    f"[DEBUG] BacktestEngine: Final unrealized P&L: "
                    f"position={position:.2f}, entry_price={entry_price:.2f}, "
                    f"final_price={final_price:.2f}, unrealized_pnl={unrealized_pnl:.2f}"
                )

        # Convert to DataFrames
        equity_curve = pd.DataFrame(equity_history)
        trades = pd.DataFrame(trades_history) if trades_history else pd.DataFrame(
            columns=["date", "action", "quantity", "price", "pnl", "position_after"]
        )

        # Compute metrics
        metrics = compute_metrics(equity_curve, trades)

        logger.info(
            f"Backtest complete: CAGR={metrics.cagr:.2%}, Sharpe={metrics.sharpe:.2f}, "
            f"Max DD={metrics.max_drawdown:.2%}, Trades={metrics.total_trades}"
        )

        return equity_curve, trades, metrics
