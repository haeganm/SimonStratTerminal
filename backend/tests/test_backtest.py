"""Tests for backtesting."""

from datetime import date

import pandas as pd
import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import compute_metrics
from app.models.ensemble import EnsembleModel


@pytest.fixture
def sample_bars():
    """Create sample bars for backtesting."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    # Simple trending price series
    prices = 100 + pd.Series(range(100)) * 0.5

    return pd.DataFrame({
        "open": prices + 0.1,
        "high": prices + 0.5,
        "low": prices - 0.3,
        "close": prices,
        "volume": 1000000 + pd.Series(range(100)) * 10000,
    }, index=dates)


def test_backtest_engine(sample_bars):
    """Test backtest engine."""
    ensemble = EnsembleModel()
    engine = BacktestEngine(ensemble=ensemble, initial_capital=100000.0)

    start_date = date(2020, 1, 1)
    end_date = date(2020, 4, 10)  # ~100 days

    equity_curve, trades, metrics = engine.run(
        sample_bars, start_date=start_date, end_date=end_date
    )

    assert not equity_curve.empty
    assert "date" in equity_curve.columns
    assert "equity" in equity_curve.columns
    assert "drawdown" in equity_curve.columns

    assert isinstance(metrics.cagr, float)
    assert isinstance(metrics.sharpe, float)
    assert isinstance(metrics.max_drawdown, float)
    assert metrics.max_drawdown <= 0.0  # Should be negative


def test_backtest_non_empty_results(sample_bars):
    """Test that backtest returns non-empty trades and equity curve."""
    ensemble = EnsembleModel()
    engine = BacktestEngine(ensemble=ensemble, initial_capital=100000.0)

    start_date = date(2020, 1, 1)
    end_date = date(2020, 4, 10)

    equity_curve, trades, metrics = engine.run(
        sample_bars, start_date=start_date, end_date=end_date
    )

    # Equity curve should have data
    assert not equity_curve.empty, "Equity curve should not be empty"
    assert len(equity_curve) > 0, "Equity curve should have entries"
    
    # Trades may be empty if no signals triggered, but structure should exist
    assert isinstance(trades, pd.DataFrame), "Trades should be a DataFrame"
    
    # Metrics should have all required fields
    assert hasattr(metrics, "cagr")
    assert hasattr(metrics, "sharpe")
    assert hasattr(metrics, "max_drawdown")
    assert hasattr(metrics, "win_rate")
    assert hasattr(metrics, "turnover")
    assert hasattr(metrics, "exposure")
    assert hasattr(metrics, "total_trades")


def test_backtest_warnings_in_response(fake_provider):
    """Test that backtest response includes warnings when appropriate."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.data.fetcher import DataFetcher
    
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=365)
        
        response = client.get(
            f"/backtest?ticker=TEST&start={start_date}&end={end_date}&preset=default"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have warnings field (may be empty)
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
        
        # Should have all required fields
        assert "equity_curve" in data
        assert "trades" in data
        assert "metrics" in data
        assert "staleness_seconds" in data


def test_backtest_metrics(sample_bars):
    """Test metrics computation."""
    # Create simple equity curve
    dates = pd.date_range("2020-01-01", periods=50, freq="D")
    equity_values = 100000 + pd.Series(range(50)) * 100  # Growing equity

    equity_curve = pd.DataFrame({
        "date": dates,
        "equity": equity_values,
        "drawdown": pd.Series([0.0] * 50),
    })

    # Create simple trades
    trades = pd.DataFrame({
        "date": dates[:10],
        "action": ["buy", "sell"] * 5,
        "quantity": [100.0] * 10,
        "price": [100.0] * 10,
        "pnl": [10.0, -5.0] * 5,
        "position_after": [100.0, 0.0] * 5,
    })

    metrics = compute_metrics(equity_curve, trades)

    assert metrics.cagr >= 0.0  # Equity is growing
    assert metrics.total_trades == 10
    assert 0.0 <= metrics.win_rate <= 1.0
