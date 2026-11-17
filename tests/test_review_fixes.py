"""Regression tests for the publish-readiness review fixes."""

from starlette.testclient import TestClient

from portly.backend import app as app_module
from portly.backend.actions.docker_actions import SAFE_COMMAND_BINARIES
from portly.backend.store import Store


def test_import_rejects_malformed_backup_without_writing(tmp_path):
    test_store = Store(str(tmp_path / "import.db"))
    orig = app_module.store
    app_module.store = test_store
    try:
        before = test_store.get_categories()
        client = TestClient(app_module.app)
        res = client.post("/api/import", json={"categories": [{"id": "broken"}], "rules": []})
        assert res.status_code == 400
        assert res.json()["detail"]["code"] == "INVALID_BACKUP"
        assert test_store.get_categories() == before
    finally:
        app_module.store = orig


def test_ls_is_not_an_allowed_diagnostic_command():
    assert "ls" not in SAFE_COMMAND_BINARIES
