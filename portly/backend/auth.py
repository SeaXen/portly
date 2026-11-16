"""Authentication, role management, and session validation."""

import secrets
import time
from typing import Any, Dict, Optional

import bcrypt

from portly.backend.store import Store

# Active sessions cache: token -> session dict
_sessions: Dict[str, Dict[str, Any]] = {}
_store: Optional[Store] = None


def _get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_session(user_id: str, username: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + (86400 * 7)  # 7 days
    sess = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "created_at": time.time(),
        "expires_at": expires_at,
    }
    _sessions[token] = sess
    try:
        _get_store().save_session(token, user_id, username, role, expires_at)
    except Exception:
        pass
    return token


def validate_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    sess = _sessions.get(token)
    if not sess:
        try:
            db_sess = _get_store().get_session(token)
            if db_sess:
                sess = dict(db_sess)
                _sessions[token] = sess
        except Exception:
            pass
    if not sess:
        return None
    if time.time() > sess["expires_at"]:
        _sessions.pop(token, None)
        try:
            _get_store().delete_session(token)
        except Exception:
            pass
        return None
    return sess


def revoke_session(token: str):
    _sessions.pop(token, None)
    try:
        _get_store().delete_session(token)
    except Exception:
        pass


def require_role(session: Optional[Dict[str, Any]], required_role: str = "admin") -> bool:
    """Returns True if session meets role requirements."""
    if not session:
        return False
    user_role = session.get("role", "viewer")
    if required_role == "admin" and user_role != "admin":
        return False
    return True
