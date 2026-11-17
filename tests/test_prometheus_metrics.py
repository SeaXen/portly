"""Tests for Prometheus metrics exporter endpoint (/api/metrics)."""

import pytest
from fastapi.testclient import TestClient
from portly.backend.app import app, store
from portly.backend import auth


@pytest.fixture
def client():
    return TestClient(app)


def test_prometheus_metrics_unauthorized(client, monkeypatch):
    """When users exist, /api/metrics requires authentication or a valid metrics token."""
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    monkeypatch.setenv("PORTLY_METRICS_TOKEN", "secret-scrape-key-123")

    # No token or session -> 401
    res = client.get("/api/metrics")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "UNAUTHORIZED"

    # Bad token -> 401
    res_bad = client.get("/api/metrics?token=wrong-token")
    assert res_bad.status_code == 401


def test_prometheus_metrics_scrape_token(client, monkeypatch):
    """Prometheus scraper can query /api/metrics with ?token= or Authorization: Bearer."""
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    monkeypatch.setenv("PORTLY_METRICS_TOKEN", "secret-scrape-key-123")

    # Query param token
    res_query = client.get("/api/metrics?token=secret-scrape-key-123")
    assert res_query.status_code == 200
    assert "text/plain" in res_query.headers["content-type"]
    body = res_query.text
    assert "# TYPE portly_active_listeners_total gauge" in body
    assert "portly_up 1" in body
    assert "portly_host_cpu_percent" in body
    assert "portly_port_reservations_total" in body

    # Header bearer token
    res_header = client.get("/api/metrics", headers={"Authorization": "Bearer secret-scrape-key-123"})
    assert res_header.status_code == 200
    assert "portly_up 1" in res_header.text


def test_prometheus_metrics_session_auth(client, monkeypatch):
    """Logged in user can also query /api/metrics."""
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    admin_token = auth.create_session("u_adm", "admin_alice", role="admin")
    client.cookies.set("portly_session", admin_token)

    res = client.get("/api/metrics")
    assert res.status_code == 200
    assert "portly_up 1" in res.text
