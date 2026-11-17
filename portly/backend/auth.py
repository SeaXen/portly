"""Authentication, role management, session validation, and security rate limiting."""

import hmac
import logging
import os
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import bcrypt

from portly.backend.store import Store

logger = logging.getLogger("portly.auth")

# Active sessions cache: token -> session dict
_sessions: Dict[str, Dict[str, Any]] = {}
_store: Optional[Store] = None
_auth_lock = threading.Lock()

# Rate limiting for logins: key (e.g. IP or username) -> list of failed timestamp floats
_failed_attempts: Dict[str, List[float]] = {}

# Precomputed valid bcrypt hash for constant-time evaluation on non-existent users
# (prevents timing side-channel user enumeration)
DUMMY_BCRYPT_HASH = "$2b$10$wT0lhK0GkHwD0YQxX9b7u.4g7z3q8n1v7j5e2r0t9y8u7i6o5p4a3"

# Setup token for first-run remote admin initialization
_setup_token: Optional[str] = None


def _get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def get_setup_token() -> str:
    """Returns the single-use setup token required for first-run setup in server mode."""
    global _setup_token
    with _auth_lock:
        if _setup_token is None:
            env_token = os.environ.get("PORTLY_SETUP_TOKEN", "").strip()
            _setup_token = env_token if env_token else secrets.token_hex(16)
        return _setup_token


def verify_setup_token(provided_token: str) -> bool:
    """Validates the setup token using constant-time comparison."""
    expected = get_setup_token()
    if not provided_token or not expected:
        return False
    return hmac.compare_digest(provided_token.strip(), expected.strip())


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Enforces minimum 10 characters password rule."""
    if not password or len(password) < 10:
        return False, "Password must be at least 10 characters long."
    return True, ""


def check_rate_limit(key: str, max_attempts: int = 5, window_sec: float = 60.0) -> bool:
    """Returns True if the key is allowed to attempt login, False if rate limited."""
    now = time.time()
    with _auth_lock:
        attempts = _failed_attempts.get(key, [])
        # Prune old attempts outside window
        valid_attempts = [t for t in attempts if now - t < window_sec]
        _failed_attempts[key] = valid_attempts
        return len(valid_attempts) < max_attempts


def record_failed_attempt(key: str):
    """Records a failed authentication attempt."""
    now = time.time()
    with _auth_lock:
        if key not in _failed_attempts:
            _failed_attempts[key] = []
        _failed_attempts[key].append(now)


def clear_failed_attempts(key: str):
    """Clears failed attempts upon successful login."""
    with _auth_lock:
        _failed_attempts.pop(key, None)


def validate_password(password: str) -> Tuple[bool, str]:
    """Validates password strength (minimum 10 characters)."""
    if not password or len(password) < 10:
        return False, "Password must be at least 10 characters long."
    return True, ""


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def verify_dummy_password(password: str):
    """Executes a bcrypt check against a dummy hash to normalize timing on missing users."""
    try:
        bcrypt.checkpw(password.encode("utf-8"), DUMMY_BCRYPT_HASH.encode("utf-8"))
    except Exception:
        pass


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
    with _auth_lock:
        _sessions[token] = sess
    try:
        _get_store().save_session(token, user_id, username, role, expires_at)
    except Exception as e:
        logger.warning(f"Could not persist session to database: {e}")
    return token


def validate_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    with _auth_lock:
        sess = _sessions.get(token)
    if not sess:
        try:
            db_sess = _get_store().get_session(token)
            if db_sess:
                sess = dict(db_sess)
                with _auth_lock:
                    _sessions[token] = sess
        except Exception:
            pass
    if not sess:
        return None
    if time.time() > sess["expires_at"]:
        with _auth_lock:
            _sessions.pop(token, None)
        try:
            _get_store().delete_session(token)
        except Exception:
            pass
        return None
    return sess


def revoke_session(token: str):
    with _auth_lock:
        _sessions.pop(token, None)
    try:
        _get_store().delete_session(token)
    except Exception:
        pass


def revoke_all_sessions(user_id: str):
    """Revokes all active sessions for a user across memory and database."""
    with _auth_lock:
        tokens_to_drop = [t for t, s in _sessions.items() if s.get("user_id") == user_id]
        for t in tokens_to_drop:
            _sessions.pop(t, None)
    try:
        _get_store().delete_user_sessions(user_id)
    except Exception:
        pass


def prune_expired_sessions():
    now = time.time()
    with _auth_lock:
        expired = [t for t, s in _sessions.items() if s.get("expires_at", 0) < now]
        for t in expired:
            _sessions.pop(t, None)
    try:
        _get_store().prune_expired_sessions()
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
