"""Change detection, event logging, and event broadcasting with webhook alerts."""

import asyncio
from datetime import datetime, timezone
import ipaddress
import json
import logging
import os
import queue
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.error
import urllib.parse
import urllib.request

from portly.backend.health import _is_safe_health_host, _NoRedirectHandler
from portly.backend.store import Store

logger = logging.getLogger("portly.notifications")

# Key: (port, proto, app_id) -> name
_previous_ports: Dict[Tuple[int, str, str], str] = {}
_previous_container_states: Dict[str, str] = {}
_previous_conflicts: Set[Tuple[int, str]] = set()
_initialized = False

# Cooldown tracking: event_key -> last_sent_timestamp
_cooldown_tracker: Dict[str, float] = {}
_cooldown_lock = threading.Lock()


def format_webhook_payload(
    webhook_type: str,
    event_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    url: str = ""
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
        chat_id = ""
        if url:
            try:
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                if "chat_id" in params:
                    chat_id = params["chat_id"][0]
            except Exception:
                pass
        # Escape Markdown specials: raw container names like "my_app" otherwise
        # make Telegram reject the whole alert with a 400.
        safe_msg = message.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")
        payload = {
            "text": f"⚓ *Portly: {event_type.replace('_', ' ').title()}*\n\n{safe_msg}",
            "parse_mode": "Markdown",
        }
        if chat_id:
            payload["chat_id"] = chat_id
    elif w_type == "ntfy":
        headers["Title"] = f"Portly: {event_type.replace('_', ' ').title()}"
        headers["Priority"] = "default"
        headers["Tags"] = "anchor,server"
        headers["Content-Type"] = "text/plain; charset=utf-8"
        return headers, message.encode("utf-8")
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


def _is_internal_webhook_host(host: str) -> bool:
    """True for private/loopback/reserved hosts that need an explicit opt-in to target."""
    lower = host.lower().strip().strip("[]")
    if lower in ("localhost", "metadata", "metadata.google.internal", "instance-data"):
        return True
    try:
        ip = ipaddress.ip_address(lower)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        pass
    # DNS names: check every resolved record — an attacker domain with an
    # internal A record must not bypass the guard. Fail closed on DNS errors.
    try:
        for info in socket.getaddrinfo(lower, None):
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                return True
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return True
    except Exception:
        return True
    return False


def _internal_webhooks_allowed() -> bool:
    return os.environ.get("PORTLY_ALLOW_INTERNAL_WEBHOOKS", "").strip().lower() in ("1", "true", "yes")


def send_webhook_sync(
    url: str,
    webhook_type: str,
    event_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    timeout: float = 3.5,
    max_retries: int = 2
) -> Tuple[bool, str]:
    """Delivers an alert payload to a webhook URL with timeout and retry backoff."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False, "Invalid webhook URL: must begin with http:// or https://"

    host = urllib.parse.urlparse(url).hostname or ""
    if not _is_safe_health_host(host):
        return False, f"Webhook host '{host}' is blocked (link-local/metadata address)."
    if _is_internal_webhook_host(host) and not _internal_webhooks_allowed():
        return False, f"Webhook host '{host}' is internal. Set PORTLY_ALLOW_INTERNAL_WEBHOOKS=1 to permit."

    headers, body = format_webhook_payload(webhook_type, event_type, message, details, url=url)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirectHandler)

    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            with opener.open(req, timeout=timeout) as resp:
                status = resp.status
                if status < 400:
                    return True, f"Delivered successfully (HTTP {status})"
                last_err = f"Server responded with status {status}"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            last_err = f"Connection Error: {e.reason}"
        except Exception as e:
            last_err = f"Webhook delivery error: {str(e)}"

        if attempt < max_retries:
            time.sleep(0.5 * (attempt + 1))

    return False, last_err


def dispatch_webhook_async(
    event_type: str,
    message: str,
    store: Store,
    details: Optional[Dict[str, Any]] = None
):
    """Fires a webhook notification in a background daemon thread with cooldown gating."""
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

    # Cooldown check: prevent flapping events within 10 seconds
    cooldown_key = f"{event_type}:{details.get('port') if details else ''}:{details.get('container') if details else ''}"
    now = time.time()
    with _cooldown_lock:
        last_time = _cooldown_tracker.get(cooldown_key, 0.0)
        if now - last_time < 10.0:
            return
        _cooldown_tracker[cooldown_key] = now
        if len(_cooldown_tracker) > 500:
            for k in [k for k, v in _cooldown_tracker.items() if v < now - 60.0]:
                _cooldown_tracker.pop(k, None)

    webhook_type = store.get_setting("webhook_type", "generic").strip()

    _ensure_webhook_worker()
    try:
        _webhook_queue.put_nowait((url, webhook_type, event_type, message, details))
    except queue.Full:
        logger.warning(f"Webhook queue full; dropping alert for {event_type}")


_webhook_queue: "queue.Queue" = queue.Queue(maxsize=200)
_webhook_worker_lock = threading.Lock()
_webhook_worker_started = False


def _ensure_webhook_worker():
    """Single delivery worker: a flap storm must not spawn one thread per event."""
    global _webhook_worker_started
    with _webhook_worker_lock:
        if _webhook_worker_started:
            return

        def _loop():
            while True:
                url, w_type, event_type, message, details = _webhook_queue.get()
                try:
                    ok, res = send_webhook_sync(url, w_type, event_type, message, details)
                    if not ok:
                        logger.warning(f"Background webhook delivery failed for {event_type}: {res}")
                except Exception as e:
                    logger.warning(f"Webhook worker error: {e}")
                finally:
                    _webhook_queue.task_done()

        threading.Thread(target=_loop, daemon=True, name="portly-webhook").start()
        _webhook_worker_started = True


def detect_changes(current_apps: List[Dict[str, Any]], current_conflicts: List[Dict[str, Any]], store: Store) -> List[Dict[str, Any]]:
    """Compares current apps with previous state, generates event logs, and dispatches webhook alerts."""
    global _previous_ports, _previous_container_states, _previous_conflicts, _initialized

    events_emitted = []
    # Key by (port, proto, app_id)
    current_ports_map: Dict[Tuple[int, str, str], str] = {}
    for a in current_apps:
        port = a.get("port", 0)
        if port > 0:
            current_ports_map[(port, a.get("proto", "tcp").lower(), a.get("id", ""))] = a.get("name", "App")

    current_cont_map = {a["id"]: a.get("status", "up") for a in current_apps if a.get("source") == "docker"}

    current_conflicts_map: Dict[Tuple[int, str], str] = {}
    for c in current_conflicts:
        port = c.get("port")
        if port:
            current_conflicts_map[(port, c.get("proto", "tcp").lower())] = ", ".join(c.get("apps", []))

    if not _initialized:
        _previous_ports = current_ports_map
        _previous_container_states = current_cont_map
        _previous_conflicts = set(current_conflicts_map.keys())
        _initialized = True
        return []

    # Check for newly opened ports
    for (port, proto, app_id), name in current_ports_map.items():
        if (port, proto, app_id) not in _previous_ports:
            msg = f"Port {port}/{proto} opened by {name}"
            evt = store.log_event("port_opened", msg, app_id=app_id)
            events_emitted.append(evt)
            dispatch_webhook_async("port_opened", msg, store, {"port": port, "proto": proto, "name": name, "app_id": app_id})

    # Check for closed ports
    for (port, proto, app_id), name in _previous_ports.items():
        if (port, proto, app_id) not in current_ports_map:
            msg = f"Port {port}/{proto} closed ({name})"
            evt = store.log_event("port_closed", msg, app_id=app_id)
            events_emitted.append(evt)
            dispatch_webhook_async("port_closed", msg, store, {"port": port, "proto": proto, "name": name, "app_id": app_id})

    # Check for container state changes
    for c_id, status in current_cont_map.items():
        old_status = _previous_container_states.get(c_id)
        if old_status and old_status != status:
            msg = f"Container {c_id} state changed from {old_status} to {status}"
            evt = store.log_event("container_state", msg, app_id=c_id)
            events_emitted.append(evt)
            dispatch_webhook_async("container_state", msg, store, {"container": c_id, "from": old_status, "to": status})

    # Check for newly discovered conflicts
    for (port, proto), apps in current_conflicts_map.items():
        if (port, proto) not in _previous_conflicts:
            msg = f"Port conflict on {port}/{proto}: claimed by {apps}"
            evt = store.log_event("port_conflict", msg)
            events_emitted.append(evt)
            dispatch_webhook_async("port_conflict", msg, store, {"port": port, "proto": proto, "apps": apps})

    # Check for resolved conflicts
    for (port, proto) in _previous_conflicts:
        if (port, proto) not in current_conflicts_map:
            msg = f"Port conflict on {port}/{proto} resolved"
            evt = store.log_event("port_conflict_resolved", msg)
            events_emitted.append(evt)
            dispatch_webhook_async("port_conflict_resolved", msg, store, {"port": port, "proto": proto})

    _previous_ports = current_ports_map
    _previous_container_states = current_cont_map
    _previous_conflicts = set(current_conflicts_map.keys())

    return events_emitted
