"""Comprehensive authentication and authorization matrix tests (T-1)."""

import pytest
from fastapi.testclient import TestClient
from portly.backend.app import app, store
from portly.backend import auth


@pytest.fixture
def auth_client():
    return TestClient(app)


def test_auth_matrix_setup_required(auth_client, monkeypatch):
    """When running in server mode with no users, protected endpoints require setup."""
    monkeypatch.setenv("PORTLY_MODE", "server")
    monkeypatch.setenv("PORTLY_ALLOW_INSECURE_BIND", "false")
    monkeypatch.setattr(store, "get_user_count", lambda: 0)

    # Calling mutating endpoint without users returns 403 SETUP_REQUIRED
    res = auth_client.post("/api/scan")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "SETUP_REQUIRED"

    # Setup me endpoint returns needs_setup=True
    me_res = auth_client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["needs_setup"] is True


def test_auth_matrix_unauthenticated(auth_client, monkeypatch):
    """When users exist in system, unauthenticated requests without session token return 401."""
    monkeypatch.setattr(store, "get_user_count", lambda: 1)

    res = auth_client.get("/api/apps")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "UNAUTHORIZED"

    # Expired or invalid token returns 401
    res_bad = auth_client.get("/api/apps", cookies={"portly_session": "invalid_session_token"})
    assert res_bad.status_code == 401
    assert res_bad.json()["detail"]["code"] == "UNAUTHORIZED"


def test_auth_matrix_viewer_vs_admin_rbac(auth_client, monkeypatch):
    """Viewer role can read apps/stats but is blocked from all mutating/admin actions (T-1)."""
    monkeypatch.setattr(store, "get_user_count", lambda: 2)

    # Create tokens for viewer and admin
    viewer_token = auth.create_session("u_v", "viewer_bob", role="viewer")
    admin_token = auth.create_session("u_a", "admin_alice", role="admin")

    viewer_cookies = {"portly_session": viewer_token}
    admin_cookies = {"portly_session": admin_token}

    # 1. /api/apps (Read: both viewer and admin allowed)
    monkeypatch.setattr("portly.backend.app._cached_apps", [])
    monkeypatch.setattr("portly.backend.app._cached_conflicts", [])
    v_apps = auth_client.get("/api/apps", cookies=viewer_cookies)
    assert v_apps.status_code == 200
    a_apps = auth_client.get("/api/apps", cookies=admin_cookies)
    assert a_apps.status_code == 200

    # 2. /api/users (Admin only)
    v_users = auth_client.get("/api/users", cookies=viewer_cookies)
    assert v_users.status_code == 403
    assert v_users.json()["detail"]["code"] == "FORBIDDEN"

    monkeypatch.setattr(store, "list_users", lambda: [{"id": "u_a", "username": "admin_alice", "role": "admin"}])
    a_users = auth_client.get("/api/users", cookies=admin_cookies)
    assert a_users.status_code == 200

    # 3. /api/audit-logs (Admin only)
    v_audit = auth_client.get("/api/audit-logs", cookies=viewer_cookies)
    assert v_audit.status_code == 403
    assert v_audit.json()["detail"]["code"] == "FORBIDDEN"

    monkeypatch.setattr(store, "get_events", lambda limit=100, event_type=None: [])
    a_audit = auth_client.get("/api/audit-logs", cookies=admin_cookies)
    assert a_audit.status_code == 200

    # 4. /api/ports/preflight (Admin only)
    v_pre = auth_client.post("/api/ports/preflight", json={"command": "docker run -p 80:80 nginx"}, cookies=viewer_cookies)
    assert v_pre.status_code == 403

    a_pre = auth_client.post("/api/ports/preflight", json={"command": "docker run -p 80:80 nginx"}, cookies=admin_cookies)
    assert a_pre.status_code == 200

    # 5. /api/docker/prune (Admin only)
    v_prune = auth_client.post("/api/docker/prune", cookies=viewer_cookies)
    assert v_prune.status_code == 403

    # Clean up sessions
    auth.revoke_session(viewer_token)
    auth.revoke_session(admin_token)


def test_auth_rate_limiting_and_lockout(auth_client, monkeypatch):
    """5 failed password attempts triggers IP/username rate limit (S-1)."""
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    monkeypatch.setattr(store, "get_user", lambda u: {"id": "u1", "username": "admin", "password_hash": auth.hash_password("ValidPassword123!")})

    # Clear prior attempts
    auth._failed_attempts.clear()

    # 5 failed login attempts
    for _ in range(5):
        res = auth_client.post("/api/auth/login", json={"username": "admin", "password": "WrongPassword!"})
        assert res.status_code == 401

    # 6th attempt should be blocked with 429
    res_locked = auth_client.post("/api/auth/login", json={"username": "admin", "password": "ValidPassword123!"})
    assert res_locked.status_code == 429
    assert res_locked.json()["detail"]["code"] == "RATE_LIMITED"

    # Reset
    auth._failed_attempts.clear()
