"""Test preservation of custom app configuration during port changes."""

import pytest
from fastapi.testclient import TestClient
from portly.backend.app import app, store

client = TestClient(app)


def test_custom_app_port_preserves_configuration(tmp_path):
    # Ensure safe mode is disabled for mutation
    store.set_setting("safe_mode", "false")

    # 1. Create a custom app with complete configuration
    app_id = "test_custom_preserve_1"
    create_payload = {
        "id": app_id,
        "name": "Full Config App",
        "host": "localhost",
        "port": 4001,
        "health_path": "/api/health",
        "health_interval": 20,
        "start_cmd": "echo starting 4001",
        "stop_cmd": "auto",
        "workdir": str(tmp_path),
        "log_file": str(tmp_path / "app.log"),
        "start_on_boot": True,
        "env": {"NODE_ENV": "production", "SECRET_KEY": "test"},
        "update_cmd": "echo updating"
    }

    create_res = client.post("/api/custom-apps", json=create_payload)
    assert create_res.status_code == 200

    # Verify initial stored data
    orig = store.get_custom_app(app_id)
    assert orig is not None
    assert orig["start_cmd"] == "echo starting 4001"
    assert orig["stop_cmd"] == "auto"
    assert orig["workdir"] == str(tmp_path)
    assert orig["log_file"] == str(tmp_path / "app.log")
    assert orig["start_on_boot"] is True
    assert orig["env"] == {"NODE_ENV": "production", "SECRET_KEY": "test"}
    assert orig["update_cmd"] == "echo updating"

    # 2. Perform a port change via the port change endpoint
    port_payload = {
        "host_port": 4002,
        "bind": "127.0.0.1"
    }
    change_res = client.post(f"/api/apps/custom:{app_id}/port?apply=true", json=port_payload)
    assert change_res.status_code == 200
    assert change_res.json()["new_port"] == 4002

    # 3. CRITICAL VERIFICATION: Check that ALL configuration was preserved!
    updated = store.get_custom_app(app_id)
    assert updated is not None
    assert updated["port"] == 4002
    assert updated["name"] == "Full Config App"
    assert updated["start_cmd"] == "echo starting 4001"
    assert updated["stop_cmd"] == "auto"
    assert updated["workdir"] == str(tmp_path)
    assert updated["log_file"] == str(tmp_path / "app.log")
    assert updated["start_on_boot"] is True
    assert updated["env"] == {"NODE_ENV": "production", "SECRET_KEY": "test"}
    assert updated["update_cmd"] == "echo updating"
    assert updated["health_path"] == "/api/health"
    assert updated["health_interval"] == 20

    # Cleanup
    client.delete(f"/api/custom-apps/{app_id}")
    store.set_setting("safe_mode", "true")
