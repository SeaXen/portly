"""Change detection, event logging, and event broadcasting."""

import logging
import time
from typing import Any, Dict, List, Optional, Set

from portly.backend.store import Store

logger = logging.getLogger("portly.notifications")

_previous_ports: Dict[int, str] = {}
_previous_container_states: Dict[str, str] = {}
_previous_conflicts: Set[int] = set()
_initialized = False


def detect_changes(current_apps: List[Dict[str, Any]], current_conflicts: List[Dict[str, Any]], store: Store) -> List[Dict[str, Any]]:
    """Compares current apps with previous state and generates event logs."""
    global _previous_ports, _previous_container_states, _previous_conflicts, _initialized

    events_emitted = []
    current_ports_map = {a["port"]: a["name"] for a in current_apps if a.get("port", 0) > 0}
    current_cont_map = {a["id"]: a.get("status", "up") for a in current_apps if a.get("source") == "docker"}
    current_conflicts_map = {c["port"]: ", ".join(c.get("apps", [])) for c in current_conflicts if c.get("port")}

    if not _initialized:
        _previous_ports = current_ports_map
        _previous_container_states = current_cont_map
        _previous_conflicts = set(current_conflicts_map.keys())
        _initialized = True
        return []

    # Check for newly opened ports
    for port, name in current_ports_map.items():
        if port not in _previous_ports:
            evt = store.log_event("port_opened", f"Port {port} opened by {name}")
            events_emitted.append(evt)

    # Check for closed ports
    for port, name in _previous_ports.items():
        if port not in current_ports_map:
            evt = store.log_event("port_closed", f"Port {port} closed ({name})")
            events_emitted.append(evt)

    # Check for container state changes
    for c_id, status in current_cont_map.items():
        old_status = _previous_container_states.get(c_id)
        if old_status and old_status != status:
            evt = store.log_event("container_state", f"Container {c_id} state changed from {old_status} to {status}", app_id=c_id)
            events_emitted.append(evt)

    # Check for newly discovered conflicts
    for port, apps in current_conflicts_map.items():
        if port not in _previous_conflicts:
            evt = store.log_event("port_conflict", f"Port conflict on port {port}: claimed by {apps}")
            events_emitted.append(evt)

    # Check for resolved conflicts
    for port in _previous_conflicts:
        if port not in current_conflicts_map:
            evt = store.log_event("port_conflict_resolved", f"Port conflict on port {port} resolved")
            events_emitted.append(evt)

    _previous_ports = current_ports_map
    _previous_container_states = current_cont_map
    _previous_conflicts = set(current_conflicts_map.keys())

    return events_emitted
