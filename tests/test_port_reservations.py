"""Tests for Port Reservations and Intent Registry."""

import pytest
from fastapi.testclient import TestClient
from portly.backend.app import app, store
from portly.backend import auth
from portly.backend.ports import check_port_availability, check_preflight_collisions


@pytest.fixture
def client():
    return TestClient(app)


def test_port_reservation_lifecycle(client, monkeypatch):
    """Test creating, listing, conflict detection, and deletion of a port reservation."""
    # Ensure admin session
    admin_token = auth.create_session("u_adm", "admin_alice", role="admin")
    client.cookies.set("portly_session", admin_token)

    # 1. Create reservation for port 9444
    res = client.post("/api/ports/reservations", json={
        "port": 9444,
        "proto": "tcp",
        "name": "Planned Redis Cluster",
        "service": "redis-prod",
        "description": "Reserved for production Redis cache",
    }, headers={"X-Portly-Client": "1"})
    assert res.status_code == 200
    data = res.json()
    assert data["port"] == 9444
    assert data["name"] == "Planned Redis Cluster"
    res_id = data["id"]

    # 2. List reservations
    list_res = client.get("/api/ports/reservations")
    assert list_res.status_code == 200
    res_list = list_res.json()["reservations"]
    assert any(r["id"] == res_id for r in res_list)

    # 3. Verify check_port_availability identifies it as reserved
    avail = check_port_availability(9444, "0.0.0.0", proto="tcp", store=store)
    assert avail["free"] is False
    assert avail.get("reserved") is True
    assert "Planned Redis Cluster" in avail["used_by"]

    # 4. Verify preflight collision detection flags it
    preflight = check_preflight_collisions(command="docker run -d -p 9444:6379 redis", store=store)
    assert preflight["has_conflicts"] is True
    assert any(c["port"] == 9444 and c["conflict_type"] == "reservation_conflict" for c in preflight["collisions"])

    # 5. Delete reservation
    del_res = client.delete(f"/api/ports/reservations/{res_id}", headers={"X-Portly-Client": "1"})
    assert del_res.status_code == 200

    # Verify deleted
    list_after = client.get("/api/ports/reservations").json()["reservations"]
    assert not any(r["id"] == res_id for r in list_after)


def test_port_reservation_rbac(client, monkeypatch):
    """Viewers cannot create or delete reservations."""
    monkeypatch.setattr(store, "get_user_count", lambda: 2)
    viewer_token = auth.create_session("u_view", "viewer_bob", role="viewer")
    client.cookies.set("portly_session", viewer_token)

    # Viewer cannot create reservation
    res = client.post("/api/ports/reservations", json={
        "port": 9555,
        "name": "Forbidden",
    }, headers={"X-Portly-Client": "1"})
    assert res.status_code == 403

    # Viewer can view reservations
    get_res = client.get("/api/ports/reservations")
    assert get_res.status_code == 200
