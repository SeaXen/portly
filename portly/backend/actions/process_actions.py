"""Process lifecycle actions, subprocess management, and log tailing for custom and local apps."""

import collections
import logging
import os
import shlex
import subprocess
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
    "kthreadd", "kworker", "launchd"
}


def _is_safe_log_path(path: str) -> bool:
    if not path or not isinstance(path, str):
        return False
    if "\0" in path:
        return False
    try:
        import posixpath
        # Normalize separators for cross-platform resolution
        norm = os.path.abspath(os.path.realpath(path.replace("\\", os.sep)))
        lower = norm.lower().replace("\\", "/")
        raw_lower = path.strip().lower().replace("\\", "/")
        norm_posix = posixpath.normpath("/" + raw_lower.lstrip("/"))

        # Strip Windows drive letter (e.g. "c:" or "d:") to get absolute POSIX-like path
        path_without_drive = lower
        if len(lower) >= 2 and lower[1] == ":" and lower[0].isalpha():
            path_without_drive = lower[2:]

        # Forbidden system root directories (checked on canonical, posix, and raw paths)
        forbidden_system_dirs = (
            "/etc", "/var", "/proc", "/sys", "/dev", "/root", "/bin", "/sbin", "/boot", "/lib",
            "/windows", "/winnt", "/program files", "/program files (x86)", "/programdata",
            "/system volume information"
        )
        for fdir in forbidden_system_dirs:
            if (
                path_without_drive.startswith(fdir + "/") or path_without_drive == fdir
                or raw_lower.startswith(fdir + "/") or raw_lower == fdir
                or norm_posix.startswith(fdir + "/") or norm_posix == fdir
                or lower.startswith(fdir + "/") or lower == fdir
            ):
                return False

        # Windows system paths
        system_root = os.environ.get("SystemRoot", r"C:\Windows").lower().replace("\\", "/")
        if lower.startswith(system_root + "/") or lower == system_root or norm_posix.startswith("/windows/"):
            return False

        # Block credential & secret directory patterns anywhere in the path
        blocked_path_patterns = (
            "/.ssh", "/.gnupg", "/.aws", "/.azure", "/.kube", "/.docker",
            "/credentials", "/shadow", "/passwd", "/sam", "/system32"
        )
        for pat in blocked_path_patterns:
            if pat in lower or pat in raw_lower or pat in norm_posix:
                return False

        # Block database files, WAL files, private keys, certificates, secrets, env
        blocked_extensions = (
            ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm",
            ".key", ".pem", ".env", ".id_rsa", ".id_ed25519", ".crt", ".pfx", ".p12",
            ".cer", ".token", ".secret"
        )
        for ext in blocked_extensions:
            if lower.endswith(ext) or raw_lower.endswith(ext) or norm_posix.endswith(ext):
                return False

        return True
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


def start_custom_app(app_id: str, store: Store) -> Dict[str, Any]:
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

        # Start process
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

    store.log_event("custom_app_start", f"Started app '{custom_app['name']}' (PID {proc.pid})", app_id=app_id)
    return {"status": "started", "pid": proc.pid, "name": custom_app["name"]}


def stop_custom_app(app_id: str, store: Store) -> Dict[str, Any]:
    _check_safe_mode(store)
    clean_id = app_id.replace("custom:", "")
    custom_app = store.get_custom_app(clean_id)
    name = custom_app["name"] if custom_app else clean_id

    stop_cmd = custom_app.get("stop_cmd") if custom_app else None

    with _lock:
        proc = _running_processes.pop(app_id, None)

    if proc and proc.poll() is None:
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                try:
                    child.terminate()
                except Exception:
                    pass
            parent.terminate()
            parent.wait(timeout=2)
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
            subprocess.run(stop_cmd, shell=True, timeout=5)
        except Exception as e:
            logger.warning(f"Custom stop command failed: {e}")

    store.log_event("custom_app_stop", f"Stopped app '{name}'", app_id=app_id)
    return {"status": "stopped", "name": name}


def restart_custom_app(app_id: str, store: Store) -> Dict[str, Any]:
    _check_safe_mode(store)
    stop_custom_app(app_id, store)
    time.sleep(0.5)
    return start_custom_app(app_id, store)


def get_custom_app_logs(app_id: str, store: Store, tail: int = 500) -> List[str]:
    clean_id = app_id.replace("custom:", "")
    custom_app = store.get_custom_app(clean_id)

    # 1. Check in-memory log buffer
    with _lock:
        buf = _log_buffers.get(app_id) or _log_buffers.get(clean_id)
        if buf and len(buf) > 0:
            lines = list(buf)
            return lines[-tail:]

    # 2. Check configured log_file if buffer is empty
    if custom_app and custom_app.get("log_file"):
        path = custom_app["log_file"]
        if not _is_safe_log_path(path):
            return [f"Access denied: Log file path '{path}' is not permitted."]
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.rstrip("\r\n") for l in f.readlines()]
                    return lines[-tail:]
            except Exception as e:
                return [f"Error reading log file {path}: {e}"]

    return [f"No logs recorded yet for {clean_id}."]


def kill_host_process(pid: int, store: Store) -> Dict[str, Any]:
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
        p.terminate()
        store.log_event("kill_process", f"Killed process {name} (PID {pid})")
        return {"status": "killed", "pid": pid, "name": name}
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to kill process {pid}: {e}")
