"""Integration checklist test - validates all endpoints work correctly."""

import logging
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.data.fetcher import DataFetcher
from app.main import app

logger = logging.getLogger(__name__)


@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


@pytest.fixture
def test_tickers():
    """Test tickers to use."""
    return ["NVDA", "AAPL"]


def test_health_endpoint(client):
    """Test /health endpoint."""
    logger.info("Testing /health endpoint")
    response = client.get("/health")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    
    assert "status" in data
    assert "data_source" in data
    assert "as_of" in data
    assert "is_delayed" in data
    assert "staleness_seconds" in data
    assert "warnings" in data
    assert isinstance(data["warnings"], list)
    
    logger.info(f"/health response: status={data['status']}, data_source={data['data_source']}")


def test_history_endpoint(client, fake_provider, test_tickers):
    """Test /history endpoint with NVDA and AAPL."""
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        for ticker in test_tickers:
            logger.info(f"Testing /history endpoint with ticker={ticker}")
            
            end_date = date.today()
            start_date = end_date - timedelta(days=365)
            
            response = client.get(
                f"/history?ticker={ticker}&start={start_date}&end={end_date}"
            )
            
            assert response.status_code == 200, f"Expected 200 for {ticker}, got {response.status_code}"
            data = response.json()
            
            # Log request params
            logger.info(f"[HISTORY] ticker={ticker} start={start_date} end={end_date} -> status={response.status_code}")
            
            assert "ticker" in data
            assert "data" in data
            assert isinstance(data["data"], list)
            assert "data_source" in data
            assert "as_of" in data
            assert "is_delayed" in data
            assert "staleness_seconds" in data
            assert "warnings" in data
            assert isinstance(data["warnings"], list)
            
            # Check for non-empty results
            if len(data["data"]) > 0:
                bar = data["data"][0]
                assert "date" in bar
                assert "open" in bar
                assert "high" in bar
                assert "low" in bar
                assert "close" in bar
                assert "volume" in bar
                logger.info(f"  -> {len(data['data'])} bars returned")


def test_signals_endpoint(client, fake_provider, test_tickers):
    """Test /signals endpoint with NVDA and AAPL."""
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        for ticker in test_tickers:
            logger.info(f"Testing /signals endpoint with ticker={ticker}")
            
            end_date = date.today()
            start_date = end_date - timedelta(days=90)
            
            response = client.get(
                f"/signals?ticker={ticker}&start={start_date}&end={end_date}"
            )
            
            assert response.status_code == 200, f"Expected 200 for {ticker}, got {response.status_code}"
            data = response.json()
            
            # Log request params
            logger.info(f"[SIGNALS] ticker={ticker} start={start_date} end={end_date} -> status={response.status_code}")
            
            assert "ticker" in data
            assert "signals" in data
            assert isinstance(data["signals"], list)
            assert "data_source" in data
            assert "as_of" in data
            assert "is_delayed" in data
            assert "staleness_seconds" in data
            assert "warnings" in data
            assert isinstance(data["warnings"], list)
            
            logger.info(f"  -> {len(data['signals'])} signals returned")


def test_forecast_endpoint(client, fake_provider, test_tickers):
    """Test /forecast endpoint with NVDA and AAPL."""
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        for ticker in test_tickers:
            logger.info(f"Testing /forecast endpoint with ticker={ticker}")
            
            response = client.get(f"/forecast?ticker={ticker}&preset=trend")
            
            assert response.status_code == 200, f"Expected 200 for {ticker}, got {response.status_code}"
            data = response.json()
            
            # Log request params
            logger.info(f"[FORECAST] ticker={ticker} preset=trend -> status={response.status_code}")
            
            assert "ticker" in data
            assert "direction" in data
            assert data["direction"] in ["long", "flat", "short"]
            assert "confidence" in data
            assert 0.0 <= data["confidence"] <= 1.0
            assert "suggested_position_size" in data
            assert "explanation" in data
            assert "data_source" in data
            assert "as_of" in data
            assert "is_delayed" in data
            assert "staleness_seconds" in data
            assert "warnings" in data
            assert isinstance(data["warnings"], list)
            
            logger.info(f"  -> direction={data['direction']}, confidence={data['confidence']:.2f}")


def test_backtest_endpoint(client, fake_provider, test_tickers):
    """Test /backtest endpoint with NVDA and AAPL."""
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        for ticker in test_tickers:
            logger.info(f"Testing /backtest endpoint with ticker={ticker}")
            
            end_date = date.today()
            start_date = end_date - timedelta(days=365)
            
            response = client.get(
                f"/backtest?ticker={ticker}&start={start_date}&end={end_date}&preset=default"
            )
            
            assert response.status_code == 200, f"Expected 200 for {ticker}, got {response.status_code}"
            data = response.json()
            
            # Log request params
            logger.info(f"[BACKTEST] ticker={ticker} start={start_date} end={end_date} preset=default -> status={response.status_code}")
            
            assert "ticker" in data
            assert "preset" in data
            assert "metrics" in data
            assert "equity_curve" in data
            assert isinstance(data["equity_curve"], list)
            assert "trades" in data
            assert isinstance(data["trades"], list)
            assert "data_source" in data
            assert "as_of" in data
            assert "is_delayed" in data
            assert "staleness_seconds" in data
            assert "warnings" in data
            assert isinstance(data["warnings"], list)
            
            # Check metrics structure
            metrics = data["metrics"]
            assert "cagr" in metrics
            assert "sharpe" in metrics
            assert "max_drawdown" in metrics
            assert "win_rate" in metrics
            assert "turnover" in metrics
            assert "exposure" in metrics
            assert "total_trades" in metrics
            
            logger.info(f"  -> {len(data['equity_curve'])} equity points, {len(data['trades'])} trades")


def test_all_endpoints_integration(client, fake_provider, test_tickers):
    """Run all endpoint tests in sequence for a comprehensive check."""
    logger.info("=" * 60)
    logger.info("Running comprehensive integration checklist")
    logger.info("=" * 60)
    
    # Run all tests
    test_health_endpoint(client)
    
    fetcher = DataFetcher(provider=fake_provider)
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        test_history_endpoint(client, fake_provider, test_tickers)
        test_signals_endpoint(client, fake_provider, test_tickers)
        test_forecast_endpoint(client, fake_provider, test_tickers)
        test_backtest_endpoint(client, fake_provider, test_tickers)
    
    logger.info("=" * 60)
    logger.info("Integration checklist complete - all endpoints validated")
    logger.info("=" * 60)
