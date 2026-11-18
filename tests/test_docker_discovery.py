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


MB = 1024 * 1024
V2_CPU = {
    "cpu_stats": {"cpu_usage": {"total_usage": 2000000000}, "system_cpu_usage": 40000000000, "online_cpus": 8},
    "precpu_stats": {"cpu_usage": {"total_usage": 1000000000}, "system_cpu_usage": 36000000000},
}


def _raw_stats(cache_fields, usage=200 * MB):
    return {
        "cpu_stats": {"cpu_usage": {"total_usage": 2000000000}, "system_cpu_usage": 40000000000, "online_cpus": 2},
        "precpu_stats": {"cpu_usage": {"total_usage": 1000000000}, "system_cpu_usage": 36000000000},
        "memory_stats": {"usage": usage, "limit": 1000 * MB, "stats": cache_fields},
    }


class _FakeStatsContainer:
    def __init__(self, cid, raw):
        self.id = cid
        self._raw = raw

    def stats(self, stream=False):
        return self._raw


def test_calculate_cpu_percent_cgroup_v2():
    assert docker_src._calculate_cpu_percent(V2_CPU) == 200.0


def test_calculate_cpu_percent_cgroup_v1_percpu():
    d = {
        "cpu_stats": {"cpu_usage": {"total_usage": 2000000000, "percpu_usage": [1, 2, 3, 4]},
                      "system_cpu_usage": 40000000000},
        "precpu_stats": {"cpu_usage": {"total_usage": 1000000000}, "system_cpu_usage": 36000000000},
    }
    assert docker_src._calculate_cpu_percent(d) == 100.0


def test_calculate_cpu_percent_falls_back_to_psutil_count(monkeypatch):
    monkeypatch.setattr(docker_src.psutil, "cpu_count", lambda: 4)
    d = {
        "cpu_stats": {"cpu_usage": {"total_usage": 2000000000}, "system_cpu_usage": 40000000000},
        "precpu_stats": {"cpu_usage": {"total_usage": 1000000000}, "system_cpu_usage": 36000000000},
    }
    assert docker_src._calculate_cpu_percent(d) == 100.0


def test_refresh_memory_cgroup_v2_inactive_file():
    docker_src.clear_container_stats_cache("mem_v2")
    raw = _raw_stats({"inactive_file": 50 * MB, "cache": 199 * MB})
    docker_src._refresh_container_stats(_FakeStatsContainer("mem_v2", raw))
    cached = docker_src.get_cached_container_stats("mem_v2")
    assert cached["memory_mb"] == 150.0
    assert cached["memory_limit_mb"] == 1000.0
    docker_src.clear_container_stats_cache("mem_v2")


def test_refresh_memory_cgroup_v1_cache_fallback():
    docker_src.clear_container_stats_cache("mem_v1")
    raw = _raw_stats({"cache": 50 * MB})
    docker_src._refresh_container_stats(_FakeStatsContainer("mem_v1", raw))
    assert docker_src.get_cached_container_stats("mem_v1")["memory_mb"] == 150.0
    docker_src.clear_container_stats_cache("mem_v1")


def test_refresh_memory_total_inactive_file_fallback():
    docker_src.clear_container_stats_cache("mem_ti")
    raw = _raw_stats({"total_inactive_file": 40 * MB})
    docker_src._refresh_container_stats(_FakeStatsContainer("mem_ti", raw))
    assert docker_src.get_cached_container_stats("mem_ti")["memory_mb"] == 160.0
    docker_src.clear_container_stats_cache("mem_ti")


def test_refresh_memory_clamped_at_zero():
    docker_src.clear_container_stats_cache("mem_clamp")
    raw = _raw_stats({"inactive_file": 50 * MB}, usage=10 * MB)
    docker_src._refresh_container_stats(_FakeStatsContainer("mem_clamp", raw))
    assert docker_src.get_cached_container_stats("mem_clamp")["memory_mb"] == 0.0
    docker_src.clear_container_stats_cache("mem_clamp")


def test_collect_running_container_stats_is_parallel():
    class SlowContainer:
        def __init__(self, cid):
            self.id = cid

        def stats(self, stream=False):
            time.sleep(0.2)
            return _raw_stats({})

    containers = [SlowContainer(f"par{i:02d}") for i in range(20)]
    t0 = time.perf_counter()
    ids = docker_src._collect_running_container_stats(containers)
    elapsed = time.perf_counter() - t0
    assert len(ids) == 20
    assert elapsed < 1.5, f"parallel stats collection took {elapsed:.2f}s"
    for c in containers:
        docker_src.clear_container_stats_cache(c.id[:12])


def test_collect_running_container_stats_handles_errors():
    class BadContainer:
        id = "badc"

        def stats(self, stream=False):
            raise RuntimeError("stats unavailable")

    good = _FakeStatsContainer("goodc", _raw_stats({}))
    docker_src.clear_container_stats_cache("goodc")
    ids = docker_src._collect_running_container_stats([BadContainer(), good])
    assert "badc" in ids
    assert docker_src.get_cached_container_stats("goodc")["memory_mb"] == 200.0
    docker_src.clear_container_stats_cache("badc")
    docker_src.clear_container_stats_cache("goodc")


def test_stats_cache_exposes_age():
    docker_src.clear_container_stats_cache("agec")
    assert docker_src.get_cached_container_stats("agec")["stats_age_sec"] is None
    docker_src.update_container_stats_cache("agec", {"cpu_percent": 1.0})
    assert docker_src.get_cached_container_stats("agec")["stats_age_sec"] is not None
    docker_src._container_stats_cache["agec"]["ts"] = time.time() - 12.5
    assert docker_src.get_cached_container_stats("agec")["stats_age_sec"] == 12.5
    docker_src.clear_container_stats_cache("agec")
