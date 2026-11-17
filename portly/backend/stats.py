"""System stats monitoring with ring buffer history and sparkline generation."""

import collections
import os
import platform
import threading
import time
from typing import Any, Dict, List, Optional

import psutil

MAX_HISTORY = 60

# Ring buffer for system history
_history: collections.deque = collections.deque(maxlen=MAX_HISTORY)
_last_net = None
_last_net_time = 0.0
_lock = threading.RLock()


def _format_bytes(bytes_val: float) -> str:
    gb = bytes_val / (1024 ** 3)
    if gb >= 1.0:
        return f"{round(gb, 1)} GB"
    mb = bytes_val / (1024 ** 2)
    return f"{round(mb, 1)} MB"


def _format_rate(bytes_per_sec: float) -> str:
    mb_s = bytes_per_sec / (1024 ** 2)
    if mb_s >= 1.0:
        return f"{round(mb_s, 1)} MB/s"
    kb_s = bytes_per_sec / 1024
    return f"{round(kb_s, 1)} KB/s"


def _generate_sparkline_points(values: List[float], width: float = 60.0, height: float = 22.0) -> str:
    """Generates an SVG polyline points string from a list of real telemetry numbers."""
    if not values:
        return f"0.0,{height} {width},{height}"

    n = len(values)
    if n == 1:
        return f"0.0,{height / 2} {width},{height / 2}"

    min_v = min(values)
    max_v = max(values)
    diff = max_v - min_v if max_v != min_v else 1.0

    step = width / (n - 1)
    points = []
    # 2px padding top/bottom
    avail_h = height - 4.0
    for i, v in enumerate(values):
        x = round(i * step, 1)
        normalized = (v - min_v) / diff
        # SVG y coordinates: 0 is top, height is bottom
        y = round((height - 2.0) - (normalized * avail_h), 1)
        points.append(f"{x},{y}")

    return " ".join(points)


def collect_snapshot(containers_running: int = 0, listening_count: int = 0, conflict_count: int = 0) -> Dict[str, Any]:
    global _last_net, _last_net_time

    now = time.time()

    # CPU
    cpu_pct = round(psutil.cpu_percent(interval=None), 1)
    cpu_cores = psutil.cpu_count(logical=True) or 1

    # Memory
    mem = psutil.virtual_memory()
    mem_used_gb = round(mem.used / (1024 ** 3), 1)
    mem_total_gb = round(mem.total / (1024 ** 3), 1)
    mem_pct = mem.percent

    # Disk - inspect host root via PORTLY_HOSTFS if inside container
    try:
        hostfs = os.getenv("PORTLY_HOSTFS")
        root_path = hostfs if (hostfs and os.path.isdir(hostfs)) else os.path.abspath(os.sep)
        disk = psutil.disk_usage(root_path)
        disk_used_gb = round(disk.used / (1024 ** 3), 1)
        disk_total_gb = round(disk.total / (1024 ** 3), 1)
        disk_pct = disk.percent
    except Exception:
        disk_used_gb = 0.0
        disk_total_gb = 100.0
        disk_pct = 0.0

    # Network rate
    net_now = psutil.net_io_counters()
    net_down_bps = 0.0
    net_up_bps = 0.0
    if _last_net and _last_net_time > 0:
        dt = max(0.1, now - _last_net_time)
        net_down_bps = max(0.0, (net_now.bytes_recv - _last_net.bytes_recv) / dt)
        net_up_bps = max(0.0, (net_now.bytes_sent - _last_net.bytes_sent) / dt)

    _last_net = net_now
    _last_net_time = now

    entry = {
        "ts": now,
        "cpu_pct": cpu_pct,
        "cpu_cores": cpu_cores,
        "mem_used_gb": mem_used_gb,
        "mem_total_gb": mem_total_gb,
        "mem_pct": mem_pct,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_pct": disk_pct,
        "net_down_bps": net_down_bps,
        "net_up_bps": net_up_bps,
        "containers_running": containers_running,
        "listening_count": listening_count,
        "conflict_count": conflict_count,
    }

    with _lock:
        _history.append(entry)

    return entry


def get_current_stats(containers_running: int = 0, listening_count: int = 0, conflict_count: int = 0) -> Dict[str, Any]:
    with _lock:
        if not _history:
            collect_snapshot(containers_running, listening_count, conflict_count)

        latest = _history[-1] if _history else collect_snapshot(containers_running, listening_count, conflict_count)

        # Real telemetry history only
        cpu_hist = [h["cpu_pct"] for h in _history]
        mem_hist = [h["mem_pct"] for h in _history]
        disk_hist = [h["disk_pct"] for h in _history]
        net_hist = [round(h["net_down_bps"] / (1024 ** 2), 2) for h in _history]
        cont_hist = [float(h["containers_running"]) for h in _history]
        port_hist = [float(h["listening_count"]) for h in _history]

    conflict_label = f"{conflict_count} conflict" if conflict_count == 1 else (f"{conflict_count} conflicts" if conflict_count > 1 else "no conflicts")

    return {
        "cpu": {
            "label": "CPU",
            "value": f"{latest['cpu_pct']}%",
            "context": f"{latest['cpu_cores']} cores",
            "percent": latest["cpu_pct"],
            "sparkline": _generate_sparkline_points(cpu_hist),
            "history": cpu_hist,
        },
        "memory": {
            "label": "RAM",
            "value": f"{latest['mem_used_gb']} GB",
            "context": f"of {latest['mem_total_gb']} GB",
            "percent": latest["mem_pct"],
            "sparkline": _generate_sparkline_points(mem_hist),
            "history": mem_hist,
        },
        "disk": {
            "label": "Disk",
            "value": f"{latest['disk_used_gb']} GB",
            "context": f"of {latest['disk_total_gb']} GB",
            "percent": latest["disk_pct"],
            "sparkline": _generate_sparkline_points(disk_hist),
            "history": disk_hist,
        },
        "network": {
            "label": "Network",
            "value": f"↓ {_format_rate(latest['net_down_bps'])}",
            "context": f"↑ {_format_rate(latest['net_up_bps'])}",
            "percent": min(100.0, (latest["net_down_bps"] / (10 * 1024 * 1024)) * 100),
            "sparkline": _generate_sparkline_points(net_hist),
            "history": net_hist,
        },
        "containers": {
            "label": "Containers",
            "value": str(latest["containers_running"]),
            "context": "running",
            "percent": min(100.0, float(latest["containers_running"]) * 10),
            "sparkline": _generate_sparkline_points(cont_hist),
            "history": cont_hist,
        },
        "listening": {
            "label": "Listening Ports",
            "value": str(latest["listening_count"]),
            "context": conflict_label,
            "percent": min(100.0, float(latest["listening_count"]) * 5),
            "conflict_count": conflict_count,
            "sparkline": _generate_sparkline_points(port_hist),
            "history": port_hist,
        },
        "ts": latest["ts"],
    }


def get_detailed_system_stats() -> Dict[str, Any]:
    """Provides deep stats for the System drawer / NAS mode."""
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Disks
    partitions = []
    try:
        for p in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 1),
                    "used_gb": round(usage.used / (1024 ** 3), 1),
                    "free_gb": round(usage.free / (1024 ** 3), 1),
                    "percent": usage.percent,
                })
            except Exception:
                continue
    except Exception:
        pass

    # Network interfaces
    interfaces = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for if_name, if_addrs in addrs.items():
            st = stats.get(if_name)
            ip = ""
            for a in if_addrs:
                fam = getattr(a.family, "name", str(a.family))
                if ("AF_INET" in fam or "AF_INET6" in fam) and not a.address.startswith("127."):
                    ip = a.address
                    break
            interfaces.append({
                "name": if_name,
                "ip": ip,
                "is_up": st.isup if st else True,
                "speed": st.speed if st else 0,
            })
    except Exception:
        pass

    # System uptime
    uptime_sec = int(time.time() - psutil.boot_time())
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    uptime_str = f"{days}d {hours}h" if days > 0 else f"{hours}h { (uptime_sec % 3600)//60 }m"

    load_avg = None
    if hasattr(os, "getloadavg"):
        load_avg = os.getloadavg()

    return {
        "platform": platform.platform(),
        "hostname": platform.node(),
        "uptime": uptime_str,
        "uptime_sec": uptime_sec,
        "cpu_per_core": cpu_per_core,
        "load_avg": load_avg,
        "memory": {
            "total_gb": round(mem.total / (1024 ** 3), 1),
            "used_gb": round(mem.used / (1024 ** 3), 1),
            "available_gb": round(mem.available / (1024 ** 3), 1),
            "percent": mem.percent,
        },
        "swap": {
            "total_gb": round(swap.total / (1024 ** 3), 1),
            "used_gb": round(swap.used / (1024 ** 3), 1),
            "percent": swap.percent,
        },
        "disks": partitions,
        "interfaces": interfaces,
    }
