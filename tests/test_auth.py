"""Authentication and session management tests."""

import time
import pytest
from portly.backend import auth
from portly.backend.store import Store


def test_password_hashing():
    pw = "SuperSecretPassword123!"
    hashed = auth.hash_password(pw)
    assert hashed != pw
    assert auth.verify_password(pw, hashed) is True
    assert auth.verify_password("WrongPassword", hashed) is False


def test_session_lifecycle():
    token = auth.create_session("u_1", "admin_user", role="admin")
    assert isinstance(token, str)
    assert len(token) > 20

    # Validate session
    sess = auth.validate_session(token)
    assert sess is not None
    assert sess["user_id"] == "u_1"
    assert sess["username"] == "admin_user"
    assert sess["role"] == "admin"

    # Revoke session
    auth.revoke_session(token)
    assert auth.validate_session(token) is None


def test_session_expiration():
    token = auth.create_session("u_2", "expiring_user", role="viewer")
    # Manually expire the session
    auth._sessions[token]["expires_at"] = time.time() - 10
    assert auth.validate_session(token) is None


def test_store_user_management(tmp_path):
    store = Store(str(tmp_path / "test_auth.db"))
    assert store.get_user_count() == 0

    pw_hash = auth.hash_password("admin_pass")
    user = store.create_user("u_admin", "admin", pw_hash, role="admin")
    assert user["username"] == "admin"
    assert store.get_user_count() == 1

    fetched = store.get_user("admin")
    assert fetched is not None
    assert fetched["id"] == "u_admin"
    assert auth.verify_password("admin_pass", fetched["password_hash"]) is True
