import pytest
from unittest.mock import MagicMock, patch
from portly.backend.actions.docker_actions import manage_compose_stack, deploy_container
from portly.backend.store import Store


def test_manage_compose_stack_safe_mode(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    store.set_setting("safe_mode", "true")

    with pytest.raises(PermissionError, match="Safe mode is active"):
        manage_compose_stack("my_stack", "restart", store)


def test_manage_compose_stack_restart(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    store.set_setting("safe_mode", "false")

    mock_client = MagicMock()
    mock_c1 = MagicMock()
    mock_c1.name = "web"
    mock_c1.labels = {"com.docker.compose.project": "my_stack"}
    mock_c2 = MagicMock()
    mock_c2.name = "db"
    mock_c2.labels = {"com.docker.compose.project": "my_stack"}
    mock_client.containers.list.return_value = [mock_c1, mock_c2]

    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client):
        res = manage_compose_stack("my_stack", "restart", store)
        assert res["status"] == "ok"
        assert res["action"] == "restart"
        assert len(res["affected_containers"]) == 2
        mock_c1.restart.assert_called_once()
        mock_c2.restart.assert_called_once()


def test_deploy_container_safe_mode(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    store.set_setting("safe_mode", "true")

    with pytest.raises(PermissionError, match="Safe mode is active"):
        deploy_container("redis:alpine", "my_redis", {"6379/tcp": 6379}, {}, [], "unless-stopped", store)


def test_deploy_container_success(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    store.set_setting("safe_mode", "false")

    mock_client = MagicMock()
    mock_cont = MagicMock()
    mock_cont.name = "my_redis"
    mock_cont.id = "abcdef123456"
    mock_client.containers.run.return_value = mock_cont

    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client):
        with patch("portly.backend.actions.docker_actions.check_port_availability", return_value={"free": True, "used_by": ""}):
            res = deploy_container(
                image="redis:alpine",
                name="my_redis",
                ports={"6379/tcp": 6379},
                env={"REDIS_PORT": "6379"},
                volumes=[],
                restart_policy="unless-stopped",
                store=store
            )
            assert res["status"] == "deployed"
            assert res["container"] == "my_redis"
            mock_client.containers.run.assert_called_once()


def test_api_compose_and_deploy_safe_mode():
    from fastapi.testclient import TestClient
    from portly.backend.app import app, store
    client = TestClient(app)
    store.set_setting("safe_mode", "true")

    res_compose = client.post("/api/docker/compose/my_stack/action", json={"action": "restart"})
    assert res_compose.status_code == 403

    res_deploy = client.post("/api/docker/containers/deploy", json={
        "image": "redis:alpine",
        "name": "my_redis",
        "ports": {"6379/tcp": 6379}
    })
    assert res_deploy.status_code == 403

