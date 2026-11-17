"""Process lifecycle actions, subprocess management, and log tailing for custom and local apps."""

import collections
import logging
import os
import platform
import shlex
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

import psutil

from portly.backend.store import Store

logger = logging.getLogger("portly.process_actions")

# In-memory registry of running processes started by Portly
_running_processes: Dict[str, subprocess.Popen] = {}
# Log buffer: app_id -> deque of lines
_log_buffers: Dict[str, collections.deque] = {}
_lock = threading.Lock()


CRITICAL_PROCESS_NAMES = {
    # Windows core & system processes
    "system", "system idle process", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "lsm.exe", "winlogon.exe", "svchost.exe",
    "fontdrvhost.exe", "dwm.exe", "registry", "memory compression",
    # Linux / Unix core & init processes
    "init", "systemd", "systemd-journald", "systemd-udevd", "systemd-logind",
    "kthreadd", "kworker", "launchd",
    # Infrastructure and critical daemons
    "sshd", "dockerd", "containerd", "docker-proxy", "docker", "portly"
}


def _get_allowed_log_roots(workdir: Optional[str] = None) -> List[str]:
    """Builds an allowlist of directories where log files are permitted."""
    roots = []
    # 1. Custom configured log roots from environment
    env_dirs = os.environ.get("PORTLY_LOG_DIRS", "")
    for p in env_dirs.split(","):
        p = p.strip()
        if p and os.path.isdir(p):
            roots.append(os.path.realpath(p))

    # 2. Portly data directory and logs subdir
    data_dir = os.environ.get("PORTLY_DATA_DIR", "")
    if not data_dir:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    if os.path.isdir(data_dir):
        roots.append(os.path.realpath(data_dir))
        logs_dir = os.path.join(data_dir, "logs")
        if os.path.isdir(logs_dir):
            roots.append(os.path.realpath(logs_dir))

    # 3. Workdir of the app if valid
    if workdir and os.path.isdir(workdir):
        roots.append(os.path.realpath(workdir))

    # 4. Standard OS log directories
    if platform.system() != "Windows":
        if os.path.isdir("/var/log"):
            roots.append(os.path.realpath("/var/log"))
    else:
        system_drive = os.environ.get("SystemDrive", "C:")
        sys_logs = os.path.join(system_drive, "\\Logs")
        if os.path.isdir(sys_logs):
            roots.append(os.path.realpath(sys_logs))

    # 5. System temp directory (used for temporary logs and test suites)
    try:
        tmp_dir = tempfile.gettempdir()
        if os.path.isdir(tmp_dir):
            roots.append(os.path.realpath(tmp_dir))
    except Exception:
        pass

    return roots


def _is_safe_log_path(path: str, workdir: Optional[str] = None) -> bool:
    """
    Validates log path using an allowlist of permitted directories,
    resolving symlinks and blocking sensitive files.
    """
    if not path or not isinstance(path, str):
        return False
    if "\0" in path:
        return False

    try:
        norm_path = os.path.abspath(os.path.realpath(path.replace("\\", os.sep)))
        lower = norm_path.lower().replace("\\", "/")

        # Block credential & secret file patterns anywhere
        blocked_names = (
            ".bash_history", ".zsh_history", ".history", "shadow", "passwd",
            "id_rsa", "id_ed25519", "credentials", ".docker/config.json",
            "sam", "system32/config", "auth.log", "secure", "wtmp", "btmp",
            "lastlog", "audit.log", "tallylog", "faillog", ".bashrc", ".profile", ".zshrc"
        )
        base_name = os.path.basename(lower)
        for b in blocked_names:
            if (
                lower.endswith(b)
                or f"/{b}" in lower
                or base_name == b
                or base_name.startswith(f"{b}.")
                or base_name.startswith(f"{b}-")
            ):
                return False

        # Block database and sensitive extensions
        blocked_extensions = (
            ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm",
            ".key", ".pem", ".env", ".crt", ".pfx", ".p12", ".cer", ".token", ".secret"
        )
        for ext in blocked_extensions:
            if lower.endswith(ext):
                return False

        # Verify path falls under at least one allowed root directory
        allowed_roots = _get_allowed_log_roots(workdir)
        for root in allowed_roots:
            try:
                common = os.path.commonpath([norm_path, root])
                if common == root:
                    return True
            except ValueError:
                continue

        # If path is inside current working directory or relative to app dir
        cwd = os.path.realpath(os.getcwd())
        try:
            if os.path.commonpath([norm_path, cwd]) == cwd:
                return True
        except ValueError:
            pass

        return False
    except Exception:
        return False


def _check_safe_mode(store: Store):
    safe_mode = store.get_setting("safe_mode", "true").lower() == "true"
    if safe_mode:
        raise PermissionError("Safe mode is active. Mutating actions (start, stop, restart, kill) are locked.")


def _read_output_stream(app_id: str, proc: subprocess.Popen, log_file: Optional[str] = None):
    log_fp = None
    if log_file and _is_safe_log_path(log_file):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            log_fp = open(log_file, "a", encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to open log file {log_file}: {e}")

    with _lock:
        if app_id not in _log_buffers:
            _log_buffers[app_id] = collections.deque(maxlen=2000)

    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            line_str = line.rstrip("\r\n")
            with _lock:
                _log_buffers[app_id].append(line_str)
            if log_fp:
                log_fp.write(line_str + "\n")
                log_fp.flush()
    except Exception:
        pass
    finally:
        if log_fp:
            try:
                log_fp.close()
            except Exception:
                pass


def start_custom_app(app_id: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    _check_safe_mode(store)
    clean_id = app_id.replace("custom:", "")
    custom_app = store.get_custom_app(clean_id)
    if not custom_app:
        raise ValueError(f"Custom app '{clean_id}' not found.")

    start_cmd = custom_app.get("start_cmd")
    if not start_cmd:
        raise ValueError("No start command configured for this app.")

    # Substitute {port} placeholder if present
    port = custom_app.get("port", 3000)
    cmd = start_cmd.replace("{port}", str(port))

    # Environment variables
    env = os.environ.copy()
    env["PORT"] = str(port)
    for k, v in custom_app.get("env", {}).items():
        env[str(k)] = str(v)

    workdir = custom_app.get("workdir") or None
    if workdir and not os.path.isdir(workdir):
        workdir = None

    with _lock:
        # Check if already running
        existing = _running_processes.get(app_id)
        if existing and existing.poll() is None:
            return {"status": "already_running", "pid": existing.pid}

        # Clear existing in-memory log buffer on fresh start
        if app_id in _log_buffers:
            _log_buffers[app_id].clear()

        # Start process with detached session / process group
        creationflags = 0
        start_new_session = False
        if platform.system() == "Windows":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=workdir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
            _running_processes[app_id] = proc
        except Exception as e:
            raise RuntimeError(f"Failed to start process: {e}")

    # Launch log reader thread
    t = threading.Thread(
        target=_read_output_stream,
        args=(app_id, proc, custom_app.get("log_file")),
        daemon=True,
        name=f"log-reader-{clean_id}"
    )
    t.start()

    store.log_event("custom_app_start", f"Started app '{custom_app['name']}' (PID {proc.pid})", app_id=app_id, actor=actor)
    return {"status": "started", "pid": proc.pid, "name": custom_app["name"]}


def stop_custom_app(app_id: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    _check_safe_mode(store)
    clean_id = app_id.replace("custom:", "")
    custom_app = store.get_custom_app(clean_id)
    name = custom_app["name"] if custom_app else clean_id
    workdir = custom_app.get("workdir") if custom_app else None

    stop_cmd = custom_app.get("stop_cmd") if custom_app else None

    with _lock:
        proc = _running_processes.pop(app_id, None)

    if proc and proc.poll() is None:
        try:
            parent = psutil.Process(proc.pid)
            # Terminate entire process tree
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except Exception:
                    pass
            parent.terminate()
            gone, alive = psutil.wait_procs(children + [parent], timeout=3.0)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass

    if stop_cmd and stop_cmd.lower() != "auto":
        try:
            env = os.environ.copy()
            if custom_app and custom_app.get("port"):
                env["PORT"] = str(custom_app["port"])
            if custom_app and custom_app.get("env"):
                for k, v in custom_app["env"].items():
                    env[str(k)] = str(v)
            subprocess.run(stop_cmd, shell=True, timeout=5, cwd=workdir, env=env)
        except Exception as e:
            logger.warning(f"Custom stop command failed: {e}")

    store.log_event("custom_app_stop", f"Stopped app '{name}'", app_id=app_id, actor=actor)
    return {"status": "stopped", "name": name}


def restart_custom_app(app_id: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    _check_safe_mode(store)
    stop_custom_app(app_id, store, actor=actor)
    time.sleep(0.5)
    return start_custom_app(app_id, store, actor=actor)


def get_custom_app_logs(app_id: str, store: Store, tail: int = 500) -> List[str]:
    clean_id = app_id.replace("custom:", "")
    custom_app = store.get_custom_app(clean_id)

    # 1. Check in-memory log buffer first
    with _lock:
        buf = _log_buffers.get(app_id) or _log_buffers.get(clean_id)
        if buf and len(buf) > 0:
            lines = list(buf)
            return lines[-tail:]

    # 2. Check configured log_file safely with tail seek
    if custom_app and custom_app.get("log_file"):
        path = custom_app["log_file"]
        workdir = custom_app.get("workdir")
        if not _is_safe_log_path(path, workdir=workdir):
            return [f"Access denied: Log file path '{path}' is not within an allowed directory."]
        if os.path.isfile(path):
            try:
                size = os.path.getsize(path)
                # Seek tail of file to avoid reading large files into memory
                read_size = min(size, 524288)  # Read up to last 512 KB
                with open(path, "rb") as f:
                    if size > read_size:
                        f.seek(size - read_size)
                    content = f.read().decode("utf-8", errors="replace")
                    lines = [l.rstrip("\r\n") for l in content.splitlines()]
                    return lines[-tail:]
            except Exception as e:
                return [f"Error reading log file {path}: {e}"]

    return [f"No logs recorded yet for {clean_id}."]


def kill_host_process(pid: int, store: Store, actor: str = "system") -> Dict[str, Any]:
    _check_safe_mode(store)
    if pid <= 4:
        raise ValueError("Cannot terminate system core process.")
    if pid == os.getpid():
        raise ValueError("Cannot terminate Portly process itself.")
    try:
        p = psutil.Process(pid)
        name = p.name()
        name_lower = name.lower()
        name_clean = name_lower.removesuffix(".exe")
        if (
            name_lower in CRITICAL_PROCESS_NAMES
            or name_clean in CRITICAL_PROCESS_NAMES
            or name_clean.startswith("systemd")
        ):
            raise ValueError(f"Cannot terminate critical system process '{name}' (PID {pid}).")

        # Escalate SIGTERM -> SIGKILL
        p.terminate()
        try:
            p.wait(timeout=3.0)
        except psutil.TimeoutExpired:
            p.kill()

        store.log_event("kill_process", f"Killed process {name} (PID {pid})", actor=actor)
        return {"status": "killed", "pid": pid, "name": name}
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to kill process {pid}: {e}")
