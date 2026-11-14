"""Tests for port availability, suggestion, and planning."""

from unittest.mock import MagicMock
import pytest
from portly.backend.ports import (
    check_port_availability,
    plan_port_change,
    suggest_free_ports,
    can_bind_port,
    is_port_in_socket_table
)
from portly.backend.store import Store


def test_suggest_free_ports():
    ports = suggest_free_ports(start_port=18000, count=3)
    assert len(ports) == 3
    for p in ports:
        assert p >= 18000
        avail = check_port_availability(p)
        assert avail["free"] is True


def test_check_port_availability_invalid():
    res_zero = check_port_availability(0)
    assert res_zero["free"] is False
    assert "Invalid port" in res_zero["used_by"]

    res_large = check_port_availability(70000)
    assert res_large["free"] is False
    assert "Invalid port" in res_large["used_by"]


def test_plan_port_change_custom(tmp_path):
    db_file = str(tmp_path / "test_portly.db")
    store = Store(db_file)
    store.upsert_custom_app("billing", "Billing API", "localhost", 4000)

    # Suggest a free port
    free_port = suggest_free_ports(start_port=21000, count=1)[0]
    res = plan_port_change("custom:billing", free_port, "127.0.0.1", store)
    assert res["valid"] is True
    plan = res["plan"]
    assert plan["type"] == "custom"
    assert plan["new_port"] == free_port
    assert len(plan["steps"]) > 0


def test_plan_port_change_docker(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_docker_plan.db")
    store = Store(db_file)

    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.name = "redis-cache"
    mock_container.attrs = {"Config": {"Image": "redis:alpine"}}
    mock_client.containers.get.return_value = mock_container

    from portly.backend import ports
    monkeypatch.setattr(ports, "get_docker_client", lambda: mock_client)

    free_port = suggest_free_ports(start_port=22000, count=1)[0]
    res = plan_port_change("docker:redis-cache:6379/tcp", free_port, "0.0.0.0", store)
    assert res["valid"] is True
    plan = res["plan"]
    assert plan["type"] == "docker"
    assert plan["container_name"] == "redis-cache"
    assert plan["new_host_port"] == free_port


def test_plan_port_change_unmanaged_host(tmp_path):
    db_file = str(tmp_path / "test_host_plan.db")
    store = Store(db_file)

    free_port = suggest_free_ports(start_port=23000, count=1)[0]
    res = plan_port_change("host:python:8000", free_port, "0.0.0.0", store)
    assert res["valid"] is False
    assert "unmanaged host processes" in res["error"]


def test_plan_port_change_port_in_use(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_busy_plan.db")
    store = Store(db_file)

    from portly.backend import ports
    monkeypatch.setattr(ports, "check_port_availability", lambda p, b: {"free": False, "used_by": "Bound by system"})

    res = plan_port_change("custom:test", 5000, "127.0.0.1", store)
    assert res["valid"] is False
    assert "not free" in res["error"]


def test_ports_additional_edge_cases(tmp_path, monkeypatch):
    from portly.backend import ports
    db_file = str(tmp_path / "edge_cases.db")
    store = Store(db_file)

    # 1. is_port_in_socket_table finds matching port
    found, msg = ports.is_port_in_socket_table(8080, [{"port": 8080, "name": "nginx", "pid": 1234}])
    assert found is True
    assert "1234" in msg

    # 2. can_bind_port on invalid bind address
    can_b, err_b = ports.can_bind_port(80, "999.999.999.999")
    assert can_b is False
    assert "cannot be bound" in err_b

    # 3. Docker port mapping check in check_port_availability
    mock_c = MagicMock()
    mock_c.name = "my_postgres"
    mock_c.attrs = {
        "NetworkSettings": {
            "Ports": {
                "5432/tcp": [{"HostPort": "5432", "HostIp": "0.0.0.0"}]
            }
        }
    }
    mock_docker = MagicMock()
    mock_docker.containers.list.return_value = [mock_c]

    monkeypatch.setattr(ports, "is_docker_available", lambda: (True, ""))
    monkeypatch.setattr(ports, "get_docker_client", lambda: mock_docker)
    monkeypatch.setattr(ports, "can_bind_port", lambda p, b: (True, ""))
    monkeypatch.setattr(ports, "is_port_in_socket_table", lambda p: (False, ""))

    res_dock = ports.check_port_availability(5432)
    assert res_dock["free"] is False
    assert "Claimed by container 'my_postgres'" in res_dock["used_by"]

    # 4. plan_port_change with docker unavailable
    monkeypatch.setattr(ports, "check_port_availability", lambda p, b: {"free": True, "used_by": ""})
    monkeypatch.setattr(ports, "get_docker_client", lambda: None)
    res_no_dock = ports.plan_port_change("docker:redis:6379/tcp", 6380, "0.0.0.0", store)
    assert res_no_dock["valid"] is False
    assert "Docker is not available" in res_no_dock["error"]

    # 5. plan_port_change with container not found
    mock_client = MagicMock()
    mock_client.containers.get.side_effect = Exception("No such container")
    monkeypatch.setattr(ports, "get_docker_client", lambda: mock_client)
    res_not_found = ports.plan_port_change("docker:missing:6379/tcp", 6380, "0.0.0.0", store)
    assert res_not_found["valid"] is False
    assert "Container not found" in res_not_found["error"]

    # 6. plan_port_change with custom app not found
    res_no_custom = ports.plan_port_change("custom:nonexistent", 6380, "0.0.0.0", store)
    assert res_no_custom["valid"] is False
    assert "Custom app not found" in res_no_custom["error"]

