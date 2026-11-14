"""Tests for process actions, custom apps lifecycle, and safe log access."""

from unittest.mock import MagicMock
import pytest
from portly.backend.actions import process_actions
from portly.backend.store import Store


class MockPopen:
    def __init__(self, *args, **kwargs):
        self.pid = 4321
        self._poll = None
        self.stdout = MagicMock()
        self.stdout.readline = MagicMock(side_effect=["worker ready\n", ""])

    def poll(self):
        return self._poll

    def terminate(self):
        self._poll = 0

    def kill(self):
        self._poll = 0


def test_custom_app_lifecycle(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "test_proc.db"))
    store.set_setting("safe_mode", "false")

    app_id = "test_py_worker"
    log_file = str(tmp_path / "worker.log")

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    store.upsert_custom_app(
        app_id=app_id,
        name="Worker App",
        host="localhost",
        port=6001,
        start_cmd="python worker.py",
        stop_cmd="auto",
        workdir=str(tmp_path),
        log_file=log_file,
    )

    # Start
    res_start = process_actions.start_custom_app(f"custom:{app_id}", store)
    assert res_start["status"] == "started"
    assert res_start["pid"] == 4321

    # Start again while running should report already_running
    res_again = process_actions.start_custom_app(f"custom:{app_id}", store)
    assert res_again["status"] == "already_running"

    # Read logs from in-memory buffer
    logs = process_actions.get_custom_app_logs(f"custom:{app_id}", store)
    assert any("worker ready" in line for line in logs)

    # Stop
    res_stop = process_actions.stop_custom_app(f"custom:{app_id}", store)
    assert res_stop["status"] == "stopped"

    # Restart
    res_restart = process_actions.restart_custom_app(f"custom:{app_id}", store)
    assert res_restart["status"] == "started"

    # Final cleanup
    process_actions.stop_custom_app(f"custom:{app_id}", store)


def test_custom_app_unsafe_log_file_blocked(tmp_path):
    store = Store(str(tmp_path / "test_unsafe_log.db"))
    store.set_setting("safe_mode", "false")

    # Create app pointing to sensitive file
    store.upsert_custom_app(
        app_id="evil_app",
        name="Evil App",
        host="localhost",
        port=6002,
        log_file="/etc/shadow"
    )

    logs = process_actions.get_custom_app_logs("custom:evil_app", store)
    assert len(logs) == 1
    assert "Access denied" in logs[0]
