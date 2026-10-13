import ipaddress
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.utils.ssrf import SSRFBlockedError, is_ip_allowed, validate_safe_url


def test_root_endpoint():
    """Verify root / returns service status and banner."""
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "document-extractor"
        assert data["status"] == "running"


def test_security_headers_present():
    """Verify defensive security headers are injected on responses."""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_docs_enabled_in_development():
    """Verify docs are available in development by default."""
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200


def test_docs_disabled_in_production():
    """Verify that in production (or when ENABLE_DOCS=False), docs return 404."""
    # Test setting docs_enabled property
    s = Settings(ENVIRONMENT="production")
    assert s.is_production is True
    assert s.docs_enabled is False

    s_explicit = Settings(ENVIRONMENT="production", ENABLE_DOCS=True)
    assert s_explicit.docs_enabled is True

    s_dev_disabled = Settings(ENVIRONMENT="development", ENABLE_DOCS=False)
    assert s_dev_disabled.docs_enabled is False


def test_production_fails_without_api_key():
    """Verify lifespan raises RuntimeError if in production without API_KEY."""

    prod_settings = Settings(ENVIRONMENT="production", API_KEY=None, REQUIRE_API_KEY=True)
    with patch("app.main.settings", prod_settings):
        with pytest.raises(RuntimeError, match="API_KEY must be configured in production"):
            with TestClient(app):
                pass


def test_api_key_timing_safe_authentication():
    """Verify API key verification behavior with secrets.compare_digest."""
    auth_settings = Settings(ENVIRONMENT="development", API_KEY="super-secret-key-12345")
    with patch("app.dependencies.settings", auth_settings):
        with TestClient(app) as client:
            # Missing header
            resp = client.get("/cache")
            assert resp.status_code == 401
            assert "missing" in resp.json()["detail"].lower()

            # Invalid key
            resp = client.get("/cache", headers={"X-API-Key": "wrong-key"})
            assert resp.status_code == 401
            assert "invalid" in resp.json()["detail"].lower()

            # Valid key
            resp = client.get("/cache", headers={"X-API-Key": "super-secret-key-12345"})
            assert resp.status_code == 200


def test_ssrf_ip_filtering():
    """Verify is_ip_allowed blocks all dangerous and private IP ranges."""
    blocked_ips = [
        "127.0.0.1",
        "127.0.0.2",
        "10.0.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # Cloud metadata
        "100.64.0.1",  # Carrier grade NAT
        "::1",  # IPv6 loopback
        "fc00::1",  # IPv6 unique local
        "fe80::1",  # IPv6 link local
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 loopback
        "::ffff:169.254.169.254",  # IPv4-mapped cloud metadata
    ]
    for ip_str in blocked_ips:
        ip = ipaddress.ip_address(ip_str)
        assert is_ip_allowed(ip) is False, f"Expected {ip_str} to be blocked"

    allowed_ips = [
        "8.8.8.8",
        "1.1.1.1",
        "93.184.216.34",  # example.com
        "2606:4700:4700::1111",  # Cloudflare DNS
    ]
    for ip_str in allowed_ips:
        ip = ipaddress.ip_address(ip_str)
        assert is_ip_allowed(ip) is True, f"Expected {ip_str} to be allowed"


def test_ssrf_url_validation():
    """Verify validate_safe_url raises SSRFBlockedError on dangerous targets."""
    invalid_urls = [
        "http://127.0.0.1:8000/health",
        "http://localhost:8000/docs",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/secret",
        "http://example.com:22/file.pdf",
        "http://example.com:6379/eval",
        "ftp://example.com/file.pdf",
        "file:///etc/passwd",
    ]
    for url in invalid_urls:
        with pytest.raises(SSRFBlockedError):
            validate_safe_url(url)


def test_url_extract_endpoint_blocks_ssrf():
    """Verify /extract/urls returns SecurityError when SSRF is attempted."""
    with TestClient(app) as client:
        resp = client.post("/extract/urls", json={"urls": ["http://127.0.0.1:8000/health"]})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["content"] is None
        assert "SecurityError" in results[0]["error"]
