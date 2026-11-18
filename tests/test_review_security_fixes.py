"""Regression tests for the round-2 review fixes (P0-1, P0-2, L-6, L-8, L-9, S-1, S-2, S-5, S-6, S-8)."""

import pytest
from fastapi.testclient import TestClient

from portly.backend import auth, notifications
from portly.backend.app import _is_ip_literal, _parse_host, app, store


@pytest.fixture
def client():
    return TestClient(app)


# --- S-1 / S-2: restrictive CSP ------------------------------------------------

def test_csp_has_no_inline_scripts_or_wildcard_connect(client):
    csp = client.get("/api/auth/me").headers.get("content-security-policy", "")
    assert "script-src 'self';" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "connect-src 'self';" in csp
    assert "ws:" not in csp and "wss:" not in csp


# --- P0-1 / L-6: host parsing and validation -----------------------------------

def test_parse_host_handles_ipv6_ports_and_bare_hosts():
    assert _parse_host("127.0.0.1:5533") == "127.0.0.1"
    assert _parse_host("[::1]:5533") == "::1"
    assert _parse_host("[2001:db8::1]") == "2001:db8::1"
    assert _parse_host("example.com") == "example.com"
    assert _parse_host("") == ""
    assert _is_ip_literal("192.168.1.1")
    assert _is_ip_literal("::1")
    assert not _is_ip_literal("example.com")


def _strict_host_env(monkeypatch):
    monkeypatch.delenv("PORTLY_TESTING", raising=False)
    monkeypatch.setenv("PORTLY_ALLOW_INSECURE_BIND", "false")
    monkeypatch.delenv("PORTLY_ALLOWED_HOSTS", raising=False)


def test_host_validation_accepts_ip_literals(client, monkeypatch):
    _strict_host_env(monkeypatch)
    assert client.get("/api/auth/me", headers={"host": "192.168.1.20:5533"}).status_code == 200
    assert client.get("/api/auth/me", headers={"host": "[::1]:5533"}).status_code == 200


def test_host_validation_rejects_unknown_host_with_helpful_message(client, monkeypatch):
    _strict_host_env(monkeypatch)
    res = client.get("/api/auth/me", headers={"host": "evil.example.com:5533"})
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_HOST"
    assert "PORTLY_ALLOWED_HOSTS=evil.example.com" in res.json()["message"]


def test_host_validation_honors_allowed_hosts_env(client, monkeypatch):
    _strict_host_env(monkeypatch)
    monkeypatch.setenv("PORTLY_ALLOWED_HOSTS", "nas.lan, [::1]:5533")
    assert client.get("/api/auth/me", headers={"host": "nas.lan:5533"}).status_code == 200


# --- P0-2 / S-5: route order and auth on favicon --------------------------------

def test_reveal_env_route_not_shadowed_and_admin_only(client, monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 2)
    monkeypatch.setattr(
        store, "get_custom_app",
        lambda cid: {"id": cid, "name": "Rev", "port": 1, "env": {"SECRET": "s3cr3t"}},
    )
    admin = auth.create_session("u_a", "admin_a", role="admin")
    viewer = auth.create_session("u_v", "viewer_v", role="viewer")

    url = "/api/apps/custom:revtest/inspect/reveal-env"
    assert client.get(url, cookies={"portly_session": viewer}).status_code == 403
    res = client.get(url, cookies={"portly_session": admin})
    assert res.status_code == 200
    assert res.json()["env"]["SECRET"] == "s3cr3t"


def test_favicon_requires_auth(client, monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    assert client.get("/api/apps/custom:none/favicon").status_code == 401


# --- L-9: export injection neutralization --------------------------------------

def test_export_csv_formula_injection_neutralized(client, monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    admin = auth.create_session("u_a", "admin_a", role="admin")
    monkeypatch.setattr(
        "portly.backend.app._cached_apps",
        [{"name": "=1+1", "port": 80, "source": "host", "bind": "127.0.0.1",
          "category_id": "web", "status": "up", "image": "@SUM(A1)"}],
    )
    body = client.get("/api/export?format=csv", cookies={"portly_session": admin}).text
    assert "'=1+1" in body
    assert "'@SUM(A1)" in body


def test_export_markdown_escapes_pipes(client, monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    admin = auth.create_session("u_a", "admin_a", role="admin")
    monkeypatch.setattr(
        "portly.backend.app._cached_apps",
        [{"name": "web|db", "port": 80, "source": "host", "bind": "127.0.0.1", "status": "up"}],
    )
    body = client.get("/api/export?format=markdown", cookies={"portly_session": admin}).text
    assert "web\\|db" in body


# --- L-8: self password change keeps caller signed in --------------------------

def test_self_password_change_keeps_session(client, monkeypatch):
    pw_hash = auth.hash_password("OldPass123!")
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    monkeypatch.setattr(
        store, "get_user_by_id",
        lambda uid: {"id": uid, "username": "admin", "password_hash": pw_hash, "role": "admin"},
    )
    monkeypatch.setattr(store, "update_user_password", lambda uid, h: None)

    old_token = auth.create_session("u1", "admin", role="admin")
    res = client.post(
        "/api/users/u1/password",
        json={"current_password": "OldPass123!", "new_password": "NewPass123!"},
        cookies={"portly_session": old_token},
    )
    assert res.status_code == 200
    new_token = res.cookies.get("portly_session")
    assert new_token and auth.validate_session(new_token)
    assert auth.validate_session(old_token) is None


# --- S-8: secure cookie flags ---------------------------------------------------

def test_login_cookie_flags_when_secure_enabled(client, monkeypatch):
    monkeypatch.setenv("PORTLY_COOKIE_SECURE", "1")
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    monkeypatch.setattr(
        store, "get_user",
        lambda u: {"id": "u1", "username": "admin", "password_hash": auth.hash_password("Pass123!")},
    )
    auth._failed_attempts.clear()
    res = client.post("/api/auth/login", json={"username": "admin", "password": "Pass123!"})
    assert res.status_code == 200
    cookie = res.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie
    monkeypatch.delenv("PORTLY_COOKIE_SECURE", raising=False)


# --- S-6: webhook SSRF guard + no redirects ------------------------------------

class _FakeResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeOpener:
    def open(self, req, timeout=None):
        return _FakeResp()


def test_webhook_blocks_metadata_and_internal_hosts(client, monkeypatch):
    monkeypatch.delenv("PORTLY_ALLOW_INTERNAL_WEBHOOKS", raising=False)
    ok, msg = notifications.send_webhook_sync(
        "http://169.254.169.254/latest/meta-data", "generic", "test", "x", max_retries=0
    )
    assert not ok and "blocked" in msg.lower()

    ok, msg = notifications.send_webhook_sync(
        "http://192.168.1.10:1234/hook", "generic", "test", "x", max_retries=0
    )
    assert not ok and "PORTLY_ALLOW_INTERNAL_WEBHOOKS" in msg


def test_webhook_opt_in_allows_internal_host_without_following_redirects(client, monkeypatch):
    captured = {}

    def fake_build_opener(handler):
        captured["handler"] = handler
        return _FakeOpener()

    monkeypatch.setenv("PORTLY_ALLOW_INTERNAL_WEBHOOKS", "1")
    monkeypatch.setattr(notifications.urllib.request, "build_opener", fake_build_opener)
    ok, _ = notifications.send_webhook_sync(
        "http://192.168.1.10:1234/hook", "generic", "test", "x", max_retries=0
    )
    assert ok
    assert captured.get("handler") is notifications._NoRedirectHandler
    monkeypatch.delenv("PORTLY_ALLOW_INTERNAL_WEBHOOKS", raising=False)


# --- S-4: setup token is hash-only and regenerable -------------------------------

def test_setup_token_never_stored_in_plaintext(monkeypatch):
    monkeypatch.delenv("PORTLY_SETUP_TOKEN", raising=False)
    token = auth.get_setup_token()
    record = store.get_setup_token_record()
    assert "token_plain" not in record
    assert token not in record.values()
    assert auth.verify_setup_token(token)
    auth.consume_setup_token()


def test_regenerating_setup_token_invalidates_previous(monkeypatch):
    monkeypatch.delenv("PORTLY_SETUP_TOKEN", raising=False)
    first = auth.get_setup_token()
    second = auth.get_setup_token()
    assert first != second
    assert not auth.verify_setup_token(first)
    assert auth.verify_setup_token(second)
    auth.consume_setup_token()
