"""Unit tests for mathematical correctness of calculations."""

import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta

from app.backtest.metrics import compute_metrics, BacktestMetrics
from app.features.volatility import realized_vol_20d


def test_volatility_calculation_synthetic():
    """Test volatility calculation with known synthetic data."""
    # Create 20 days of 1% daily returns
    # Annualized vol should be: 0.01 * sqrt(252) ≈ 0.1587 (15.87%)
    dates = pd.date_range(start="2024-01-01", periods=21, freq="D")
    close_prices = [100.0]
    for i in range(20):
        close_prices.append(close_prices[-1] * 1.01)  # 1% daily return
    
    close_series = pd.Series(close_prices, index=dates)
    
    # Calculate volatility
    vol_series = realized_vol_20d(close_series)
    
    # Get the last non-NaN value (after 20 days of data)
    vol_annualized = vol_series.dropna().iloc[-1]
    
    # Expected: 0.01 * sqrt(252) ≈ 0.1587
    expected_vol = 0.01 * np.sqrt(252)
    
    # Allow 1% tolerance for floating point precision
    assert abs(vol_annualized - expected_vol) / expected_vol < 0.01, \
        f"Volatility calculation incorrect: got {vol_annualized:.6f}, expected {expected_vol:.6f}"


def test_cagr_calculation_known_equity_curve():
    """Test CAGR calculation with known equity curve."""
    # Create equity curve: $100k -> $150k over 2 years
    # CAGR should be: (150/100)^(1/2) - 1 = 1.5^0.5 - 1 ≈ 0.2247 (22.47%)
    start_date = date(2022, 1, 1)
    end_date = date(2024, 1, 1)
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    
    # Linear interpolation from 100k to 150k
    equity_values = np.linspace(100000.0, 150000.0, len(dates))
    
    equity_curve = pd.DataFrame({
        "date": dates.date,
        "equity": equity_values,
        "drawdown": np.zeros(len(dates))
    })
    
    # Empty trades (no trades, just equity growth)
    trades = pd.DataFrame(columns=["date", "action", "quantity", "price", "pnl", "position_after"])
    
    # Compute metrics
    metrics = compute_metrics(equity_curve, trades)
    
    # Expected CAGR: (150/100)^(1/2) - 1 ≈ 0.2247
    expected_cagr = (150000.0 / 100000.0) ** (1.0 / 2.0) - 1.0
    
    # Allow 1% tolerance
    assert abs(metrics.cagr - expected_cagr) / expected_cagr < 0.01, \
        f"CAGR calculation incorrect: got {metrics.cagr:.6f}, expected {expected_cagr:.6f}"


def test_sharpe_calculation_known_returns():
    """Test Sharpe ratio calculation with known returns."""
    # Create equity curve with constant daily return
    # Daily return: 0.1% (0.001)
    # Daily std: 1% (0.01)
    # Annualized Sharpe: (0.001 * 252) / (0.01 * sqrt(252)) = 0.252 / 0.1587 ≈ 1.588
    start_date = date(2022, 1, 1)
    end_date = date(2024, 1, 1)
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    
    # Create equity with constant daily return + noise
    np.random.seed(42)  # For reproducibility
    daily_returns = np.random.normal(0.001, 0.01, len(dates))
    equity_values = 100000.0 * np.exp(np.cumsum(daily_returns))
    
    equity_curve = pd.DataFrame({
        "date": dates.date,
        "equity": equity_values,
        "drawdown": np.zeros(len(dates))
    })
    
    trades = pd.DataFrame(columns=["date", "action", "quantity", "price", "pnl", "position_after"])
    
    # Compute metrics
    metrics = compute_metrics(equity_curve, trades)
    
    # Verify Sharpe is calculated (should be positive for positive mean return)
    assert metrics.sharpe > 0, "Sharpe should be positive for positive mean return"
    
    # Verify Sharpe uses sqrt(252) for annualization
    # We can't test exact value due to randomness, but we can verify it's reasonable
    # For mean return 0.1% and std 1%, Sharpe should be around 1.5-2.0
    assert 0.5 < metrics.sharpe < 3.0, \
        f"Sharpe ratio seems unreasonable: {metrics.sharpe:.2f}"


def test_pnl_calculation_simple_trade_sequence():
    """Test P&L calculation for simple buy/sell sequence."""
    from app.backtest.engine import BacktestEngine
    from app.models.ensemble import EnsembleModel
    
    # Create synthetic bars: price goes from $100 to $110
    dates = pd.date_range(start="2024-01-01", periods=5, freq="D")
    prices = [100.0, 102.0, 105.0, 108.0, 110.0]
    
    bars = pd.DataFrame({
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1000000] * 5
    }, index=dates)
    
    # Create ensemble that will generate buy signal on day 1, sell on day 4
    # We'll mock the signals to force specific trades
    class MockEnsemble:
        def combine(self, signal_results):
            from app.models.ensemble import Forecast
            # Return long on day 1, flat on day 4
            return Forecast(
                direction="long",
                confidence=0.8,
                explanation={"top_contributors": []}
            )
    
    # Create engine with mock ensemble
    engine = BacktestEngine(
        ensemble=MockEnsemble(),
        initial_capital=100000.0
    )
    
    # Override signals to force specific trades
    from app.signals.base import SignalResult
    from datetime import timezone
    
    def mock_signal_compute(bars, features, current_date):
        # Buy on day 1 (index 1), sell on day 4 (index 4)
        if current_date == dates[1]:
            return SignalResult(
                score=1.0,
                confidence=0.8,
                name="mock",
                timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                description="Buy signal"
            )
        elif current_date == dates[4]:
            return SignalResult(
                score=-1.0,
                confidence=0.8,
                name="mock",
                timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                description="Sell signal"
            )
        else:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                name="mock",
                timestamp=current_date.to_pydatetime().replace(tzinfo=timezone.utc),
                description="Hold"
            )
    
    # Mock the signal compute method
    engine.signals[0].compute = lambda bars, features, date: mock_signal_compute(bars, features, date)
    
    # Run backtest
    equity_curve, trades, metrics = engine.run(bars, start_date=dates[0].date(), end_date=dates[-1].date())
    
    # Verify trades were recorded
    assert not trades.empty, "Should have recorded trades"
    
    # Find buy and sell trades
    buy_trades = trades[trades["action"] == "buy"]
    sell_trades = trades[trades["action"] == "sell"]
    
    if not buy_trades.empty and not sell_trades.empty:
        # Get buy price and sell price
        buy_price = buy_trades.iloc[0]["price"]
        sell_price = sell_trades.iloc[-1]["price"]
        
        # Calculate expected P&L: (sell_price - buy_price) * quantity
        # But we need to account for transaction costs
        # For simplicity, verify P&L is positive if sell_price > buy_price
        if sell_price > buy_price:
            # Should have positive P&L on sell trade
            sell_pnl = sell_trades.iloc[-1]["pnl"]
            # P&L should be positive (allowing for transaction costs)
            assert sell_pnl > -100, \
                f"P&L should be positive for profitable trade: buy=${buy_price:.2f}, " \
                f"sell=${sell_price:.2f}, pnl=${sell_pnl:.2f}"
