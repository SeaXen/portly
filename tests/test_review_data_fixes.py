"""Response-shape regressions for the discovery/data-honesty review fixes."""

import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psutil

from portly.backend.discovery import docker_src, host
from portly.backend.discovery.merge import merge_discovered_apps
from portly.backend.store import Store


def _merge_custom(store):
    with patch("portly.backend.discovery.merge.discover_host_ports", return_value=[]), \
         patch("portly.backend.discovery.merge.discover_docker_containers", return_value=[]):
        return merge_discovered_apps(store)[0]


def test_custom_app_unknown_without_health_snapshot(tmp_path):
    store = Store(str(tmp_path / "review.db"))
    store.upsert_custom_app("no-health", "No Health App", "localhost", 8101)

    app = next(a for a in _merge_custom(store) if a["id"] == "custom:no-health")
    assert app["status"] == "unknown"
    assert app["cpu_percent"] is None
    assert app["ram_mb"] is None
    assert app["uptime_sec"] is None


def test_custom_app_status_from_health_snapshot(tmp_path):
    store = Store(str(tmp_path / "review2.db"))
    store.upsert_custom_app("with-health", "With Health", "localhost", 8102)
    store.record_health("custom:with-health", ok=True, latency_ms=12.5)

    app = next(a for a in _merge_custom(store) if a["id"] == "custom:with-health")
    assert app["status"] == "up"
    assert app["latency_ms"] == 12.5


def test_host_unreadable_metrics_are_none(monkeypatch):
    class DeniedProcess:
        def __init__(self, pid):
            pass

        def is_running(self):
            return True

        def create_time(self):
            raise psutil.AccessDenied()

        def name(self):
            return "denied"

        def cmdline(self):
            return ["denied"]

        def cwd(self):
            return "/tmp"

        def cpu_percent(self, interval=None):
            return 0.0

        def memory_info(self):
            raise psutil.AccessDenied()

    class Conn:
        type = socket.SOCK_STREAM
        status = psutil.CONN_LISTEN
        pid = 5555
        laddr = SimpleNamespace(ip="127.0.0.1", port=8123)

    monkeypatch.setattr(psutil, "Process", DeniedProcess)
    monkeypatch.setattr(psutil, "net_connections", lambda kind="inet": [Conn()])
    host._proc_instances.clear()
    ports = host.discover_host_ports()

    entry = next(p for p in ports if p["port"] == 8123)
    assert entry["cpu_percent"] is None
    assert entry["ram_mb"] is None
    assert entry["uptime_sec"] is None


def test_docker_app_carries_stats_age(monkeypatch):
    c = MagicMock()
    c.id = "ageapp000001"  # 12 chars -> short id is the whole string
    c.name = "ageapp"
    c.status = "running"
    c.image.tags = ["img:latest"]
    c.labels = {}
    c.attrs = {
        "NetworkSettings": {"Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8181"}]}},
        "State": {"Status": "running"},
    }
    client = MagicMock()
    client.containers.list.return_value = [c]
    monkeypatch.setattr(docker_src, "get_docker_client", lambda force_retry=False: client)
    monkeypatch.setattr(docker_src, "_docker_available", True)
    docker_src.update_container_stats_cache("ageapp000001", {"cpu_percent": 5.0})
    try:
        entry = next(r for r in docker_src.discover_docker_containers() if r["port"] == 8181)
        assert "stats_age_sec" in entry
        assert entry["stats_age_sec"] is not None
    finally:
        docker_src.clear_container_stats_cache("ageapp000001")
