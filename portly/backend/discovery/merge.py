"""Merges and unifies host processes, Docker containers, and custom apps."""

import time
from typing import Any, Dict, List, Optional, Set, Tuple

from portly.backend.categories import categorize_app
from portly.backend.discovery.docker_src import discover_docker_containers, is_docker_available
from portly.backend.discovery.host import discover_host_ports
from portly.backend.store import Store


def merge_discovered_apps(store: Store, public_host: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Discovers all sources, merges them according to merge rules,
    resolves conflicts, applies overrides and categorization.
    Returns (apps_list, conflicts_list).
    """
    host_apps = discover_host_ports()
    docker_apps = discover_docker_containers()
    custom_apps_raw = store.get_custom_apps()
    app_overrides = store.get_all_app_overrides()
    rules = store.get_rules()

    # 1. Filter host apps: suppress docker-proxy and container relay wrapper processes
    # (e.g. wslrelay, com.docker.backend, vpnkit, rootlesskit) so we don't double-count docker listeners
    # or generate false-positive conflicts against Docker relays on Windows/macOS.
    filtered_host: List[Dict[str, Any]] = []
    for h in host_apps:
        p_name = h.get("process_name", "").lower()
        if any(r in p_name for r in ("docker-proxy", "wslrelay", "com.docker.backend", "vpnkit", "rootlesskit")):
            continue
        filtered_host.append(h)

    # 2. Add custom apps
    custom_apps: List[Dict[str, Any]] = []
    for ca in custom_apps_raw:
        app_id = ca["id"]
        # Format stable id if not already custom:
        if not app_id.startswith("custom:"):
            app_id = f"custom:{app_id}"

        # Resolve live status from background health poller if recorded;
        # with no snapshot the state is genuinely unknown, not healthy.
        custom_status = "unknown"
        latency_ms = 0.0
        if store and hasattr(store, "get_latest_health"):
            latest = store.get_latest_health(app_id)
            if latest:
                custom_status = "up" if latest.get("ok") else "down"
                latency_ms = float(latest.get("latency_ms", 0.0))

        custom_apps.append({
            "id": app_id,
            "source": "custom",
            "name": ca["name"],
            "process_name": ca["name"],
            "port": ca["port"],
            "host": ca.get("host", "localhost"),
            "proto": "tcp",
            "bind": "127.0.0.1" if ca.get("host") in ("localhost", "127.0.0.1") else "0.0.0.0",
            "status": custom_status,
            "latency_ms": latency_ms,
            "health_path": ca.get("health_path", "/health"),
            "health_interval": ca.get("health_interval", 30),
            "start_cmd": ca.get("start_cmd"),
            "stop_cmd": ca.get("stop_cmd"),
            "workdir": ca.get("workdir"),
            "log_file": ca.get("log_file"),
            "start_on_boot": ca.get("start_on_boot", False),
            "env": ca.get("env", {}),
            "update_cmd": ca.get("update_cmd"),
            "expected_status": ca.get("expected_status", "200,204,301,302"),
            "custom_headers": ca.get("custom_headers", {}),
            "cpu_percent": None,
            "ram_mb": None,
            "uptime_sec": None,
            "created_at": ca.get("created_at", time.time()),
        })

    # Combine all raw discovered apps
    all_raw = docker_apps + filtered_host + custom_apps

    # 3. Conflict Detection:
    # If two different apps claim the same host port on the same protocol with overlapping binds, mark conflict
    port_proto_to_apps: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    for app in all_raw:
        port = app.get("port", 0)
        if port <= 0:
            continue
        proto = app.get("proto", "tcp").lower()
        port_proto_to_apps.setdefault((port, proto), []).append(app)

    conflicts: List[Dict[str, Any]] = []
    conflicted_ids: Set[str] = set()

    for (port, proto), app_list in port_proto_to_apps.items():
        if len(app_list) > 1:
            unique_sources = set(a["id"] for a in app_list)
            if len(unique_sources) > 1:
                binds = [a.get("bind", "0.0.0.0") for a in app_list]
                has_wildcard = any(b in ("0.0.0.0", "::") for b in binds)
                has_duplicate_bind = len(binds) != len(set(binds))
                if has_wildcard or has_duplicate_bind:
                    conflicts.append({
                        "port": port,
                        "proto": proto,
                        "apps": [a["name"] for a in app_list],
                        "ids": list(unique_sources)
                    })
                    for a in app_list:
                        conflicted_ids.add(a["id"])

    # 4. Finalize Unified Apps List with Stored Overrides
    final_apps: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    for item in all_raw:
        app_id = item["id"]
        if app_id in seen_ids:
            continue
        seen_ids.add(app_id)

        # Merge stored overrides
        override = app_overrides.get(app_id, {})

        name = override.get("name") or item.get("label_name") or item.get("name") or "App"
        icon = override.get("icon") or item.get("label_icon") or ""
        tags = override.get("tags") or []
        notes = override.get("notes") or ""

        # Check explicit overrides vs label fallback
        if override.get("pinned") is not None:
            pinned = bool(override["pinned"])
        else:
            pinned = False

        if override.get("hidden") is not None:
            hidden = bool(override["hidden"])
        else:
            hidden = bool(item.get("hidden_by_label", False))

        sort_order = override.get("sort_order", 0)
        url_override = override.get("url_override") or item.get("label_url") or ""

        # Category resolution
        manual_category = override.get("category_id")
        if manual_category:
            category_id = manual_category
            category_mode = "manual"
        else:
            category_id = item.get("label_category") or categorize_app(item, rules)
            category_mode = "manual" if item.get("label_category") else "auto"

        # Status
        status = item.get("status", "unknown")
        if app_id in conflicted_ids:
            status = "conflict"

        # URL Construction
        port = item.get("port", 0)
        bind = item.get("bind", "127.0.0.1")
        has_custom_url = bool(url_override)
        if url_override:
            open_url = url_override
        else:
            if public_host:
                open_url = f"http://{public_host}:{port}" if port > 0 else ""
            elif bind in ("127.0.0.1", "0.0.0.0", "::", "::1", None, ""):
                open_url = f"http://localhost:{port}" if port > 0 else ""
            else:
                open_url = f"http://{bind}:{port}" if port > 0 else ""

        # Local only badge if bound strictly to 127.0.0.1
        local_only = (bind == "127.0.0.1")
        has_tls = bool(item.get("has_tls") or port in (443, 8443))

        final_app = {
            **item,
            "id": app_id,
            "name": name,
            "icon": icon,
            "category_id": category_id,
            "category_mode": category_mode,
            "tags": tags,
            "notes": notes,
            "pinned": pinned,
            "hidden": hidden,
            "sort_order": sort_order,
            "status": status,
            "open_url": open_url,
            "has_custom_url": has_custom_url,
            "local_only": local_only,
            "has_tls": has_tls,
            "tls_days_remaining": item.get("tls_days_remaining"),
            "tls_expired": item.get("tls_expired"),
        }
        final_apps.append(final_app)

    return final_apps, conflicts
