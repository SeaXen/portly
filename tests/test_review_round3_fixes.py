"""Regression tests for the round-3 review fixes (N-1 ... N-12)."""

import asyncio
import json
import os
import threading
from pathlib import Path

import bcrypt
import pytest
from fastapi.testclient import TestClient

from portly import __version__
from portly.backend import app as appmod
from portly.backend import auth
from portly.backend.app import app, store

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    return TestClient(app)


def _strict_host_env(monkeypatch):
    """Turn off the testing exemption so Host validation actually runs."""
    monkeypatch.delenv("PORTLY_TESTING", raising=False)
    monkeypatch.delenv("PORTLY_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("PORTLY_ALLOW_INSECURE_BIND", raising=False)


# --- N-1: SSE subscriber queue must not leak ------------------------------------


def test_sse_registration_is_deferred_and_does_not_leak(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("stats unavailable")

    monkeypatch.setattr(appmod, "get_current_stats", boom)
    monkeypatch.setattr(appmod, "_sse_subscribers", [])

    for _ in range(70):
        with pytest.raises(RuntimeError):
            asyncio.run(appmod.sse_stream(request=None, user={"role": "admin"}))

    assert appmod._sse_subscribers == []


def test_sse_queue_registered_only_when_generator_starts(monkeypatch):
    monkeypatch.setattr(appmod, "_sse_subscribers", [])

    class _FakeRequest:
        async def is_disconnected(self):
            return True

    response = asyncio.run(appmod.sse_stream(request=_FakeRequest(), user={"role": "admin"}))
    # Registration happens inside the generator, not before it.
    assert appmod._sse_subscribers == []
    assert response is not None


# --- N-2: Host validation is not disabled by ALLOW_INSECURE_BIND ---------------


def test_insecure_bind_does_not_disable_host_validation(client, monkeypatch):
    _strict_host_env(monkeypatch)
    monkeypatch.setenv("PORTLY_ALLOW_INSECURE_BIND", "1")
    res = client.get("/api/auth/me", headers={"host": "evil.example.com"})
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID_HOST"


def test_subdomains_require_explicit_wildcard(client, monkeypatch):
    _strict_host_env(monkeypatch)
    monkeypatch.setenv("PORTLY_ALLOWED_HOSTS", "example.com")
    assert client.get("/api/auth/me", headers={"host": "a.example.com"}).status_code == 400

    monkeypatch.setenv("PORTLY_ALLOWED_HOSTS", "*.example.com")
    assert client.get("/api/auth/me", headers={"host": "a.example.com"}).status_code == 200


def test_ip_literal_hosts_still_allowed(client, monkeypatch):
    _strict_host_env(monkeypatch)
    assert client.get("/api/auth/me", headers={"host": "192.168.1.20:5533"}).status_code == 200
    assert client.get("/api/auth/me", headers={"host": "[::1]:5533"}).status_code == 200


# --- N-3: lockout is per username and per IP -----------------------------------


def _user(username, password="CorrectPass123"):
    return {"id": f"u_{username}", "username": username, "password_hash": auth.hash_password(password), "role": "admin"}


def test_lockout_does_not_block_a_different_user_from_same_ip(client, monkeypatch):
    auth._failed_attempts.clear()
    users = {"a": _user("a"), "b": _user("b")}
    monkeypatch.setattr(store, "get_user", lambda u: users.get(u))

    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "a", "password": "wrong"}).status_code == 401

    assert client.post("/api/auth/login", json={"username": "a", "password": "CorrectPass123"}).status_code == 429
    assert client.post("/api/auth/login", json={"username": "b", "password": "CorrectPass123"}).status_code == 200
    auth._failed_attempts.clear()


def test_lockout_accumulates_across_ips_for_same_user(monkeypatch):
    auth._failed_attempts.clear()
    users = {"a": _user("a")}
    monkeypatch.setattr(store, "get_user", lambda u: users.get(u))

    for i in range(5):
        c = TestClient(app, client=(f"10.9.0.{i + 1}", 1000))
        assert c.post("/api/auth/login", json={"username": "a", "password": "wrong"}).status_code == 401

    blocked = TestClient(app, client=("10.9.0.99", 1000))
    assert blocked.post("/api/auth/login", json={"username": "a", "password": "wrong"}).status_code == 429
    auth._failed_attempts.clear()


# --- N-4: concurrent first-run setup yields exactly one admin -------------------


def test_concurrent_setup_creates_one_admin(monkeypatch):
    for user in store.list_users():
        store.delete_user(user["id"])
    monkeypatch.setenv("PORTLY_MODE", "desktop")
    monkeypatch.setenv("PORTLY_HOST", "127.0.0.1")
    monkeypatch.delenv("PORTLY_ALLOW_INSECURE_BIND", raising=False)

    statuses = []
    barrier = threading.Barrier(2)

    def attempt(i):
        c = TestClient(app)
        barrier.wait(timeout=5)
        res = c.post("/api/auth/setup", json={"username": f"admin{i}", "password": "longpassword123"})
        statuses.append(res.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(statuses) == [200, 400]
    assert len(store.list_users()) == 1

    for user in store.list_users():
        store.delete_user(user["id"])


# --- N-5: dummy bcrypt hash is a real digest -----------------------------------


def test_dummy_bcrypt_hash_is_valid():
    assert bcrypt.checkpw(b"x", auth.DUMMY_BCRYPT_HASH.encode()) is False


def test_dummy_password_check_costs_like_a_real_check():
    import time

    start = time.perf_counter()
    auth.verify_dummy_password("wrong-password")
    dummy_sec = time.perf_counter() - start

    start = time.perf_counter()
    auth.verify_password("wrong-password", auth.hash_password("right-password"))
    real_sec = time.perf_counter() - start

    assert dummy_sec > 0.005 and real_sec > 0.005
    assert dummy_sec < real_sec * 5


# --- N-6: browser login response carries no session token -----------------------


def test_browser_login_has_no_token_in_body(client, monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    monkeypatch.setattr(store, "get_user", lambda u: _user("admin"))
    auth._failed_attempts.clear()

    res = client.post("/api/auth/login", json={"username": "admin", "password": "CorrectPass123"})
    assert res.status_code == 200
    assert "token" not in res.json()
    assert res.cookies.get("portly_session")

    cli = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "CorrectPass123"},
        headers={"x-portly-client": "cli"},
    )
    assert cli.json()["token"]
    auth._failed_attempts.clear()


# --- N-7: public_host is cached, not read from SQLite per request --------------


def test_public_host_is_read_once_for_many_requests(client, monkeypatch):
    calls = []
    original = store.get_setting

    def spy(key, default=""):
        if key == "public_host":
            calls.append(key)
        return original(key, default)

    monkeypatch.setattr(store, "get_setting", spy)
    appmod._invalidate_public_host_cache()

    for _ in range(100):
        client.get("/api/auth/me")

    assert len(calls) <= 1


def test_public_host_setting_takes_effect_on_next_request(client, monkeypatch):
    _strict_host_env(monkeypatch)
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    token = auth.create_session("u_admin", "admin", role="admin")

    res = client.patch("/api/settings", json={"public_host": "portly.lan"}, cookies={"portly_session": token})
    assert res.status_code == 200
    assert client.get("/api/auth/me", headers={"host": "portly.lan"}).status_code == 200

    store.set_setting("public_host", "")
    appmod._invalidate_public_host_cache()


# --- N-8: security headers on early rejections ---------------------------------


def test_rejected_host_carries_security_headers(client, monkeypatch):
    _strict_host_env(monkeypatch)
    res = client.get("/api/auth/me", headers={"host": "evil.example.com"})
    assert res.status_code == 400
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in res.headers["content-security-policy"]


def test_csrf_rejection_carries_security_headers(client):
    res = client.post("/api/auth/logout", headers={"origin": "null"})
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_DETECTED"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in res.headers


# --- N-9: cache headers --------------------------------------------------------


def test_spa_shell_and_sw_are_no_cache(client):
    if not (REPO_ROOT / "portly" / "frontend" / "dist" / "index.html").is_file():
        pytest.skip("frontend dist not built")
    assert client.get("/").headers.get("cache-control") == "no-cache"
    assert client.get("/sw.js").headers.get("cache-control") == "no-cache"
    assert client.get("/manifest.webmanifest").headers.get("cache-control") == "no-cache"


def test_hashed_assets_are_immutable(client):
    assets_dir = REPO_ROOT / "portly" / "frontend" / "dist" / "assets"
    if not assets_dir.is_dir():
        pytest.skip("frontend dist not built")
    files = sorted(p.name for p in assets_dir.iterdir() if p.is_file())
    if not files:
        pytest.skip("no built assets")
    res = client.get(f"/assets/{files[0]}")
    assert res.status_code == 200
    assert "immutable" in res.headers.get("cache-control", "")


# --- N-10: Secure cookie behind a trusted TLS-terminating proxy ----------------


def test_untrusted_proxy_headers_surface_in_system_stats(client, monkeypatch):
    monkeypatch.delenv("PORTLY_TRUSTED_PROXIES", raising=False)
    monkeypatch.setattr(appmod, "_untrusted_forwarded_for_seen", False)
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    token = auth.create_session("u_admin", "admin", role="admin")

    assert client.get("/api/system", cookies={"portly_session": token}).json()["untrusted_proxy_detected"] is False
    client.get("/api/auth/me", headers={"x-forwarded-for": "203.0.113.7"})
    assert client.get("/api/system", cookies={"portly_session": token}).json()["untrusted_proxy_detected"] is True


def test_forwarded_proto_from_trusted_proxy_sets_secure_cookie(monkeypatch):
    monkeypatch.delenv("PORTLY_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("PORTLY_TRUSTED_PROXIES", "10.1.1.1")
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    monkeypatch.setattr(store, "get_user", lambda u: _user("admin"))
    auth._failed_attempts.clear()

    trusted = TestClient(app, client=("10.1.1.1", 5000))
    res = trusted.post(
        "/api/auth/login",
        json={"username": "admin", "password": "CorrectPass123"},
        headers={"x-forwarded-proto": "https"},
    )
    assert res.status_code == 200
    assert "Secure" in res.headers["set-cookie"]

    untrusted = TestClient(app, client=("10.2.2.2", 5000))
    res2 = untrusted.post(
        "/api/auth/login",
        json={"username": "admin", "password": "CorrectPass123"},
        headers={"x-forwarded-proto": "https"},
    )
    assert res2.status_code == 200
    assert "Secure" not in res2.headers["set-cookie"]
    auth._failed_attempts.clear()


# --- N-11: default compose does not mount the host root ------------------------


def test_default_compose_does_not_mount_host_root():
    text = (REPO_ROOT / "docker-compose.yml").read_text()
    uncommented = [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not any("/:/hostfs" in line for line in uncommented)


# --- N-12: one version source of truth -----------------------------------------


def test_version_is_single_source():
    assert app.version == __version__
    pkg = json.loads((REPO_ROOT / "portly" / "frontend" / "package.json").read_text())
    assert pkg["version"] == __version__


# --- T-11: route order regression guard ----------------------------------------


def test_app_detail_route_declared_after_specific_app_routes():
    routes = [(r.path, getattr(r, "methods", set()) or set()) for r in app.routes]
    detail_idx = next(
        i for i, (path, methods) in enumerate(routes)
        if path == "/api/apps/{app_id:path}" and "GET" in methods
    )
    later_app_gets = [
        path for path, methods in routes[detail_idx + 1:]
        if path.startswith("/api/apps/") and "GET" in methods
    ]
    assert later_app_gets == []
