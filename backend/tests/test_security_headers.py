"""Tests for security headers middleware."""
import pytest
from fastapi.testclient import TestClient

from main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_security_headers_present_on_health_check(client):
    """Security headers present on health check response."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "strict-transport-security" in response.headers
    assert "x-content-type-options" in response.headers
    assert "x-frame-options" in response.headers
    assert "content-security-policy" in response.headers


def test_hsts_header_value(client):
    """HSTS header has correct max-age."""
    response = client.get("/health")
    hsts = response.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts


def test_x_content_type_options_header(client):
    """X-Content-Type-Options set to nosniff."""
    response = client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_x_frame_options_header(client):
    """X-Frame-Options set to DENY."""
    response = client.get("/health")
    assert response.headers.get("x-frame-options") == "DENY"


def test_x_xss_protection_header(client):
    """X-XSS-Protection set correctly."""
    response = client.get("/health")
    assert response.headers.get("x-xss-protection") == "1; mode=block"


def test_referrer_policy_header(client):
    """Referrer-Policy set to strict-origin-when-cross-origin."""
    response = client.get("/health")
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_csp_header_present(client):
    """Content-Security-Policy header present."""
    response = client.get("/health")
    csp = response.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: https:" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp


def test_security_headers_on_api_endpoint(client):
    """Security headers present on API endpoints."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "strict-transport-security" in response.headers
    assert "x-content-type-options" in response.headers


def test_security_headers_on_error_response(client):
    """Security headers present even on 404 responses."""
    response = client.get("/api/nonexistent")
    assert response.status_code == 404
    assert "strict-transport-security" in response.headers
    assert "x-content-type-options" in response.headers
