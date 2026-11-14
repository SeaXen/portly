"""Tests for change detection and notification deduplication."""

import pytest
from portly.backend import notifications
from portly.backend.store import Store


def test_conflict_deduplication(tmp_path):
    store = Store(str(tmp_path / "test_notif.db"))

    # Reset module state
    notifications._initialized = False
    notifications._previous_ports = {}
    notifications._previous_container_states = {}
    notifications._previous_conflicts = set()

    apps = [{"id": "a1", "name": "App 1", "port": 8080}]
    conflicts = [{"port": 8080, "apps": ["App 1", "App 2"]}]

    # 1. First scan initializes state
    evts0 = notifications.detect_changes(apps, conflicts, store)
    assert len(evts0) == 0

    # 2. Subsequent scan with SAME conflict must NOT produce duplicate conflict events
    evts1 = notifications.detect_changes(apps, conflicts, store)
    conflict_evts1 = [e for e in evts1 if e.get("type") == "port_conflict"]
    assert len(conflict_evts1) == 0

    # 3. Third scan still with same conflict - still 0 duplicate conflict events
    evts2 = notifications.detect_changes(apps, conflicts, store)
    conflict_evts2 = [e for e in evts2 if e.get("type") == "port_conflict"]
    assert len(conflict_evts2) == 0

    # 4. Now a NEW conflict arises on port 9090
    conflicts_new = [
        {"port": 8080, "apps": ["App 1", "App 2"]},
        {"port": 9090, "apps": ["App 3", "App 4"]}
    ]
    evts3 = notifications.detect_changes(apps, conflicts_new, store)
    conflict_evts3 = [e for e in evts3 if e.get("type") == "port_conflict"]
    assert len(conflict_evts3) == 1
    assert "9090" in conflict_evts3[0]["message"]

    # 5. Conflict on 8080 is resolved
    conflicts_resolved = [{"port": 9090, "apps": ["App 3", "App 4"]}]
    evts4 = notifications.detect_changes(apps, conflicts_resolved, store)
    resolved_evts = [e for e in evts4 if e.get("type") == "port_conflict_resolved"]
    assert len(resolved_evts) == 1
    assert "8080" in resolved_evts[0]["message"]


def test_port_open_and_close(tmp_path):
    store = Store(str(tmp_path / "test_notif2.db"))

    notifications._initialized = False
    notifications._previous_ports = {}
    notifications._previous_container_states = {}
    notifications._previous_conflicts = set()

    # Initial state: port 3000
    notifications.detect_changes([{"port": 3000, "name": "App 3000"}], [], store)

    # Port 4000 opened
    evts = notifications.detect_changes([
        {"port": 3000, "name": "App 3000"},
        {"port": 4000, "name": "App 4000"}
    ], [], store)
    opened = [e for e in evts if e.get("type") == "port_opened"]
    assert len(opened) == 1
    assert "4000" in opened[0]["message"]

    # Port 3000 closed
    evts_close = notifications.detect_changes([
        {"port": 4000, "name": "App 4000"}
    ], [], store)
    closed = [e for e in evts_close if e.get("type") == "port_closed"]
    assert len(closed) == 1
    assert "3000" in closed[0]["message"]
