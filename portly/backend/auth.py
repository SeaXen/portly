"""Authentication, role management, session validation, and security rate limiting."""

import hashlib
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

# Active sessions cache: token -> session dict (authoritative state lives in the DB)
_sessions: Dict[str, Dict[str, Any]] = {}
_store: Optional[Store] = None
_auth_lock = threading.Lock()

# Kept for callers/tests that reset the legacy in-process counter; the real,
# shared counter lives in the DB so all workers see the same failures.
class _FailedAttempts(dict):
    def clear(self):
        super().clear()
        try:
            _get_store().clear_all_login_attempts()
        except Exception:
            pass

_failed_attempts = _FailedAttempts()
_next_rate_cleanup: float = 0.0
_RATE_CLEANUP_INTERVAL = 60.0
LOGIN_LOCKOUT_SEC = 900.0  # 15 minutes, matching SECURITY.md

# Precomputed valid bcrypt hash for constant-time evaluation on non-existent users
# (prevents timing side-channel user enumeration)
DUMMY_BCRYPT_HASH = "$2b$10$wT0lhK0GkHwD0YQxX9b7u.4g7z3q8n1v7j5e2r0t9y8u7i6o5p4a3"


def _get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_setup_token() -> str:
    """Generates a single-use setup token, printing it once. Only its hash is stored.

    A new token is created each call (invalidating any previous one), so a token
    lost before setup can be regenerated with `portly reset-setup-token`.
    """
    env_token = os.environ.get("PORTLY_SETUP_TOKEN", "").strip()
    if env_token:
        return env_token
    with _auth_lock:
        token = secrets.token_hex(16)
        _get_store().save_setup_token(_token_hash(token))
        return token


def verify_setup_token(provided_token: str) -> bool:
    """Validates the setup token using constant-time hash comparison."""
    if not provided_token:
        return False
    provided = provided_token.strip()
    env_token = os.environ.get("PORTLY_SETUP_TOKEN", "").strip()
    if env_token:
        return hmac.compare_digest(provided, env_token)
    record = _get_store().get_setup_token_record()
    if not record or not record.get("token_hash"):
        return False
    return hmac.compare_digest(_token_hash(provided), record["token_hash"])


def consume_setup_token():
    """Invalidates the setup token after the first admin is created."""
    if os.environ.get("PORTLY_SETUP_TOKEN", "").strip():
        return  # env override cannot be consumed
    with _auth_lock:
        _get_store().delete_setup_token()


def check_rate_limit(key: str, max_attempts: int = 5, window_sec: float = LOGIN_LOCKOUT_SEC) -> bool:
    """Returns True if the key is allowed to attempt login, False if rate limited."""
    global _next_rate_cleanup
    now = time.time()
    with _auth_lock:
        # Sweep the legacy dict so it cannot grow forever with unique keys.
        if now >= _next_rate_cleanup:
            for k in list(_failed_attempts):
                live = [t for t in _failed_attempts[k] if now - t < window_sec]
                if live:
                    _failed_attempts[k] = live
                else:
                    del _failed_attempts[k]
            _next_rate_cleanup = now + _RATE_CLEANUP_INTERVAL
    # The shared DB counter is authoritative across workers.
    since = now - window_sec
    try:
        db_attempts = _get_store().get_login_attempts(key, since)
    except Exception:
        db_attempts = []
    local = [t for t in _failed_attempts.get(key, []) if now - t < window_sec]
    return len(set(db_attempts) | set(local)) < max_attempts


def record_failed_attempt(key: str):
    """Records a failed authentication attempt in the shared store."""
    now = time.time()
    with _auth_lock:
        _failed_attempts.setdefault(key, []).append(now)
    try:
        _get_store().add_login_attempt(key, now)
    except Exception:
        pass


def clear_failed_attempts(key: str):
    """Clears failed attempts upon successful login."""
    with _auth_lock:
        _failed_attempts.pop(key, None)
    try:
        _get_store().clear_login_attempts(key)
    except Exception:
        pass


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
    # The DB is authoritative: logout, demotion or deletion on any worker is
    # visible immediately. The in-memory dict is only a local expiry override.
    try:
        db_sess = _get_store().get_session(token)
    except Exception:
        db_sess = None
    with _auth_lock:
        local = _sessions.get(token)
    if not db_sess:
        if local:
            with _auth_lock:
                _sessions.pop(token, None)
        return None
    sess = dict(db_sess)
    now = time.time()
    if (local and now > local["expires_at"]) or now > sess["expires_at"]:
        with _auth_lock:
            _sessions.pop(token, None)
        try:
            _get_store().delete_session(token)
        except Exception:
            pass
        return None
    # Reflect the current role in case the users table changed.
    try:
        user = _get_store().get_user_by_id(sess.get("user_id", ""))
        if user:
            sess["role"] = user["role"]
            sess["username"] = user["username"]
    except Exception:
        pass
    with _auth_lock:
        _sessions[token] = sess
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

