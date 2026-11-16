"""Port availability checks, suggestion, and port migration planning/execution."""

import logging
import socket
from typing import Any, Dict, List, Optional, Tuple

from portly.backend.discovery.docker_src import get_docker_client, is_docker_available
from portly.backend.discovery.host import discover_host_ports
from portly.backend.store import Store

logger = logging.getLogger("portly.ports")


def is_port_in_socket_table(port: int, host_ports: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, str]:
    """Checks whether the port is currently reported listening by psutil/netstat."""
    if host_ports is None:
        host_ports = discover_host_ports()
    for h in host_ports:
        if h["port"] == port:
            return True, f"In use by host process {h['name']} (PID {h['pid']})"
    return False, ""


def can_bind_port(port: int, bind_ip: str = "0.0.0.0") -> Tuple[bool, str]:
    """Attempts to bind a socket to test availability directly on the OS."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((bind_ip, port))
        s.listen(1)
        return True, ""
    except socket.error as e:
        return False, f"Port {port} cannot be bound on {bind_ip}: {e}"
    finally:
        try:
            s.close()
        except Exception:
            pass


def check_port_availability(port: int, bind_ip: str = "0.0.0.0") -> Dict[str, Any]:
    """
    Comprehensive availability check:
    1. Direct socket bind attempt
    2. Host listening socket table check
    3. Docker container port mapping check
    """
    if port < 1 or port > 65535:
        return {"free": False, "used_by": "Invalid port number (must be 1-65535)"}

    # 1. Bind check
    can_bind, bind_err = can_bind_port(port, bind_ip)
    if not can_bind:
        return {"free": False, "used_by": bind_err}

    # 2. Host socket check
    in_table, table_err = is_port_in_socket_table(port)
    if in_table:
        return {"free": False, "used_by": table_err}

    # 3. Docker check if docker is available
    docker_avail, _ = is_docker_available()
    if docker_avail:
        try:
            client = get_docker_client()
            if client:
                for c in client.containers.list(all=True):
                    ports = c.attrs.get("NetworkSettings", {}).get("Ports") or {}
                    for _, host_maps in ports.items():
                        if not host_maps:
                            continue
                        for m in host_maps:
                            try:
                                if int(m.get("HostPort", 0)) == port:
                                    return {"free": False, "used_by": f"Claimed by container '{c.name}'"}
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass

    return {"free": True, "used_by": ""}


def suggest_free_ports(start_port: int = 3000, count: int = 5, bind_ip: str = "0.0.0.0") -> List[int]:
    """Scans and returns the next N free ports efficiently without looping system discovery."""
    free_ports: List[int] = []
    current = max(1024, start_port)
    host_listeners = discover_host_ports()
    used_ports = {h["port"] for h in host_listeners}

    # Query Docker mapped ports once if available
    docker_avail, _ = is_docker_available()
    if docker_avail:
        try:
            client = get_docker_client()
            if client:
                for c in client.containers.list(all=True):
                    ports = c.attrs.get("NetworkSettings", {}).get("Ports") or {}
                    for _, host_maps in ports.items():
                        if not host_maps:
                            continue
                        for m in host_maps:
                            try:
                                hp = int(m.get("HostPort", 0))
                                if hp > 0:
                                    used_ports.add(hp)
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass

    while len(free_ports) < count and current < 65535:
        if current not in used_ports:
            can_bind, _ = can_bind_port(current, bind_ip)
            if can_bind:
                free_ports.append(current)
        current += 1

    return free_ports


def plan_port_change(app_id: str, new_port: int, bind: str, store: Store) -> Dict[str, Any]:
    """
    Creates a dry-run plan for changing an app's port.
    Returns details of actions that will be performed.
    """
    avail = check_port_availability(new_port, bind)
    if not avail["free"]:
        return {
            "valid": False,
            "error": f"Port {new_port} is not free: {avail['used_by']}",
            "plan": None,
        }

    if app_id.startswith("docker:"):
        # Docker container port change plan
        client = get_docker_client()
        if not client:
            return {"valid": False, "error": "Docker is not available.", "plan": None}

        # Parse docker id: docker:<container_name>:<container_port>/<proto>
        parts = app_id.split(":")
        container_name = parts[1] if len(parts) > 1 else ""
        c_port_proto = parts[2] if len(parts) > 2 else ""

        try:
            container = client.containers.get(container_name)
        except Exception as e:
            return {"valid": False, "error": f"Container not found: {e}", "plan": None}

        plan = {
            "type": "docker",
            "app_id": app_id,
            "container_name": container.name,
            "image": container.attrs.get("Config", {}).get("Image", ""),
            "target_container_port": c_port_proto,
            "new_host_port": new_port,
            "bind": bind,
            "steps": [
                f"Inspect container '{container.name}' configuration",
                f"Take snapshot of current container settings for rollback",
                f"Stop container '{container.name}'",
                f"Remove container '{container.name}'",
                f"Recreate container '{container.name}' with new host port mapping {bind}:{new_port}->{c_port_proto}",
                f"Wait for container start and verify health",
            ],
            "estimated_downtime": "2-3 seconds",
            "rollback_supported": True,
        }
        return {"valid": True, "error": "", "plan": plan}

    elif app_id.startswith("custom:"):
        custom_app = store.get_custom_app(app_id.replace("custom:", ""))
        if not custom_app:
            return {"valid": False, "error": "Custom app not found.", "plan": None}

        plan = {
            "type": "custom",
            "app_id": app_id,
            "name": custom_app["name"],
            "old_port": custom_app["port"],
            "new_port": new_port,
            "bind": bind,
            "steps": [
                f"Stop running process for '{custom_app['name']}' if active",
                f"Update port to {new_port} with PORT={new_port} in environment",
                f"Execute start command with new port configuration",
                f"Verify health check at http://{custom_app.get('host', 'localhost')}:{new_port}{custom_app.get('health_path', '')}",
            ],
            "estimated_downtime": "1-2 seconds",
            "rollback_supported": True,
        }
        return {"valid": True, "error": "", "plan": plan}

    else:
        return {
            "valid": False,
            "error": "Portly can only change ports of Docker containers and Portly-managed Custom apps. For unmanaged host processes, consider adopting as a Custom app.",
            "plan": None,
        }
