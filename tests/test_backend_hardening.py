"""Regression tests for backend hardening findings (CORS, CSRF, validation, bcrypt, exec kill)."""

import logging
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from portly.backend import app as app_module, auth
from portly.backend.actions import docker_actions
from portly.backend.app import _dashboard_origins, app, store
from portly.backend.ports import can_bind_port


# --- Finding 1: dev CORS origins are dev-only ---------------------------------

def test_dev_origins_excluded_from_production(monkeypatch):
    monkeypatch.delenv("PORTLY_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("PORTLY_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("PORTLY_TESTING", raising=False)
    monkeypatch.delenv("PORTLY_DEV", raising=False)

    assert not any(":5173" in o for o in _dashboard_origins())

    monkeypatch.setenv("PORTLY_DEV", "1")
    dev = _dashboard_origins()
    assert "http://localhost:5173" in dev
    assert "http://127.0.0.1:5173" in dev

    monkeypatch.delenv("PORTLY_DEV", raising=False)
    monkeypatch.setenv("PORTLY_TESTING", "1")
    assert "http://localhost:5173" in _dashboard_origins()


# --- Finding 2: headerless mutating requests ----------------------------------

def test_headerless_mutation_rejected_outside_testing(monkeypatch):
    monkeypatch.delenv("PORTLY_TESTING", raising=False)
    client = TestClient(app)

    res = client.post("/api/auth/logout")
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_DETECTED"

    # Requests that do carry a header keep their existing behaviour.
    assert client.post("/api/auth/logout", headers={"Origin": "http://testserver"}).status_code != 403


def test_headerless_mutation_allowed_in_testing_mode(monkeypatch):
    monkeypatch.setenv("PORTLY_TESTING", "1")
    assert TestClient(app).post("/api/auth/logout").status_code != 403


# --- Finding 3: port range ----------------------------------------------------

def test_can_bind_port_out_of_range_returns_false():
    assert can_bind_port(99999)[0] is False
    assert can_bind_port(-1)[0] is False


def test_check_port_endpoint_rejects_out_of_range(monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    token = auth.create_session("u_harden", "admin_harden", role="admin")
    client = TestClient(app)
    cookies = {"portly_session": token}

    assert client.get("/api/ports/check?port=99999", cookies=cookies).status_code == 422
    assert client.get("/api/ports/check?port=-1", cookies=cookies).status_code == 422
    assert client.get("/api/ports/check?port=12345", cookies=cookies).status_code == 200


# --- Finding 4: bounded limit query params ------------------------------------

def test_event_and_audit_limits_are_capped(monkeypatch):
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    token = auth.create_session("u_harden2", "admin_harden2", role="admin")
    client = TestClient(app)
    cookies = {"portly_session": token}

    for path in ("/api/events", "/api/audit-logs"):
        assert client.get(f"{path}?limit=0", cookies=cookies).status_code == 422
        assert client.get(f"{path}?limit=1001", cookies=cookies).status_code == 422
        assert client.get(f"{path}?limit=1000", cookies=cookies).status_code == 200


# --- Finding 5: bcrypt 72-byte limit ------------------------------------------

def test_validate_password_rejects_over_72_bytes():
    assert auth.validate_password("a" * 72)[0] is True
    ok, msg = auth.validate_password("a" * 73)
    assert ok is False
    assert "72" in msg
    # Multibyte characters count as bytes, not characters.
    assert auth.validate_password("你" * 25)[0] is False


# --- Finding 6: env setup token warning ---------------------------------------

def test_env_setup_token_warns_and_remains_reusable(monkeypatch, caplog):
    monkeypatch.setenv("PORTLY_SETUP_TOKEN", "env-token-harden")
    with caplog.at_level(logging.WARNING, logger="portly.auth"):
        assert auth.verify_setup_token("env-token-harden") is True
    assert any("PORTLY_SETUP_TOKEN" in r.getMessage() for r in caplog.records)

    auth.consume_setup_token()
    assert auth.verify_setup_token("env-token-harden") is True


# --- Finding 7: IP-literal Host headers honour the allowlist -------------------

def test_ip_literal_host_restricted_when_allowlist_configured(monkeypatch):
    monkeypatch.delenv("PORTLY_TESTING", raising=False)
    monkeypatch.setenv("PORTLY_ALLOWED_HOSTS", "portly.lan")
    client = TestClient(app)

    assert client.get("/api/auth/me", headers={"host": "192.168.1.20:5533"}).status_code == 400
    # Loopback remains available for local healthchecks.
    assert client.get("/api/auth/me", headers={"host": "127.0.0.1:5533"}).status_code == 200

    monkeypatch.setenv("PORTLY_ALLOWED_HOSTS", "portly.lan, 192.168.1.20")
    assert client.get("/api/auth/me", headers={"host": "192.168.1.20:5533"}).status_code == 200


# --- Finding 8: timed-out exec is killed --------------------------------------

def _timeout_exec_client(monkeypatch, kill_error=None):
    client = MagicMock()
    api = client.api
    container = client.containers.get.return_value
    container.id = "cid"
    container.name = "cname"
    api.exec_create.return_value = {"Id": "exec-harden"}
    api._url.return_value = "/v1.41/exec/exec-harden/kill"

    def chunks():
        yield b"partial"
        raise RuntimeError("timed out")

    api.exec_start.return_value = chunks()
    api.exec_inspect.return_value = {"ExitCode": 0}
    if kill_error:
        api._post.side_effect = kill_error
    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: client)
    return api


def test_timed_out_exec_kills_container_process(monkeypatch):
    api = _timeout_exec_client(monkeypatch)
    res = docker_actions.exec_in_container("cname", "ps aux", store=None, timeout=1)

    assert "timed out" in res["output"]
    api._post.assert_called_once()
    call = api._post.call_args
    assert "/exec/exec-harden/kill" in call.args[0]
    assert call.kwargs.get("params") == {"signal": "SIGKILL"}


def test_exec_kill_failure_does_not_mask_timeout_result(monkeypatch):
    _timeout_exec_client(monkeypatch, kill_error=RuntimeError("kill failed"))
    res = docker_actions.exec_in_container("cname", "ps aux", store=None, timeout=1)
    assert "timed out" in res["output"]
    assert res["exit_code"] == 0
