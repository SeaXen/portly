"""Health checking service for HTTP and TCP endpoints with SSRF guards and degraded state detection."""

import ipaddress
import logging
import socket
import time
from typing import Any, Dict, Optional, Tuple
import urllib.error
import urllib.request

logger = logging.getLogger("portly.health")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Leaves 3xx responses untouched so expected_status can match them and redirects aren't followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
    try:
        # create_connection resolves both IPv4 and IPv6, unlike an AF_INET-only socket
        sock = socket.create_connection((host, port), timeout=timeout)
        latency = (time.perf_counter() - t0) * 1000.0
        sock.close()
        return True, round(latency, 1)
    except Exception:
        return False, 0.0


def check_http_endpoint(
    url: str,
    timeout: float = 2.0,
    expected_status: Optional[str] = None,
    custom_headers: Optional[Dict[str, str]] = None,
) -> Tuple[bool, int, float]:
    """Attempts an HTTP GET request to url and returns (success, status_code, latency_ms)."""
    t0 = time.perf_counter()
    headers = {"User-Agent": "Portly-HealthCheck/1.0"}
    if custom_headers and isinstance(custom_headers, dict):
        headers.update(custom_headers)

    # Parse expected status codes if provided (e.g. "200,204,301,302")
    allowed_codes = set()
    if expected_status:
        for s in str(expected_status).split(","):
            s_clean = s.strip()
            if s_clean.isdigit():
                allowed_codes.add(int(s_clean))

    req = urllib.request.Request(
        url,
        headers=headers
    )
    try:
        opener = urllib.request.build_opener(_NoRedirectHandler)
        with opener.open(req, timeout=timeout) as response:
            latency = (time.perf_counter() - t0) * 1000.0
            if allowed_codes:
                is_ok = response.status in allowed_codes
            else:
                is_ok = (response.status < 400)
            return is_ok, response.status, round(latency, 1)
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000.0
        if allowed_codes and e.code in allowed_codes:
            return True, e.code, round(latency, 1)
        return False, e.code, round(latency, 1)
    except Exception:
        return False, 0, 0.0


def check_app_health(app: Dict[str, Any]) -> Dict[str, Any]:
    """Performs appropriate health check for an app, correctly identifying up, degraded, and down states."""
    host = app.get("host") or (app.get("bind") if app.get("bind") not in ("0.0.0.0", "::", None) else "127.0.0.1")
    port = app.get("port")
    health_path = app.get("health_path")
    expected_status = app.get("expected_status")
    custom_headers = app.get("custom_headers")

    if not port or port <= 0:
        return {"status": "down", "ok": False, "latency_ms": 0.0, "code": 0}

    if not _is_safe_health_host(host):
        return {"status": "down", "ok": False, "latency_ms": 0.0, "code": 403, "error": "Blocked link-local address"}

    # If health_path is configured and valid, HTTP check is decisive
    if health_path and health_path.startswith("/"):
        http_url = f"http://{host}:{port}{health_path}"
        ok, code, lat = check_http_endpoint(
            http_url,
            expected_status=expected_status,
            custom_headers=custom_headers
        )
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
