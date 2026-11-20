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
    import time
    store = Store(str(tmp_path / "test_proc.db"))
    store.set_setting("safe_mode", "false")

    app_id = "test_py_worker"
    log_file = str(tmp_path / "worker.log")

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    # Never touch real host processes: MockPopen.pid 4321 may be a live PID.
    class FakePsutilProc:
        def __init__(self, pid):
            self.pid = pid
        def create_time(self):
            return 123.0
        def is_running(self):
            return True
        def status(self):
            return "running"
        def children(self, recursive=True):
            return []
        def terminate(self):
            pass
        def kill(self):
            pass
    monkeypatch.setattr(process_actions.psutil, "Process", FakePsutilProc)
    monkeypatch.setattr(process_actions.psutil, "wait_procs", lambda procs, timeout=3.0: (procs, []))

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

    # Read logs from in-memory buffer (poll: the reader is a daemon thread)
    logs = []
    for _ in range(40):
        logs = process_actions.get_custom_app_logs(f"custom:{app_id}", store)
        if any("worker ready" in line for line in logs):
            break
        time.sleep(0.05)
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


def test_custom_app_ownership_survives_restart(tmp_path, monkeypatch):
    """Stop must kill a process started by a previous Portly instance (persisted
    PID), and start must not spawn a duplicate while that process is alive."""
    import subprocess
    store = Store(str(tmp_path / "test_own.db"))
    store.set_setting("safe_mode", "false")
    app_id = "own_worker"
    store.upsert_custom_app(
        app_id=app_id, name="Own", host="localhost", port=6005,
        start_cmd="python worker.py", stop_cmd="auto", workdir=str(tmp_path),
    )
    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    res = process_actions.start_custom_app(f"custom:{app_id}", store)
    assert res["status"] == "started"
    assert store.get_custom_app(app_id)["managed_pid"] == 4321

    # Simulate a Portly restart: the in-memory registry is lost.
    process_actions._running_processes.clear()

    class FakeProc:
        def __init__(self, pid):
            self.pid = pid
        def create_time(self):
            return (store.get_custom_app(app_id) or {}).get("managed_pid_started") or 0.0
        def is_running(self):
            return True
        def status(self):
            return "running"
        def children(self, recursive=True):
            return []
        def terminate(self):
            killed.append(self.pid)
        def kill(self):
            killed.append(self.pid)

    killed = []
    monkeypatch.setattr(process_actions.psutil, "Process", lambda pid: FakeProc(pid))
    monkeypatch.setattr(process_actions.psutil, "wait_procs", lambda procs, timeout=3.0: (procs, []))

    # Start must re-adopt, not duplicate.
    res_again = process_actions.start_custom_app(f"custom:{app_id}", store)
    assert res_again["status"] == "already_running"
    assert res_again["pid"] == 4321

    # Stop must kill the persisted process.
    res_stop = process_actions.stop_custom_app(f"custom:{app_id}", store)
    assert res_stop["status"] == "stopped"
    assert 4321 in killed
    assert store.get_custom_app(app_id)["managed_pid"] is None
