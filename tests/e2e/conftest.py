"""Shared pytest fixtures for Playwright E2E browser tests."""

import os
import random
import socket
import subprocess
import sys
import time
import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
    collect_ignore_glob = ["*"]


from portly.backend.store import Store
from portly.backend import auth

E2E_SESSION_TOKEN = "e2e_test_admin_token_secret_12345"


def get_free_port():
    for _ in range(100):
        port = random.randint(15000, 35000)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError("Could not find free port")


@pytest.fixture(scope="session")
def portly_server_info(tmp_path_factory):
    port = get_free_port()
    data_dir = str(tmp_path_factory.mktemp("portly_e2e_data"))

    # Pre-seed admin user and active session into test SQLite DB
    db_path = os.path.join(data_dir, "portly.db")
    s = Store(db_path=db_path)
    s.create_user("u_e2e_admin", "admin", auth.hash_password("Password1234!"), role="admin")
    s.save_session(E2E_SESSION_TOKEN, "u_e2e_admin", "admin", "admin", time.time() + 86400 * 7)

    env = os.environ.copy()
    env["PORTLY_DATA_DIR"] = data_dir
    env["PORTLY_PORT"] = str(port)
    env["PORTLY_HOST"] = "127.0.0.1"
    env["PORTLY_MODE"] = "desktop"
    env.pop("PORTLY_TESTING", None)

    cmd = [sys.executable, "-m", "portly", "run", "--port", str(port), "--host", "127.0.0.1"]
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ready = False
    start_time = time.time()
    while time.time() - start_time < 25:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                ready = True
                break
        except Exception:
            time.sleep(0.3)

    if not ready:
        proc.kill()
        raise RuntimeError(f"Portly server failed to start on port {port}")

    yield {
        "url": f"http://127.0.0.1:{port}",
        "port": port,
        "token": E2E_SESSION_TOKEN,
        "data_dir": data_dir,
    }

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def portly_server(portly_server_info):
    return portly_server_info["url"]


@pytest.fixture(scope="session")
def browser_instance():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--explicitly-allowed-ports=1-65535"]
        )
        yield browser
        browser.close()


@pytest.fixture
def authenticated_context(browser_instance, portly_server_info):
    """Browser context pre-authenticated with admin session cookie."""
    context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
    context.add_cookies([{
        "name": "portly_session",
        "value": portly_server_info["token"],
        "url": portly_server_info["url"],
    }])
    yield context
    context.close()


@pytest.fixture(scope="session")
def fresh_portly_server_info(tmp_path_factory):
    """A fresh Portly instance with no users, so the first-run setup screen is shown."""
    port = get_free_port()
    data_dir = str(tmp_path_factory.mktemp("portly_e2e_fresh"))

    env = os.environ.copy()
    env["PORTLY_DATA_DIR"] = data_dir
    env["PORTLY_PORT"] = str(port)
    env["PORTLY_HOST"] = "127.0.0.1"
    env["PORTLY_MODE"] = "desktop"
    env.pop("PORTLY_TESTING", None)

    cmd = [sys.executable, "-m", "portly", "run", "--port", str(port), "--host", "127.0.0.1"]
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ready = False
    start_time = time.time()
    while time.time() - start_time < 25:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                ready = True
                break
        except Exception:
            time.sleep(0.3)

    if not ready:
        proc.kill()
        raise RuntimeError(f"Portly server failed to start on port {port}")

    yield {
        "url": f"http://127.0.0.1:{port}",
        "port": port,
        "data_dir": data_dir,
    }

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
