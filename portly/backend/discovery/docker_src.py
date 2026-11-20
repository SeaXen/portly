"""Docker container discovery and stats collection via docker-py."""

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import psutil

logger = logging.getLogger("portly.docker")

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None
    DockerException = Exception

_client: Optional[Any] = None
_client_init_attempted = False
_docker_available = False
_docker_error_msg = ""
_last_init_attempt: float = 0.0
_container_stats_cache: Dict[str, Dict[str, Any]] = {}
_on_event_callback: Optional[Callable[[], None]] = None
_event_thread: Optional[threading.Thread] = None
_stats_thread: Optional[threading.Thread] = None
_client_lock = threading.Lock()
_debounce_timer: Optional[threading.Timer] = None
_debounce_lock = threading.Lock()
_last_good_containers: List[Dict[str, Any]] = []
_last_good_ts: float = 0.0


def get_docker_client(force_retry: bool = False) -> Optional[Any]:
    global _client, _client_init_attempted, _docker_available, _docker_error_msg, _last_init_attempt
    with _client_lock:
        now = time.time()

        if _docker_available and _client is not None and not force_retry:
            return _client

        if _client_init_attempted and not force_retry and (now - _last_init_attempt < 4.0):
            return None

        _last_init_attempt = now
        _client_init_attempted = True

        if docker is None:
            _docker_available = False
            _docker_error_msg = "Python docker package is not installed."
            return None

        try:
            # Check standard env or socket
            _client = docker.from_env(timeout=3)
            _client.ping()
            _docker_available = True
            _docker_error_msg = ""
            _start_event_listener()
            _start_stats_collector()
            return _client
        except Exception as e:
            _docker_available = False
            _docker_error_msg = f"Docker daemon not reachable: {e}"
            _client = None
            return None


def is_docker_available() -> Tuple[bool, str]:
    # Non-blocking after first init: report cached state so async routes never
    # stall on a slow/dead daemon. Retries happen in discovery (executor).
    if not _client_init_attempted:
        get_docker_client()
    return _docker_available, _docker_error_msg


def _dispatch_debounced_event():
    if _on_event_callback:
        try:
            _on_event_callback()
        except Exception as e:
            logger.warning(f"Error executing docker event callback: {e}")


def _trigger_event():
    global _debounce_timer
    with _debounce_lock:
        if _debounce_timer:
            _debounce_timer.cancel()
        _debounce_timer = threading.Timer(0.5, _dispatch_debounced_event)
        _debounce_timer.daemon = True
        _debounce_timer.start()


def set_on_docker_event(callback: Callable[[], None]):
    global _on_event_callback
    _on_event_callback = callback


def _start_event_listener():
    global _event_thread
    if os.getenv("PORTLY_TESTING") == "1":
        return
    if _event_thread and _event_thread.is_alive():
        return

    def listener():
        global _client, _docker_available
        while _docker_available and _client:
            try:
                events_stream = _client.events(decode=True)
                for event in events_stream:
                    if not isinstance(event, dict):
                        time.sleep(1)
                        break
                    action = event.get("Action", "")
                    # start, stop, die, destroy, restart, create, pause, unpause
                    if action in ("start", "stop", "die", "destroy", "restart", "create", "pause", "unpause"):
                        _trigger_event()
            except Exception:
                time.sleep(5)

    _event_thread = threading.Thread(target=listener, daemon=True, name="portly-docker-events")
    _event_thread.start()


def _calculate_cpu_percent(d: Dict[str, Any]) -> float:
    try:
        cpu_stats = d.get("cpu_stats", {})
        cpu_usage = cpu_stats.get("cpu_usage", {})
        # cgroup v2 has no percpu_usage; online_cpus is the reliable core count there.
        cpu_count = cpu_stats.get("online_cpus") or len(cpu_usage.get("percpu_usage", [])) or psutil.cpu_count() or 1
        cpu_delta = float(cpu_usage.get("total_usage", 0)) - \
                    float(d.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0))
        system_delta = float(cpu_stats.get("system_cpu_usage", 0)) - \
                       float(d.get("precpu_stats", {}).get("system_cpu_usage", 0))

        if system_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
            return round(max(0.0, cpu_percent), 1)
    except Exception:
        pass
    return 0.0


_STATS_MAX_WORKERS = 8


def _refresh_container_stats(c: Any) -> str:
    """Fetch and cache resource stats for one container; returns its short id (or "" on error)."""
    try:
        c_id = c.id[:12]
    except Exception:
        return ""
    try:
        raw_stats = c.stats(stream=False)
        cpu_pct = _calculate_cpu_percent(raw_stats)
        mem_stats = raw_stats.get("memory_stats", {})
        mem_usage = mem_stats.get("usage", 0)
        mem_detail = mem_stats.get("stats", {})
        # cgroup v2 uses inactive_file, v1 uses cache — subtract reclaimable page cache
        mem_cache = mem_detail.get("inactive_file", mem_detail.get("total_inactive_file", mem_detail.get("cache", 0)))
        actual_mem = max(0, mem_usage - mem_cache)
        mem_mb = round(actual_mem / (1024 * 1024), 1)
        mem_limit_mb = round(mem_stats.get("limit", 0) / (1024 * 1024), 1)

        rx_bytes = 0
        tx_bytes = 0
        for net_if in raw_stats.get("networks", {}).values():
            rx_bytes += net_if.get("rx_bytes", 0)
            tx_bytes += net_if.get("tx_bytes", 0)

        blk_read = 0
        blk_write = 0
        io_stats = raw_stats.get("blkio_stats", {}).get("io_service_bytes_recursive") or []
        for entry in io_stats:
            op = entry.get("op", "").lower()
            val = entry.get("value", 0)
            if op == "read":
                blk_read += val
            elif op == "write":
                blk_write += val

        update_container_stats_cache(c_id, {
            "cpu_percent": cpu_pct,
            "memory_mb": mem_mb,
            "memory_limit_mb": mem_limit_mb,
            "net_rx_mb": round(rx_bytes / (1024 * 1024), 2),
            "net_tx_mb": round(tx_bytes / (1024 * 1024), 2),
            "block_read_mb": round(blk_read / (1024 * 1024), 2),
            "block_write_mb": round(blk_write / (1024 * 1024), 2),
        })
    except Exception:
        pass
    return c_id


def _collect_running_container_stats(containers: List[Any]) -> Set[str]:
    """Fetch stats for all containers in a bounded thread pool; returns the ids that were seen."""
    active_ids: Set[str] = set()
    with ThreadPoolExecutor(max_workers=_STATS_MAX_WORKERS) as executor:
        for c_id in executor.map(_refresh_container_stats, containers):
            active_ids.add(c_id)
    return active_ids


def _start_stats_collector():
    """Background task to periodically collect real CPU, memory, and IO metrics for running containers."""
    global _stats_thread
    if os.getenv("PORTLY_TESTING") == "1":
        return
    if _stats_thread and _stats_thread.is_alive():
        return

    def stats_worker():
        global _client, _docker_available
        while True:
            if not _docker_available or not _client:
                time.sleep(5)
                continue
            try:
                running_containers = _client.containers.list(filters={"status": "running"})
                active_ids = _collect_running_container_stats(running_containers)
                # Purge inactive containers from cache
                for cid in list(_container_stats_cache.keys()):
                    if cid not in active_ids:
                        clear_container_stats_cache(cid)
            except Exception:
                pass
            time.sleep(4)

    _stats_thread = threading.Thread(target=stats_worker, daemon=True, name="portly-docker-stats")
    _stats_thread.start()


def get_cached_container_stats(container_id: str) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "cpu_percent": 0.0,
        "memory_mb": 0.0,
        "memory_limit_mb": 0.0,
        "net_rx_mb": 0.0,
        "net_tx_mb": 0.0,
        "block_read_mb": 0.0,
        "block_write_mb": 0.0,
    }
    cached = _container_stats_cache.get(container_id)
    if not cached:
        defaults["stats_age_sec"] = None
        return defaults
    result = dict(cached)
    ts = cached.get("ts")
    result["stats_age_sec"] = round(time.time() - ts, 1) if ts else None
    return result


def update_container_stats_cache(container_id: str, stats: Dict[str, Any]):
    """Updates the container resource metrics cache, stamping it with the collection time."""
    entry = dict(stats)
    entry["ts"] = time.time()
    _container_stats_cache[container_id] = entry


def clear_container_stats_cache(container_id: Optional[str] = None):
    """Cleans up cached metrics for inactive or stopped containers."""
    if container_id:
        _container_stats_cache.pop(container_id, None)
    else:
        _container_stats_cache.clear()


def discover_docker_containers() -> List[Dict[str, Any]]:
    global _client, _docker_available, _last_good_containers, _last_good_ts
    client = get_docker_client()
    if not client or not _docker_available:
        return []

    results: List[Dict[str, Any]] = []
    try:
        containers = client.containers.list(all=True)
        for c in containers:
            try:
                c_id = c.id[:12]
                name = c.name.lstrip("/")
                status = c.status.lower()  # running, exited, paused, restarting
                image_tag = (c.image.tags[0] if c.image and c.image.tags else c.attrs.get("Config", {}).get("Image", "unknown"))
                labels = c.labels or {}

                label_name = labels.get("portly.name")
                label_icon = labels.get("portly.icon")
                label_category = labels.get("portly.category")
                label_url = labels.get("portly.url")
                label_hide = labels.get("portly.hide", "").lower() in ("true", "1", "yes")

                compose_project = labels.get("com.docker.compose.project", "")
                compose_service = labels.get("com.docker.compose.service", "")

                # Published port mappings: format container_port -> [{'HostIp': '0.0.0.0', 'HostPort': '5432'}]
                ports_dict = c.attrs.get("NetworkSettings", {}).get("Ports") or {}
                # If stopped or NetworkSettings.Ports is empty, fallback to HostConfig.PortBindings
                if not ports_dict or not any(ports_dict.values()):
                    host_bindings = c.attrs.get("HostConfig", {}).get("PortBindings") or {}
                    if host_bindings:
                        ports_dict = host_bindings

                # Check health status
                health_status = "unknown"
                state_dict = c.attrs.get("State", {})
                if "Health" in state_dict:
                    health_status = state_dict["Health"].get("Status", "unknown")

                created_at = c.attrs.get("Created", "")
                
                # Stats calculation
                stats = get_cached_container_stats(c_id)

                # Process port mappings
                found_ports = False
                for c_port_proto, host_mappings in ports_dict.items():
                    if not host_mappings:
                        continue
                    # c_port_proto is e.g. "5432/tcp"
                    c_port_str, proto = c_port_proto.split("/") if "/" in c_port_proto else (c_port_proto, "tcp")
                    try:
                        c_port = int(c_port_str)
                    except ValueError:
                        c_port = 0

                    for m in host_mappings:
                        host_ip = m.get("HostIp", "0.0.0.0")
                        host_port_str = m.get("HostPort", "0")
                        try:
                            host_port = int(host_port_str)
                        except ValueError:
                            host_port = 0

                        if host_port == 0:
                            continue

                        found_ports = True

                        # Normalize bind
                        bind = host_ip
                        if bind in ("::", "0.0.0.0", ""):
                            bind = "0.0.0.0"
                        elif bind in ("127.0.0.1", "::1", "localhost"):
                            bind = "127.0.0.1"

                        stable_id = f"docker:{name}:{c_port}/{proto}"

                        results.append({
                            "id": stable_id,
                            "source": "docker",
                            "name": label_name or name,
                            "container_name": name,
                            "container_id": c_id,
                            "image": image_tag,
                            "port": host_port,
                            "container_port": c_port,
                            "proto": proto,
                            "bind": bind,
                            "status": "up" if status == "running" else "down",
                            "health": health_status,
                            "docker_state": status,
                            "compose_project": compose_project,
                            "compose_service": compose_service,
                            "labels": labels,
                            "label_icon": label_icon,
                            "label_category": label_category,
                            "label_url": label_url,
                            "hidden_by_label": label_hide,
                            "cpu_percent": stats.get("cpu_percent", 0.0),
                            "ram_mb": stats.get("memory_mb", 0.0),
                            "ram_limit_mb": stats.get("memory_limit_mb", 0.0),
                            "net_rx_mb": stats.get("net_rx_mb", 0.0),
                            "net_tx_mb": stats.get("net_tx_mb", 0.0),
                            "block_read_mb": stats.get("block_read_mb", 0.0),
                            "block_write_mb": stats.get("block_write_mb", 0.0),
                            "stats_age_sec": stats.get("stats_age_sec"),
                            "created_at": created_at,
                        })

                # If container has no published ports, still list it under port 0 so it can be managed & monitored
                if not found_ports:
                    results.append({
                        "id": f"docker:{name}:0/tcp",
                        "source": "docker",
                        "name": label_name or name,
                        "container_name": name,
                        "container_id": c_id,
                        "image": image_tag,
                        "port": 0,
                        "container_port": 0,
                        "proto": "tcp",
                        "bind": "none",
                        "status": "up" if status == "running" else "down",
                        "health": health_status,
                        "docker_state": status,
                        "compose_project": compose_project,
                        "compose_service": compose_service,
                        "labels": labels,
                        "label_icon": label_icon,
                        "label_category": label_category,
                        "label_url": label_url,
                        "hidden_by_label": label_hide,
                        "cpu_percent": stats.get("cpu_percent", 0.0),
                        "ram_mb": stats.get("memory_mb", 0.0),
                        "ram_limit_mb": stats.get("memory_limit_mb", 0.0),
                        "net_rx_mb": stats.get("net_rx_mb", 0.0),
                        "net_tx_mb": stats.get("net_tx_mb", 0.0),
                        "block_read_mb": stats.get("block_read_mb", 0.0),
                        "block_write_mb": stats.get("block_write_mb", 0.0),
                        "stats_age_sec": stats.get("stats_age_sec"),
                        "created_at": created_at,
                    })

            except Exception as e:
                logger.warning(f"Error inspecting container {c}: {e}")
    except Exception as e:
        logger.error(f"Error querying docker containers: {e}")
        # Transient daemon hiccup: serve the last good inventory briefly instead
        # of firing port_closed for every container (empty UI + alert spam).
        if _last_good_containers and (time.time() - _last_good_ts) < 120.0:
            return _last_good_containers
        _docker_available = False
        _client = None

    if results:
        _last_good_containers = results
        _last_good_ts = time.time()
    return results
