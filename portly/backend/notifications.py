"""Change detection, event logging, and event broadcasting with webhook alerts."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.error
import urllib.parse
import urllib.request

from portly.backend.store import Store

logger = logging.getLogger("portly.notifications")

_previous_ports: Dict[int, str] = {}
_previous_container_states: Dict[str, str] = {}
_previous_conflicts: Set[int] = set()
_initialized = False


def format_webhook_payload(
    webhook_type: str,
    event_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, str], bytes]:
    """Formats event into target webhook payload and HTTP headers."""
    w_type = webhook_type.lower().strip()
    headers = {"User-Agent": "Portly-WebhookDispatcher/1.0", "Content-Type": "application/json"}

    if w_type == "discord":
        color_map = {
            "port_opened": 0x5EEAD4,
            "port_closed": 0xF5A3D0,
            "container_state": 0x8C9EFF,
            "port_conflict": 0xFF5C5C,
            "port_conflict_resolved": 0xB6E36B,
            "test": 0x8C9EFF,
        }
        payload = {
            "embeds": [
                {
                    "title": f"⚓ Portly: {event_type.replace('_', ' ').title()}",
                    "description": message,
                    "color": color_map.get(event_type, 0x8C9EFF),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {"text": "Portly Notification Service"},
                }
            ]
        }
    elif w_type == "slack":
        payload = {
            "text": f"⚓ *Portly Alert*: {message}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚓ *Portly: {event_type.replace('_', ' ').title()}*\n{message}",
                    },
                }
            ],
        }
    elif w_type == "telegram":
        payload = {
            "text": f"⚓ *Portly: {event_type.replace('_', ' ').title()}*\n\n{message}",
            "parse_mode": "Markdown",
        }
    elif w_type == "ntfy":
        headers["Title"] = f"Portly: {event_type.replace('_', ' ').title()}"
        headers["Priority"] = "default"
        headers["Tags"] = "anchor,server"
        payload = {
            "title": f"Portly: {event_type.replace('_', ' ').title()}",
            "message": message,
        }
    elif w_type == "gotify":
        payload = {
            "title": f"Portly: {event_type.replace('_', ' ').title()}",
            "message": message,
            "priority": 5,
        }
    else:
        # Generic webhook format
        payload = {
            "event": event_type,
            "message": message,
            "timestamp": time.time(),
            "details": details or {},
        }

    return headers, json.dumps(payload).encode("utf-8")


def send_webhook_sync(
    url: str,
    webhook_type: str,
    event_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    timeout: float = 3.5
) -> Tuple[bool, str]:
    """Synchronously delivers an alert payload to a webhook URL with strict timeout."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False, "Invalid webhook URL: must begin with http:// or https://"

    try:
        headers, body = format_webhook_payload(webhook_type, event_type, message, details)
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", getattr(resp, "code", getattr(resp, "getcode", lambda: 200)()))
            if status < 400:
                return True, f"Delivered successfully (HTTP {status})"
            return False, f"Server responded with status {status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection Error: {e.reason}"
    except Exception as e:
        return False, f"Webhook delivery error: {str(e)}"


def dispatch_webhook_async(
    event_type: str,
    message: str,
    store: Store,
    details: Optional[Dict[str, Any]] = None
):
    """Fires a webhook notification in a background daemon thread without blocking discovery."""
    enabled = store.get_setting("webhook_enabled", "false").lower() == "true"
    if not enabled:
        return

    configured_events = store.get_setting("webhook_events", "port_opened,port_closed,container_state,port_conflict")
    allowed_list = [e.strip() for e in configured_events.split(",") if e.strip()]
    if event_type not in allowed_list and "*" not in allowed_list:
        return

    url = store.get_setting("webhook_url", "").strip()
    if not url:
        return

    webhook_type = store.get_setting("webhook_type", "generic").strip()

    def _worker():
        ok, res = send_webhook_sync(url, webhook_type, event_type, message, details)
        if not ok:
            logger.warning(f"Background webhook delivery failed for {event_type}: {res}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def detect_changes(current_apps: List[Dict[str, Any]], current_conflicts: List[Dict[str, Any]], store: Store) -> List[Dict[str, Any]]:
    """Compares current apps with previous state, generates event logs, and dispatches webhook alerts."""
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
            msg = f"Port {port} opened by {name}"
            evt = store.log_event("port_opened", msg)
            events_emitted.append(evt)
            dispatch_webhook_async("port_opened", msg, store, {"port": port, "name": name})

    # Check for closed ports
    for port, name in _previous_ports.items():
        if port not in current_ports_map:
            msg = f"Port {port} closed ({name})"
            evt = store.log_event("port_closed", msg)
            events_emitted.append(evt)
            dispatch_webhook_async("port_closed", msg, store, {"port": port, "name": name})

    # Check for container state changes
    for c_id, status in current_cont_map.items():
        old_status = _previous_container_states.get(c_id)
        if old_status and old_status != status:
            msg = f"Container {c_id} state changed from {old_status} to {status}"
            evt = store.log_event("container_state", msg, app_id=c_id)
            events_emitted.append(evt)
            dispatch_webhook_async("container_state", msg, store, {"container": c_id, "from": old_status, "to": status})

    # Check for newly discovered conflicts
    for port, apps in current_conflicts_map.items():
        if port not in _previous_conflicts:
            msg = f"Port conflict on port {port}: claimed by {apps}"
            evt = store.log_event("port_conflict", msg)
            events_emitted.append(evt)
            dispatch_webhook_async("port_conflict", msg, store, {"port": port, "apps": apps})

    # Check for resolved conflicts
    for port in _previous_conflicts:
        if port not in current_conflicts_map:
            msg = f"Port conflict on port {port} resolved"
            evt = store.log_event("port_conflict_resolved", msg)
            events_emitted.append(evt)
            dispatch_webhook_async("port_conflict_resolved", msg, store, {"port": port})

    _previous_ports = current_ports_map
    _previous_container_states = current_cont_map
    _previous_conflicts = set(current_conflicts_map.keys())

    return events_emitted
