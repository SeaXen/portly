"""Health checking service for HTTP and TCP endpoints with SSRF guards and degraded state detection."""

import ipaddress
import logging
import socket
import time
from typing import Any, Dict, Optional, Tuple
import urllib.error
import urllib.request

logger = logging.getLogger("portly.health")


def _is_safe_health_host(host: str) -> bool:
    """Verifies that host does not target cloud metadata or link-local addresses."""
    if not host:
        return False
    lower_host = host.lower().strip()
    if lower_host in ("169.254.169.254", "metadata.google.internal", "metadata", "instance-data"):
        return False
    try:
        ip = ipaddress.ip_address(lower_host)
        if ip.is_link_local or ip.is_multicast:
            return False
    except ValueError:
        pass
    return True


def check_tcp_port(host: str, port: int, timeout: float = 1.5) -> Tuple[bool, float]:
    """Attempts a TCP connection to host:port and returns (success, latency_ms)."""
    if not _is_safe_health_host(host):
        return False, 0.0

    t0 = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        latency = (time.perf_counter() - t0) * 1000.0
        return True, round(latency, 1)
    except Exception:
        return False, 0.0
    finally:
        try:
            s.close()
        except Exception:
            pass


def check_http_endpoint(url: str, timeout: float = 2.0) -> Tuple[bool, int, float]:
    """Attempts an HTTP GET request to url and returns (success, status_code, latency_ms)."""
    t0 = time.perf_counter()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Portly-HealthCheck/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency = (time.perf_counter() - t0) * 1000.0
            # Strict success: only 2xx and 3xx codes are healthy
            return (response.status < 400), response.status, round(latency, 1)
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000.0
        return False, e.code, round(latency, 1)
    except Exception:
        return False, 0, 0.0


def check_app_health(app: Dict[str, Any]) -> Dict[str, Any]:
    """Performs appropriate health check for an app, correctly identifying up, degraded, and down states."""
    host = app.get("host") or (app.get("bind") if app.get("bind") not in ("0.0.0.0", "::", None) else "127.0.0.1")
    port = app.get("port")
    health_path = app.get("health_path")

    if not port or port <= 0:
        return {"status": "down", "ok": False, "latency_ms": 0.0, "code": 0}

    if not _is_safe_health_host(host):
        return {"status": "down", "ok": False, "latency_ms": 0.0, "code": 403, "error": "Blocked link-local address"}

    # If health_path is configured and valid, HTTP check is decisive
    if health_path and health_path.startswith("/"):
        http_url = f"http://{host}:{port}{health_path}"
        ok, code, lat = check_http_endpoint(http_url)
        if ok:
            return {"status": "up", "ok": True, "latency_ms": lat, "code": code}

        # HTTP check failed - check if TCP port is reachable to detect 'degraded' vs 'down'
        tcp_ok, tcp_lat = check_tcp_port(host, port)
        if tcp_ok:
            return {
                "status": "degraded",
                "ok": False,
                "latency_ms": lat or tcp_lat,
                "code": code,
                "message": f"TCP port is listening, but HTTP health check returned status {code or 'error'}"
            }
        else:
            return {
                "status": "down",
                "ok": False,
                "latency_ms": 0.0,
                "code": code,
                "message": "Service is unreachable"
            }

    # Otherwise fallback to TCP socket check
    tcp_ok, lat = check_tcp_port(host, port)
    return {
        "status": "up" if tcp_ok else "down",
        "ok": tcp_ok,
        "latency_ms": lat,
        "code": 200 if tcp_ok else 0
    }
