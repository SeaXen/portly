import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from portly.backend.proxy_gen import generate_cloudflared_config, sanitize_domain
from portly.backend.app import app


def test_generate_cloudflared_config():
    cfg = generate_cloudflared_config("grafana.homelab.arpa", "127.0.0.1", 3000)
    assert "ingress:" in cfg
    assert "hostname: grafana.homelab.arpa" in cfg
    assert "service: http://127.0.0.1:3000" in cfg
    assert "service: http_status:404" in cfg


def test_api_cloudflared_proxy_config():
    client = TestClient(app)
    mock_apps = [{
        "id": "host:test_cf_app:8080",
        "name": "test_cf_app",
        "port": 8080,
        "host": "127.0.0.1",
        "bind": "127.0.0.1",
    }]
    with patch("portly.backend.app._cached_apps", mock_apps):
        res = client.get("/api/apps/host:test_cf_app:8080/proxy-config?format=cloudflared&domain=mytest.example.com")
        assert res.status_code == 200
        data = res.json()
        assert data["format"] == "cloudflared"
        assert "ingress:" in data["config"]
        assert "mytest.example.com" in data["config"]
