"""API contract tests to lock in JSON structure (warnings, staleness_seconds)."""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.data.fetcher import DataFetcher
from app.main import app
from tests.conftest import fake_provider


def test_health_warnings_and_staleness():
    """Test /health endpoint returns warnings as list and staleness_seconds is present."""
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Verify warnings is a list
    assert isinstance(data["warnings"], list), f"warnings should be list, got {type(data['warnings'])}"
    assert all(isinstance(w, str) for w in data["warnings"]), "All warning items should be strings"

    # Verify staleness_seconds exists and is None or number
    assert "staleness_seconds" in data, "staleness_seconds key must be present"
    assert data["staleness_seconds"] is None or isinstance(
        data["staleness_seconds"], (int, float)
    ), f"staleness_seconds should be None or number, got {type(data['staleness_seconds'])}"

    # Verify raw JSON structure (warnings is array, not dict)
    raw_json = json.loads(response.text)
    assert raw_json["warnings"] == [], "warnings should be empty array [] in raw JSON, not {}"
    assert isinstance(raw_json["warnings"], list), "warnings must be list type in raw JSON"


def test_forecast_warnings_and_staleness(fake_provider):
    """Test /forecast endpoint returns warnings as list and staleness_seconds is present."""
    from app.api.routes import get_data_fetcher

    # Inject fake provider
    fetcher = DataFetcher(provider=fake_provider)

    with patch("app.api.routes.get_data_fetcher", return_value=fetcher):
        client = TestClient(app)
        response = client.get("/forecast?ticker=TEST")

        assert response.status_code == 200
        data = response.json()

        # Verify warnings is a list
        assert isinstance(data["warnings"], list), f"warnings should be list, got {type(data['warnings'])}"
        assert all(isinstance(w, str) for w in data["warnings"]), "All warning items should be strings"

        # Verify staleness_seconds exists and is None or number
        assert "staleness_seconds" in data, "staleness_seconds key must be present"
        assert data["staleness_seconds"] is None or isinstance(
            data["staleness_seconds"], (int, float)
        ), f"staleness_seconds should be None or number, got {type(data['staleness_seconds'])}"

        # Verify raw JSON structure (warnings is array, not dict)
        raw_json = json.loads(response.text)
        assert isinstance(raw_json["warnings"], list), "warnings must be list type in raw JSON"
        # Warnings may not be empty for forecast (could have stale data warnings), but must be list
