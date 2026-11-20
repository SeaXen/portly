"""Tests for Phase 3: Telemetry Engine, Docker Limits, and Host Process Suppression."""

from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from portly.backend import app as app_module
from portly.backend.actions.docker_actions import apply_port_change_docker
from portly.backend.discovery.merge import merge_discovered_apps
from portly.backend.store import Store


def test_store_health_history_and_latest_health(tmp_path):
    db_file = str(tmp_path / "test_store.db")
    store = Store(db_file)
    assert store.get_latest_health("custom:app1") is None

    store.record_health("custom:app1", True, 12.5)
    latest = store.get_latest_health("custom:app1")
    assert latest is not None
    assert latest["ok"] is True
    assert latest["latency_ms"] == 12.5

    store.record_health("custom:app1", False, 0.0)
    latest2 = store.get_latest_health("custom:app1")
    assert latest2["ok"] is False


def test_merge_discovered_apps_docker_relay_suppression(tmp_path):
    db_file = str(tmp_path / "test_store.db")
    store = Store(db_file)

    # Mock docker app on port 8080
    mock_docker_apps = [{
        "id": "docker:web:8080/tcp",
        "name": "web",
        "port": 8080,
        "bind": "0.0.0.0",
        "proto": "tcp",
        "source": "docker",
        "container_name": "web",
        "container_id": "c123",
        "status": "running",
    }]
    # Host port table has wslrelay.exe and vpnkit binding 8080
    mock_host_ports = [
        {"id": "host:wslrelay:8080/tcp", "port": 8080, "proto": "tcp", "bind": "0.0.0.0", "pid": 110, "process_name": "wslrelay.exe"},
        {"id": "host:vpnkit:8080/tcp", "port": 8080, "proto": "tcp", "bind": "0.0.0.0", "pid": 111, "process_name": "vpnkit"},
        {"id": "host:node:9000/tcp", "port": 9000, "proto": "tcp", "bind": "127.0.0.1", "pid": 200, "process_name": "node"},
    ]

    with patch("portly.backend.discovery.merge.discover_docker_containers", return_value=mock_docker_apps), \
         patch("portly.backend.discovery.merge.discover_host_ports", return_value=mock_host_ports):
        apps, conflicts = merge_discovered_apps(store=store)

        # There should be NO conflicts because wslrelay and vpnkit are recognized as docker relays
        assert len(conflicts) == 0

        # Docker app open_url should convert 0.0.0.0 to localhost
        docker_app = next(a for a in apps if a["source"] == "docker")
        assert docker_app["open_url"] == "http://localhost:8080"


def test_apply_port_change_preserves_resource_limits(tmp_path):
    db_file = str(tmp_path / "test_store.db")
    store = Store(db_file)
    store.set_setting("safe_mode", "false")

    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.name = "my_app"
    mock_container.attrs = {
        "Config": {
            "Image": "nginx:alpine",
            "Env": ["FOO=bar"],
            "Cmd": ["nginx", "-g", "daemon off;"],
            "Entrypoint": None,
            "Labels": {"app": "web"},
            "User": "1000",
            "WorkingDir": "/app",
            "Healthcheck": {"Test": ["CMD", "curl", "-f", "http://localhost/"]},
        },
        "HostConfig": {
            "NetworkMode": "bridge",
            "PortBindings": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
            "Binds": ["/host/data:/data:rw"],
            "RestartPolicy": {"Name": "always"},
            "Privileged": False,
            "NanoCpus": 500000000,
            "Memory": 536870912,
            "MemorySwap": 1073741824,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},
            "Sysctls": {"net.core.somaxconn": "1024"},
            "SecurityOpt": ["no-new-privileges"],
        },
        "Mounts": [],
        "NetworkSettings": {"Networks": {"bridge": {}}},
        "State": {"Running": True},
    }

    mock_new_container = MagicMock()
    mock_new_container.attrs = {"State": {"Running": True}}
    mock_client.containers.get.return_value = mock_container
    mock_client.containers.run.return_value = mock_new_container

    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client):
        result = apply_port_change_docker(
            container_name="my_app",
            new_port=8081,
            target_c_port="80/tcp",
            bind="0.0.0.0",
            store=store,
            actor="admin"
        )
        assert result["status"] == "recreated"
        assert result["new_port"] == 8081

        # Verify client.containers.run was called with resource limits
        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["nano_cpus"] == 500000000
        assert call_kwargs["mem_limit"] == 536870912
        assert call_kwargs["memswap_limit"] == 1073741824
        assert call_kwargs["healthcheck"] == {"Test": ["CMD", "curl", "-f", "http://localhost/"]}
        assert call_kwargs["tmpfs"] == {"/tmp": "rw,noexec,nosuid,size=64m"}
        assert call_kwargs["sysctls"] == {"net.core.somaxconn": "1024"}
        assert call_kwargs["security_opt"] == ["no-new-privileges"]


def test_safe_mode_update_and_relock_tracking(tmp_path):
    import time
    from unittest.mock import patch
    test_client = TestClient(app_module.app)

    # Mock admin auth
    admin_user = {"id": "u_admin", "username": "admin", "role": "admin"}
    with patch("portly.backend.app.require_admin", return_value=admin_user):
        # 1. Setting safe_mode to false sets _safe_mode_unlocked_at
        resp = test_client.patch("/api/settings", json={"safe_mode": "false", "auto_relock_seconds": 60})
        assert resp.status_code == 200
        assert app_module._safe_mode_unlocked_at is not None

        # 2. Setting safe_mode back to true clears _safe_mode_unlocked_at
        resp2 = test_client.patch("/api/settings", json={"safe_mode": "true"})
        assert resp2.status_code == 200
        assert app_module._safe_mode_unlocked_at is None
