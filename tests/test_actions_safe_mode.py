"""Tests for Safe Mode security enforcement."""

import pytest
from portly.backend.actions import docker_actions, process_actions
from portly.backend.store import Store


def test_safe_mode_blocks_process_mutations(tmp_path):
    db_file = str(tmp_path / "test_portly.db")
    store = Store(db_file)
    store.set_setting("safe_mode", "true")

    # Start custom app should raise PermissionError
    with pytest.raises(PermissionError, match="Safe mode is active"):
        process_actions.start_custom_app("custom:dummy", store)

    # Stop should raise PermissionError
    with pytest.raises(PermissionError, match="Safe mode is active"):
        process_actions.stop_custom_app("custom:dummy", store)

    # Kill should raise PermissionError
    with pytest.raises(PermissionError, match="Safe mode is active"):
        process_actions.kill_host_process(12345, store)


def test_safe_mode_blocks_docker_mutations(tmp_path):
    db_file = str(tmp_path / "test_portly.db")
    store = Store(db_file)
    store.set_setting("safe_mode", "true")

    with pytest.raises(PermissionError, match="Safe mode is active"):
        docker_actions.start_container("dummy", store)

    with pytest.raises(PermissionError, match="Safe mode is active"):
        docker_actions.stop_container("dummy", store)

    with pytest.raises(PermissionError, match="Safe mode is active"):
        docker_actions.restart_container("dummy", store)
