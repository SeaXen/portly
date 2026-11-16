import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from portly.backend.actions.docker_actions import (
    get_docker_system_df,
    list_docker_images,
    list_docker_volumes,
    prune_docker_system,
)
from portly.backend.store import Store
from portly.backend.app import app


def test_docker_system_df(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    mock_client = MagicMock()
    mock_client.df.return_value = {
        "LayersSize": 1000000,
        "Images": [{"Id": "img1", "Size": 500000}],
        "Containers": [{"Id": "c1"}],
        "Volumes": [{"Name": "vol1", "UsageData": {"Size": 200000}}],
        "BuildCache": []
    }
    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client):
        res = get_docker_system_df(store)
        assert res["images_count"] == 1
        assert res["containers_count"] == 1
        assert res["volumes_count"] == 1
        assert res["total_reclaimable_mb"] >= 0


def test_list_docker_images_and_volumes(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    mock_client = MagicMock()
    mock_img = MagicMock()
    mock_img.id = "sha256:1234567890abcdef"
    mock_img.tags = ["my-app:v1"]
    mock_img.attrs = {"Size": 104857600, "Created": "2026-11-15T00:00:00Z"}
    mock_client.images.list.return_value = [mock_img]

    mock_vol = MagicMock()
    mock_vol.name = "my_volume"
    mock_vol.attrs = {"Driver": "local", "Mountpoint": "/var/lib/docker/volumes/my_volume/_data"}
    mock_client.volumes.list.return_value = [mock_vol]

    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client):
        imgs = list_docker_images(store)
        assert len(imgs) == 1
        assert imgs[0]["tags"] == ["my-app:v1"]
        assert imgs[0]["size_mb"] == 100.0

        vols = list_docker_volumes(store)
        assert len(vols) == 1
        assert vols[0]["name"] == "my_volume"


def test_prune_docker_system_safe_mode(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    store.set_setting("safe_mode", "true")

    with pytest.raises(PermissionError, match="Safe mode is active"):
        prune_docker_system(store)


def test_prune_docker_system_success(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    store.set_setting("safe_mode", "false")

    mock_client = MagicMock()
    mock_client.containers.prune.return_value = {"ContainersDeleted": ["c1"], "SpaceReclaimed": 50000}
    mock_client.images.prune.return_value = {"ImagesDeleted": ["img1"], "SpaceReclaimed": 100000}
    mock_client.volumes.prune.return_value = {"VolumesDeleted": ["v1"], "SpaceReclaimed": 20000}
    mock_client.networks.prune.return_value = {"NetworksDeleted": ["net1"]}

    with patch("portly.backend.actions.docker_actions.get_docker_client", return_value=mock_client):
        res = prune_docker_system(store)
        assert res["space_reclaimed_mb"] >= 0
        assert "c1" in res["deleted"]["containers"]
