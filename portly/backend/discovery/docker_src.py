"""Docker container discovery and stats collection via docker-py."""

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

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


def get_docker_client(force_retry: bool = False) -> Optional[Any]:
    global _client, _client_init_attempted, _docker_available, _docker_error_msg, _last_init_attempt
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
        return _client
    except Exception as e:
        _docker_available = False
        _docker_error_msg = f"Docker daemon not reachable: {e}"
        _client = None
        return None


def is_docker_available() -> Tuple[bool, str]:
    get_docker_client()
    return _docker_available, _docker_error_msg


def set_on_docker_event(callback: Callable[[], None]):
    global _on_event_callback
    _on_event_callback = callback


def _start_event_listener():
    global _event_thread
    if _event_thread and _event_thread.is_alive():
        return

    def listener():
        global _client, _docker_available
        while _docker_available and _client:
            try:
                events_stream = _client.events(decode=True)
                has_event = False
                for event in events_stream:
                    has_event = True
                    if not isinstance(event, dict):
                        time.sleep(1)
                        break
                    action = event.get("Action", "")
                    # start, stop, die, destroy, restart, create
                    if action in ("start", "stop", "die", "destroy", "restart", "create"):
                        if _on_event_callback:
                            try:
                                _on_event_callback()
                            except Exception:
                                pass
                if not has_event:
                    time.sleep(1)
            except Exception:
                time.sleep(5)

    _event_thread = threading.Thread(target=listener, daemon=True, name="portly-docker-events")
    _event_thread.start()


def get_cached_container_stats(container_id: str) -> Dict[str, Any]:
    return _container_stats_cache.get(container_id, {
        "cpu_percent": 0.0,
        "memory_mb": 0.0,
        "memory_limit_mb": 0.0,
        "net_rx_mb": 0.0,
        "net_tx_mb": 0.0,
        "block_read_mb": 0.0,
        "block_write_mb": 0.0,
    })


def update_container_stats_cache(container_id: str, stats: Dict[str, Any]):
    """Updates the container resource metrics cache."""
    _container_stats_cache[container_id] = stats


def clear_container_stats_cache(container_id: Optional[str] = None):
    """Cleans up cached metrics for inactive or stopped containers."""
    if container_id:
        _container_stats_cache.pop(container_id, None)
    else:
        _container_stats_cache.clear()


def discover_docker_containers() -> List[Dict[str, Any]]:
    global _client, _docker_available
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

                # Portly label autodiscovery overrides
                label_name = labels.get("portly.name")
                label_icon = labels.get("portly.icon")
                label_category = labels.get("portly.category")
                label_url = labels.get("portly.url")
                label_hide = labels.get("portly.hide", "").lower() in ("true", "1", "yes")

                compose_project = labels.get("com.docker.compose.project", "")
                compose_service = labels.get("com.docker.compose.service", "")

                # Published port mappings: format container_port -> [{'HostIp': '0.0.0.0', 'HostPort': '5432'}]
                ports_dict = c.attrs.get("NetworkSettings", {}).get("Ports") or {}
                
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
                    found_ports = True
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
                            "created_at": created_at,
                        })

                # If container has no published ports (e.g. backend worker), still capture if desired, or skip port entry
                if not found_ports and status == "running":
                    # Capture unmapped container under port 0 for overview if needed
                    pass

            except Exception as e:
                logger.warning(f"Error inspecting container {c}: {e}")
    except Exception as e:
        logger.error(f"Error querying docker containers: {e}")
        _docker_available = False
        _client = None

    return results
