"""Host listening port and process discovery via psutil with netstat/lsof fallback."""

import os
import platform
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

import psutil

# Cache process cpu & memory lookups briefly to prevent spikes
_proc_cache: Dict[int, Dict[str, Any]] = {}
_last_cache_time = 0.0


def _get_process_info(pid: int) -> Dict[str, Any]:
    global _proc_cache, _last_cache_time
    now = time.time()
    if now - _last_cache_time > 3.0:
        _proc_cache.clear()
        _last_cache_time = now

    if pid in _proc_cache:
        return _proc_cache[pid]

    info = {
        "name": f"PID {pid}",
        "cmdline": "",
        "cwd": "",
        "cpu_percent": 0.0,
        "ram_mb": 0.0,
        "create_time": 0.0,
    }

    try:
        p = psutil.Process(pid)
        info["name"] = p.name()
        try:
            info["cmdline"] = " ".join(p.cmdline())
        except (psutil.AccessDenied, psutil.ZombieProcess):
            info["cmdline"] = info["name"]
        try:
            info["cwd"] = p.cwd()
        except (psutil.AccessDenied, psutil.ZombieProcess):
            info["cwd"] = ""
        try:
            info["cpu_percent"] = round(p.cpu_percent(interval=None), 1)
        except Exception:
            info["cpu_percent"] = 0.0
        try:
            mem = p.memory_info()
            info["ram_mb"] = round(mem.rss / (1024 * 1024), 1)
        except Exception:
            info["ram_mb"] = 0.0
        try:
            info["create_time"] = p.create_time()
        except Exception:
            info["create_time"] = 0.0
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

    _proc_cache[pid] = info
    return info


def _fallback_netstat_windows() -> List[Dict[str, Any]]:
    """Fallback parser for Windows netstat -ano."""
    results = []
    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            line = line.strip()
            if not line or not line.startswith("TCP"):
                continue
            parts = re.split(r"\s+", line)
            # TCP local_address foreign_address state PID
            if len(parts) >= 5 and parts[3].upper() == "LISTENING":
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
                    except ValueError:
                        continue
                    results.append({
                        "proto": "tcp",
                        "bind": ip_part.strip("[]"),
                        "port": port,
                        "pid": pid,
                    })
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
    """Discovers all listening ports on the host system."""
    raw_conns = []
    try:
        # psutil net_connections
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr:
                raw_conns.append({
                    "proto": "tcp",
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

    results: List[Dict[str, Any]] = []
    seen = set()

    for item in raw_conns:
        port = item["port"]
        bind = item["bind"]
        pid = item["pid"]
        proto = item.get("proto", "tcp")

        # Normalize bind
        if bind in ("0.0.0.0", "::"):
            bind_norm = "0.0.0.0"
        elif bind in ("127.0.0.1", "::1", "localhost"):
            bind_norm = "127.0.0.1"
        else:
            bind_norm = bind

        dedup_key = (port, bind_norm, pid)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        pinfo = _get_process_info(pid) if pid else {
            "name": "System Listener",
            "cmdline": "",
            "cwd": "",
            "cpu_percent": 0.0,
            "ram_mb": 0.0,
            "create_time": 0.0,
        }

        proc_name = pinfo["name"] or "process"
        stable_id = f"host:{proc_name}:{port}"

        uptime_sec = 0
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
            "pid": pid,
            "cmdline": pinfo.get("cmdline", ""),
            "cwd": pinfo.get("cwd", ""),
            "cpu_percent": pinfo.get("cpu_percent", 0.0),
            "ram_mb": pinfo.get("ram_mb", 0.0),
            "uptime_sec": uptime_sec,
            "status": "up",
            "created_at": pinfo.get("create_time", time.time()),
        })

    return results
