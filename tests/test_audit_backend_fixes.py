"""Regression tests for the backend audit fixes (cross-origin trust, proxy IP,
atomic imports, session/lockout/setup persistence, exec streaming and port fields)."""

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from portly.backend import app as app_module
from portly.backend import auth
from portly.backend.actions import docker_actions, process_actions
from portly.backend.store import Store


def _admin_headers():
    token = auth.create_session("u_audit_admin", "audit_admin", role="admin")
    return {"Authorization": f"Bearer {token}", "X-Portly-Client": "1"}


def _async_noop():
    async def _noop():
        return None
    return _noop


# --- Finding 1: cross-origin CSRF ---

def test_malicious_localhost_origin_blocked_even_with_client_header():
    """A public X-Portly-Client header must not bypass origin validation."""
    client = TestClient(app_module.app)
    res = client.post("/api/settings", json={"theme": "light"}, headers={
        "Origin": "http://localhost:9999",
        "X-Portly-Client": "1",
    })
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_DETECTED"


def test_same_origin_request_allowed():
    client = TestClient(app_module.app)
    res = client.post("/api/auth/logout", headers={
        "Origin": "http://localhost:5533",
        "X-Portly-Client": "1",
    })
    assert res.status_code == 200
    assert res.json().get("status") == "logged_out"


def test_dynamic_request_origin_allowed():
    """A non-default host/port or reverse proxy still passes its own origin."""
    client = TestClient(app_module.app)
    res = client.post("/api/auth/logout", headers={"Origin": "http://testserver"})
    assert res.status_code == 200


def test_tls_proxy_origin_allowed():
    """A TLS-terminating proxy forwards Host but the app sees an http request URL."""
    client = TestClient(app_module.app)
    res = client.post("/api/auth/logout", headers={"Origin": "https://testserver"})
    assert res.status_code == 200


# --- Finding 2: trusted proxies / remote admin ---

def test_remote_via_localhost_proxy_does_not_get_admin(monkeypatch):
    monkeypatch.setattr(app_module.store, "get_user_count", lambda: 0)
    monkeypatch.delenv("PORTLY_MODE", raising=False)
    monkeypatch.delenv("PORTLY_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("PORTLY_ALLOW_INSECURE_BIND", raising=False)
    req = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"x-forwarded-for": "203.0.113.9"},
    )
    user = app_module.get_current_user(req, session_token=None, authorization=None)
    assert user["role"] == "setup"


def test_trusted_proxy_config_limits_xff_trust(monkeypatch):
    monkeypatch.setenv("PORTLY_TRUSTED_PROXIES", "10.0.0.1")
    untrusted = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"x-forwarded-for": "1.2.3.4"},
    )
    assert app_module.get_client_ip(untrusted) == "127.0.0.1"
    trusted = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.1"),
        headers={"x-forwarded-for": "spoofed, 1.2.3.4, 10.0.0.1"},
    )
    assert app_module.get_client_ip(trusted) == "1.2.3.4"


# --- Finding 3: atomic import ---

def test_import_bad_override_leaves_no_partial_state(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "import_atomic.db"))
    monkeypatch.setattr(app_module, "store", test_store)
    client = TestClient(app_module.app)
    backup = {
        "categories": [{"id": "audit_cat", "name": "Audit", "color": "#000"}],
        "app_overrides": {"audit_app": {"tags": "not-a-list"}},
        "settings": {"safe_mode": "false"},
    }
    res = client.post("/api/import", json=backup, headers=_admin_headers())
    assert res.status_code == 400
    assert not any(c["id"] == "audit_cat" for c in test_store.get_categories())
    assert "audit_app" not in test_store.get_all_app_overrides()
    assert test_store.get_setting("safe_mode") == "true"


def test_import_rejects_bad_setting_value(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "import_setting.db"))
    monkeypatch.setattr(app_module, "store", test_store)
    client = TestClient(app_module.app)
    res = client.post("/api/import", json={"settings": {"theme": "neon"}}, headers=_admin_headers())
    assert res.status_code == 400
    assert test_store.get_setting("theme") == "dark"


# --- Finding 4: safe-mode normalization ---

def test_safe_mode_one_normalizes_to_true(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "safe_one.db"))
    monkeypatch.setattr(app_module, "store", test_store)
    client = TestClient(app_module.app)
    res = client.patch("/api/settings", json={"safe_mode": "1"}, headers=_admin_headers())
    assert res.status_code == 200
    assert test_store.get_setting("safe_mode") == "true"
    assert app_module._safe_mode_unlocked_at is None


def test_safe_mode_import_normalizes_and_arms_relock(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "safe_import.db"))
    monkeypatch.setattr(app_module, "store", test_store)
    monkeypatch.setattr(app_module, "refresh_discovery", _async_noop())
    client = TestClient(app_module.app)
    res = client.post("/api/import", json={"settings": {"safe_mode": "0"}}, headers=_admin_headers())
    assert res.status_code == 200
    assert test_store.get_setting("safe_mode") == "false"
    assert app_module._safe_mode_unlocked_at is not None
    app_module._safe_mode_unlocked_at = None


# --- Finding 5: stack name validation ---

def test_stack_name_traversal_rejected():
    with pytest.raises(Exception) as exc:
        app_module._require_valid_stack_name("../evil")
    assert getattr(exc.value, "status_code", None) == 400
    with pytest.raises(ValueError):
        docker_actions.execute_stack_file_action("../evil", "services: {}", "up")


# --- Finding 9: session cache ---

def test_session_revoked_in_db_is_rejected_without_local_clear(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "sessions.db"))
    monkeypatch.setattr(auth, "_store", test_store)
    token = auth.create_session("u_s", "session_user", role="admin")
    assert auth.validate_session(token) is not None
    # Simulate a different worker revoking the session directly in the DB.
    test_store.delete_session(token)
    assert auth.validate_session(token) is None


def test_session_reflects_role_change_in_db(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "roles.db"))
    monkeypatch.setattr(auth, "_store", test_store)
    test_store.create_user("u_r", "role_user", auth.hash_password("Password1234!"), role="admin")
    token = auth.create_session("u_r", "role_user", role="admin")
    test_store.update_user_role("u_r", "viewer")
    assert auth.validate_session(token)["role"] == "viewer"


# --- Finding 10: DB-backed lockout ---

def test_login_lockout_shared_and_window_is_15_minutes(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "lockout.db"))
    monkeypatch.setattr(auth, "_store", test_store)
    key = "203.0.113.77"
    for _ in range(5):
        test_store.add_login_attempt(key, time.time())
    assert auth.check_rate_limit(key) is False
    auth.clear_failed_attempts(key)
    assert auth.check_rate_limit(key) is True
    for _ in range(5):
        test_store.add_login_attempt(key, time.time() - 1000)
    assert auth.check_rate_limit(key) is True  # outside the 15-minute window


# --- Finding 11: single-use setup token ---

def test_setup_token_cannot_be_reused(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "setup.db"))
    monkeypatch.setattr(app_module, "store", test_store)
    monkeypatch.setattr(auth, "_store", test_store)
    monkeypatch.delenv("PORTLY_SETUP_TOKEN", raising=False)
    monkeypatch.setenv("PORTLY_MODE", "server")
    monkeypatch.delenv("PORTLY_TRUSTED_PROXIES", raising=False)

    token = auth.get_setup_token()
    assert auth.verify_setup_token(token)
    client = TestClient(app_module.app)
    res = client.post("/api/auth/setup", json={
        "username": "first_admin", "password": "Password1234!", "setup_token": token,
    })
    assert res.status_code == 200
    assert auth.verify_setup_token(token) is False
    # The token is consumed in the DB; a second request is rejected either as
    # setup-done or as an invalid token, but never succeeds.
    res2 = client.post("/api/auth/setup", json={
        "username": "second_admin", "password": "Password1234!", "setup_token": token,
    })
    assert res2.status_code in (400, 403)


# --- Finding 12: last admin ---

def test_cannot_demote_last_admin(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "last_admin.db"))
    monkeypatch.setattr(app_module, "store", test_store)
    test_store.create_user("u_a", "only_admin", auth.hash_password("Password1234!"), role="admin")
    client = TestClient(app_module.app)
    res = client.patch(
        "/api/users/u_a/role", json={"role": "viewer"}, headers=_admin_headers()
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "LAST_ADMIN"
    assert test_store.get_user_by_id("u_a")["role"] == "admin"


# --- Finding 13: exec streaming ---

def test_exec_streams_and_truncates_bounded_output(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "exec.db"))
    test_store.set_setting("safe_mode", "false")

    class FakeContainer:
        name = "fake"
        id = "fake123"

    def chunks():
        yield b"A" * 200000
        yield b"B" * 200000

    # Real docker-py 7.x contract: low-level exec_create/start/inspect.
    class FakeAPI:
        def exec_create(self, cid, cmd, **kwargs):
            return {"Id": "exec1"}

        def exec_start(self, eid, stream=True, demux=False):
            assert stream is True
            return chunks()

        def exec_inspect(self, eid):
            return {"ExitCode": 0}

    client = SimpleNamespace(api=FakeAPI(), containers=SimpleNamespace(get=lambda name: FakeContainer()))
    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: client)
    res = docker_actions.exec_in_container("fake", "ps aux", store=test_store, timeout=3)
    assert res["exit_code"] == 0
    assert "Output truncated at 256 KB" in res["output"]
    assert len(res["output"]) < 300000


def test_exec_stops_reading_at_deadline(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "exec_timeout.db"))
    test_store.set_setting("safe_mode", "false")

    class FakeContainer:
        name = "fake"
        id = "fake123"

    class FakeAPI:
        def exec_create(self, cid, cmd, **kwargs):
            return {"Id": "exec1"}

        def exec_start(self, eid, stream=True, demux=False):
            def chunks():
                yield b"first"
                yield b"second"
            return chunks()

        def exec_inspect(self, eid):
            return {"ExitCode": None}

    client = SimpleNamespace(api=FakeAPI(), containers=SimpleNamespace(get=lambda name: FakeContainer()))
    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: client)
    times = iter([0.0, 0.0, 100.0])
    monkeypatch.setattr(docker_actions.time, "perf_counter", lambda: next(times, 100.0))
    res = docker_actions.exec_in_container("fake", "ps aux", store=test_store, timeout=1)
    assert "Execution timed out after 1s" in res["output"]
    assert "second" not in res["output"]


def test_exec_silent_stream_timeout_returns_partial(monkeypatch, tmp_path):
    """A silent stream hits the client's 3s socket timeout; that must surface as
    a bounded partial result, not a 500."""
    test_store = Store(str(tmp_path / "exec_silent.db"))
    test_store.set_setting("safe_mode", "false")

    class FakeContainer:
        name = "fake"
        id = "fake123"

    class FakeAPI:
        def exec_create(self, cid, cmd, **kwargs):
            return {"Id": "exec1"}

        def exec_start(self, eid, stream=True, demux=False):
            def chunks():
                yield b"partial"
                raise OSError("Read timed out. (read timeout=3)")
            return chunks()

        def exec_inspect(self, eid):
            return {"ExitCode": None}

    client = SimpleNamespace(api=FakeAPI(), containers=SimpleNamespace(get=lambda name: FakeContainer()))
    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: client)
    res = docker_actions.exec_in_container("fake", "ps aux", store=test_store, timeout=10)
    assert "partial" in res["output"]
    assert "Execution timed out after 10s" in res["output"]


# --- Finding 14: port change preserves health fields ---

def test_port_change_preserves_health_fields(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "port_fields.db"))
    test_store.set_setting("safe_mode", "false")
    test_store.create_custom_app(
        "ca1", "My App", "localhost", 8080,
        expected_status="200,201", custom_headers={"X-Test": "1"},
        health_path="/ok", health_interval=7,
    )
    monkeypatch.setattr(app_module, "store", test_store)
    monkeypatch.setattr(
        app_module, "plan_port_change",
        lambda *a, **k: {"valid": True, "plan": {"type": "custom", "name": "My App"}},
    )
    monkeypatch.setattr(process_actions, "restart_custom_app", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "refresh_discovery", _async_noop())

    client = TestClient(app_module.app)
    res = client.post(
        "/api/apps/custom:ca1/port?apply=true",
        json={"host_port": 9090, "bind": "0.0.0.0"},
        headers=_admin_headers(),
    )
    assert res.status_code == 200
    updated = test_store.get_custom_app("ca1")
    assert updated["expected_status"] == "200,201"
    assert updated["custom_headers"] == {"X-Test": "1"}
    assert updated["health_path"] == "/ok"
