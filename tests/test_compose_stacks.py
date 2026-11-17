"""Tests for Compose Stacks Management."""

import pytest
from fastapi.testclient import TestClient
from portly.backend.app import app, store
from portly.backend import auth


@pytest.fixture
def client():
    return TestClient(app)


def test_compose_stacks_lifecycle(client, monkeypatch):
    """Test saving, listing, collision rejection, and deleting compose stacks."""
    admin_token = auth.create_session("u_adm", "admin_alice", role="admin")
    client.cookies.set("portly_session", admin_token)

    # 1. Save valid stack
    valid_yaml = """version: '3.8'
services:
  cache:
    image: redis:alpine
    ports:
      - "9876:6379"
"""
    res = client.post("/api/stacks", json={
        "name": "my-cache-stack",
        "compose_yaml": valid_yaml,
        "force": False,
    }, headers={"X-Portly-Client": "1"})
    assert res.status_code == 200
    assert res.json()["status"] == "saved"

    # 2. Get stack
    get_res = client.get("/api/stacks/my-cache-stack")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "my-cache-stack"
    assert "redis:alpine" in get_res.json()["compose_yaml"]

    # 3. List stacks
    list_res = client.get("/api/stacks")
    assert list_res.status_code == 200
    stacks = list_res.json()["stacks"]
    assert any(s["name"] == "my-cache-stack" for s in stacks)

    # 4. Safe mode blocks action
    monkeypatch.setattr(store, "get_setting", lambda k, default="true": "true" if k == "safe_mode" else default)
    act_res = client.post("/api/stacks/my-cache-stack/action", json={
        "action": "up"
    }, headers={"X-Portly-Client": "1"})
    assert act_res.status_code == 403
    assert act_res.json()["detail"]["code"] == "SAFE_MODE"

    # 5. Delete stack
    del_res = client.delete("/api/stacks/my-cache-stack", headers={"X-Portly-Client": "1"})
    assert del_res.status_code == 200

    # Verify deleted
    get_after = client.get("/api/stacks/my-cache-stack")
    assert get_after.status_code == 404


def test_compose_stacks_collision_guard(client, monkeypatch):
    """Saving a stack with colliding ports is rejected unless force=True."""
    admin_token = auth.create_session("u_adm", "admin_alice", role="admin")
    client.cookies.set("portly_session", admin_token)

    # Reserve port 9877 first
    store.create_port_reservation({"port": 9877, "name": "Existing Service", "proto": "tcp"})

    colliding_yaml = """version: '3.8'
services:
  web:
    image: nginx
    ports:
      - "9877:80"
"""
    # Attempt save without force -> 409 PORT_COLLISION
    res = client.post("/api/stacks", json={
        "name": "clashing-stack",
        "compose_yaml": colliding_yaml,
        "force": False,
    }, headers={"X-Portly-Client": "1"})
    assert res.status_code == 409
    assert res.json()["code"] == "PORT_COLLISION"

    # Save with force=True -> 200
    res_force = client.post("/api/stacks", json={
        "name": "clashing-stack",
        "compose_yaml": colliding_yaml,
        "force": True,
    }, headers={"X-Portly-Client": "1"})
    assert res_force.status_code == 200

    # Cleanup
    client.delete("/api/stacks/clashing-stack", headers={"X-Portly-Client": "1"})
