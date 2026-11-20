"""Regression tests for the repo-audit fixes (session revocation, XFF spoofing,
rate-limit memory, and typed backup validation)."""

from types import SimpleNamespace

from starlette.testclient import TestClient

from portly.backend import app as app_module
from portly.backend import auth
from portly.backend.store import Store


def test_role_change_revokes_sessions(monkeypatch):
    """Demoting a user must drop their existing admin sessions immediately."""
    revoked = []
    monkeypatch.setattr(app_module.store, "get_user_by_id", lambda uid: {"id": uid, "username": "bob", "role": "admin"})
    monkeypatch.setattr(app_module.store, "update_user_role", lambda uid, role: None)
    monkeypatch.setattr(auth, "revoke_all_sessions", lambda uid: revoked.append(uid))

    client = TestClient(app_module.app)
    res = client.patch("/api/users/u_bob/role", json={"role": "viewer"})
    assert res.status_code == 200
    assert revoked == ["u_bob"]


def test_get_client_ip_ignores_untrusted_xff(monkeypatch):
    """Without PORTLY_TRUSTED_PROXIES, X-Forwarded-For never changes the client IP
    (a loopback peer must not be able to rotate rate-limit keys via a fake XFF)."""
    monkeypatch.delenv("PORTLY_TRUSTED_PROXIES", raising=False)
    loopback = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"x-forwarded-for": "1.2.3.4"})
    remote = SimpleNamespace(client=SimpleNamespace(host="8.8.8.8"), headers={"x-forwarded-for": "1.2.3.4"})

    assert app_module.get_client_ip(loopback) == "127.0.0.1"
    assert app_module.get_client_ip(remote) == "8.8.8.8"


def test_rate_limit_sweeps_stale_keys():
    """Periodic cleanup removes expired keys so the dict cannot grow forever."""
    orig_enabled = auth._next_rate_cleanup
    try:
        auth._failed_attempts.clear()
        auth._next_rate_cleanup = 0.0
        for i in range(50):
            auth._failed_attempts[f"stale-{i}"] = [0.0]  # long-expired attempt
        auth.check_rate_limit("fresh")  # triggers the sweep
        assert len(auth._failed_attempts) <= 2
    finally:
        auth._failed_attempts.clear()
        auth._next_rate_cleanup = orig_enabled


def test_import_rejects_wrong_value_type_without_writing(tmp_path):
    """A wrong field type is rejected before any row is written."""
    test_store = Store(str(tmp_path / "import.db"))
    orig = app_module.store
    app_module.store = test_store
    try:
        before = test_store.get_categories()
        client = TestClient(app_module.app)
        res = client.post(
            "/api/import",
            json={"categories": [], "rules": [], "custom_apps": [{"id": "x", "name": "x", "port": "abc"}]},
        )
        assert res.status_code == 400
        assert res.json()["detail"]["code"] == "INVALID_BACKUP"
        assert test_store.get_categories() == before
    finally:
        app_module.store = orig
