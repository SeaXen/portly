"""Security regression and vulnerability tests for Portly."""

import os
import pytest
from fastapi.testclient import TestClient
from portly.backend.app import app, store
from portly.backend.actions import process_actions


client = TestClient(app)


def test_spa_path_traversal_blocked():
    # Attempting to read files outside FRONTEND_DIST via path traversal
    # Encoded traversal paths are decoded by ASGI into full_path with '..'
    res1 = client.get("/..%2F..%2Fdata%2Fportly.db")
    assert res1.status_code == 404

    res2 = client.get("/%2e%2e/%2e%2e/data/portly.db")
    assert res2.status_code == 404

    res3 = client.get("/%2e%2e%2f%2e%2e%2fpyproject.toml")
    assert res3.status_code == 404

    # Also verify with serve_spa directly
    from portly.backend.app import serve_spa
    import asyncio
    import concurrent.futures
    from fastapi import HTTPException

    def _call_async(coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    with pytest.raises(HTTPException) as exc1:
        _call_async(serve_spa("../../data/portly.db"))
    assert exc1.value.status_code == 404

    with pytest.raises(HTTPException) as exc2:
        _call_async(serve_spa("../pyproject.toml"))
    assert exc2.value.status_code == 404


def test_cors_configuration():
    # CORS on localhost should be allowed
    res_local = client.options(
        "/api/apps",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert res_local.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res_local.headers.get("access-control-allow-credentials") == "true"

    # CORS on arbitrary untrusted external domain should NOT be wildcarded with credentials
    res_evil = client.options(
        "/api/apps",
        headers={
            "Origin": "http://evil-attacker.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    # The header must NOT allow evil-attacker.com or wildcard with credentials
    allowed = res_evil.headers.get("access-control-allow-origin")
    assert allowed != "http://evil-attacker.com"
    assert allowed != "*"


def test_safe_log_path_validation(tmp_path):
    # Safe paths
    safe_log = str(tmp_path / "app.log")
    assert process_actions._is_safe_log_path(safe_log) is True

    # Dangerous paths
    assert process_actions._is_safe_log_path(r"C:\Windows\System32\config\SAM") is False
    assert process_actions._is_safe_log_path("/etc/shadow") is False
    assert process_actions._is_safe_log_path("/etc/passwd") is False
    assert process_actions._is_safe_log_path("../../../../etc/passwd") is False
    assert process_actions._is_safe_log_path(r"..\..\..\..\Windows\win.ini") is False
    assert process_actions._is_safe_log_path(r"C:\Users\Admin\.ssh\id_rsa") is False
    assert process_actions._is_safe_log_path("data/portly.db") is False
    assert process_actions._is_safe_log_path("data/portly.db-wal") is False
    assert process_actions._is_safe_log_path("data/portly.db-shm") is False
    assert process_actions._is_safe_log_path("/var/log/auth.log") is False
    assert process_actions._is_safe_log_path("/root/.bashrc") is False
    assert process_actions._is_safe_log_path("app.log\0.txt") is False
    assert process_actions._is_safe_log_path("") is False
    assert process_actions._is_safe_log_path(None) is False


def test_export_requires_auth_when_users_exist(monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    # When unauthenticated
    res = client.get("/api/export")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "UNAUTHORIZED"
    monkeypatch.undo()


def test_import_sanitizes_unsafe_log_file(monkeypatch):
    store.set_setting("safe_mode", "false")
    backup = {
        "categories": [],
        "rules": [],
        "custom_apps": [{
            "id": "evil_import",
            "name": "Evil Import",
            "host": "localhost",
            "port": 9200,
            "log_file": "/etc/shadow",
        }],
        "views": [],
        "app_overrides": {},
        "settings": {}
    }
    res = client.post("/api/import", json=backup)
    assert res.status_code == 200
    app_data = store.get_custom_app("evil_import")
    assert app_data is not None
    # log_file must be sanitized to None
    assert app_data["log_file"] is None


def test_critical_process_kill_protection(monkeypatch):
    # Safe mode must be off to test process name filtering
    store.set_setting("safe_mode", "false")

    # PID <= 4 must raise ValueError
    with pytest.raises(ValueError, match="Cannot terminate system core process"):
        process_actions.kill_host_process(4, store)

    with pytest.raises(ValueError, match="Cannot terminate system core process"):
        process_actions.kill_host_process(0, store)

    # Current Portly process PID must be protected
    with pytest.raises(ValueError, match="Cannot terminate Portly process itself"):
        process_actions.kill_host_process(os.getpid(), store)

    # Critical Windows/Linux process names
    class MockProcess:
        def __init__(self, name):
            self._name = name
        def name(self):
            return self._name
        def terminate(self):
            pass

    import psutil
    for crit_name in ["csrss.exe", "lsass.exe", "services.exe", "wininit.exe", "systemd", "smss.exe"]:
        monkeypatch.setattr(psutil, "Process", lambda pid, n=crit_name: MockProcess(n))
        with pytest.raises(ValueError, match="Cannot terminate critical system process"):
            process_actions.kill_host_process(9999, store)

    # Re-enable safe mode
    store.set_setting("safe_mode", "true")


def test_unauthenticated_admin_escalation_blocked(monkeypatch):
    # When binding to 0.0.0.0 or in server mode without PORTLY_ALLOW_INSECURE_BIND
    monkeypatch.setenv("PORTLY_MODE", "server")
    monkeypatch.setenv("PORTLY_ALLOW_INSECURE_BIND", "false")
    monkeypatch.setattr(store, "get_user_count", lambda: 0)

    # Attempting an admin mutation like stopping an app without credentials
    res = client.post("/api/apps/custom:test/stop")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "SETUP_REQUIRED"

    # Reset
    monkeypatch.undo()
