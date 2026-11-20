"""Health check service tests."""

import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytest
from portly.backend import health


class DummyHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == "/error":
            self.send_response(500)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def dummy_http_server():
    server = HTTPServer(("127.0.0.1", 0), DummyHTTPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


def test_check_tcp_port_open(dummy_http_server):
    ok, latency = health.check_tcp_port("127.0.0.1", dummy_http_server)
    assert ok is True
    assert latency >= 0.0


def test_check_tcp_port_closed():
    # Find an unused port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    unused_port = s.getsockname()[1]
    s.close()

    ok, latency = health.check_tcp_port("127.0.0.1", unused_port, timeout=0.3)
    assert ok is False
    assert latency == 0.0


def test_check_http_endpoint_ok(dummy_http_server):
    url = f"http://127.0.0.1:{dummy_http_server}/health"
    ok, code, lat = health.check_http_endpoint(url)
    assert ok is True
    assert code == 200
    assert lat >= 0.0


def test_check_http_endpoint_error(dummy_http_server):
    url = f"http://127.0.0.1:{dummy_http_server}/error"
    ok, code, lat = health.check_http_endpoint(url)
    assert ok is False
    assert code == 500


def test_check_app_health_tcp(dummy_http_server):
    app = {
        "host": "127.0.0.1",
        "port": dummy_http_server,
    }
    res = health.check_app_health(app)
    assert res["status"] == "up"
    assert res["ok"] is True


def test_check_app_health_http(dummy_http_server):
    app = {
        "host": "127.0.0.1",
        "port": dummy_http_server,
        "health_path": "/health"
    }
    res = health.check_app_health(app)
    assert res["status"] == "up"
    assert res["ok"] is True
    assert res["code"] == 200


def test_check_app_health_invalid_port():
    app = {
        "host": "127.0.0.1",
        "port": -1,
    }
    res = health.check_app_health(app)
    assert res["status"] == "down"
    assert res["ok"] is False


def test_check_http_endpoint_expected_status(dummy_http_server):
    url = f"http://127.0.0.1:{dummy_http_server}/error"
    # Normally 500 is failure
    ok_normal, code, _ = health.check_http_endpoint(url)
    assert ok_normal is False
    assert code == 500

    # If 500 is explicitly expected, reports ok
    ok_expected, code, _ = health.check_http_endpoint(url, expected_status="200,500")
    assert ok_expected is True
    assert code == 500


class RedirectHTTPHandler(BaseHTTPRequestHandler):
    redirect_target_hits = 0

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirect-target")
            self.end_headers()
        elif self.path == "/redirect-target":
            type(self).redirect_target_hits += 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def redirect_http_server():
    server = HTTPServer(("127.0.0.1", 0), RedirectHTTPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


def test_check_http_endpoint_does_not_follow_redirect(redirect_http_server):
    RedirectHTTPHandler.redirect_target_hits = 0
    url = f"http://127.0.0.1:{redirect_http_server}/redirect"
    ok, code, _ = health.check_http_endpoint(url, expected_status="200,302")
    assert ok is True
    assert code == 302
    assert RedirectHTTPHandler.redirect_target_hits == 0


def test_check_tcp_port_ipv6_only():
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.bind(("::1", 0))
    except OSError:
        pytest.skip("IPv6 loopback not available")
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        ok, latency = health.check_tcp_port("::1", port, timeout=0.5)
        assert ok is True
        assert latency >= 0.0
    finally:
        sock.close()


def test_health_guard_blocks_metadata_ula_broadcast():
    assert health._is_safe_health_host("169.254.169.254") is False
    assert health._is_safe_health_host("fd00:ec2::254") is False
    assert health._is_safe_health_host("255.255.255.255") is False
    assert health._is_safe_health_host("::1") is True
    assert health._is_safe_health_host("127.0.0.1") is True
    assert health._is_safe_health_host("192.168.1.10") is True
