"""Tests for Docker container discovery, reconnection, and stats."""

import time
from unittest.mock import MagicMock
import pytest
from portly.backend.discovery import docker_src


class MockDockerContainer:
    def __init__(self, name="nginx-test", status="running", ports=None, labels=None):
        self.id = "abcdef9876543210"
        self.name = name
        self.status = status
        self.image = MagicMock()
        self.image.tags = ["nginx:1.25-alpine"]
        self.labels = labels or {
            "portly.name": "Custom Nginx",
            "portly.icon": "server",
            "portly.category": "web",
            "portly.url": "http://localhost:8080",
            "com.docker.compose.project": "myproject",
            "com.docker.compose.service": "web"
        }
        self.attrs = {
            "Id": self.id,
            "Created": "2026-11-14T00:00:00Z",
            "Config": {"Image": "nginx:1.25-alpine"},
            "State": {"Status": status, "Health": {"Status": "healthy"}},
            "NetworkSettings": {
                "Ports": ports or {
                    "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
                    "443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8443"}],
                }
            }
        }


def test_docker_reconnection_after_initial_failure(monkeypatch):
    # Reset docker_src module state
    docker_src._client = None
    docker_src._client_init_attempted = False
    docker_src._docker_available = False
    docker_src._docker_error_msg = ""
    docker_src._last_init_attempt = 0.0

    # 1. First attempt fails (e.g. Docker not started yet)
    mock_docker_module = MagicMock()
    mock_docker_module.from_env.side_effect = Exception("Docker daemon is not running")
    monkeypatch.setattr(docker_src, "docker", mock_docker_module)

    client1 = docker_src.get_docker_client(force_retry=True)
    assert client1 is None
    avail1, msg1 = docker_src.is_docker_available()
    assert avail1 is False
    assert "not reachable" in msg1

    # 2. Subsequent attempt after Docker starts succeeds (VERIFIES RECONNECT LOCKOUT FIX)
    mock_working_client = MagicMock()
    mock_working_client.events.return_value = []
    mock_docker_module.from_env.side_effect = None
    mock_docker_module.from_env.return_value = mock_working_client

    client2 = docker_src.get_docker_client(force_retry=True)
    assert client2 is not None
    avail2, _ = docker_src.is_docker_available()
    assert avail2 is True


def test_discover_docker_containers(monkeypatch):
    mock_client = MagicMock()
    mock_client.events.return_value = []
    c1 = MockDockerContainer("web-app", "running")
    c2 = MockDockerContainer("worker", "running", ports={})
    c3 = MockDockerContainer("stopped-db", "exited", ports={"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]})
    mock_client.containers.list.return_value = [c1, c2, c3]

    monkeypatch.setattr(docker_src, "get_docker_client", lambda force_retry=False: mock_client)
    monkeypatch.setattr(docker_src, "_docker_available", True)

    results = docker_src.discover_docker_containers()
    assert len(results) >= 2

    # Check port mappings and metadata extraction
    ports = [r["port"] for r in results]
    assert 8080 in ports
    assert 8443 in ports

    web_entry = next(r for r in results if r["port"] == 8080)
    assert web_entry["name"] == "Custom Nginx"
    assert web_entry["compose_project"] == "myproject"
    assert web_entry["compose_service"] == "web"
    assert web_entry["status"] == "up"
    assert web_entry["health"] == "healthy"


def test_cached_container_stats():
    # Unknown container returns defaults
    stats = docker_src.get_cached_container_stats("unknown_id_123")
    assert stats["cpu_percent"] == 0.0
    assert stats["memory_mb"] == 0.0

    # Populated container returns cached values
    docker_src._container_stats_cache["c_test"] = {
        "cpu_percent": 12.5,
        "memory_mb": 256.0,
        "memory_limit_mb": 1024.0,
        "net_rx_mb": 1.2,
        "net_tx_mb": 3.4,
        "block_read_mb": 0.0,
        "block_write_mb": 0.5,
    }
    cached = docker_src.get_cached_container_stats("c_test")
    assert cached["cpu_percent"] == 12.5
    assert cached["memory_mb"] == 256.0
