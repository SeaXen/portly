"""Authentication, role management, and session validation."""

import secrets
import time
from typing import Any, Dict, Optional

import bcrypt

from portly.backend.store import Store

# Active sessions: token -> session dict
_sessions: Dict[str, Dict[str, Any]] = {}


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
    _sessions[token] = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "created_at": time.time(),
        "expires_at": time.time() + (86400 * 7),  # 7 days
    }
    return token


def validate_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or token not in _sessions:
        return None
    sess = _sessions[token]
    if time.time() > sess["expires_at"]:
        _sessions.pop(token, None)
        return None
    return sess


def revoke_session(token: str):
    _sessions.pop(token, None)


def require_role(session: Optional[Dict[str, Any]], required_role: str = "admin") -> bool:
    """Returns True if session meets role requirements."""
    if not session:
        return False
    user_role = session.get("role", "viewer")
    if required_role == "admin" and user_role != "admin":
        return False
    return True
