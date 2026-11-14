"""Automatic Favicon and App Icon Fetcher with SSRF and private network safeguards."""

import hashlib
import ipaddress
import logging
import os
import re
import socket
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("portly.favicon")

DEFAULT_FALLBACK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="#8C9EFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10" stroke="#8C9EFF" fill="#141824" />
  <text x="12" y="16" font-family="system-ui, sans-serif" font-size="12" font-weight="bold" fill="#8C9EFF" text-anchor="middle">{letter}</text>
</svg>"""

BLOCKED_IP_RANGES = [
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud metadata (e.g. AWS/GCP 169.254.169.254)
    ipaddress.ip_network("224.0.0.0/4"),     # Multicast
    ipaddress.ip_network("240.0.0.0/4"),     # Reserved
    ipaddress.ip_network("0.0.0.0/8"),       # Current network
]


def is_safe_target_ip(ip_str: str) -> bool:
    """Verifies that an IP is not in a forbidden metadata or multicast range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for blocked in BLOCKED_IP_RANGES:
            if ip in blocked:
                return False
        return True
    except ValueError:
        return False


def resolve_and_check_host(host: str) -> Tuple[bool, str]:
    """Resolves hostname to IP and verifies that it is safe to probe."""
    if host in ("localhost", "127.0.0.1", "::1"):
        return True, "127.0.0.1"

    try:
        addr_info = socket.getaddrinfo(host, None)
        if not addr_info:
            return False, ""
        target_ip = addr_info[0][4][0]
        if not is_safe_target_ip(target_ip):
            return False, ""
        return True, target_ip
    except Exception:
        return False, ""


def detect_image_type(data: bytes) -> Optional[str]:
    """Inspects magic bytes to determine image MIME type."""
    if len(data) < 4:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\x00\x00\x01\x00") or data.startswith(b"\x00\x00\x02\x00"):
        return "image/x-icon"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    # SVG check
    snippet = data[:512].lower()
    if b"<svg" in snippet:
        return "image/svg+xml"
    return None


def extract_favicon_url(html_content: str, base_url: str) -> Optional[str]:
    """Parses HTML to find <link rel='icon' href='...'>."""
    match = re.search(r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
    if not match:
        match = re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'](?:shortcut )?icon["\']', html_content, re.IGNORECASE)
    if match:
        href = match.group(1).strip()
        return urllib.parse.urljoin(base_url, href)
    return None


def fetch_favicon_from_url(url: str, timeout: float = 1.5, max_bytes: int = 524288) -> Optional[Tuple[bytes, str]]:
    """Safely fetches an image from URL with SSRF safeguards, short timeout, and size limit."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None

    safe, _ = resolve_and_check_host(parsed.hostname or "")
    if not safe:
        return None

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Portly-IconFetcher/1.0", "Accept": "image/*, */*"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None  # Exceeded max size
            mime = detect_image_type(data)
            if mime:
                return data, mime
            # Content-Type header fallback if header claims image
            header_ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if header_ct.startswith("image/"):
                return data, header_ct
            return None
    except Exception:
        return None


def get_cached_icon(cache_dir: str, app_id: str) -> Optional[Tuple[bytes, str]]:
    """Checks if icon is already cached on disk."""
    safe_name = hashlib.sha256(app_id.encode()).hexdigest()[:24]
    for ext, mime in [(".ico", "image/x-icon"), (".png", "image/png"), (".svg", "image/svg+xml"), (".webp", "image/webp")]:
        fp = os.path.join(cache_dir, f"{safe_name}{ext}")
        if os.path.isfile(fp):
            try:
                with open(fp, "rb") as f:
                    return f.read(), mime
            except Exception:
                pass
    return None


def save_cached_icon(cache_dir: str, app_id: str, data: bytes, mime: str):
    """Saves icon bytes to disk cache."""
    os.makedirs(cache_dir, exist_ok=True)
    safe_name = hashlib.sha256(app_id.encode()).hexdigest()[:24]
    ext_map = {
        "image/x-icon": ".ico",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
        "image/gif": ".gif"
    }
    ext = ext_map.get(mime, ".ico")
    fp = os.path.join(cache_dir, f"{safe_name}{ext}")
    try:
        with open(fp, "wb") as f:
            f.write(data)
    except Exception as e:
        logger.warning(f"Could not save cached icon for {app_id}: {e}")


def get_fallback_svg(app_name: str) -> Tuple[bytes, str]:
    """Generates a clean vector SVG badge based on app name initial."""
    letter = (app_name[0] if app_name else "P").upper()
    svg = DEFAULT_FALLBACK_SVG.replace("{letter}", letter)
    return svg.encode("utf-8"), "image/svg+xml"


def fetch_or_generate_app_icon(
    app: Dict[str, Any],
    cache_dir: str,
    probe_network: bool = True
) -> Tuple[bytes, str]:
    """Retrieves or probes favicon for app, with SSRF protection and fallback."""
    app_id = app.get("id", "")
    app_name = app.get("name", "App")

    # 1. Check cache
    cached = get_cached_icon(cache_dir, app_id)
    if cached:
        return cached

    if not probe_network:
        return get_fallback_svg(app_name)

    # 2. Probe HTTP endpoint
    port = app.get("port")
    if not port or port <= 0:
        return get_fallback_svg(app_name)

    bind = app.get("bind") or "127.0.0.1"
    host = "127.0.0.1" if bind in ("0.0.0.0", "::", "") else bind

    safe, _ = resolve_and_check_host(host)
    if not safe:
        return get_fallback_svg(app_name)

    base_url = f"http://{host}:{port}"

    # Try /favicon.ico first
    result = fetch_favicon_from_url(f"{base_url}/favicon.ico")
    if result:
        data, mime = result
        save_cached_icon(cache_dir, app_id, data, mime)
        return data, mime

    # Next, try index page HTML parse
    try:
        req = urllib.request.Request(base_url, headers={"User-Agent": "Portly-IconFetcher/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            html = resp.read(32768).decode("utf-8", errors="ignore")
            icon_url = extract_favicon_url(html, base_url)
            if icon_url:
                result = fetch_favicon_from_url(icon_url)
                if result:
                    data, mime = result
                    save_cached_icon(cache_dir, app_id, data, mime)
                    return data, mime
    except Exception:
        pass

    # Fallback SVG badge
    return get_fallback_svg(app_name)
