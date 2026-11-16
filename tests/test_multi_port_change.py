import pytest
from unittest.mock import MagicMock, patch
from portly.backend.actions.docker_actions import apply_multi_port_change_docker
from portly.backend.store import Store


def test_apply_multi_port_change_safe_mode(tmp_path):
    db_file = str(tmp_path / "test.db")
    store = Store(db_file)
    store.set_setting("safe_mode", "true")

    with pytest.raises(PermissionError, match="Safe mode is active"):
        apply_multi_port_change_docker("my_container", [{"container_port": "80/tcp", "host_port": 8080}], store)


def test_apply_multi_port_change_docker(tmp_path):
    db_file = str(tmp_path / "test.db")
    store = Store(db_file)
    store.set_setting("safe_mode", "false")

    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.name = "my_container"
    mock_container.attrs = {
        "Config": {"Image": "nginx:latest", "Env": ["ENV=prod"], "Labels": {}},
        "HostConfig": {
            "PortBindings": {
                "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "80"}],
                "443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"}]
            },
            "Binds": [],
            "RestartPolicy": {}
        },
        "NetworkSettings": {"Networks": {"bridge": {}}},
        "Mounts": []
    }
    mock_client.containers.get.return_value = mock_container
    mock_new_container = MagicMock()
    mock_new_container.name = "my_container"
    mock_client.containers.run.return_value = mock_new_container

    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client):
        with patch("portly.backend.actions.docker_actions.check_port_availability", return_value={"free": True, "used_by": ""}):
            res = apply_multi_port_change_docker(
                "my_container",
                [
                    {"container_port": "80/tcp", "host_port": 8080, "bind": "0.0.0.0"},
                    {"container_port": "443/tcp", "host_port": 8443, "bind": "0.0.0.0"}
                ],
                store
            )

            assert res["status"] == "recreated"
            assert res["container"] == "my_container"
            assert len(res["mappings"]) == 2
            mock_client.containers.run.assert_called_once()
            call_kwargs = mock_client.containers.run.call_args[1]
            assert call_kwargs["ports"]["80/tcp"] == [{"HostIp": "0.0.0.0", "HostPort": "8080"}]
            assert call_kwargs["ports"]["443/tcp"] == [{"HostIp": "0.0.0.0", "HostPort": "8443"}]


def test_api_multi_port_change_safe_mode():
    from fastapi.testclient import TestClient
    from portly.backend.app import app, store
    client = TestClient(app)
    store.set_setting("safe_mode", "true")

    res = client.post(
        "/api/apps/docker:my_test_container:80/ports-multi",
        json={"mappings": [{"container_port": "80/tcp", "host_port": 8888, "bind": "0.0.0.0"}]}
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "SAFE_MODE"

