"""Tests for Docker actions and non-destructive port changes."""

from unittest.mock import MagicMock
import pytest
from portly.backend.actions import docker_actions
from portly.backend.store import Store


class FakeContainer:
    def __init__(self, name="webapp", image="nginx:alpine"):
        self.name = name
        self.id = "abcdef1234567890"
        self.status = "running"
        self.attrs = {
            "Id": self.id,
            "Name": f"/{name}",
            "Config": {
                "Image": image,
                "Env": ["FOO=BAR"],
                "Cmd": ["nginx", "-g", "daemon off;"],
                "Entrypoint": ["/docker-entrypoint.sh"],
                "Labels": {"com.example": "test"},
                "User": "1000",
                "WorkingDir": "/var/www",
            },
            "HostConfig": {
                "PortBindings": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
                "Binds": ["/host/data:/container/data:rw"],
                "RestartPolicy": {"Name": "always"},
            },
            "NetworkSettings": {
                "Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
                "Networks": {"bridge": {}},
            },
            "Mounts": [
                {"Type": "volume", "Name": "named_vol_data", "Destination": "/var/lib/data", "Mode": "rw"}
            ],
            "State": {
                "Status": "running",
                "Health": {"Status": "healthy"}
            }
        }
        self.stopped = False
        self.removed = False
        self.started = False
        self.restarted = False

    def start(self):
        self.started = True

    def stop(self, timeout=10):
        self.stopped = True

    def restart(self, timeout=10):
        self.restarted = True

    def remove(self, v=False):
        self.removed = True

    def rename(self, new_name):
        self.name = new_name

    def logs(self, tail=500, timestamps=True, stream=False, follow=False):
        return b"2026-11-14T10:00:00Z [INFO] Server started\n2026-11-14T10:00:01Z [INFO] Ready\n"


def test_docker_apply_port_change_success(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "test_docker.db"))
    store.set_setting("safe_mode", "false")

    fake_old = FakeContainer("my_service", "postgres:15")
    fake_new = FakeContainer("my_service", "postgres:15")

    mock_client = MagicMock()
    mock_client.events.return_value = []
    mock_client.containers.get.return_value = fake_old
    mock_client.containers.run.return_value = fake_new

    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: mock_client)

    res = docker_actions.apply_port_change_docker(
        container_name="my_service",
        new_port=5433,
        target_c_port="80/tcp",
        bind="0.0.0.0",
        store=store
    )

    assert res["status"] == "recreated"
    assert res["new_port"] == 5433

    # Check that run was called with preserved arguments
    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["image"] == "postgres:15"
    assert call_kwargs["name"] == "my_service"
    assert call_kwargs["ports"]["80/tcp"] == [{"HostIp": "0.0.0.0", "HostPort": "5433"}]
    assert "/host/data:/container/data:rw" in call_kwargs["volumes"]
    assert "named_vol_data:/var/lib/data:rw" in call_kwargs["volumes"]
    assert call_kwargs["entrypoint"] == ["/docker-entrypoint.sh"]
    assert call_kwargs["command"] == ["nginx", "-g", "daemon off;"]
    assert call_kwargs["restart_policy"] == {"Name": "always"}
    assert call_kwargs["environment"] == ["FOO=BAR"]

    # Verify old container was removed ONLY after run succeeded
    assert fake_old.removed is True

    # Verify snapshot was saved in store
    snap = store.get_port_snapshot("docker:my_service:80/tcp")
    assert snap is not None
    assert snap["original_port"] == 8080
    assert snap["new_port"] == 5433


def test_docker_apply_port_change_failure_restores_container(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "test_docker_fail.db"))
    store.set_setting("safe_mode", "false")

    fake_old = FakeContainer("critical_service", "redis:alpine")
    mock_client = MagicMock()
    mock_client.events.return_value = []
    mock_client.containers.get.return_value = fake_old
    # Simulate failure on recreate (e.g. port already bound by OS)
    mock_client.containers.run.side_effect = RuntimeError("Port 6380 already allocated")

    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: mock_client)

    with pytest.raises(RuntimeError, match="Failed to apply port change"):
        docker_actions.apply_port_change_docker(
            container_name="critical_service",
            new_port=6380,
            target_c_port="80/tcp",
            bind="0.0.0.0",
            store=store
        )

    # CRITICAL NON-DESTRUCTIVE CHECK:
    # 1. Original container must NOT be removed!
    assert fake_old.removed is False
    # 2. Original container must be renamed back to original name!
    assert fake_old.name == "critical_service"
    # 3. Original container must be restarted!
    assert fake_old.started is True


def test_docker_rollback_port_change(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "test_docker_rb.db"))
    store.set_setting("safe_mode", "false")

    app_id = "docker:web_app:80/tcp"
    store.save_port_snapshot(app_id, 8080, 8081, {
        "image": "nginx:latest",
        "ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
        "env": ["STAGE=dev"],
        "cmd": ["nginx"],
        "binds": ["/var/log:/var/log:rw"],
    })

    fake_c = FakeContainer("web_app", "nginx:latest")
    fake_restored = FakeContainer("web_app", "nginx:latest")
    mock_client = MagicMock()
    mock_client.events.return_value = []
    mock_client.containers.get.return_value = fake_c
    mock_client.containers.run.return_value = fake_restored

    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: mock_client)

    res = docker_actions.rollback_port_change_docker(app_id, store)
    assert res["status"] == "rolled_back"
    assert res["port"] == 8080

    # Snapshot should now be cleared
    assert store.get_port_snapshot(app_id) is None


def test_docker_container_lifecycle(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "test_docker_lc.db"))
    store.set_setting("safe_mode", "false")

    fake_c = FakeContainer("worker", "worker:latest")
    mock_client = MagicMock()
    mock_client.events.return_value = []
    mock_client.containers.get.return_value = fake_c

    monkeypatch.setattr(docker_actions, "get_docker_client", lambda: mock_client)

    res_start = docker_actions.start_container("worker", store)
    assert res_start["status"] == "started"

    res_stop = docker_actions.stop_container("worker", store)
    assert res_stop["status"] == "stopped"

    res_restart = docker_actions.restart_container("worker", store)
    assert res_restart["status"] == "restarted"

    # Inspect
    inspect = docker_actions.inspect_container("worker")
    assert inspect["name"] == "worker"
    assert inspect["status"] == "running"
    assert inspect["image"] == "worker:latest"

    # Logs
    logs = docker_actions.get_container_logs("worker")
    assert len(logs) == 2
    assert "Server started" in logs[0]
