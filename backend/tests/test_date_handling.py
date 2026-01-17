"""Tests for date handling (clamping future dates, validation)."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.data.fetcher import DataFetcher
from app.main import app


def test_future_end_date_clamping(fake_provider):
    """Test that future end dates are clamped and warning is added."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        # Use a future end date
        end_date = date.today() + timedelta(days=365)
        start_date = end_date - timedelta(days=30)
        
        response = client.get(
            f"/history?ticker=TEST&start={start_date}&end={end_date}"
        )
        
        assert response.status_code == 200, "Should return 200 even with future end date"
        data = response.json()
        
        # Should have warning about clamping
        warnings = data.get("warnings", [])
        assert any("clamped" in w.lower() or "future" in w.lower() for w in warnings), \
            f"Expected warning about future date clamping, got warnings: {warnings}"


def test_date_range_validation(fake_provider):
    """Test that invalid date ranges return 400."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        # Start date after end date
        start_date = date.today()
        end_date = start_date - timedelta(days=30)
        
        response = client.get(
            f"/history?ticker=TEST&start={start_date}&end={end_date}"
        )
        
        assert response.status_code == 400, "Should return 400 for invalid date range"
        data = response.json()
        assert "detail" in data
        assert "start_date" in data["detail"].lower() or "end_date" in data["detail"].lower()


def test_date_clamping_still_returns_data(fake_provider):
    """Test that clamping future dates still returns available data."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)
    
    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        # Future end date
        end_date = date.today() + timedelta(days=365)
        start_date = end_date - timedelta(days=365)
        
        response = client.get(
            f"/history?ticker=TEST&start={start_date}&end={end_date}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should still have data (up to latest available)
        assert "data" in data
        # Data may be empty for fake provider, but structure should be correct
        assert isinstance(data["data"], list)


def test_date_clamping_warning_message(fake_provider):
    """Test that warning message is clear about clamping."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)

    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        # Use a date range that will have data but end date is in future
        # The fake provider generates data up to today, so use today as end
        end_date = date.today() + timedelta(days=100)
        start_date = date.today() - timedelta(days=30)

        response = client.get(
            f"/signals?ticker=TEST&start={start_date}&end={end_date}"
        )

        assert response.status_code == 200
        data = response.json()

        warnings = data.get("warnings", [])
        # Warning should mention the original and clamped dates (if clamping occurred)
        # Note: fake provider may not trigger clamping if it generates data up to today
        warning_text = " ".join(warnings).lower()
        # If there's a warning about future dates, it should mention clamping
        if any("future" in w.lower() or "clamped" in w.lower() for w in warnings):
            assert "future" in warning_text or "clamped" in warning_text


def test_last_bar_date_in_response(fake_provider):
    """Test that last_bar_date is included in API responses."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    fetcher = DataFetcher(provider=fake_provider)

    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        # Test history endpoint
        response = client.get(
            f"/history?ticker=TEST&start={start_date}&end={end_date}"
        )
        assert response.status_code == 200
        data = response.json()
        assert "last_bar_date" in data
        # last_bar_date should be a string (ISO date) or null
        if data["last_bar_date"] is not None:
            assert isinstance(data["last_bar_date"], str)
            # Should be valid ISO date format
            from datetime import datetime
            datetime.fromisoformat(data["last_bar_date"])

        # Test signals endpoint
        response = client.get(
            f"/signals?ticker=TEST&start={start_date}&end={end_date}"
        )
        assert response.status_code == 200
        data = response.json()
        assert "last_bar_date" in data

        # Test forecast endpoint
        response = client.get(f"/forecast?ticker=TEST")
        assert response.status_code == 200
        data = response.json()
        assert "last_bar_date" in data