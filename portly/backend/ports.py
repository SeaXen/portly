"""Port availability checks, suggestion, migration planning, and pre-flight collision analysis."""

import errno
import ipaddress
import logging
import platform
import re
import socket
from typing import Any, Dict, List, Optional, Tuple

from portly.backend.discovery.docker_src import get_docker_client, is_docker_available
from portly.backend.discovery.host import discover_host_ports
from portly.backend.store import Store

logger = logging.getLogger("portly.ports")


def _normalize_and_validate_bind(bind_ip: str) -> Tuple[bool, bool, str]:
    """
    Validates bind address.
    Returns (is_valid, is_ipv6, normalized_ip_str).
    """
    if not bind_ip or bind_ip.strip() in ("0.0.0.0", ""):
        return True, False, "0.0.0.0"
    if bind_ip.strip() in ("::", "[::]"):
        return True, True, "::"
    if bind_ip.strip() in ("localhost", "127.0.0.1"):
        return True, False, "127.0.0.1"
    if bind_ip.strip() in ("::1", "[::1]"):
        return True, True, "::1"

    cleaned = bind_ip.strip().strip("[]")
    try:
        ip = ipaddress.ip_address(cleaned)
        return True, (ip.version == 6), cleaned
    except ValueError:
        return False, False, bind_ip


def is_port_in_socket_table(port: int, host_ports: Optional[List[Dict[str, Any]]] = None, proto: str = "tcp") -> Tuple[bool, str]:
    """Checks whether the port is currently reported listening by psutil/netstat."""
    if host_ports is None:
        host_ports = discover_host_ports()
    target_proto = proto.lower()
    for h in host_ports:
        if h["port"] == port and h.get("proto", "tcp").lower() == target_proto:
            return True, f"In use by host process {h['name']} (PID {h['pid']})"
    return False, ""


def can_bind_port(port: int, bind_ip: str = "0.0.0.0", proto: str = "tcp") -> Tuple[bool, str]:
    """
    Attempts to bind a socket to test OS-level port availability.
    Handles Windows exclusive bind rules, IPv6, UDP, and permission errors.
    """
    valid, is_v6, norm_ip = _normalize_and_validate_bind(bind_ip)
    if not valid:
        return False, f"Invalid bind IP address '{bind_ip}': address cannot be bound"

    family = socket.AF_INET6 if is_v6 else socket.AF_INET
    sock_type = socket.SOCK_DGRAM if proto.lower() == "udp" else socket.SOCK_STREAM

    s = socket.socket(family, sock_type)

    # On Windows, SO_REUSEADDR allows multiple processes to bind same port (false negative).
    # SO_EXCLUSIVEADDRUSE prevents stealing / false positives.
    if platform.system() == "Windows":
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        except Exception:
            pass
    else:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass

    try:
        s.bind((norm_ip, port))
        if proto.lower() == "tcp":
            s.listen(1)
        return True, ""
    except (socket.error, OverflowError, ValueError) as e:
        err_code = getattr(e, "errno", None)
        if err_code in (errno.EACCES, getattr(errno, "WSAEACCES", 10013)):
            if port < 1024:
                return False, f"Permission denied on privileged port {port} (< 1024). Elevation required to bind."
            return False, f"Permission denied on port {port}: {e}"
        if err_code in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048)):
            return False, f"Port {port} ({proto.upper()}) is already bound on {norm_ip}"
        return False, f"Port {port} cannot be bound on {norm_ip}: {e}"
    finally:
        try:
            s.close()
        except Exception:
            pass


def check_port_availability(port: int, bind_ip: str = "0.0.0.0", proto: str = "tcp", store: Optional[Any] = None) -> Dict[str, Any]:
    """
    Comprehensive availability check:
    0. Active port reservation check
    1. Direct socket bind attempt (respecting proto, ipv4/v6, Windows exclusive rules)
    2. Host listening socket table check
    3. Docker container port mapping check (including stopped containers via HostConfig)
    """
    if port < 1 or port > 65535:
        return {"free": False, "available": False, "used_by": "Invalid port number (must be 1-65535)"}

    # 0. Active port reservation check
    if store is not None and hasattr(store, "get_port_reservations"):
        try:
            for r in store.get_port_reservations():
                if r["port"] == port and r.get("proto", "tcp").lower() == proto.lower():
                    return {
                        "free": False,
                        "available": False,
                        "used_by": f"Reserved for '{r['name']}' ({r.get('service') or 'Intent Registry'})",
                        "reserved": True,
                        "reservation": r,
                    }
        except Exception:
            pass

    # 1. Bind check
    can_bind, bind_err = can_bind_port(port, bind_ip, proto=proto)
    if not can_bind:
        return {"free": False, "available": False, "used_by": bind_err}

    # 2. Host socket check
    in_table, table_err = is_port_in_socket_table(port, proto=proto)
    if in_table:
        return {"free": False, "available": False, "used_by": table_err}

    # 3. Docker check across running and stopped containers
    docker_avail, _ = is_docker_available()
    if docker_avail:
        try:
            client = get_docker_client()
            if client:
                for c in client.containers.list(all=True):
                    # Check NetworkSettings first, fallback to HostConfig.PortBindings for stopped
                    ports = c.attrs.get("NetworkSettings", {}).get("Ports") or {}
                    if not ports or not any(ports.values()):
                        ports = c.attrs.get("HostConfig", {}).get("PortBindings") or {}

                    for c_spec, host_maps in ports.items():
                        if not host_maps:
                            continue
                        spec_proto = c_spec.split("/")[1] if "/" in c_spec else "tcp"
                        if spec_proto.lower() != proto.lower():
                            continue
                        for m in host_maps:
                            try:
                                if int(m.get("HostPort", 0)) == port:
                                    status_note = " (stopped)" if c.status.lower() != "running" else ""
                                    return {"free": False, "available": False, "used_by": f"Claimed by container '{c.name}'{status_note}"}
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass

    return {"free": True, "available": True, "used_by": ""}


def suggest_free_ports(start_port: int = 3000, count: int = 5, bind_ip: str = "0.0.0.0", proto: str = "tcp", store: Optional[Any] = None) -> List[int]:
    """Scans and returns the next N free ports efficiently without repetitive heavy queries."""
    free_ports: List[int] = []
    current = max(1024, start_port)
    host_listeners = discover_host_ports()
    target_proto = proto.lower()
    used_ports = {h["port"] for h in host_listeners if h.get("proto", "tcp").lower() == target_proto}

    # Reserved ports are not free even when nothing is listening yet.
    if store is not None and hasattr(store, "get_port_reservations"):
        try:
            used_ports |= {r["port"] for r in store.get_port_reservations() if r.get("proto", "tcp").lower() == target_proto}
        except Exception:
            pass

    # Query Docker mapped ports once if available
    docker_avail, _ = is_docker_available()
    if docker_avail:
        try:
            client = get_docker_client()
            if client:
                for c in client.containers.list(all=True):
                    ports = c.attrs.get("NetworkSettings", {}).get("Ports") or {}
                    if not ports or not any(ports.values()):
                        ports = c.attrs.get("HostConfig", {}).get("PortBindings") or {}

                    for c_spec, host_maps in ports.items():
                        if not host_maps:
                            continue
                        spec_proto = c_spec.split("/")[1] if "/" in c_spec else "tcp"
                        if spec_proto.lower() != target_proto:
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
            can_bind, _ = can_bind_port(current, bind_ip, proto=proto)
            if can_bind:
                free_ports.append(current)
        current += 1

    return free_ports


def check_preflight_collisions(
    compose_or_run_text: str = "",
    compose_content: Optional[str] = None,
    command: Optional[str] = None,
    ports: Optional[List[int]] = None,
    store: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Pre-flight port collision detector:
    Parses docker-compose or docker run commands, extracts desired published ports,
    tests for collisions, and suggests free alternatives.
    """
    text_to_parse = command or compose_content or compose_or_run_text or ""
    extracted_ports: List[Dict[str, Any]] = []

    # If explicit ports list was provided
    if ports:
        for p in ports:
            extracted_ports.append({
                "host_port": p,
                "container_port": p,
                "bind": "0.0.0.0",
                "proto": "tcp",
            })

    # 1. Check docker run pattern: -p 8080:80 or -p 127.0.0.1:8080:80/udp
    run_matches = re.findall(r'(?:-p|--publish)\s+(?:["\']?)([0-9a-zA-Z\.\:\/]+)(?:["\']?)', text_to_parse)
    for m in run_matches:
        parts = m.split(":")
        proto = "tcp"
        if "/" in parts[-1]:
            proto = parts[-1].split("/")[1]

        bind = "0.0.0.0"
        host_port = 0
        container_port = 0
        if len(parts) == 3:
            bind = parts[0]
            try:
                host_port = int(parts[1])
                container_port = int(parts[2].split("/")[0])
            except ValueError:
                continue
        elif len(parts) == 2:
            try:
                host_port = int(parts[0])
                container_port = int(parts[1].split("/")[0])
            except ValueError:
                continue
        elif len(parts) == 1:
            try:
                host_port = int(parts[0].split("/")[0])
                container_port = host_port
            except ValueError:
                continue

        if host_port > 0:
            extracted_ports.append({
                "host_port": host_port,
                "container_port": container_port,
                "bind": bind,
                "proto": proto,
            })

    # 2. Check compose ports yaml pattern: "8080:80" or "127.0.0.1:8080:80"
    yaml_matches = re.findall(r'-\s+["\']?([0-9\.\:]+(?:\/(?:tcp|udp))?)["\']?', text_to_parse)
    for ym in yaml_matches:
        if ":" in ym:
            parts = ym.split(":")
            proto = "tcp"
            if "/" in parts[-1]:
                proto = parts[-1].split("/")[1]
            try:
                if len(parts) == 3:
                    bind = parts[0]
                    hp = int(parts[1])
                    cp = int(parts[2].split("/")[0])
                else:
                    bind = "0.0.0.0"
                    hp = int(parts[0])
                    cp = int(parts[1].split("/")[0])
                if not any(ep["host_port"] == hp and ep["proto"] == proto for ep in extracted_ports):
                    extracted_ports.append({
                        "host_port": hp,
                        "container_port": cp,
                        "bind": bind,
                        "proto": proto,
                    })
            except ValueError:
                pass

    results = []
    has_conflicts = False

    for req in extracted_ports:
        port = req["host_port"]
        bind = req["bind"]
        proto = req["proto"]
        avail = check_port_availability(port, bind, proto=proto, store=store)
        is_free = avail["free"]
        suggestion = None
        if not is_free:
            has_conflicts = True
            sug = suggest_free_ports(start_port=port + 1, count=1, bind_ip=bind, proto=proto)
            suggestion = sug[0] if sug else None

        results.append({
            "requested_port": port,
            "container_port": req["container_port"],
            "bind": bind,
            "proto": proto,
            "available": is_free,
            "conflict_reason": avail.get("used_by", ""),
            "suggested_port": suggestion,
            "reserved": avail.get("reserved", False),
        })

    collisions = [
        {
            "port": d["requested_port"],
            "proto": d["proto"],
            "bind": d["bind"],
            "conflict_with": d["conflict_reason"],
            "conflict_type": "reservation_conflict" if d.get("reserved") else "port_in_use",
            "service_name": d["conflict_reason"],
            "owner": d["conflict_reason"],
            "source": "reservation" if d.get("reserved") else "host",
        }
        for d in results
        if not d["available"]
    ]

    return {
        "ports_found": len(extracted_ports),
        "has_conflicts": has_conflicts,
        "has_collision": has_conflicts,
        "valid": not has_conflicts,
        "collisions": collisions,
        "ports": [
            {"port": d["requested_port"], "proto": d["proto"], "bind": d["bind"]}
            for d in results
        ],
        "checked_ports": [d["requested_port"] for d in results],
        "details": results,
        "summary": f"{len(results)} ports checked, {len(collisions)} collision(s)",
    }


def plan_port_change(app_id: str, new_port: int, bind: str, store: Store) -> Dict[str, Any]:
    """
    Creates a dry-run plan for changing an app's port.
    Returns details of actions that will be performed matching the exact non-destructive recreate procedure.
    """
    avail = check_port_availability(new_port, bind, store=store)
    if not avail["free"]:
        return {
            "valid": False,
            "error": f"Port {new_port} is not free: {avail['used_by']}",
            "plan": None,
        }

    if app_id.startswith("docker:"):
        client = get_docker_client()
        if not client:
            return {"valid": False, "error": "Docker is not available.", "plan": None}

        parts = app_id.split(":")
        container_name = parts[1] if len(parts) > 1 else ""
        c_port_proto = parts[2] if len(parts) > 2 else ""
        if c_port_proto.split("/")[0] in ("0", ""):
            return {
                "valid": False,
                "error": "This container has no published port to remap. Add a port mapping when deploying it first.",
                "plan": None,
            }

        try:
            container = client.containers.get(container_name)
        except Exception as e:
            return {"valid": False, "error": f"Container not found: {e}", "plan": None}

        host_cfg = container.attrs.get("HostConfig", {})
        if host_cfg.get("NetworkMode") == "host":
            return {
                "valid": False,
                "error": f"Container '{container.name}' uses host networking mode. Port mappings are managed on the host directly and cannot be remapped in Docker.",
                "plan": None
            }

        plan = {
            "type": "docker",
            "app_id": app_id,
            "container_name": container.name,
            "image": container.attrs.get("Config", {}).get("Image", ""),
            "target_container_port": c_port_proto,
            "new_host_port": new_port,
            "bind": bind,
            "steps": [
                f"Inspect container '{container.name}' and save snapshot of HostConfig, volumes, env, and network bindings",
                f"Gracefully stop container '{container.name}' and rename to temporary backup '{container.name}_portly_bak_...'",
                f"Create and start new container '{container.name}' with new host port mapping {bind}:{new_port}->{c_port_proto}",
                f"Verify new container is running, reports healthy, and port responds",
                f"Automatically rollback on any failure; remove temporary backup container only after verification succeeds",
            ],
            "estimated_downtime": "1-3 seconds",
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
            "rollback_supported": False,
        }
        return {"valid": True, "error": "", "plan": plan}

    else:
        return {
            "valid": False,
            "error": "Portly can only change ports of Docker containers and Portly-managed Custom apps. For unmanaged host processes, consider adopting as a Custom app.",
            "plan": None,
        }
