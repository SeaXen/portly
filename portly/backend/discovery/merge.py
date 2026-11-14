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

    # Set of ports claimed by Docker containers
    docker_ports: Set[int] = set()
    for d_app in docker_apps:
        docker_ports.add(d_app["port"])

    # 1. Deduplicate host apps vs Docker (suppress raw host process if docker publishes that port)
    filtered_host: List[Dict[str, Any]] = []
    for h in host_apps:
        p_name = h.get("process_name", "").lower()
        port = h["port"]
        # If docker-proxy owns it, or docker container maps this host port, suppress raw host process
        if port in docker_ports or "docker-proxy" in p_name:
            continue
        filtered_host.append(h)

    # 2. Add custom apps
    custom_apps: List[Dict[str, Any]] = []
    for ca in custom_apps_raw:
        app_id = ca["id"]
        # Format stable id if not already custom:
        if not app_id.startswith("custom:"):
            app_id = f"custom:{app_id}"

        custom_apps.append({
            "id": app_id,
            "source": "custom",
            "name": ca["name"],
            "process_name": ca["name"],
            "port": ca["port"],
            "host": ca.get("host", "localhost"),
            "proto": "tcp",
            "bind": "127.0.0.1" if ca.get("host") in ("localhost", "127.0.0.1") else "0.0.0.0",
            "status": "up",  # health checker updates this
            "health_path": ca.get("health_path", "/health"),
            "health_interval": ca.get("health_interval", 30),
            "start_cmd": ca.get("start_cmd"),
            "stop_cmd": ca.get("stop_cmd"),
            "workdir": ca.get("workdir"),
            "log_file": ca.get("log_file"),
            "start_on_boot": ca.get("start_on_boot", False),
            "env": ca.get("env", {}),
            "update_cmd": ca.get("update_cmd"),
            "cpu_percent": 0.0,
            "ram_mb": 0.0,
            "uptime_sec": 0,
            "created_at": ca.get("created_at", time.time()),
        })

    # Combine all
    all_raw = docker_apps + filtered_host + custom_apps

    # 3. Conflict Detection:
    # If two different apps claim the same host port, mark both conflict
    port_to_apps: Dict[int, List[Dict[str, Any]]] = {}
    for app in all_raw:
        port = app["port"]
        if port <= 0:
            continue
        port_to_apps.setdefault(port, []).append(app)

    conflicts: List[Dict[str, Any]] = []
    conflicted_ids: Set[str] = set()

    for port, app_list in port_to_apps.items():
        if len(app_list) > 1:
            # Check if they are truly different (not duplicate IPv4/IPv6 of same container)
            unique_sources = set(a["id"] for a in app_list)
            if len(unique_sources) > 1:
                conflicts.append({
                    "port": port,
                    "apps": [a["name"] for a in app_list],
                    "ids": list(unique_sources)
                })
                for a in app_list:
                    conflicted_ids.add(a["id"])

    # 4. Finalize Unified Apps List
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
        pinned = bool(override.get("pinned", False))
        hidden = bool(override.get("hidden", item.get("hidden_by_label", False)))
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
        status = item.get("status", "up")
        if app_id in conflicted_ids:
            status = "conflict"

        # URL Construction
        port = item.get("port", 0)
        bind = item.get("bind", "127.0.0.1")
        if url_override:
            open_url = url_override
        else:
            host_for_url = public_host if public_host else ("localhost" if bind == "127.0.0.1" else "localhost")
            open_url = f"http://{host_for_url}:{port}" if port > 0 else ""

        # Local only badge if bound strictly to 127.0.0.1
        local_only = (bind == "127.0.0.1")

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
            "local_only": local_only,
        }
        final_apps.append(final_app)

    return final_apps, conflicts
