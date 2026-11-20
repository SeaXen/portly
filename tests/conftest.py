import os
import tempfile

# Set testing environment variable early before any app imports
os.environ["PORTLY_TESTING"] = "1"
# Fresh DB per run: the old persistent tests/test_data_dir leaked safe_mode,
# sessions, custom apps and reservations across tests AND runs (flake root cause).
os.environ["PORTLY_DATA_DIR"] = tempfile.mkdtemp(prefix="portly_test_data_")

import pytest


@pytest.fixture(autouse=True)
def _isolate_app_state(monkeypatch):
    """Unit tests must not run real host/Docker discovery on every mutation
    (ambient network calls, host-dependent cache pollution, minutes of runtime)
    and must not inherit safe_mode from a previous test."""
    from portly.backend import app as app_module

    async def _noop_refresh():
        return None

    monkeypatch.setattr(app_module, "refresh_discovery", _noop_refresh)
    yield
    app_module.store.set_setting("safe_mode", "true")
