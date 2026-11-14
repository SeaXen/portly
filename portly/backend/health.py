"""Health checking service for HTTP and TCP endpoints."""

import socket
import time
from typing import Any, Dict, Optional, Tuple
import urllib.request
import urllib.error


def check_tcp_port(host: str, port: int, timeout: float = 1.5) -> Tuple[bool, float]:
    """Attempts a TCP connection to host:port and returns (success, latency_ms)."""
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
            return (response.status < 400), response.status, round(latency, 1)
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000.0
        # 4xx or 5xx still means the server is reachable and listening!
        return (e.code < 500), e.code, round(latency, 1)
    except Exception:
        return False, 0, 0.0


def check_app_health(app: Dict[str, Any]) -> Dict[str, Any]:
    """Performs appropriate health check for an app."""
    host = app.get("host") or (app.get("bind") if app.get("bind") not in ("0.0.0.0", "::") else "127.0.0.1")
    port = app.get("port")
    health_path = app.get("health_path")

    if not port or port <= 0:
        return {"status": "down", "ok": False, "latency_ms": 0.0, "code": 0}

    # If health_path is configured and valid
    if health_path and health_path.startswith("/"):
        http_url = f"http://{host}:{port}{health_path}"
        ok, code, lat = check_http_endpoint(http_url)
        if ok:
            return {"status": "up", "ok": True, "latency_ms": lat, "code": code}

    # Otherwise fallback to TCP socket check
    tcp_ok, lat = check_tcp_port(host, port)
    return {
        "status": "up" if tcp_ok else "down",
        "ok": tcp_ok,
        "latency_ms": lat,
        "code": 200 if tcp_ok else 0
    }
