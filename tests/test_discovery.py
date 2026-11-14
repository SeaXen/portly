"""Tests for discovery and merge logic."""

import os
from unittest.mock import MagicMock
import pytest
from portly.backend.discovery import host
from portly.backend.discovery.host import discover_host_ports, _get_process_info, _fallback_netstat_windows, _fallback_lsof_unix
from portly.backend.discovery.merge import merge_discovered_apps
from portly.backend.store import Store


def test_discover_host_ports():
    ports = discover_host_ports()
    assert isinstance(ports, list)
    if ports:
        p = ports[0]
        assert "id" in p
        assert p["id"].startswith("host:")
        assert "port" in p
        assert "bind" in p
        assert "source" in p
        assert p["source"] == "host"


def test_get_process_info():
    info = _get_process_info(os.getpid())
    assert "name" in info
    assert "cpu_percent" in info
    assert "ram_mb" in info


def test_fallback_netstat_windows(monkeypatch):
    sample_output = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:80             0.0.0.0:0              LISTENING       1234
  TCP    127.0.0.1:5432         0.0.0.0:0              LISTENING       5678
  TCP    [::]:8080              [::]:0                 LISTENING       9012
  TCP    127.0.0.1:49152        127.0.0.1:5432         ESTABLISHED     1234
"""
    monkeypatch.setattr(host.subprocess, "check_output", lambda *args, **kwargs: sample_output)
    res = _fallback_netstat_windows()
    assert len(res) == 3
    ports = [r["port"] for r in res]
    assert 80 in ports
    assert 5432 in ports
    assert 8080 in ports


def test_fallback_lsof_unix(monkeypatch):
    sample_output = """COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
node     1234 user   23u  IPv4 0x1234      0t0  TCP *:3000 (LISTEN)
postgres 5678 user   24u  IPv6 0x5678      0t0  TCP [::1]:5432 (LISTEN)
"""
    monkeypatch.setattr(host.subprocess, "check_output", lambda *args, **kwargs: sample_output)
    res = _fallback_lsof_unix()
    assert len(res) == 2
    ports = [r["port"] for r in res]
    assert 3000 in ports
    assert 5432 in ports


def test_merge_discovered_apps_dedup_and_conflict(tmp_path):
    db_file = str(tmp_path / "test_portly.db")
    store = Store(db_file)

    # Add custom apps on same port to test conflict
    store.upsert_custom_app("c1", "Custom App 1", "localhost", 9999)
    store.upsert_custom_app("c2", "Custom App 2", "localhost", 9999)

    apps, conflicts = merge_discovered_apps(store)
    assert len(conflicts) >= 1
    conflict_ports = [c["port"] for c in conflicts]
    assert 9999 in conflict_ports

    # Verify both have status 'conflict'
    c1 = next(a for a in apps if a["id"] == "custom:c1")
    c2 = next(a for a in apps if a["id"] == "custom:c2")
    assert c1["status"] == "conflict"
    assert c2["status"] == "conflict"


def test_stable_ids(tmp_path):
    db_file = str(tmp_path / "test_portly.db")
    store = Store(db_file)
    store.upsert_custom_app("my-app", "My App", "localhost", 4321)

    apps, _ = merge_discovered_apps(store)
    found = [a for a in apps if a["port"] == 4321]
    assert len(found) == 1
    assert found[0]["id"] == "custom:my-app"
