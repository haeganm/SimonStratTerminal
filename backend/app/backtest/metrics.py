"""Backtest performance metrics."""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestMetrics:
    """Backtest performance metrics."""

    cagr: float  # Annualized return
    sharpe: float  # Sharpe ratio (daily)
    max_drawdown: float  # Maximum drawdown (negative value, e.g., -0.15)
    win_rate: float  # Win rate (0.0 to 1.0)
    turnover: float  # Average turnover (0.0 to 1.0)
    exposure: float  # Average exposure (0.0 to 1.0)
    total_trades: int  # Total number of trades (buy/sell, excluding holds)
    profit_factor: Optional[float] = None  # Gross profit / gross loss


def compute_metrics(
    equity_curve: pd.DataFrame, trades: pd.DataFrame
) -> BacktestMetrics:
    """
    Compute backtest performance metrics.

    Args:
        equity_curve: DataFrame with columns: date, equity, drawdown
        trades: DataFrame with columns: date, action, quantity, price, pnl, position_after

    Returns:
        BacktestMetrics object
    """
    if equity_curve.empty:
        return BacktestMetrics(
            cagr=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            turnover=0.0,
            exposure=0.0,
            total_trades=0,
        )

    equity = equity_curve["equity"].values
    dates = pd.to_datetime(equity_curve["date"])

    # Compute returns
    returns = pd.Series(equity).pct_change(fill_method=None).dropna()

    if len(returns) == 0:
        return BacktestMetrics(
            cagr=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            turnover=0.0,
            exposure=0.0,
            total_trades=0,
        )

    # CAGR (Compound Annual Growth Rate)
    start_equity = equity[0]
    end_equity = equity[-1]
    num_years = (dates.iloc[-1] - dates.iloc[0]).days / 365.25

    if num_years > 0 and start_equity > 0:
        cagr = ((end_equity / start_equity) ** (1.0 / num_years)) - 1.0
    else:
        cagr = 0.0

    # Sharpe ratio (annualized)
    if returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252)  # Annualized
    else:
        sharpe = 0.0

    # Max drawdown (negative value)
    running_max = pd.Series(equity).cummax()
    drawdowns = (equity - running_max) / running_max
    max_drawdown = float(drawdowns.min())

    # Win rate (from trades)
    if not trades.empty and "pnl" in trades.columns:
        pnl_values = trades["pnl"].values
        profitable_trades = pnl_values[pnl_values > 0]
        total_trades = len(pnl_values[pnl_values != 0])
        win_rate = len(profitable_trades) / total_trades if total_trades > 0 else 0.0

        # Profit factor
        gross_profit = pnl_values[pnl_values > 0].sum()
        gross_loss = abs(pnl_values[pnl_values < 0].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    else:
        win_rate = 0.0
        profit_factor = None

    # Turnover (from trades)
    if not trades.empty:
        trade_actions = trades["action"].values
        total_trades_count = len(trade_actions[(trade_actions == "buy") | (trade_actions == "sell")])
        num_days = len(equity_curve)
        turnover = (total_trades_count / num_days) if num_days > 0 else 0.0
    else:
        total_trades_count = 0
        turnover = 0.0

    # Exposure (fraction of time with non-zero position)
    # NOTE: This calculation uses trades dataframe, which only records days when positions change.
    # This may understate exposure if positions are held for long periods without trading.
    # A more accurate calculation would track position for every day, but this requires
    # changes to the backtest engine to record position on every day, not just trade days.
    if not trades.empty and "position_after" in trades.columns:
        positions = trades["position_after"].values
        non_zero_days = np.sum(np.abs(positions) > 1e-6)
        exposure = non_zero_days / len(equity_curve) if len(equity_curve) > 0 else 0.0
        
        # Validation: exposure should be between 0.0 and 1.0
        if exposure > 1.0:
            logger.warning(f"Exposure {exposure:.4f} > 1.0 - this should not happen. Clamping to 1.0.")
            exposure = 1.0
        if exposure < 0.0:
            logger.warning(f"Exposure {exposure:.4f} < 0.0 - this should not happen. Clamping to 0.0.")
            exposure = 0.0
    else:
        exposure = 0.0

    return BacktestMetrics(
        cagr=float(cagr),
        sharpe=float(sharpe),
        max_drawdown=float(max_drawdown),
        win_rate=float(win_rate),
        turnover=float(turnover),
        exposure=float(exposure),
        total_trades=int(total_trades_count),
        profit_factor=float(profit_factor) if profit_factor is not None else None,
    )
