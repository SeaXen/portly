"""Host listening port and process discovery via psutil with netstat/lsof fallback."""

import logging
import os
import platform
import re
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger("portly.host")

# Cache process objects across scans so cpu_percent(interval=None) returns real delta metrics
_proc_instances: Dict[int, Tuple[float, psutil.Process]] = {}


def _get_process_info(pid: int) -> Dict[str, Any]:
    info = {
        "name": f"PID {pid}",
        "cmdline": "",
        "cwd": "",
        "cpu_percent": None,
        "ram_mb": None,
        "create_time": None,
    }
    if not pid or pid <= 0:
        return info

    proc_obj: Optional[psutil.Process] = None
    if pid in _proc_instances:
        saved_ctime, cached_proc = _proc_instances[pid]
        try:
            if cached_proc.is_running() and cached_proc.create_time() == saved_ctime:
                proc_obj = cached_proc
            else:
                _proc_instances.pop(pid, None)
        except Exception:
            _proc_instances.pop(pid, None)

    if proc_obj is None:
        try:
            if len(_proc_instances) > 500:
                dead_pids = [p_id for p_id, (_, pr) in _proc_instances.items() if not pr.is_running()]
                for d in dead_pids:
                    _proc_instances.pop(d, None)

            p = psutil.Process(pid)
            ctime = p.create_time()
            p.cpu_percent(interval=None)  # Prime initial sample
            _proc_instances[pid] = (ctime, p)
            proc_obj = p
        except Exception:
            return info

    try:
        info["name"] = proc_obj.name()
        try:
            cmd = proc_obj.cmdline()
            info["cmdline"] = " ".join(cmd) if cmd else info["name"]
        except (psutil.AccessDenied, psutil.ZombieProcess):
            info["cmdline"] = info["name"]
        try:
            info["cwd"] = proc_obj.cwd()
        except (psutil.AccessDenied, psutil.ZombieProcess):
            info["cwd"] = ""
        try:
            info["cpu_percent"] = round(proc_obj.cpu_percent(interval=None), 1)
        except Exception:
            info["cpu_percent"] = None
        try:
            mem = proc_obj.memory_info()
            info["ram_mb"] = round(mem.rss / (1024 * 1024), 1)
        except Exception:
            info["ram_mb"] = None
        try:
            info["create_time"] = proc_obj.create_time()
        except Exception:
            info["create_time"] = None
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        _proc_instances.pop(pid, None)

    return info


def _fallback_netstat_windows() -> List[Dict[str, Any]]:
    """Fallback parser for Windows netstat -ano."""
    results = []
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"\s+", line)
            proto_raw = parts[0].upper()
            if proto_raw.startswith("TCP") and len(parts) >= 5 and parts[3].upper() == "LISTENING":
                local_addr = parts[1]
                pid_str = parts[4]
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue
                if ":" in local_addr:
                    ip_part, port_part = local_addr.rsplit(":", 1)
                    try:
                        port = int(port_part)
                        results.append({
                            "proto": "tcp",
                            "bind": ip_part.strip("[]"),
                            "port": port,
                            "pid": pid,
                        })
                    except ValueError:
                        continue
            elif proto_raw.startswith("UDP") and len(parts) >= 4:
                local_addr = parts[1]
                pid_str = parts[3]
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue
                if ":" in local_addr:
                    ip_part, port_part = local_addr.rsplit(":", 1)
                    try:
                        port = int(port_part)
                        if port > 0:
                            results.append({
                                "proto": "udp",
                                "bind": ip_part.strip("[]"),
                                "port": port,
                                "pid": pid,
                            })
                    except ValueError:
                        continue
    except Exception:
        pass
    return results


def _fallback_lsof_unix() -> List[Dict[str, Any]]:
    """Fallback parser for macOS/Linux lsof."""
    results = []
    try:
        out = subprocess.check_output(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
            text=True,
            stderr=subprocess.DEVNULL
        )
        for line in out.splitlines()[1:]:
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 9:
                try:
                    pid = int(parts[1])
                    name = parts[8]
                    if ":" in name:
                        ip_part, port_str = name.rsplit(":", 1)
                        port = int(port_str)
                        results.append({
                            "proto": "tcp",
                            "bind": ip_part,
                            "port": port,
                            "pid": pid,
                        })
                except Exception:
                    continue
    except Exception:
        pass
    return results


def discover_host_ports() -> List[Dict[str, Any]]:
    """Discovers all listening TCP and bound UDP ports on the host system."""
    raw_conns: List[Dict[str, Any]] = []
    try:
        # psutil net_connections
        for c in psutil.net_connections(kind="inet"):
            if not c.laddr:
                continue
            if c.type == socket.SOCK_STREAM and c.status == psutil.CONN_LISTEN:
                raw_conns.append({
                    "proto": "tcp",
                    "bind": c.laddr.ip,
                    "port": c.laddr.port,
                    "pid": c.pid or 0,
                })
            elif c.type == socket.SOCK_DGRAM:
                raw_conns.append({
                    "proto": "udp",
                    "bind": c.laddr.ip,
                    "port": c.laddr.port,
                    "pid": c.pid or 0,
                })
    except (psutil.AccessDenied, PermissionError):
        if platform.system() == "Windows":
            raw_conns = _fallback_netstat_windows()
        else:
            raw_conns = _fallback_lsof_unix()
    except Exception:
        if platform.system() == "Windows":
            raw_conns = _fallback_netstat_windows()
        else:
            raw_conns = _fallback_lsof_unix()

    # If psutil gave 0 listeners on Windows, try netstat just in case
    if not raw_conns and platform.system() == "Windows":
        raw_conns = _fallback_netstat_windows()

    # Clean up dead PIDs from _proc_instances
    current_pids = {item["pid"] for item in raw_conns if item.get("pid")}
    for cached_pid in list(_proc_instances.keys()):
        if cached_pid not in current_pids:
            _proc_instances.pop(cached_pid, None)

    # Group sockets by (port, proto, normalized_bind) to collapse multiple worker PIDs to the lowest PID
    grouped_sockets: Dict[Tuple[int, str, str], List[int]] = {}
    for item in raw_conns:
        port = item["port"]
        bind = item["bind"]
        pid = item["pid"]
        proto = item.get("proto", "tcp")

        if port <= 0 or port > 65535:
            continue

        # Normalize bind
        if bind in ("0.0.0.0", "::"):
            bind_norm = "0.0.0.0"
        elif bind in ("127.0.0.1", "::1", "localhost"):
            bind_norm = "127.0.0.1"
        else:
            bind_norm = bind

        key = (port, proto, bind_norm)
        if key not in grouped_sockets:
            grouped_sockets[key] = []
        if pid:
            grouped_sockets[key].append(pid)

    results: List[Dict[str, Any]] = []

    for (port, proto, bind_norm), pids in grouped_sockets.items():
        # Choose lowest non-zero PID (master / parent process)
        valid_pids = sorted([p for p in pids if p > 0])
        primary_pid = valid_pids[0] if valid_pids else 0

        pinfo = _get_process_info(primary_pid) if primary_pid else {
            "name": "System Listener",
            "cmdline": "",
            "cwd": "",
            "cpu_percent": None,
            "ram_mb": None,
            "create_time": None,
        }

        proc_name = pinfo["name"] or "process"
        if bind_norm not in ("0.0.0.0", "127.0.0.1"):
            stable_id = f"host:{proc_name}:{bind_norm}:{port}/{proto}"
        else:
            stable_id = f"host:{proc_name}:{port}/{proto}"

        uptime_sec = None
        if pinfo.get("create_time"):
            uptime_sec = max(0, int(time.time() - pinfo["create_time"]))

        results.append({
            "id": stable_id,
            "source": "host",
            "name": proc_name,
            "process_name": proc_name,
            "port": port,
            "proto": proto,
            "bind": bind_norm,
            "pid": primary_pid,
            "worker_pids": valid_pids,
            "cmdline": pinfo.get("cmdline", ""),
            "cwd": pinfo.get("cwd", ""),
            "cpu_percent": pinfo.get("cpu_percent"),
            "ram_mb": pinfo.get("ram_mb"),
            "uptime_sec": uptime_sec,
            "status": "up",
            "created_at": pinfo.get("create_time") or time.time(),
        })

    return results
