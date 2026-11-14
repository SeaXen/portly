"""API endpoint integration tests."""

import pytest
from fastapi.testclient import TestClient
from portly.backend.app import app

client = TestClient(app)


def test_get_apps():
    res = client.get("/api/apps")
    assert res.status_code == 200
    data = res.json()
    assert "apps" in data
    assert "total" in data
    assert "conflicts" in data
    assert "docker_status" in data


def test_get_stats():
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert "cpu" in data
    assert "memory" in data
    assert "disk" in data
    assert "network" in data
    assert "containers" in data
    assert "listening" in data


def test_custom_app_crud():
    # Create
    payload = {
        "id": "test_app_1",
        "name": "Integration Test App",
        "host": "localhost",
        "port": 9988,
        "health_path": "/healthz",
        "health_interval": 15,
        "start_cmd": "python -m http.server 9988",
        "env": {"TEST_VAR": "true"}
    }
    create_res = client.post("/api/custom-apps", json=payload)
    assert create_res.status_code == 200
    assert create_res.json()["name"] == "Integration Test App"

    # Read list
    list_res = client.get("/api/custom-apps")
    assert list_res.status_code == 200
    items = [x for x in list_res.json() if x["id"] == "test_app_1"]
    assert len(items) == 1

    # Delete
    del_res = client.delete("/api/custom-apps/test_app_1")
    assert del_res.status_code == 200


def test_export_endpoints():
    res_json = client.get("/api/export?format=json")
    assert res_json.status_code == 200
    assert "categories" in res_json.json()

    res_csv = client.get("/api/export?format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]

    res_md = client.get("/api/export?format=markdown")
    assert res_md.status_code == 200
    assert "Portly - Ports Cheat Sheet" in res_md.text
