"""Tests for ticker normalization."""

import pytest
from app.core.exceptions import DataProviderError
from app.data.stooq_provider import StooqProvider


def test_ticker_normalization_candidates():
    """Test that ticker normalization generates correct candidates."""
    provider = StooqProvider()
    
    # Test without dot - should try both as-is and with .US
    candidates = provider._normalize_ticker("NVDA")
    assert "NVDA" in candidates
    assert "NVDA.US" in candidates
    assert len(candidates) == 2
    
    # Test with .us suffix
    candidates = provider._normalize_ticker("NVDA.us")
    assert "NVDA.US" in candidates
    assert len(candidates) >= 1
    
    # Test case variations
    candidates = provider._normalize_ticker("nvda")
    assert "NVDA" in candidates
    assert "NVDA.US" in candidates
    
    candidates = provider._normalize_ticker("NvDa")
    assert "NVDA" in candidates
    assert "NVDA.US" in candidates
    
    # Test with different suffix
    candidates = provider._normalize_ticker("AAPL.UK")
    assert "AAPL.UK" in candidates
    assert "AAPL.US" in candidates


def test_ticker_normalization_case_insensitive():
    """Test that ticker normalization is case-insensitive."""
    provider = StooqProvider()
    
    # All these should produce the same candidates
    variants = ["nvda", "NVDA", "NvDa", "nVdA"]
    for variant in variants:
        candidates = provider._normalize_ticker(variant)
        assert "NVDA" in candidates or "NVDA.US" in candidates


def test_ticker_search_endpoint():
    """Test /tickers/search endpoint."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    
    # Test search for NVDA
    response = client.get("/tickers/search?q=nv")
    assert response.status_code == 200
    data = response.json()
    
    assert "tickers" in data
    assert isinstance(data["tickers"], list)
    
    # Should find NVDA
    nvda_found = any(t["symbol"] == "NVDA" for t in data["tickers"])
    assert nvda_found, "NVDA should be found in search results"
    
    # Test case-insensitive search
    response = client.get("/tickers/search?q=NV")
    assert response.status_code == 200
    data = response.json()
    nvda_found = any(t["symbol"] == "NVDA" for t in data["tickers"])
    assert nvda_found
    
    # Test empty query
    response = client.get("/tickers/search?q=")
    assert response.status_code == 200
    data = response.json()
    assert data["tickers"] == []
    
    # Test no matches
    response = client.get("/tickers/search?q=ZZZZZZ")
    assert response.status_code == 200
    data = response.json()
    assert data["tickers"] == []


def test_ticker_search_prefix_matching():
    """Test that ticker search uses prefix matching."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    
    # Search for "AA" should find AAPL
    response = client.get("/tickers/search?q=AA")
    assert response.status_code == 200
    data = response.json()
    
    aapl_found = any(t["symbol"] == "AAPL" for t in data["tickers"])
    assert aapl_found, "AAPL should be found with prefix 'AA'"
    
    # Search for "AAP" should also find AAPL
    response = client.get("/tickers/search?q=AAP")
    assert response.status_code == 200
    data = response.json()
    
    aapl_found = any(t["symbol"] == "AAPL" for t in data["tickers"])
    assert aapl_found, "AAPL should be found with prefix 'AAP'"
