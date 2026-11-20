"""Regression tests for review-round-2 security fixes: CSRF origin matching,
untrusted X-Forwarded-For, Safe Mode gates on create/delete, viewer redaction,
and the exec allowlist default."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from portly.backend import app as app_module
from portly.backend import auth
from portly.backend.actions import docker_actions, process_actions

client = TestClient(app_module.app)


# --- CSRF: same host, different port is a different origin ---

def test_csrf_blocks_same_host_different_port():
    res = client.post("/api/auth/logout", headers={"Origin": "http://localhost:9999"})
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_DETECTED"
    # Port-less loopback origin (implicit :80) is not the dashboard either.
    res80 = client.post("/api/auth/logout", headers={"Origin": "http://localhost"})
    assert res80.status_code == 403
    assert res80.json()["code"] == "CSRF_DETECTED"


def test_csrf_allows_true_same_origin_and_tls_proxy():
    ok = client.post("/api/auth/logout", headers={"Origin": "http://testserver"})
    assert ok.status_code == 200
    # TLS-terminating proxy: https Origin, http backend URL, same host+port.
    tls = client.post("/api/auth/logout", headers={"Origin": "https://testserver"})
    assert tls.status_code == 200


# --- XFF: untrusted proxy headers must not grant local setup trust ---

def test_untrusted_xff_cannot_fake_local_admin(monkeypatch):
    monkeypatch.setattr(app_module.store, "get_user_count", lambda: 0)
    monkeypatch.delenv("PORTLY_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("PORTLY_MODE", raising=False)
    monkeypatch.delenv("PORTLY_ALLOW_INSECURE_BIND", raising=False)
    monkeypatch.setenv("PORTLY_HOST", "127.0.0.1")
    req = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"x-forwarded-for": "127.0.0.1"},
    )
    user = app_module.get_current_user(req, session_token=None, authorization=None)
    assert user["role"] == "setup"  # NOT admin


def test_setup_requires_token_behind_untrusted_proxy(monkeypatch):
    monkeypatch.setattr(app_module.store, "get_user_count", lambda: 0)
    monkeypatch.delenv("PORTLY_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("PORTLY_MODE", raising=False)
    monkeypatch.delenv("PORTLY_ALLOW_INSECURE_BIND", raising=False)
    monkeypatch.setenv("PORTLY_HOST", "127.0.0.1")
    res = client.post(
        "/api/auth/setup",
        json={"username": "attacker", "password": "***", "setup_token": ""},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "INVALID_SETUP_TOKEN"


# --- Safe Mode gates on custom-app create/delete ---

def test_create_with_boot_start_respects_safe_mode(monkeypatch):
    app_module.store.set_setting("safe_mode", "true")
    started = []
    monkeypatch.setattr(
        process_actions, "start_custom_app",
        lambda *a, **k: started.append(a) or {"status": "started"},
    )
    try:
        res = client.post("/api/custom-apps", json={
            "id": "r2boot", "name": "Boot", "host": "localhost", "port": 6199,
            "start_cmd": "python x.py", "start_on_boot": True,
        })
        assert res.status_code == 200
        assert started == []  # locked: interactive create must not auto-start
    finally:
        app_module.store.delete_custom_app("r2boot")
        app_module.store.set_setting("safe_mode", "true")


def test_delete_custom_app_locked_by_safe_mode():
    app_module.store.set_setting("safe_mode", "true")
    app_module.store.upsert_custom_app(app_id="r2del", name="Del", host="localhost", port=6198)
    try:
        res = client.delete("/api/custom-apps/custom:r2del")
        assert res.status_code == 403
        assert res.json()["detail"]["code"] == "SAFE_MODE"
        assert app_module.store.get_custom_app("r2del") is not None
    finally:
        app_module.store.delete_custom_app("r2del")


# --- Viewer redaction ---

def test_summary_redacts_headers_argv_cwd_and_labels():
    sample = {
        "id": "custom:x", "env": {"A": "1"},
        "start_cmd": "secret --token=abc", "custom_headers": {"Authorization": "Bearer xyz"},
        "cmdline": "python secret.py", "cwd": "/root",
        "labels": {"com.docker.compose.project": "p", "secret.label": "hunter2"},
    }
    clean = app_module.redact_app_for_summary(sample)
    for k in ("start_cmd", "custom_headers", "cmdline", "cwd", "env"):
        assert k not in clean
    assert clean["labels"] == {"com.docker.compose.project": "p"}


def test_viewer_endpoints_hide_execution_config(monkeypatch):
    monkeypatch.setattr(
        auth, "validate_session",
        lambda t: {"user_id": "u_v", "username": "viewer", "role": "viewer"} if t == "viewer-token" else None,
    )
    monkeypatch.setattr(app_module, "_cached_apps", [{
        "id": "custom:r2v", "source": "custom", "name": "V", "port": 6197,
        "status": "up", "start_cmd": "run --secret",
        "custom_headers": {"Authorization": "Bearer t"},
    }])
    app_module.store.upsert_custom_app(
        app_id="r2v", name="V", host="localhost", port=6197,
        start_cmd="run --secret", custom_headers={"Authorization": "Bearer t"},
    )
    app_module.store.log_event(
        "custom_app_start", "Started app 'V' (PID 1) | command: run --secret", app_id="custom:r2v",
    )
    c = TestClient(app_module.app)
    c.cookies.set("portly_session", "viewer-token")
    try:
        lst = c.get("/api/custom-apps")
        assert lst.status_code == 200
        entry = next(a for a in lst.json() if a["id"] == "r2v")
        assert "start_cmd" not in entry and "custom_headers" not in entry

        det = c.get("/api/apps/custom:r2v")
        assert det.status_code == 200
        assert "start_cmd" not in det.json()["app"]
        assert "custom_headers" not in det.json()["app"]

        ev = c.get("/api/events")
        assert ev.status_code == 200
        msgs = [e["message"] for e in ev.json() if e.get("app_id") == "custom:r2v"]
        assert msgs and all("command:" not in m for m in msgs)
    finally:
        app_module.store.delete_custom_app("r2v")


# --- Exec allowlist is the default when no store is supplied ---

def test_exec_without_store_defaults_to_allowlist():
    with pytest.raises((ValueError, PermissionError)):
        docker_actions.exec_in_container("any-container", "rm -rf /")


# --- Previously untested CSRF rejection branches ---

def test_csrf_rejects_cross_site_null_origin_and_foreign_referer():
    r1 = client.post("/api/auth/logout", headers={"sec-fetch-site": "cross-site"})
    assert r1.status_code == 403 and r1.json()["code"] == "CSRF_DETECTED"
    r2 = client.post("/api/auth/logout", headers={"Origin": "null"})
    assert r2.status_code == 403 and r2.json()["code"] == "CSRF_DETECTED"
    r3 = client.post("/api/auth/logout", headers={"Referer": "https://evil.example.com/page"})
    assert r3.status_code == 403 and r3.json()["code"] == "CSRF_DETECTED"


def test_weak_setup_password_rejected(monkeypatch):
    monkeypatch.setattr(app_module.store, "get_user_count", lambda: 0)
    monkeypatch.delenv("PORTLY_MODE", raising=False)
    monkeypatch.delenv("PORTLY_ALLOW_INSECURE_BIND", raising=False)
    monkeypatch.setenv("PORTLY_HOST", "127.0.0.1")
    res = client.post("/api/auth/setup", json={"username": "admin", "password": "short"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "WEAK_PASSWORD"


def test_viewer_cannot_create_users(monkeypatch):
    monkeypatch.setattr(
        auth, "validate_session",
        lambda t: {"user_id": "u_v", "username": "v", "role": "viewer"} if t == "vt" else None,
    )
    c = TestClient(app_module.app)
    c.cookies.set("portly_session", "vt")
    res = c.post("/api/users", json={"username": "x", "password": "***", "role": "viewer"})
    assert res.status_code == 403


# --- Backup export/import round-trip (was 100% broken) + secret handling ---

def test_export_import_round_trip_and_masked_restore(monkeypatch):
    monkeypatch.setattr(
        auth, "validate_session",
        lambda t: {"user_id": "u_a", "username": "a", "role": "admin"} if t == "at" else None,
    )
    c = TestClient(app_module.app)
    c.cookies.set("portly_session", "at")
    app_module.store.upsert_custom_app(
        app_id="rt_app", name="RT", host="localhost", port=6123,
        env={"SECRET": "realvalue"}, custom_headers={"Authorization": "Bearer realtok"},
    )
    app_module.store.set_setting("webhook_url", "https://hooks.example.com/services/T00/B00/XXXX")
    app_module.store.create_port_reservation({"port": 6124, "proto": "tcp", "name": "rt-res", "service": "rt"})
    app_module.store.save_compose_stack("rtstack", "services: {}\n", "stopped")
    try:
        exp = c.get("/api/export?format=json")
        assert exp.status_code == 200
        backup = exp.json()
        ca = next(a for a in backup["custom_apps"] if a["id"] == "rt_app")
        assert "env_json" not in ca  # raw secret column must not ride along
        assert ca["env"]["SECRET"] == "********"
        assert ca["custom_headers"]["Authorization"] == "********"
        assert backup["settings"]["webhook_url"] == "https://********"

        imp = c.post("/api/import", json=backup)
        assert imp.status_code == 200, imp.text

        saved = app_module.store.get_custom_app("rt_app")
        assert saved["env"]["SECRET"] == "realvalue"  # masked restore keeps real secrets
        assert saved["custom_headers"]["Authorization"] == "Bearer realtok"
        assert app_module.store.get_setting("webhook_url") == "https://hooks.example.com/services/T00/B00/XXXX"
        assert any(r["name"] == "rt-res" for r in app_module.store.get_port_reservations())
        assert app_module.store.get_compose_stack("rtstack") is not None
    finally:
        app_module.store.delete_custom_app("rt_app")
        app_module.store.set_setting("webhook_url", "")
        app_module.store.delete_compose_stack("rtstack")
        for r in app_module.store.get_port_reservations():
            if r["name"] == "rt-res":
                app_module.store.delete_port_reservation(r["id"])


def test_auth_me_does_not_leak_session_token():
    token = auth.create_session("u_me", "me_user", role="admin")
    c = TestClient(app_module.app)
    c.cookies.set("portly_session", token)
    res = c.get("/api/auth/me")
    assert res.status_code == 200
    user = res.json()["user"]
    assert user and "token" not in user  # stored hash is credential-equivalent
