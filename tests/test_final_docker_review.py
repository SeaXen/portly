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


def test_brand_favicons_and_icons_exist_and_nonempty():
    public_dir = Path(__file__).resolve().parent.parent / "portly" / "frontend" / "public"
    for rel in (
        "favicon.ico",
        "icons/icon.svg",
        "icons/icon-32.png",
        "icons/apple-touch-icon.png",
        "icons/icon-192.png",
        "icons/icon-512.png",
    ):
        asset = public_dir / rel
        assert asset.is_file(), f"Missing asset: {rel}"
        assert asset.stat().st_size > 0, f"Empty asset: {rel}"


def test_store_batch_health_lookup_used_by_merge(tmp_path, monkeypatch):
    from portly.backend.discovery import merge
    from portly.backend.store import Store

    local_store = Store(str(tmp_path / "perf.db"))
    local_store.upsert_custom_app("c1", "Svc One", "localhost", 19101)
    local_store.upsert_custom_app("c2", "Svc Two", "localhost", 19102)
    local_store.record_health("custom:c1", True, 3.2)
    local_store.record_health("custom:c2", False, 12.5)

    batch = local_store.get_all_latest_health()
    assert batch["custom:c1"]["ok"] is True
    assert batch["custom:c2"]["ok"] is False

    # Confirm merge uses batched lookup without falling back to per-app get_latest_health
    def fail_per_app(_app_id):
        raise AssertionError("Per-app N+1 query should not be called when get_all_latest_health exists")

    monkeypatch.setattr(local_store, "get_latest_health", fail_per_app)
    monkeypatch.setattr(merge, "discover_host_ports", lambda: [])
    monkeypatch.setattr(merge, "discover_docker_containers", lambda: [])

    apps, _ = merge.merge_discovered_apps(local_store)
    by_id = {a["id"]: a for a in apps}
    assert by_id["custom:c1"]["status"] == "up"
    assert by_id["custom:c2"]["status"] == "down"


def test_docker_stats_collector_reuses_executor_and_skips_empty():
    from portly.backend.discovery import docker_src

    assert docker_src._collect_running_container_stats([]) == set()
    ex1 = docker_src._get_stats_executor()
    ex2 = docker_src._get_stats_executor()
    assert ex1 is ex2


def test_host_process_metadata_cached_across_samples(monkeypatch):
    import psutil
    from portly.backend.discovery import host

    calls = {"cmdline": 0, "cwd": 0, "name": 0}

    class CachedProc:
        def __init__(self, _pid):
            pass

        def is_running(self):
            return True

        def create_time(self):
            return 1000.0

        def name(self):
            calls["name"] += 1
            return "worker"

        def cmdline(self):
            calls["cmdline"] += 1
            return ["python", "-m", "worker"]

        def cwd(self):
            calls["cwd"] += 1
            return "/opt/worker"

        def cpu_percent(self, interval=None):
            return 1.5

        def memory_info(self):
            return type("Mem", (), {"rss": 16 * 1024 * 1024})()

    host._proc_instances.clear()
    try:
        monkeypatch.setattr(psutil, "Process", CachedProc)
        first = host._get_process_info(424242)
        second = host._get_process_info(424242)
        assert first["name"] == "worker"
        assert second["cmdline"] == "python -m worker"
        assert second["cwd"] == "/opt/worker"
        assert calls == {"cmdline": 1, "cwd": 1, "name": 1}
    finally:
        host._proc_instances.clear()


def test_discover_docker_avoids_lazy_image_inspect_for_tagged_containers(monkeypatch):
    from portly.backend.discovery import docker_src

    class NoLazyImageContainer:
        id = "cont1234567890"
        name = "web"
        status = "running"
        labels = {}
        attrs = {
            "Config": {"Image": "nginx:1.27-alpine"},
            "NetworkSettings": {"Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8099"}]}},
            "State": {"Status": "running"},
        }

        @property
        def image(self):
            raise AssertionError("c.image should not be queried when Config.Image has a tag")

    fake_client = MagicMock()
    fake_client.containers.list.return_value = [NoLazyImageContainer()]
    monkeypatch.setattr(docker_src, "get_docker_client", lambda force_retry=False: fake_client)
    monkeypatch.setattr(docker_src, "_docker_available", True)

    apps = docker_src.discover_docker_containers()
    assert len(apps) == 1
    assert apps[0]["image"] == "nginx:1.27-alpine"
    assert docker_src._background_workers_enabled is False


