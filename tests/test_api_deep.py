"""Deep integration tests for all Portly API endpoints."""

import os
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from portly.backend import app as app_module
from portly.backend.app import app, store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_app_state():
    # Cache dummy apps for API testing
    app_module._cached_apps = [
        {
            "id": "docker:web:80/tcp",
            "source": "docker",
            "name": "Web Service",
            "container_name": "web",
            "port": 8080,
            "container_port": 80,
            "bind": "0.0.0.0",
            "status": "up",
            "category_id": "web",
            "image": "nginx:alpine",
            "tags": ["prod", "frontend"],
            "cpu_percent": 1.5,
            "ram_mb": 64.0,
            "uptime_sec": 3600,
            "hidden": False,
            "pinned": True,
        },
        {
            "id": "custom:worker",
            "source": "custom",
            "name": "Background Worker",
            "port": 9000,
            "bind": "127.0.0.1",
            "status": "up",
            "category_id": "tools",
            "tags": ["worker"],
            "cpu_percent": 5.0,
            "ram_mb": 128.0,
            "uptime_sec": 7200,
            "hidden": False,
            "pinned": False,
        },
        {
            "id": "host:node:3000",
            "source": "host",
            "name": "Node Dev Server",
            "port": 3000,
            "bind": "127.0.0.1",
            "status": "up",
            "category_id": "uncategorized",
            "process_name": "node.exe",
            "pid": 5432,
            "cpu_percent": 0.5,
            "ram_mb": 96.0,
            "uptime_sec": 1800,
            "hidden": True,
            "pinned": False,
        }
    ]
    app_module._cached_conflicts = []
    store.set_setting("safe_mode", "false")
    yield
    store.set_setting("safe_mode", "true")


def test_get_apps_filters_and_sorting():
    # Filter by source
    res_dock = client.get("/api/apps?source=docker")
    assert res_dock.status_code == 200
    assert len(res_dock.json()["apps"]) == 1
    assert res_dock.json()["apps"][0]["source"] == "docker"

    # Filter by category
    res_cat = client.get("/api/apps?category_id=tools")
    assert res_cat.status_code == 200
    assert len(res_cat.json()["apps"]) == 1
    assert res_cat.json()["apps"][0]["name"] == "Background Worker"

    # Filter by bind
    res_bind = client.get("/api/apps?bind=0.0.0.0")
    assert res_bind.status_code == 200
    assert len(res_bind.json()["apps"]) == 1

    # Search
    res_search = client.get("/api/apps?search=nginx")
    assert res_search.status_code == 200
    assert len(res_search.json()["apps"]) == 1

    # Include hidden
    res_hidden = client.get("/api/apps?include_hidden=true")
    assert res_hidden.status_code == 200
    assert len(res_hidden.json()["apps"]) == 3

    # Sorting
    for sort_field in ["port", "name", "cpu", "ram", "uptime", "status", "category"]:
        res_sort = client.get(f"/api/apps?sort_by={sort_field}&sort_dir=desc&include_hidden=true")
        assert res_sort.status_code == 200


def test_app_detail_and_patch(monkeypatch):
    # Detail existing
    res = client.get("/api/apps/docker:web:80/tcp")
    assert res.status_code == 200
    data = res.json()
    assert data["app"]["name"] == "Web Service"
    assert "health" in data

    # Detail 404
    res_404 = client.get("/api/apps/non_existent_app_xyz")
    assert res_404.status_code == 404

    # Patch app override
    patch_payload = {
        "name": "Renamed Web App",
        "pinned": True,
        "notes": "Critical prod web service"
    }
    res_patch = client.patch("/api/apps/docker:web:80/tcp", json=patch_payload)
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "ok"


def test_bulk_actions():
    # Move
    res_move = client.post("/api/apps/bulk", json={
        "ids": ["docker:web:80/tcp", "custom:worker"],
        "action": "move",
        "category_id": "databases"
    })
    assert res_move.status_code == 200
    assert res_move.json()["count"] == 2

    # Tag
    res_tag = client.post("/api/apps/bulk", json={
        "ids": ["docker:web:80/tcp"],
        "action": "tag",
        "tag": "v1"
    })
    assert res_tag.status_code == 200

    # Pin & Hide
    res_pin = client.post("/api/apps/bulk", json={
        "ids": ["custom:worker"],
        "action": "pin"
    })
    assert res_pin.status_code == 200

    res_hide = client.post("/api/apps/bulk", json={
        "ids": ["custom:worker"],
        "action": "hide"
    })
    assert res_hide.status_code == 200


def test_categories_crud():
    # Create category
    cat_payload = {
        "id": "test_cat",
        "name": "Test Category",
        "color": "#FF5722",
        "mode": "manual",
        "sort_order": 5
    }
    res_create = client.post("/api/categories", json=cat_payload)
    assert res_create.status_code == 200
    assert res_create.json()["name"] == "Test Category"

    # List categories
    res_list = client.get("/api/categories")
    assert res_list.status_code == 200
    assert any(c["id"] == "test_cat" for c in res_list.json())

    # Delete category
    res_del = client.delete("/api/categories/test_cat")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"


def test_rules_crud():
    # Create rule
    rule_payload = {
        "id": "rule_test_1",
        "category_id": "databases",
        "field": "name",
        "operator": "contains",
        "value": "postgres",
        "priority": 1
    }
    res_create = client.post("/api/rules", json=rule_payload)
    assert res_create.status_code == 200
    assert res_create.json()["value"] == "postgres"

    # List rules
    res_list = client.get("/api/rules")
    assert res_list.status_code == 200
    assert any(r["id"] == "rule_test_1" for r in res_list.json())

    # Delete rule
    res_del = client.delete("/api/rules/rule_test_1")
    assert res_del.status_code == 200


def test_views_crud():
    view_payload = {
        "id": "v_custom",
        "name": "Custom Table View",
        "filters": {"source": "docker"},
        "sort": {"field": "port", "dir": "asc"},
        "group_by": "none",
        "view_type": "table",
        "columns": ["port", "name", "source"]
    }
    res_create = client.post("/api/views", json=view_payload)
    assert res_create.status_code == 200

    res_list = client.get("/api/views")
    assert res_list.status_code == 200
    assert any(v["id"] == "v_custom" for v in res_list.json())

    res_del = client.delete("/api/views/v_custom")
    assert res_del.status_code == 200


def test_settings_endpoints():
    res_get = client.get("/api/settings")
    assert res_get.status_code == 200
    assert "safe_mode" in res_get.json()

    res_patch = client.patch("/api/settings", json={"refresh_interval": "5"})
    assert res_patch.status_code == 200
    assert res_patch.json()["refresh_interval"] == "5"


def test_webhook_settings_accept_ui_values():
    res = client.patch("/api/settings", json={
        "webhook_enabled": "true",
        "webhook_type": "telegram",
        "webhook_url": "https://api.telegram.org/bot123/sendMessage?chat_id=42",
    })
    assert res.status_code == 200
    assert res.json()["webhook_enabled"] == "true"
    assert res.json()["webhook_type"] == "telegram"
    assert client.patch("/api/settings", json={"webhook_type": "carrier-pigeon"}).status_code == 400
    client.patch("/api/settings", json={"webhook_enabled": "false", "webhook_type": "generic", "webhook_url": ""})


def test_custom_update_endpoint():
    store.create_custom_app("update_probe", "Update Probe", 19991, update_cmd='python -c "print(42)"')
    try:
        res = client.post("/api/apps/custom:update_probe/update/custom")
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok"
        assert "42" in res.json()["stdout"]
        assert client.post("/api/apps/docker:web:80/tcp/update/custom").status_code == 400
    finally:
        store.delete_custom_app("update_probe")


def test_ports_endpoints():
    # Check port
    res_check = client.get("/api/ports/check?port=9999&bind=127.0.0.1")
    assert res_check.status_code == 200
    assert "free" in res_check.json()

    # Suggest ports
    res_sug = client.get("/api/ports/suggest?start=8000&count=3")
    assert res_sug.status_code == 200
    assert len(res_sug.json()["suggested"]) == 3


def test_system_and_scan():
    res_sys = client.get("/api/system")
    assert res_sys.status_code == 200
    assert "cpu_per_core" in res_sys.json() or "disks" in res_sys.json()

    res_scan = client.post("/api/scan")
    assert res_scan.status_code == 200
    assert res_scan.json()["status"] == "ok"


def test_import_endpoint():
    backup = {
        "categories": [{"id": "imported_cat", "name": "Imported", "color": "#000", "mode": "manual", "sort_order": 1}],
        "rules": [{"id": "rule_imp", "category_id": "imported_cat", "field": "name", "operator": "contains", "value": "test", "priority": 5}],
        "custom_apps": [{
            "id": "imp_app",
            "name": "Imported App",
            "host": "localhost",
            "port": 9100,
            "health_path": "/healthz",
            "health_interval": 10,
            "start_cmd": "echo start",
            "stop_cmd": "echo stop",
            "workdir": "/tmp",
            "log_file": "app.log",
            "start_on_boot": False,
            "env": {"KEY": "VAL"},
            "update_cmd": "echo update",
        }],
        "views": [{"id": "imp_view", "name": "Imp View", "filters": {}, "sort": {}, "group_by": "none", "view_type": "table", "columns": ["name", "port"]}],
        "app_overrides": {"imp_app": {"notes": "Imported notes", "pinned": True}},
        "settings": {"auto_refresh": "true"}
    }
    res = client.post("/api/import", json=backup)
    assert res.status_code == 200
    assert res.json()["status"] == "imported"

    # Verify custom app was actually imported
    imp_app = store.get_custom_app("imp_app")
    assert imp_app is not None
    assert imp_app["port"] == 9100
    assert imp_app["name"] == "Imported App"
    assert imp_app["env"] == {"KEY": "VAL"}


def test_sse_stream_snapshot():
    import asyncio
    import concurrent.futures
    import json
    from unittest.mock import AsyncMock, MagicMock
    from portly.backend.app import sse_stream

    async def _test():
        req = MagicMock()
        req.is_disconnected = AsyncMock(side_effect=[False, True])
        res = await sse_stream(req)
        gen = res.body_iterator
        item = await gen.__anext__()
        assert item["event"] == "message"
        data = json.loads(item["data"])
        assert data["type"] == "snapshot"
        assert "apps" in data
        assert "stats" in data

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _test()).result()
    else:
        asyncio.run(_test())


def test_auth_flow(monkeypatch):
    # Test auth /api/auth/me
    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert "authenticated" in res_me.json()

    # Login failure with bad creds
    res_bad = client.post("/api/auth/login", json={"username": "no_such_user", "password": "wrong"})
    assert res_bad.status_code == 401

    # Logout
    res_logout = client.post("/api/auth/logout")
    assert res_logout.status_code == 200
    assert res_logout.json()["status"] == "logged_out"


def test_bulk_actions_and_safe_mode(monkeypatch):
    # Test bulk actions with safe mode enabled
    store.set_setting("safe_mode", "true")
    res_lock = client.post("/api/apps/bulk", json={
        "ids": ["custom:worker"],
        "action": "restart"
    })
    assert res_lock.status_code == 403
    assert res_lock.json()["detail"]["code"] == "SAFE_MODE"

    # Disable safe mode for mutating bulk actions
    store.set_setting("safe_mode", "false")

    # Mock docker actions and process actions to verify calls
    from portly.backend.actions import docker_actions, process_actions
    mock_start_dock = MagicMock()
    mock_stop_dock = MagicMock()
    mock_restart_dock = MagicMock()
    mock_start_cust = MagicMock()
    mock_stop_cust = MagicMock()
    mock_restart_cust = MagicMock()

    monkeypatch.setattr(docker_actions, "start_container", mock_start_dock)
    monkeypatch.setattr(docker_actions, "stop_container", mock_stop_dock)
    monkeypatch.setattr(docker_actions, "restart_container", mock_restart_dock)
    monkeypatch.setattr(process_actions, "start_custom_app", mock_start_cust)
    monkeypatch.setattr(process_actions, "stop_custom_app", mock_stop_cust)
    monkeypatch.setattr(process_actions, "restart_custom_app", mock_restart_cust)

    # Bulk pin & hide & tag
    res_pin = client.post("/api/apps/bulk", json={"ids": ["custom:worker"], "action": "pin"})
    assert res_pin.status_code == 200

    res_hide = client.post("/api/apps/bulk", json={"ids": ["custom:worker"], "action": "hide"})
    assert res_hide.status_code == 200
    assert store.get_app("custom:worker")["hidden"] == 1

    res_unhide = client.post("/api/apps/bulk", json={"ids": ["custom:worker"], "action": "unhide"})
    assert res_unhide.status_code == 200
    assert res_unhide.json()["succeeded"] == ["custom:worker"]
    assert store.get_app("custom:worker")["hidden"] == 0

    res_tag = client.post("/api/apps/bulk", json={"ids": ["custom:worker"], "action": "tag", "tag": "testtag"})
    assert res_tag.status_code == 200

    # Bulk start
    res_start = client.post("/api/apps/bulk", json={"ids": ["docker:web:80/tcp", "custom:worker"], "action": "start"})
    assert res_start.status_code == 200
    mock_start_dock.assert_called_once_with("web", store)
    mock_start_cust.assert_called_once_with("custom:worker", store)

    # Bulk stop
    res_stop = client.post("/api/apps/bulk", json={"ids": ["docker:web:80/tcp", "custom:worker"], "action": "stop"})
    assert res_stop.status_code == 200
    mock_stop_dock.assert_called_once_with("web", store)
    mock_stop_cust.assert_called_once_with("custom:worker", store)

    # Bulk restart
    res_restart = client.post("/api/apps/bulk", json={"ids": ["docker:web:80/tcp", "custom:worker"], "action": "restart"})
    assert res_restart.status_code == 200
    mock_restart_dock.assert_called_once_with("web", store)
    mock_restart_cust.assert_called_once_with("custom:worker", store)

    # Re-enable safe mode
    store.set_setting("safe_mode", "true")


def test_start_stop_restart_endpoints(monkeypatch):
    store.set_setting("safe_mode", "false")

    monkeypatch.setattr(app_module.docker_actions, "start_container", lambda c, s: {"status": "started", "container": c})
    monkeypatch.setattr(app_module.docker_actions, "stop_container", lambda c, s: {"status": "stopped", "container": c})
    monkeypatch.setattr(app_module.docker_actions, "restart_container", lambda c, s: {"status": "restarted", "container": c})
    monkeypatch.setattr(app_module.process_actions, "start_custom_app", lambda a, s: {"status": "started", "app_id": a})
    monkeypatch.setattr(app_module.process_actions, "stop_custom_app", lambda a, s: {"status": "stopped", "app_id": a})
    monkeypatch.setattr(app_module.process_actions, "restart_custom_app", lambda a, s: {"status": "restarted", "app_id": a})
    monkeypatch.setattr(app_module.process_actions, "kill_host_process", lambda pid, s: {"status": "killed", "pid": pid})

    # Start docker
    res_dock_start = client.post("/api/apps/docker:web:80/tcp/start")
    assert res_dock_start.status_code == 200
    assert res_dock_start.json()["status"] == "started"

    # Start custom
    res_cust_start = client.post("/api/apps/custom:worker/start")
    assert res_cust_start.status_code == 200
    assert res_cust_start.json()["status"] == "started"

    # Start unsupported host
    res_host_start = client.post("/api/apps/host:node:3000/start")
    assert res_host_start.status_code == 400
    assert res_host_start.json()["detail"]["code"] == "NOT_SUPPORTED"

    # Stop docker
    res_dock_stop = client.post("/api/apps/docker:web:80/tcp/stop")
    assert res_dock_stop.status_code == 200
    assert res_dock_stop.json()["status"] == "stopped"

    # Stop custom
    res_cust_stop = client.post("/api/apps/custom:worker/stop")
    assert res_cust_stop.status_code == 200

    # Stop host process
    app_module._cached_apps = [
        {"id": "host:node:3000", "source": "host", "pid": 5432, "name": "node.exe"}
    ]
    async def dummy_refresh():
        pass
    monkeypatch.setattr(app_module, "refresh_discovery", dummy_refresh)
    res_host_stop = client.post("/api/apps/host:node:3000/stop")
    assert res_host_stop.status_code == 200
    assert res_host_stop.json()["status"] == "killed"

    # Stop unknown host process
    res_unknown_stop = client.post("/api/apps/host:unknown:9999/stop")
    assert res_unknown_stop.status_code == 404

    # Restart docker & custom
    res_dock_restart = client.post("/api/apps/docker:web:80/tcp/restart")
    assert res_dock_restart.status_code == 200
    res_cust_restart = client.post("/api/apps/custom:worker/restart")
    assert res_cust_restart.status_code == 200

    # Restart unsupported host
    res_host_restart = client.post("/api/apps/host:node:3000/restart")
    assert res_host_restart.status_code == 400

    store.set_setting("safe_mode", "true")


def test_logs_endpoint(monkeypatch):
    from portly.backend.actions import docker_actions, process_actions
    monkeypatch.setattr(docker_actions, "get_container_logs", lambda c, tail=500, follow=False: ["log line 1", "log line 2"])
    monkeypatch.setattr(process_actions, "get_custom_app_logs", lambda a, s, tail=500: ["custom line 1"])

    # Docker logs
    res_dock_log = client.get("/api/apps/docker:web:80/tcp/logs")
    assert res_dock_log.status_code == 200
    assert len(res_dock_log.json()["lines"]) == 2

    # Custom logs
    res_cust_log = client.get("/api/apps/custom:worker/logs")
    assert res_cust_log.status_code == 200
    assert len(res_cust_log.json()["lines"]) == 1

    # Host logs
    res_host_log = client.get("/api/apps/host:node:3000/logs")
    assert res_host_log.status_code == 200
    assert "Direct log capture is not available" in res_host_log.json()["lines"][0]


def test_custom_apps_crud(tmp_path):
    # 1. Reject unsafe log file path
    res_bad_log = client.post("/api/custom-apps", json={
        "name": "BadApp",
        "port": 9100,
        "log_file": "/etc/shadow"
    })
    assert res_bad_log.status_code == 400
    assert res_bad_log.json()["detail"]["code"] == "INVALID_LOG_PATH"

    # 2. Create custom app with safe log file path
    safe_log = str(tmp_path / "myapp.log")
    res_create = client.post("/api/custom-apps", json={
        "name": "MySafeApp",
        "port": 9100,
        "log_file": safe_log,
        "start_cmd": "python app.py"
    })
    assert res_create.status_code == 200
    app_id = res_create.json()["id"]

    # 3. List custom apps
    res_list = client.get("/api/custom-apps")
    assert res_list.status_code == 200
    assert any(a["id"] == app_id for a in res_list.json())

    # 4. Delete custom app
    res_del = client.delete(f"/api/custom-apps/{app_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # 5. Delete nonexistent custom app (idempotent 200)
    res_del_none = client.delete("/api/custom-apps/nonexistent_xyz")
    assert res_del_none.status_code == 200
    assert res_del_none.json()["status"] == "deleted"


def test_port_change_api_execution(monkeypatch):
    # 1. Invalid port plan returns 400
    res_invalid = client.post("/api/apps/custom:worker/port", json={
        "host_port": 999999,
        "bind": "0.0.0.0"
    })
    assert res_invalid.status_code == 400
    assert res_invalid.json()["detail"]["code"] == "INVALID_PLAN"

    # 2. Plan only (apply=false)
    monkeypatch.setattr(
        "portly.backend.app.plan_port_change",
        lambda a, p, b, s: {
            "valid": True,
            "error": "",
            "plan": {"type": "docker", "container_name": "web", "target_container_port": "80/tcp", "steps": []}
        }
    )
    res_plan = client.post("/api/apps/docker:web:80/tcp/port?apply=false", json={
        "host_port": 8081,
        "bind": "0.0.0.0"
    })
    assert res_plan.status_code == 200
    assert "plan" in res_plan.json()

    # 3. Safe mode locked on apply=true
    store.set_setting("safe_mode", "true")
    res_lock = client.post("/api/apps/docker:web:80/tcp/port?apply=true", json={
        "host_port": 8081,
        "bind": "0.0.0.0"
    })
    assert res_lock.status_code == 403
    assert res_lock.json()["detail"]["code"] == "SAFE_MODE"

    # 4. Apply=true docker with safe mode off
    store.set_setting("safe_mode", "false")
    from portly.backend.actions import docker_actions, process_actions
    monkeypatch.setattr(
        docker_actions,
        "apply_port_change_docker",
        lambda c, hp, cp, b, s: {"status": "success", "new_port": hp}
    )
    res_apply_dock = client.post("/api/apps/docker:web:80/tcp/port?apply=true", json={
        "host_port": 8081,
        "bind": "0.0.0.0"
    })
    assert res_apply_dock.status_code == 200
    assert res_apply_dock.json()["status"] == "success"

    # 5. Apply=true custom app
    monkeypatch.setattr(
        "portly.backend.app.plan_port_change",
        lambda a, p, b, s: {
            "valid": True,
            "error": "",
            "plan": {"type": "custom", "name": "Worker"}
        }
    )
    monkeypatch.setattr(process_actions, "restart_custom_app", lambda a, s: {"status": "restarted"})
    res_apply_cust = client.post("/api/apps/custom:worker/port?apply=true", json={
        "host_port": 9005,
        "bind": "127.0.0.1"
    })
    assert res_apply_cust.status_code == 200
    assert res_apply_cust.json()["new_port"] == 9005

    # 6. Rollback unsupported on non-docker
    res_roll_cust = client.post("/api/apps/custom:worker/port?rollback=true", json={"host_port": 9005})
    assert res_roll_cust.status_code == 400
    assert res_roll_cust.json()["detail"]["code"] == "NOT_SUPPORTED"

    # Snapshot rollback for docker
    monkeypatch.setattr(
        docker_actions,
        "rollback_port_change_docker",
        lambda app_id, s: {"status": "rolled_back", "port": 8080}
    )
    res_roll_ok = client.post("/api/apps/docker:web:80/tcp/port?rollback=true", json={"host_port": 8080})
    assert res_roll_ok.status_code == 200
    assert res_roll_ok.json()["status"] == "rolled_back"

    store.set_setting("safe_mode", "true")


def test_image_update_endpoints(monkeypatch):
    from portly.backend.actions import docker_actions
    monkeypatch.setattr(docker_actions, "check_image_update", lambda img: {"update_available": True, "image": img})

    # Check update for docker app
    res_check = client.post("/api/apps/docker:web:80/tcp/update/check")
    assert res_check.status_code == 200
    assert res_check.json()["update_available"] is True

    # Check update for app without image tag
    res_check_none = client.post("/api/apps/custom:worker/update/check")
    assert res_check_none.status_code == 404

    # Apply update with safe mode on
    store.set_setting("safe_mode", "true")
    res_apply_lock = client.post("/api/apps/docker:web:80/tcp/update/apply")
    assert res_apply_lock.status_code == 403

    # Apply update with safe mode off
    store.set_setting("safe_mode", "false")
    res_apply_ok = client.post("/api/apps/docker:web:80/tcp/update/apply")
    assert res_apply_ok.status_code == 200
    store.set_setting("safe_mode", "true")


def test_admin_setup_and_login_lifecycle(monkeypatch):
    # Setup when user count == 0
    monkeypatch.setattr(store, "get_user_count", lambda: 0)
    monkeypatch.setattr(store, "create_user", lambda uid, uname, pwhash, role: {"id": uid, "username": uname, "role": role})

    res_setup = client.post("/api/auth/setup", json={"username": "superadmin", "password": "securepassword123"})
    assert res_setup.status_code == 200
    assert res_setup.json()["username"] == "superadmin"
    assert "portly_session" in res_setup.cookies

    # Setup when user count > 0 returns 400
    monkeypatch.setattr(store, "get_user_count", lambda: 1)
    res_setup_dup = client.post("/api/auth/setup", json={"username": "superadmin", "password": "securepassword123"})
    assert res_setup_dup.status_code == 400
    assert res_setup_dup.json()["detail"]["code"] == "SETUP_DONE"

