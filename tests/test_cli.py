"""Tests for Portly CLI."""

import json
import sys
from unittest.mock import MagicMock
import pytest
from portly import cli
from portly.backend.store import Store


def test_cli_list(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["portly", "list"])
    cli.main()
    captured = capsys.readouterr()
    assert "PORT" in captured.out
    assert "NAME" in captured.out
    assert "SOURCE" in captured.out


def test_cli_list_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["portly", "list", "--json"])
    cli.main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "apps" in data
    assert "conflicts" in data


def test_cli_list_docker_and_host(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["portly", "list", "--docker"])
    cli.main()
    captured = capsys.readouterr()
    assert "PORT" in captured.out

    monkeypatch.setattr(sys, "argv", ["portly", "list", "--host-only"])
    cli.main()
    captured2 = capsys.readouterr()
    assert "PORT" in captured2.out


def test_cli_run_insecure_bind_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["portly", "run", "--host", "0.0.0.0", "--mode", "desktop"])
    monkeypatch.setenv("PORTLY_ALLOW_INSECURE_BIND", "false")
    monkeypatch.setattr(Store, "get_user_count", lambda self: 0)

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1


def test_cli_run_success(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["portly", "run", "--host", "127.0.0.1", "--port", "5533"])
    mock_uvicorn = MagicMock()
    monkeypatch.setattr(cli.uvicorn, "run", mock_uvicorn)

    cli.main()
    assert mock_uvicorn.called
    assert mock_uvicorn.call_args[1]["host"] == "127.0.0.1"
    assert mock_uvicorn.call_args[1]["port"] == 5533


def test_cli_start_and_stop_not_found(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["portly", "start", "non_existent_app_999"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1

    monkeypatch.setattr(sys, "argv", ["portly", "stop", "non_existent_app_999"])
    with pytest.raises(SystemExit) as exc2:
        cli.main()
    assert exc2.value.code == 1


def test_cli_start_and_stop_app(monkeypatch, tmp_path):
    # Mock merge_discovered_apps to return an app
    fake_app = {"id": "custom:dummy", "name": "dummy", "source": "custom", "port": 7000}
    monkeypatch.setattr(cli, "merge_discovered_apps", lambda store: ([fake_app], []))

    from portly.backend.actions import process_actions
    monkeypatch.setattr(process_actions, "start_custom_app", lambda app_id, store: {"status": "started"})
    monkeypatch.setattr(process_actions, "stop_custom_app", lambda app_id, store: {"status": "stopped"})

    monkeypatch.setattr(sys, "argv", ["portly", "start", "dummy"])
    cli.main()

    monkeypatch.setattr(sys, "argv", ["portly", "stop", "dummy"])
    cli.main()
