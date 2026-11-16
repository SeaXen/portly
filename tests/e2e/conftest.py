"""Shared pytest fixtures for Playwright E2E browser tests."""

import os
import random
import socket
import subprocess
import sys
import time
import pytest
from playwright.sync_api import sync_playwright


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
def portly_server(tmp_path_factory):
    port = get_free_port()
    data_dir = str(tmp_path_factory.mktemp("portly_e2e_data"))
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

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def browser_instance():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--explicitly-allowed-ports=1-65535"]
        )
        yield browser
        browser.close()
