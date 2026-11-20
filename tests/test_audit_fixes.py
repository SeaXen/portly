"""Verification tests for all 10 audit findings and robustness improvements."""

import asyncio
import os
import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from portly.backend import auth
from portly.backend.app import app, on_docker_event, store
from portly.backend.discovery.docker_src import (
    clear_container_stats_cache,
    get_cached_container_stats,
    update_container_stats_cache,
)
from portly.backend.discovery.merge import merge_discovered_apps
from portly.backend.ports import suggest_free_ports
from portly.backend.proxy_gen import sanitize_domain
from portly.backend.store import Store

client = TestClient(app)


def test_stream_and_settings_require_auth_when_users_exist(monkeypatch):
    """Finding 1: SSE stream and settings endpoints require authentication when users exist."""
    monkeypatch.setattr(store, "get_user_count", lambda: 1)

    # 1. /api/stream unauthenticated must return 401
    res_stream = client.get("/api/stream")
    assert res_stream.status_code == 401
    assert res_stream.json()["detail"]["code"] == "UNAUTHORIZED"

    # 2. /api/settings unauthenticated must return 401
    res_settings = client.get("/api/settings")
    assert res_settings.status_code == 401
    assert res_settings.json()["detail"]["code"] == "UNAUTHORIZED"

    # 3. /api/settings authenticated as viewer must mask webhook URL
    store.set_setting("webhook_url", "https://discord.com/api/webhooks/12345/supersecrettoken")
    viewer_token = auth.create_session("u_view", "viewer_user", role="viewer")
    res_viewer = client.get(
        "/api/settings",
        headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert res_viewer.status_code == 200
    assert "supersecrettoken" not in res_viewer.json()["webhook_url"]
    assert "…" in res_viewer.json()["webhook_url"]

    # 4. /api/settings authenticated as admin sees full URL
    admin_token = auth.create_session("u_adm", "admin_user", role="admin")
    res_admin = client.get(
        "/api/settings",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["webhook_url"] == "https://discord.com/api/webhooks/12345/supersecrettoken"


def test_sqlite_persistent_sessions(tmp_path):
    """Finding 8: Sessions are persisted to SQLite across server reboots and multi-worker setups."""
    db_file = str(tmp_path / "sessions_test.db")
    test_store = Store(db_file)

    token = "test_persistent_token_12345"
    test_store.save_session(token, "u_10", "worker_user", "admin", time.time() + 3600)

    # Fetch directly from store
    sess = test_store.get_session(token)
    assert sess is not None
    assert sess["user_id"] == "u_10"
    assert sess["username"] == "worker_user"
    assert sess["role"] == "admin"

    # Test prune expired
    test_store.save_session("expired_token", "u_11", "old_user", "viewer", time.time() - 100)
    test_store.prune_expired_sessions()
    assert test_store.get_session("expired_token") is None
    assert test_store.get_session(token) is not None

    # Test delete session
    test_store.delete_session(token)
    assert test_store.get_session(token) is None


def test_cli_environment_propagation(monkeypatch):
    """Finding 3: CLI flags correctly set PORTLY_MODE and PORTLY_HOST in the environment."""
    import portly.cli as cli

    orig_mode = os.environ.get("PORTLY_MODE")
    orig_host = os.environ.get("PORTLY_HOST")
    orig_port = os.environ.get("PORTLY_PORT")

    test_args = ["portly", "run", "--mode", "server", "--host", "127.0.0.1", "--port", "5544"]
    monkeypatch.setattr("sys.argv", test_args)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: None)

    try:
        cli.main()
        assert os.environ.get("PORTLY_MODE") == "server"
        assert os.environ.get("PORTLY_HOST") == "127.0.0.1"
        assert os.environ.get("PORTLY_PORT") == "5544"
    finally:
        if orig_mode is not None:
            os.environ["PORTLY_MODE"] = orig_mode
        else:
            os.environ.pop("PORTLY_MODE", None)
        if orig_host is not None:
            os.environ["PORTLY_HOST"] = orig_host
        else:
            os.environ.pop("PORTLY_HOST", None)
        if orig_port is not None:
            os.environ["PORTLY_PORT"] = orig_port
        else:
            os.environ.pop("PORTLY_PORT", None)


def test_container_exec_timeout_handling(monkeypatch):
    """Finding 4: Container exec timeout is strictly enforced with HTTP 408 on stall."""
    from portly.backend.actions import docker_actions

    def _stalled_exec(*args, **kwargs):
        time.sleep(2.0)
        return {"output": "done"}

    monkeypatch.setattr(docker_actions, "exec_in_container", _stalled_exec)
    admin_token = auth.create_session("u_exec_adm", "admin", role="admin")
    store.set_setting("safe_mode", "false")

    try:
        res = client.post(
            "/api/apps/docker:stalled_app/exec",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"command": "echo test", "timeout": 1}
        )
        assert res.status_code == 408
        assert res.json()["detail"]["code"] == "TIMEOUT"
    finally:
        store.set_setting("safe_mode", "true")


def test_suggest_free_ports_performance(monkeypatch):
    """Finding 5: suggest_free_ports executes host discovery only once instead of per port loop."""
    from portly.backend import ports

    call_count = 0
    def _mock_discover():
        nonlocal call_count
        call_count += 1
        return [{"port": 8080, "name": "web", "pid": 100}]

    monkeypatch.setattr(ports, "discover_host_ports", _mock_discover)
    monkeypatch.setattr(ports, "is_docker_available", lambda: (False, ""))

    suggested = suggest_free_ports(start_port=3000, count=5)
    assert len(suggested) == 5
    assert call_count == 1  # Exactly 1 call, not 5 or more!


def test_db_retention_pruning(tmp_path):
    """Finding 6: Health history and events tables are bounded and auto-pruned."""
    db_file = str(tmp_path / "prune_test.db")
    test_store = Store(db_file)

    # 1. Health history pruning: record 250 items with limit 200
    for i in range(250):
        test_store.record_health("test_app", True, float(i), max_history=200)

    with test_store._get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) as cnt FROM health_history WHERE app_id = 'test_app'").fetchone()["cnt"]
        assert count == 200

    # 2. Discovery noise prunes to max_events; human audit records are kept
    # separately so port churn cannot evict them.
    for i in range(1050):
        test_store.log_event("port_opened", f"message {i}", max_events=1000)
    for i in range(50):
        test_store.log_event("user.create", f"audit {i}")

    with test_store._get_connection() as conn:
        noise = conn.execute("SELECT COUNT(*) as cnt FROM events WHERE type = 'port_opened'").fetchone()["cnt"]
        audit = conn.execute("SELECT COUNT(*) as cnt FROM events WHERE type = 'user.create'").fetchone()["cnt"]
        assert noise == 1000
        assert audit == 50


def test_multi_homed_no_false_conflict(tmp_path):
    """Finding 7: Distinct IP binds on the same port do not trigger false conflicts."""
    db_file = str(tmp_path / "multi_homed.db")
    test_store = Store(db_file)

    # 1. Two apps on port 8080 on distinct non-wildcard IP interfaces
    raw_apps = [
        {"id": "host:proc1:8080", "name": "LocalService", "port": 8080, "bind": "127.0.0.1", "source": "host"},
        {"id": "host:proc2:8080", "name": "LanService", "port": 8080, "bind": "192.168.1.50", "source": "host"},
    ]

    with patch("portly.backend.discovery.merge.discover_host_ports", return_value=raw_apps):
        with patch("portly.backend.discovery.merge.discover_docker_containers", return_value=[]):
            apps, conflicts = merge_discovered_apps(test_store)
            assert len(conflicts) == 0  # No false conflict!

    # 2. If one is 0.0.0.0 wildcard, conflict MUST be flagged
    raw_apps_wildcard = [
        {"id": "host:proc1:8080", "name": "LocalService", "port": 8080, "bind": "127.0.0.1", "source": "host"},
        {"id": "host:proc3:8080", "name": "GlobalService", "port": 8080, "bind": "0.0.0.0", "source": "host"},
    ]

    with patch("portly.backend.discovery.merge.discover_host_ports", return_value=raw_apps_wildcard):
        with patch("portly.backend.discovery.merge.discover_docker_containers", return_value=[]):
            apps, conflicts = merge_discovered_apps(test_store)
            assert len(conflicts) == 1
            assert conflicts[0]["port"] == 8080


def test_docker_stats_cache():
    """Finding 9: Docker container stats cache can be populated, queried, and cleared."""
    update_container_stats_cache("test_container", {
        "cpu_percent": 15.4,
        "memory_mb": 128.5,
        "memory_limit_mb": 512.0,
        "net_rx_mb": 1.2,
        "net_tx_mb": 0.8,
        "block_read_mb": 0.0,
        "block_write_mb": 0.5,
    })

    stats = get_cached_container_stats("test_container")
    assert stats["cpu_percent"] == 15.4
    assert stats["memory_mb"] == 128.5

    clear_container_stats_cache("test_container")
    stats_cleared = get_cached_container_stats("test_container")
    assert stats_cleared["cpu_percent"] == 0.0


def test_sanitize_domain_injection_prevention():
    """Finding 10: sanitize_domain blocks semicolons, newlines, and directive injection."""
    # Valid domains
    assert sanitize_domain("my-app.example.com", "my-app") == "my-app.example.com"
    assert sanitize_domain("https://sub.domain.local/path", "app") == "sub.domain.local"

    # Malicious injection attempts
    assert sanitize_domain("example.com;\nproxy_pass http://evil.com;", "fallback") == "fallback.local"
    assert sanitize_domain("evil.com} location / {", "fallback") == "fallback.local"
    assert sanitize_domain("domain..com", "fallback") == "fallback.local"
    assert sanitize_domain("", "my-service") == "my-service.local"


def test_docker_event_listener_dispatch(monkeypatch):
    """Finding 2: on_docker_event safely schedules refresh on running event loop without raising."""
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = True
    dispatched = False

    def _mock_run_coroutine_threadsafe(coro, target_loop):
        nonlocal dispatched
        dispatched = True
        coro.close()
        return MagicMock()

    monkeypatch.setattr("asyncio.run_coroutine_threadsafe", _mock_run_coroutine_threadsafe)
    monkeypatch.setattr("portly.backend.app._main_event_loop", mock_loop)

    # Calling on_docker_event must safely dispatch without throwing
    on_docker_event()
    assert dispatched is True
