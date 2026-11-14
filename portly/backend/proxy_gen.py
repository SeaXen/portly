"""Reverse proxy configuration generators for Caddy, Nginx, and Traefik."""

import re
from typing import Any, Dict, Optional


def sanitize_router_name(name: str) -> str:
    """Sanitizes an application or service name for use as a router identifier."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower()).strip("-_")
    return sanitized or "app"


def sanitize_domain(domain: Optional[str], default_name: str) -> str:
    """Returns a valid domain, falling back to a clean local domain."""
    if domain and domain.strip():
        # Remove protocol if user included it
        cleaned = re.sub(r"^https?://", "", domain.strip().lower())
        # Remove trailing slashes and paths
        cleaned = cleaned.split("/")[0].strip()
        if cleaned:
            return cleaned
    return f"{sanitize_router_name(default_name)}.local"


def generate_caddy_config(domain: str, upstream_host: str, port: int) -> str:
    """Generates a modern Caddy reverse proxy block."""
    return f"""{domain} {{
    reverse_proxy {upstream_host}:{port}
}}
"""


def generate_nginx_config(domain: str, upstream_host: str, port: int) -> str:
    """Generates an Nginx server block with WebSocket and header support."""
    return f"""server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass http://{upstream_host}:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


def generate_traefik_yaml_config(domain: str, upstream_host: str, port: int, router_name: str) -> str:
    """Generates Traefik dynamic configuration in YAML."""
    return f"""http:
  routers:
    {router_name}-router:
      rule: "Host(`{domain}`)"
      service: "{router_name}-service"
      entryPoints:
        - "web"
  services:
    {router_name}-service:
      loadBalancer:
        servers:
          - url: "http://{upstream_host}:{port}"
"""


def generate_traefik_labels(domain: str, port: int, router_name: str) -> str:
    """Generates Traefik Docker Compose service labels."""
    return f"""labels:
  - "traefik.enable=true"
  - "traefik.http.routers.{router_name}.rule=Host(`{domain}`)"
  - "traefik.http.routers.{router_name}.entrypoints=web"
  - "traefik.http.services.{router_name}.loadbalancer.server.port={port}"
"""


def generate_all_proxy_configs(
    name: str,
    port: int,
    host: str = "127.0.0.1",
    domain: Optional[str] = None
) -> Dict[str, Any]:
    """Generates reverse proxy snippets for all supported engines."""
    clean_domain = sanitize_domain(domain, name)
    router_name = sanitize_router_name(name)

    # Normalize upstream host: 0.0.0.0 or :: is a bind, not a connect target
    upstream_host = "127.0.0.1" if host in ("0.0.0.0", "::", "", None) else host

    caddy = generate_caddy_config(clean_domain, upstream_host, port)
    nginx = generate_nginx_config(clean_domain, upstream_host, port)
    traefik_yaml = generate_traefik_yaml_config(clean_domain, upstream_host, port, router_name)
    traefik_labels = generate_traefik_labels(clean_domain, port, router_name)

    return {
        "domain": clean_domain,
        "upstream_host": upstream_host,
        "port": port,
        "router_name": router_name,
        "configs": {
            "caddy": caddy,
            "nginx": nginx,
            "traefik": traefik_yaml,
            "traefik_yaml": traefik_yaml,
            "traefik_labels": traefik_labels,
        }
    }
