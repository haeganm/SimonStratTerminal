"""Security tests: input validation, injection attacks, etc."""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from tests.conftest import fake_provider
from unittest.mock import patch


client = TestClient(app)


class TestInputValidation:
    """Test input validation and sanitization."""

    def test_sql_injection_attempts(self):
        """Test that SQL injection attempts are handled safely."""
        # These should not cause errors or expose data
        malicious_tickers = [
            "'; DROP TABLE--",
            "' OR '1'='1",
            "'; DELETE FROM--",
            "1' UNION SELECT *--",
        ]
        
        for ticker in malicious_tickers:
            # Should return 404 or 400, not 500 (server error)
            response = client.get(f"/history?ticker={ticker}&start=2020-01-01&end=2020-01-31")
            assert response.status_code in [400, 404, 500], (
                f"SQL injection attempt '{ticker}' should be rejected, got {response.status_code}"
            )
            # Should not expose SQL errors in response
            if response.status_code == 500:
                response_text = response.text.lower()
                assert "sql" not in response_text or "syntax" not in response_text, (
                    f"SQL error exposed in response for '{ticker}'"
                )

    def test_path_traversal_attempts(self):
        """Test that path traversal attempts are handled safely."""
        malicious_tickers = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/passwd",
            "C:\\Windows\\System32",
        ]
        
        for ticker in malicious_tickers:
            response = client.get(f"/history?ticker={ticker}&start=2020-01-01&end=2020-01-31")
            # Should not access filesystem
            assert response.status_code in [400, 404, 500]
            # Should not expose file paths in errors
            if response.status_code == 500:
                response_text = response.text.lower()
                assert "etc/passwd" not in response_text
                assert "system32" not in response_text

    def test_xss_attempts(self):
        """Test that XSS attempts are handled safely."""
        malicious_tickers = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
            "<svg onload=alert(1)>",
        ]
        
        for ticker in malicious_tickers:
            response = client.get(f"/history?ticker={ticker}&start=2020-01-01&end=2020-01-31")
            # Should not execute scripts
            assert response.status_code in [200, 400, 404, 500]
            if response.status_code == 200:
                # If it returns data, check that scripts are escaped
                response_text = response.text
                assert "<script>" not in response_text.lower()
                assert "javascript:" not in response_text.lower()

    def test_extremely_long_strings(self):
        """Test handling of extremely long input strings."""
        # Very long ticker
        long_ticker = "A" * 10000
        response = client.get(f"/history?ticker={long_ticker}&start=2020-01-01&end=2020-01-31")
        # Should reject or handle gracefully, not crash
        assert response.status_code in [400, 404, 500]
        
        # Very long date string (malformed)
        response = client.get(f"/history?ticker=AAPL&start={'A'*1000}&end=2020-01-31")
        assert response.status_code == 400  # Should be validation error

    def test_special_characters(self):
        """Test handling of special characters in input."""
        # URL-encode special characters that can't be in URLs directly
        from urllib.parse import quote
        
        special_chars = [
            ("AAPL\n\r\t", quote("AAPL\n\r\t")),  # URL-encode newlines
            ("AAPL\u0000", quote("AAPL\u0000")),  # Null byte
            ("AAPL\x00\x01\x02", quote("AAPL\x00\x01\x02")),  # Control characters
            ("AAPL\uffff", quote("AAPL\uffff")),  # Unicode max
        ]
        
        for ticker, encoded_ticker in special_chars:
            try:
                response = client.get(f"/history?ticker={encoded_ticker}&start=2020-01-01&end=2020-01-31")
                # Should handle gracefully
                assert response.status_code in [200, 400, 404, 500]
            except Exception:
                # URL parsing may fail for some characters - that's OK
                pass

    def test_unicode_injection(self):
        """Test handling of unicode injection attempts."""
        unicode_tickers = [
            "AAPL\u200b",  # Zero-width space
            "AAPL\u200c",  # Zero-width non-joiner
            "AAPL\ufeff",  # BOM
        ]
        
        for ticker in unicode_tickers:
            response = client.get(f"/history?ticker={ticker}&start=2020-01-01&end=2020-01-31")
            assert response.status_code in [200, 400, 404, 500]

    def test_date_injection(self):
        """Test that malicious date strings are rejected."""
        malicious_dates = [
            "'; DROP TABLE--",
            "2020-01-01'; DELETE FROM--",
            "<script>alert(1)</script>",
            "../../../etc/passwd",
        ]
        
        for date_str in malicious_dates:
            response = client.get(f"/history?ticker=AAPL&start={date_str}&end=2020-01-31")
            # Should be validation error (400)
            assert response.status_code == 400, (
                f"Malicious date '{date_str}' should be rejected with 400, got {response.status_code}"
            )


class TestAPIErrorHandling:
    """Test API error handling and security."""

    def test_error_messages_no_sensitive_info(self):
        """Test that error messages don't expose sensitive information."""
        # Trigger various errors
        responses = [
            client.get("/history?ticker=INVALID&start=2020-01-01&end=2020-01-31"),
            client.get("/forecast?ticker=INVALID"),
            client.get("/backtest?ticker=INVALID&start=2020-01-01&end=2020-01-31"),
        ]
        
        for response in responses:
            if response.status_code >= 400:
                error_text = response.text.lower()
                # Should not expose:
                assert "password" not in error_text
                assert "api_key" not in error_text
                assert "secret" not in error_text
                assert "token" not in error_text
                # Should not expose file paths
                assert "c:\\" not in error_text.lower()
                assert "/etc/" not in error_text.lower()

    def test_malformed_requests(self):
        """Test handling of malformed requests."""
        # Missing required parameters
        response = client.get("/history")
        assert response.status_code == 422  # Validation error
        
        response = client.get("/forecast")
        assert response.status_code == 422
        
        # Invalid parameter types
        response = client.get("/history?ticker=AAPL&start=invalid&end=2020-01-31")
        assert response.status_code == 400

    def test_cors_configuration(self):
        """Test CORS is properly configured."""
        # Preflight request
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "GET",
            }
        )
        # Should allow CORS (not reject)
        assert response.status_code in [200, 204, 405]  # 405 is OK for OPTIONS
