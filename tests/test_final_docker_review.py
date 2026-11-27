from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from portly.backend.actions.docker_actions import deploy_container
from portly.backend.app import app, store


def test_dockerfile_runtime_dependencies_and_uid():
    dockerfile = (Path(__file__).resolve().parent.parent / "Dockerfile").read_text(encoding="utf-8")
    assert "docker-cli" in dockerfile
    assert "docker-compose" in dockerfile
    assert "PORTLY_DATA_DIR=/app/data" in dockerfile
    assert "groupadd -g 1000 portly" in dockerfile
    assert "useradd -u 1000 -g portly" in dockerfile


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/apps/docker:/logs", None),
        ("POST", "/api/apps/docker:/start", None),
        ("POST", "/api/apps/docker:/stop", None),
        ("POST", "/api/apps/docker:/restart", None),
        ("POST", "/api/apps/docker:/exec", {"command": "ps aux"}),
        ("GET", "/api/apps/docker:/compose", None),
        ("GET", "/api/apps/docker:/inspect/reveal-env", None),
        ("POST", "/api/apps/docker:/update/apply", None),
    ],
)
def test_empty_docker_app_id_returns_400(method, path, payload):
    store.set_setting("safe_mode", "false")
    try:
        client = TestClient(app)
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path, json=payload) if payload is not None else client.post(path)
        assert res.status_code == 400
        assert res.json()["detail"]["code"] == "INVALID_ID"
    finally:
        store.set_setting("safe_mode", "true")


def test_change_multi_ports_checks_per_mapping_bind():
    store.set_setting("safe_mode", "false")
    mock_client = MagicMock()
    mock_cont = MagicMock()
    mock_cont.attrs = {"HostConfig": {"PortBindings": {}}}
    mock_client.containers.get.return_value = mock_cont

    seen_calls = []

    def fake_check(port, bind="0.0.0.0", store=None):
        seen_calls.append((port, bind, store))
        return {"free": True, "used_by": ""}

    try:
        with patch("portly.backend.app.get_docker_client", return_value=mock_client), \
             patch("portly.backend.app.check_port_availability", side_effect=fake_check), \
             patch("portly.backend.actions.docker_actions.apply_multi_port_change_docker", return_value={"status": "updated"}):
            client = TestClient(app)
            res = client.post(
                "/api/apps/docker:myapp/ports-multi",
                json={"mappings": [{"container_port": "80/tcp", "host_port": 8085, "bind": "127.0.0.1"}]},
            )
            assert res.status_code == 200
            assert seen_calls == [(8085, "127.0.0.1", store)]
    finally:
        store.set_setting("safe_mode", "true")


def test_deploy_container_digest_validation_and_reservation_store(tmp_path):
    from portly.backend.store import Store

    local_store = Store(str(tmp_path / "deploy.db"))
    local_store.set_setting("safe_mode", "false")

    mock_client = MagicMock()
    mock_cont = MagicMock()
    mock_cont.name = "digest_app"
    mock_cont.id = "deadbeef1234"
    mock_client.containers.run.return_value = mock_cont

    seen = []

    def fake_avail(port, bind="0.0.0.0", store=None):
        seen.append((port, bind, store))
        return {"free": True, "used_by": ""}

    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client), \
         patch("portly.backend.actions.docker_actions.check_port_availability", side_effect=fake_avail):
        res = deploy_container(
            image="nginx@sha256:0123456789abcdef0123456789abcdef",
            name="digest_app",
            ports={"80/tcp": 18080},
            env={},
            volumes=[],
            restart_policy="unless-stopped",
            store=local_store,
        )
        assert res["status"] == "deployed"
        assert seen == [(18080, "0.0.0.0", local_store)]

        with pytest.raises(ValueError, match="Invalid restart policy"):
            deploy_container(
                image="nginx:alpine",
                name="bad_policy",
                ports={},
                env={},
                volumes=[],
                restart_policy="bogus",
                store=local_store,
            )


def test_list_compose_stacks_tolerates_malformed_host_port():
    mock_client = MagicMock()
    mock_cont = MagicMock()
    mock_cont.status = "running"
    mock_cont.labels = {"com.docker.compose.project": "stack_malformed"}
    mock_cont.attrs = {
        "NetworkSettings": {
            "Ports": {
                "80/tcp": [{"HostPort": "not-a-number"}, {"HostPort": "8088"}],
            }
        }
    }
    mock_client.containers.list.return_value = [mock_cont]
    store.save_compose_stack("stack_malformed", "services:\n  web:\n    image: nginx:alpine\n")
    try:
        with patch("portly.backend.app.get_docker_client", return_value=mock_client):
            client = TestClient(app)
            res = client.get("/api/stacks")
            assert res.status_code == 200
            stacks = {s["name"]: s for s in res.json()["stacks"]}
            assert stacks["stack_malformed"]["ports"] == [8088]
    finally:
        store.delete_compose_stack("stack_malformed")
