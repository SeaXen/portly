"""Docker container lifecycle actions, log streaming, safe container recreation, and image updates."""

import logging
import os
import re
import shlex
import time
from typing import Any, Dict, Generator, List, Optional

from portly.backend.discovery.docker_src import get_docker_client, is_docker_available
from portly.backend.ports import check_port_availability
from portly.backend.store import Store

logger = logging.getLogger("portly.docker_actions")


def _check_safe_mode(store: Store):
    safe_mode = store.get_setting("safe_mode", "true").lower() == "true"
    if safe_mode:
        raise PermissionError("Safe mode is active. Mutating actions (start, stop, recreate, update) are locked.")


def start_container(container_name_or_id: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    container.start()
    store.log_event("container_start", f"Started container {container.name}", app_id=f"docker:{container.name}", actor=actor)
    return {"status": "started", "container": container.name}


def stop_container(container_name_or_id: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    container.stop(timeout=10)
    store.log_event("container_stop", f"Stopped container {container.name}", app_id=f"docker:{container.name}", actor=actor)
    return {"status": "stopped", "container": container.name}


def restart_container(container_name_or_id: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    container.restart(timeout=10)
    store.log_event("container_restart", f"Restarted container {container.name}", app_id=f"docker:{container.name}", actor=actor)
    return {"status": "restarted", "container": container.name}


def get_container_logs(container_name_or_id: str, tail: int = 500, follow: bool = False) -> Any:
    client = get_docker_client()
    if not client:
        return ["Docker is not available on this host."]
    try:
        container = client.containers.get(container_name_or_id)
        if follow:
            return container.logs(stream=True, follow=True, tail=tail, timestamps=True)
        else:
            raw = container.logs(tail=tail, timestamps=True)
            return raw.decode("utf-8", errors="replace").splitlines()
    except Exception as e:
        return [f"Error retrieving logs for {container_name_or_id}: {e}"]


def inspect_container(container_name_or_id: str, mask_secrets: bool = True) -> Dict[str, Any]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    attrs = container.attrs
    config = attrs.get("Config", {})
    state = attrs.get("State", {})
    net = attrs.get("NetworkSettings", {})

    raw_env = config.get("Env", [])
    if mask_secrets:
        processed_env = []
        for e in raw_env:
            if "=" in e:
                k, _ = e.split("=", 1)
                processed_env.append(f"{k}=********")
            else:
                processed_env.append(e)
    else:
        processed_env = raw_env

    return {
        "id": container.id[:12],
        "name": container.name,
        "image": config.get("Image", ""),
        "created": attrs.get("Created", ""),
        "status": state.get("Status", ""),
        "health": state.get("Health", {}).get("Status", "none"),
        "restart_policy": attrs.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", "no"),
        "env": processed_env,
        "cmd": config.get("Cmd", []),
        "ports": net.get("Ports", {}),
        "mounts": [
            {
                "type": m.get("Type"),
                "source": m.get("Source"),
                "destination": m.get("Destination"),
                "mode": m.get("Mode"),
            }
            for m in attrs.get("Mounts", [])
        ],
        "networks": list(net.get("Networks", {}).keys()),
    }


def check_image_update(image_tag: str) -> Dict[str, Any]:
    """Checks if an updated image is available in the registry compared to local RepoDigests."""
    client = get_docker_client()
    if not client:
        return {"has_update": False, "current_digest": "", "latest_digest": "", "message": "Docker not available"}

    try:
        local_img = client.images.get(image_tag)
        local_digests = local_img.attrs.get("RepoDigests", [])
        current_digest = local_digests[0].split("@")[-1] if local_digests else ""
    except Exception as e:
        return {"has_update": False, "known": False, "message": str(e)}

    try:
        remote_digest = getattr(client.images.get_registry_data(image_tag), "id", "")
    except Exception as e:
        return {"has_update": False, "known": False, "message": f"Registry check failed: {e}"}

    if not remote_digest:
        return {"has_update": False, "known": False, "message": "Registry did not return a digest"}
    if not current_digest:
        return {"has_update": False, "known": False, "message": "Local image has no registry digest (built locally)"}

    has_update = remote_digest not in {d.split("@")[-1] for d in local_digests}
    return {
        "has_update": has_update,
        "known": True,
        "current_image": image_tag,
        "current_digest": current_digest[:19],
        "latest_digest": remote_digest[:19],
        "message": f"Update available: {remote_digest[:19]}" if has_update else "Image is up to date",
    }


def apply_image_update(container_name: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    """Pulls latest image and recreates container using safe recreation with rollback."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name)
    image_tag = container.attrs.get("Config", {}).get("Image")
    if not image_tag:
        raise ValueError(f"Container '{container_name}' has no image tag.")

    # Pull latest image
    try:
        client.images.pull(image_tag)
    except Exception as e:
        raise RuntimeError(f"Failed to pull image {image_tag}: {e}")

    # Recreate container
    attrs = container.attrs
    config = attrs.get("Config", {})
    host_config = attrs.get("HostConfig", {})
    ports = host_config.get("PortBindings") or {}
    binds = list(host_config.get("Binds") or [])
    networks = attrs.get("NetworkSettings", {}).get("Networks") or {}

    backup_name = f"{container_name}_portly_update_bak_{int(time.time())}"
    container.stop(timeout=10)
    container.rename(backup_name)

    run_kwargs: Dict[str, Any] = {
        "image": image_tag,
        "name": container_name,
        "detach": True,
        "ports": ports,
        "environment": config.get("Env", []),
        "labels": config.get("Labels") or {},
        "volumes": binds,
        "restart_policy": host_config.get("RestartPolicy"),
    }
    if config.get("Cmd"):
        run_kwargs["command"] = config.get("Cmd")
    if config.get("Entrypoint"):
        run_kwargs["entrypoint"] = config.get("Entrypoint")
    if config.get("User"):
        run_kwargs["user"] = config.get("User")
    if config.get("WorkingDir"):
        run_kwargs["working_dir"] = config.get("WorkingDir")

    try:
        new_container = client.containers.run(**run_kwargs)
        for net_name in networks:
            try:
                client.networks.get(net_name).connect(new_container)
            except Exception:
                pass

        time.sleep(1.0)
        new_container.reload()
        if not new_container.attrs.get("State", {}).get("Running"):
            raise RuntimeError("New container failed to stay running after update.")

        # Cleanup backup
        try:
            container.remove(v=False)
        except Exception:
            pass

        store.log_event("container_update", f"Updated container '{container_name}' to latest image", app_id=f"docker:{container_name}", actor=actor)
        return {"status": "updated", "container": container_name, "image": image_tag}
    except Exception as e:
        try:
            # Clean up new container if created
            failed_c = client.containers.get(container_name)
            failed_c.remove(force=True)
        except Exception:
            pass
        try:
            container.rename(container_name)
            container.start()
        except Exception as rb_err:
            logger.error(f"Failed to restore original container after update failure: {rb_err}")
        raise RuntimeError(f"Update failed: {e}. Original container restored.")


def apply_port_change_docker(container_name: str, new_port: int, target_c_port: str, bind: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    """Recreates a docker container with new port mapping safely, verifying start before dropping backup."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name)
    attrs = container.attrs
    config = attrs.get("Config", {})
    host_config = attrs.get("HostConfig", {})

    if host_config.get("NetworkMode") == "host":
        raise ValueError(f"Container '{container_name}' uses host networking mode. Port mappings cannot be changed via Docker.")

    ports = host_config.get("PortBindings") or {}
    binds = list(host_config.get("Binds") or [])
    mounts = attrs.get("Mounts") or []
    existing_destinations = set()
    for b in binds:
        parts = b.split(":")
        if len(parts) >= 2:
            existing_destinations.add(parts[1])
    for m in mounts:
        dest = m.get("Destination")
        if dest and dest not in existing_destinations:
            src = m.get("Source") if m.get("Type") == "bind" else (m.get("Name") or m.get("Source"))
            mode = m.get("Mode") or ("rw" if m.get("RW", True) else "ro")
            if src:
                binds.append(f"{src}:{dest}:{mode}")
                existing_destinations.add(dest)

    networks = attrs.get("NetworkSettings", {}).get("Networks") or {}
    image = config.get("Image")
    env = config.get("Env", [])
    cmd = config.get("Cmd")
    entrypoint = config.get("Entrypoint")
    labels = config.get("Labels") or {}
    user = config.get("User")
    working_dir = config.get("WorkingDir")
    restart_policy = host_config.get("RestartPolicy")

    # Find old port
    old_port = None
    for cp, maps in ports.items():
        if cp == target_c_port and maps:
            old_port = int(maps[0].get("HostPort", 0))

    # Save comprehensive snapshot
    app_id = f"docker:{container.name}:{target_c_port}"
    snapshot_config = {
        "image": image,
        "ports": ports,
        "env": env,
        "bind": bind,
        "cmd": cmd,
        "entrypoint": entrypoint,
        "labels": labels,
        "user": user,
        "working_dir": working_dir,
        "restart_policy": restart_policy,
        "binds": binds,
        "networks": list(networks.keys()),
        "privileged": host_config.get("Privileged", False),
        "cap_add": host_config.get("CapAdd"),
        "cap_drop": host_config.get("CapDrop"),
        "devices": host_config.get("Devices"),
        "extra_hosts": host_config.get("ExtraHosts"),
        "dns": host_config.get("Dns"),
        "nano_cpus": host_config.get("NanoCPUs"),
        "mem_limit": host_config.get("Memory"),
        "memswap_limit": host_config.get("MemorySwap"),
        "healthcheck": config.get("Healthcheck"),
        "tmpfs": host_config.get("Tmpfs"),
        "sysctls": host_config.get("Sysctls"),
        "ipc_mode": host_config.get("IpcMode"),
        "pid_mode": host_config.get("PidMode"),
        "security_opt": host_config.get("SecurityOpt"),
        "log_config": host_config.get("LogConfig"),
    }
    store.save_port_snapshot(app_id, old_port or 0, new_port, snapshot_config)

    # Prepare new port bindings
    new_port_bindings = dict(ports)
    new_port_bindings[target_c_port] = [{"HostIp": bind, "HostPort": str(new_port)}]

    run_kwargs: Dict[str, Any] = {
        "image": image,
        "name": container_name,
        "detach": True,
        "ports": new_port_bindings,
        "environment": env,
        "labels": labels,
        "privileged": host_config.get("Privileged", False),
    }
    if cmd:
        run_kwargs["command"] = cmd
    if entrypoint:
        run_kwargs["entrypoint"] = entrypoint
    if restart_policy:
        run_kwargs["restart_policy"] = restart_policy
    if binds:
        run_kwargs["volumes"] = binds
    if user:
        run_kwargs["user"] = user
    if working_dir:
        run_kwargs["working_dir"] = working_dir
    if host_config.get("CapAdd"):
        run_kwargs["cap_add"] = host_config.get("CapAdd")
    if host_config.get("CapDrop"):
        run_kwargs["cap_drop"] = host_config.get("CapDrop")
    if host_config.get("Devices"):
        run_kwargs["devices"] = host_config.get("Devices")
    if host_config.get("Dns"):
        run_kwargs["dns"] = host_config.get("Dns")
    if host_config.get("ExtraHosts"):
        run_kwargs["extra_hosts"] = host_config.get("ExtraHosts")
    if host_config.get("NanoCPUs"):
        run_kwargs["nano_cpus"] = host_config.get("NanoCPUs")
    if host_config.get("Memory"):
        run_kwargs["mem_limit"] = host_config.get("Memory")
    if host_config.get("MemorySwap"):
        run_kwargs["memswap_limit"] = host_config.get("MemorySwap")
    if config.get("Healthcheck"):
        run_kwargs["healthcheck"] = config.get("Healthcheck")
    if host_config.get("Tmpfs"):
        run_kwargs["tmpfs"] = host_config.get("Tmpfs")
    if host_config.get("Sysctls"):
        run_kwargs["sysctls"] = host_config.get("Sysctls")
    if host_config.get("IpcMode"):
        run_kwargs["ipc_mode"] = host_config.get("IpcMode")
    if host_config.get("PidMode"):
        run_kwargs["pid_mode"] = host_config.get("PidMode")
    if host_config.get("SecurityOpt"):
        run_kwargs["security_opt"] = host_config.get("SecurityOpt")
    if host_config.get("LogConfig"):
        run_kwargs["log_config"] = host_config.get("LogConfig")

    # Non-destructive recreation: rename original container first
    backup_name = f"{container_name}_portly_bak_{int(time.time())}"
    container.stop(timeout=10)
    container.rename(backup_name)

    try:
        new_container = client.containers.run(**run_kwargs)
        for net_name in networks:
            try:
                client.networks.get(net_name).connect(new_container)
            except Exception:
                pass

        # Post-start verification: check container is running and not immediately exiting
        time.sleep(0.1)
        if hasattr(new_container, "reload"):
            new_container.reload()
        state = getattr(new_container, "attrs", {}).get("State", {})
        if state and not state.get("Running", True):
            raise RuntimeError(f"Container failed to remain running on port {new_port} (exit code: {state.get('ExitCode')})")
        if state.get("Health", {}).get("Status") == "unhealthy":
            raise RuntimeError(f"Container reported unhealthy after port change to {new_port}")

        # Remove temporary backup container only after verification succeeds
        try:
            container.remove(v=False)
        except Exception as rm_err:
            logger.warning(f"Could not remove temporary backup container {backup_name}: {rm_err}")
    except Exception as run_err:
        # 1. Clean up created container first to prevent name conflict on rename
        try:
            created_c = client.containers.get(container_name)
            created_c.remove(force=True)
        except Exception:
            pass

        # 2. Revert rename and restart original container
        try:
            container.rename(container_name)
            container.start()
        except Exception as rb_err:
            logger.error(f"Critical: failed to restore original container {container_name}: {rb_err}")
        raise RuntimeError(f"Failed to apply port change: {run_err}. Original container was preserved and restored.")

    store.log_event("port_change", f"Changed container {container_name} port to {new_port}", app_id=app_id, actor=actor)
    return {
        "status": "recreated",
        "container": new_container.name,
        "new_port": new_port,
        "rollback_available": True
    }


def apply_multi_port_change_docker(container_name: str, mappings: List[Dict[str, Any]], store: Store, actor: str = "system") -> Dict[str, Any]:
    """Recreates a docker container with multiple updated port mappings safely and saves rollback snapshot."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name)
    attrs = container.attrs
    config = attrs.get("Config", {})
    host_config = attrs.get("HostConfig", {})

    if host_config.get("NetworkMode") == "host":
        raise ValueError(f"Container '{container_name}' uses host networking mode. Port mappings cannot be changed via Docker.")

    old_ports = host_config.get("PortBindings") or {}
    binds = list(host_config.get("Binds") or [])
    networks = attrs.get("NetworkSettings", {}).get("Networks") or {}

    new_port_bindings = dict(old_ports)
    for m in mappings:
        c_spec = m.get("container_port")
        h_port = m.get("host_port")
        bind_ip = m.get("bind", "0.0.0.0")
        if c_spec and h_port:
            new_port_bindings[c_spec] = [{"HostIp": bind_ip, "HostPort": str(h_port)}]

    app_id = f"docker:{container.name}:multi"
    store.save_port_snapshot(app_id, 0, 0, {
        "image": config.get("Image"),
        "ports": old_ports,
        "env": config.get("Env", []),
        "cmd": config.get("Cmd"),
        "entrypoint": config.get("Entrypoint"),
        "labels": config.get("Labels") or {},
        "user": config.get("User"),
        "working_dir": config.get("WorkingDir"),
        "restart_policy": host_config.get("RestartPolicy"),
        "binds": binds,
        "networks": list(networks.keys()),
        "privileged": host_config.get("Privileged", False),
        "cap_add": host_config.get("CapAdd"),
        "cap_drop": host_config.get("CapDrop"),
        "devices": host_config.get("Devices"),
        "dns": host_config.get("Dns"),
        "extra_hosts": host_config.get("ExtraHosts"),
    })

    run_kwargs: Dict[str, Any] = {
        "image": config.get("Image"),
        "name": container_name,
        "detach": True,
        "ports": new_port_bindings,
        "environment": config.get("Env", []),
        "labels": config.get("Labels") or {},
        "privileged": host_config.get("Privileged", False),
    }
    if config.get("Cmd"):
        run_kwargs["command"] = config.get("Cmd")
    if config.get("Entrypoint"):
        run_kwargs["entrypoint"] = config.get("Entrypoint")
    if host_config.get("RestartPolicy"):
        run_kwargs["restart_policy"] = host_config.get("RestartPolicy")
    if binds:
        run_kwargs["volumes"] = binds
    if config.get("User"):
        run_kwargs["user"] = config.get("User")
    if config.get("WorkingDir"):
        run_kwargs["working_dir"] = config.get("WorkingDir")
    if host_config.get("CapAdd"):
        run_kwargs["cap_add"] = host_config.get("CapAdd")
    if host_config.get("CapDrop"):
        run_kwargs["cap_drop"] = host_config.get("CapDrop")
    if host_config.get("Devices"):
        run_kwargs["devices"] = host_config.get("Devices")
    if host_config.get("Dns"):
        run_kwargs["dns"] = host_config.get("Dns")
    if host_config.get("ExtraHosts"):
        run_kwargs["extra_hosts"] = host_config.get("ExtraHosts")

    backup_name = f"{container_name}_portly_bak_{int(time.time())}"
    container.stop(timeout=10)
    container.rename(backup_name)

    try:
        new_container = client.containers.run(**run_kwargs)
        for net_name in networks:
            try:
                client.networks.get(net_name).connect(new_container)
            except Exception:
                pass

        time.sleep(0.1)
        if hasattr(new_container, "reload"):
            new_container.reload()
        state = getattr(new_container, "attrs", {}).get("State", {})
        if state and not state.get("Running", True):
            raise RuntimeError("Container failed to remain running after multi-port change.")

        try:
            container.remove(v=False)
        except Exception as rm_err:
            logger.warning(f"Could not remove backup container {backup_name}: {rm_err}")
    except Exception as run_err:
        try:
            created_c = client.containers.get(container_name)
            created_c.remove(force=True)
        except Exception:
            pass
        try:
            container.rename(container_name)
            container.start()
        except Exception as rb_err:
            logger.error(f"Failed to restore original container: {rb_err}")
        raise RuntimeError(f"Multi-port change failed: {run_err}. Original container restored.")

    store.log_event("port_change_multi", f"Updated multiple ports on container {container_name}", app_id=app_id, actor=actor)
    return {"status": "recreated", "container": container_name, "mappings": mappings, "rollback_available": True}


def rollback_port_change_docker(app_id: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    """Restores previous port mapping from snapshot non-destructively."""
    _check_safe_mode(store)
    snap = store.get_port_snapshot(app_id)
    if not snap:
        raise ValueError("No rollback snapshot found for this app.")

    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    parts = app_id.split(":")
    container_name = parts[1]
    cfg = snap["config"]

    container = client.containers.get(container_name)
    backup_name = f"{container_name}_rollback_bak_{int(time.time())}"
    container.stop(timeout=10)
    container.rename(backup_name)

    run_kwargs: Dict[str, Any] = {
        "image": cfg.get("image"),
        "name": container_name,
        "detach": True,
        "ports": cfg.get("ports"),
        "environment": cfg.get("env"),
        "labels": cfg.get("labels") or {},
        "privileged": cfg.get("privileged", False),
    }
    if cfg.get("cmd"):
        run_kwargs["command"] = cfg.get("cmd")
    if cfg.get("entrypoint"):
        run_kwargs["entrypoint"] = cfg.get("entrypoint")
    if cfg.get("restart_policy"):
        run_kwargs["restart_policy"] = cfg.get("restart_policy")
    if cfg.get("binds"):
        run_kwargs["volumes"] = cfg.get("binds")
    if cfg.get("user"):
        run_kwargs["user"] = cfg.get("user")
    if cfg.get("working_dir"):
        run_kwargs["working_dir"] = cfg.get("working_dir")
    if cfg.get("cap_add"):
        run_kwargs["cap_add"] = cfg.get("cap_add")
    if cfg.get("cap_drop"):
        run_kwargs["cap_drop"] = cfg.get("cap_drop")
    if cfg.get("devices"):
        run_kwargs["devices"] = cfg.get("devices")
    if cfg.get("dns"):
        run_kwargs["dns"] = cfg.get("dns")
    if cfg.get("extra_hosts"):
        run_kwargs["extra_hosts"] = cfg.get("extra_hosts")

    try:
        new_c = client.containers.run(**run_kwargs)
        for net_name in cfg.get("networks", []):
            try:
                client.networks.get(net_name).connect(new_c)
            except Exception:
                pass
        try:
            container.remove(v=False)
        except Exception:
            pass
    except Exception as run_err:
        try:
            created_c = client.containers.get(container_name)
            created_c.remove(force=True)
        except Exception:
            pass
        try:
            container.rename(container_name)
            container.start()
        except Exception:
            pass
        raise RuntimeError(f"Rollback failed: {run_err}. Container restored to pre-rollback state.")

    store.clear_port_snapshot(app_id)
    store.log_event("port_rollback", f"Rolled back container {container_name} ports", app_id=app_id, actor=actor)
    return {"status": "rolled_back", "port": snap["original_port"]}


FORBIDDEN_OPERATORS = [";", "&&", "||", "|", ">", ">>", "<", "`", "$(", "$", "\n", "\r", "&"]
SAFE_COMMAND_BINARIES = {"ps", "free", "df", "uptime", "uname", "whoami", "id", "hostname", "date", "pwd", "ss", "netstat", "ip"}
SAFE_COMMAND_ALLOWLIST = SAFE_COMMAND_BINARIES


def parse_and_validate_safe_command(command: str) -> List[str]:
    """
    Parses command into argv list and validates against strict allowlist.
    Returns argv list for execution.
    Raises ValueError or PermissionError.
    """
    if not command or not isinstance(command, str):
        raise ValueError("Command cannot be empty")

    for op in FORBIDDEN_OPERATORS:
        if op in command:
            raise PermissionError(f"Safe mode is active. Command contains restricted shell operator '{op}'.")

    try:
        argv = shlex.split(command)
    except Exception as e:
        raise ValueError(f"Failed to parse command arguments: {e}")

    if not argv:
        raise ValueError("Command cannot be empty")

    binary = os.path.basename(argv[0]).lower()

    if binary not in SAFE_COMMAND_BINARIES:
        raise PermissionError(
            f"Command '{binary}' is not in the safe inspection whitelist. "
            f"Unlock safe mode in the top bar to execute custom commands."
        )

    # Allowed argv rules
    if binary in ("ps", "uptime", "free", "df", "uname", "whoami", "id", "hostname", "date", "pwd"):
        for arg in argv[1:]:
            if any(c in arg for c in (";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\\")):
                raise PermissionError(f"Safe mode is active. Argument '{arg}' contains restricted shell operator.")
        return argv

    elif binary in ("ss", "netstat"):
        for arg in argv[1:]:
            if any(c in arg for c in (";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\\")):
                raise PermissionError(f"Safe mode is active. Argument '{arg}' contains restricted shell operator.")
        return argv

    elif binary == "ip":
        if len(argv) < 2:
            raise PermissionError("Safe mode is active. Bare 'ip' command is not allowed.")
        sub = argv[1].lower()
        if sub in ("addr", "a", "address"):
            if len(argv) > 2 and argv[2].lower() not in ("show", "list", "sh", "s"):
                raise PermissionError(f"Safe mode is active. 'ip addr {argv[2]}' is not allowed in safe mode.")
            return argv
        elif sub in ("route", "r", "ro"):
            if len(argv) > 2 and argv[2].lower() not in ("show", "list", "sh", "s"):
                raise PermissionError(f"Safe mode is active. 'ip route {argv[2]}' is not allowed in safe mode.")
            return argv
        else:
            raise PermissionError(f"Safe mode is active. 'ip {sub}' is not allowed in safe mode.")

    elif binary == "ls":
        for arg in argv[1:]:
            if any(c in arg for c in (";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\\")):
                raise PermissionError(f"Safe mode is active. Argument '{arg}' contains restricted shell operator.")
        return argv

    raise PermissionError(
        f"Command '{binary}' is not in the safe inspection whitelist. "
        f"Unlock safe mode in the top bar to execute custom commands."
    )


_validate_safe_command = parse_and_validate_safe_command


def exec_in_container(
    container_name_or_id: str,
    command: str,
    store: Optional[Store] = None,
    timeout: int = 10,
    actor: str = "system"
) -> Dict[str, Any]:
    """Runs a command inside a Docker container enforcing argv allowlist, bounded timeout, and output cap."""
    timeout = max(1, min(30, int(timeout or 10)))
    if store and store.get_setting("safe_mode", "true").lower() == "true":
        cmd_exec = parse_and_validate_safe_command(command)
    else:
        cmd_exec = shlex.split(command)

    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name_or_id)
    t0 = time.perf_counter()
    exec_res = container.exec_run(cmd_exec, stdout=True, stderr=True, demux=False)
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    raw_output = exec_res.output
    output_str = raw_output.decode("utf-8", errors="replace") if isinstance(raw_output, (bytes, bytearray)) else str(raw_output or "")
    if len(output_str) > 262144:  # Cap at 256 KB
        output_str = output_str[:262144] + "\n... [Output truncated at 256 KB]"

    if store:
        store.log_event("container_exec", f"Executed '{command}' in container '{container.name}'", app_id=f"docker:{container.name}", actor=actor)

    return {
        "exit_code": exec_res.exit_code,
        "output": output_str,
        "command": command,
        "duration_ms": duration_ms,
    }


def get_container_compose_config(container_name_or_id: str) -> Dict[str, Any]:
    """Inspects container labels and securely retrieves docker-compose file configuration."""
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name_or_id)
    labels = container.attrs.get("Config", {}).get("Labels") or {}

    project = labels.get("com.docker.compose.project")
    service = labels.get("com.docker.compose.service")
    working_dir = labels.get("com.docker.compose.project.working_dir")
    config_files = labels.get("com.docker.compose.project.config_files")

    if not project and not service and not working_dir:
        return {
            "has_compose": False,
            "message": f"Container '{container.name}' does not appear to be managed by Docker Compose (no compose labels found)."
        }

    candidate_path = None
    first_file = None
    if config_files:
        files = [f.strip() for f in config_files.split(",") if f.strip()]
        if files:
            first_file = files[0]
            if working_dir and not os.path.isabs(first_file):
                first_file = os.path.join(working_dir, first_file)
        for f in files:
            if os.path.isabs(f) and os.path.isfile(f):
                candidate_path = f
                break
            elif working_dir:
                joined = os.path.join(working_dir, f)
                if os.path.isfile(joined):
                    candidate_path = joined
                    break

    if not candidate_path and working_dir:
        for fname in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            fpath = os.path.join(working_dir, fname)
            if os.path.isfile(fpath):
                candidate_path = fpath
                break

    resolved_config_path = candidate_path or first_file or ""

    if not candidate_path or not os.path.isfile(candidate_path):
        return {
            "has_compose": True,
            "project": project or "unknown",
            "service": service or "unknown",
            "config_file": resolved_config_path,
            "compose_file": resolved_config_path or "Not found on host filesystem",
            "content": "# Compose file could not be located on host.\n# Check if container was deployed remotely.",
            "can_manage": False,
        }

    # Restrict compose read to yaml files <= 1MB
    norm_path = os.path.realpath(candidate_path)
    if not (norm_path.endswith(".yml") or norm_path.endswith(".yaml")):
        return {
            "has_compose": True,
            "project": project,
            "service": service,
            "config_file": resolved_config_path,
            "compose_file": candidate_path,
            "content": "# Error: Invalid compose file extension.",
            "can_manage": False,
        }

    try:
        size = os.path.getsize(norm_path)
        if size > 1048576:
            return {
                "has_compose": True,
                "project": project,
                "service": service,
                "config_file": resolved_config_path,
                "compose_file": candidate_path,
                "content": "# Error: Compose file exceeds 1MB limit.",
                "can_manage": False,
            }
        with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        content = f"# Error reading compose file: {e}"

    return {
        "has_compose": True,
        "project": project,
        "service": service,
        "working_dir": working_dir,
        "config_file": resolved_config_path,
        "compose_file": candidate_path,
        "content": content,
        "can_manage": True,
    }


def get_docker_system_df(store: Store) -> Dict[str, Any]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    try:
        raw_df = client.df()
        images = raw_df.get("Images") or []
        containers = raw_df.get("Containers") or []
        volumes = raw_df.get("Volumes") or []

        img_total = sum(i.get("Size", 0) for i in images)
        img_reclaim = sum(i.get("Size", 0) for i in images if i.get("Containers", 0) == 0)
        cont_total = sum(c.get("SizeRw", 0) for c in containers)
        vol_total = sum(v.get("UsageData", {}).get("Size", 0) for v in volumes if "UsageData" in v)
        vol_reclaim = sum(v.get("UsageData", {}).get("Size", 0) for v in volumes if v.get("UsageData", {}).get("RefCount", 0) == 0)

        total_disk = img_total + cont_total + vol_total
        total_reclaimable = img_reclaim + vol_reclaim

        return {
            "images_count": len(images),
            "containers_count": len(containers),
            "volumes_count": len(volumes),
            "total_size_mb": round(total_disk / (1024 * 1024), 2),
            "total_reclaimable_mb": round(total_reclaimable / (1024 * 1024), 2),
            "reclaimable_mb": round(total_reclaimable / (1024 * 1024), 2),
            "images": {"count": len(images), "size_mb": round(img_total / (1024 * 1024), 2), "reclaimable_mb": round(img_reclaim / (1024 * 1024), 2)},
            "containers": {"count": len(containers), "size_mb": round(cont_total / (1024 * 1024), 2)},
            "volumes": {"count": len(volumes), "size_mb": round(vol_total / (1024 * 1024), 2), "reclaimable_mb": round(vol_reclaim / (1024 * 1024), 2)},
        }
    except Exception as e:
        logger.error(f"Error querying docker df: {e}")
        return {"total_size_mb": 0.0, "reclaimable_mb": 0.0, "error": str(e)}


def list_docker_images(store: Store) -> List[Dict[str, Any]]:
    client = get_docker_client()
    if not client:
        return []
    try:
        results = []
        for img in client.images.list():
            attrs = img.attrs
            tags = img.tags or ["<none>:<none>"]
            created = attrs.get("Created", "")
            size_mb = round(attrs.get("Size", 0) / (1024 * 1024), 1)
            results.append({
                "id": img.id[:19],
                "tags": tags,
                "created": created,
                "size_mb": size_mb,
            })
        return results
    except Exception as e:
        logger.error(f"Error listing docker images: {e}")
        return []


def list_docker_volumes(store: Store) -> List[Dict[str, Any]]:
    client = get_docker_client()
    if not client:
        return []
    try:
        results = []
        for vol in client.volumes.list():
            attrs = vol.attrs
            results.append({
                "name": vol.name,
                "driver": attrs.get("Driver", "local"),
                "mountpoint": attrs.get("Mountpoint", ""),
                "created_at": attrs.get("CreatedAt", ""),
            })
        return results
    except Exception as e:
        logger.error(f"Error listing docker volumes: {e}")
        return []


def prune_docker_system(
    store: Store,
    prune_containers: bool = True,
    prune_images: bool = True,
    prune_volumes: bool = False,
    prune_networks: bool = True,
    actor: str = "system"
) -> Dict[str, Any]:
    """Prunes docker artifacts. Crucially, prune_volumes defaults to FALSE to prevent accidental data loss."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    total_reclaimed = 0
    containers_deleted = []
    images_deleted = []
    volumes_deleted = []
    networks_deleted = []

    if prune_containers:
        res = client.containers.prune()
        total_reclaimed += res.get("SpaceReclaimed", 0) or 0
        containers_deleted = res.get("ContainersDeleted") or []

    if prune_images:
        res = client.images.prune()
        total_reclaimed += res.get("SpaceReclaimed", 0) or 0
        raw_imgs = res.get("ImagesDeleted") or []
        images_deleted = [i.get("Deleted") for i in raw_imgs if isinstance(i, dict) and i.get("Deleted")]

    if prune_volumes:
        try:
            res = client.volumes.prune()
            total_reclaimed += res.get("SpaceReclaimed", 0) or 0
            volumes_deleted = res.get("VolumesDeleted") or []
        except Exception as ve:
            logger.warning(f"Could not prune volumes: {ve}")

    if prune_networks:
        try:
            res = client.networks.prune()
            networks_deleted = res.get("NetworksDeleted") or []
        except Exception:
            pass

    store.log_event("docker_prune", f"Pruned docker system, reclaimed {round(total_reclaimed / (1024*1024), 2)} MB", actor=actor)
    return {
        "status": "success",
        "space_reclaimed_mb": round(total_reclaimed / (1024 * 1024), 2),
        "deleted": {
            "containers": containers_deleted,
            "images": images_deleted,
            "volumes": volumes_deleted,
            "networks": networks_deleted,
        }
    }


def manage_compose_stack(project_name: str, action: str, store: Store, actor: str = "system") -> Dict[str, Any]:
    """Executes stack-wide action on compose project containers, reporting accurate per-container results."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    act = action.lower().strip()
    if act not in ("restart", "stop", "start", "down"):
        raise ValueError(f"Unsupported compose action: {action}")

    affected = []
    failures = []
    containers = client.containers.list(all=True)
    project_containers = []

    for c in containers:
        labels = getattr(c, "labels", None) or getattr(c, "attrs", {}).get("Config", {}).get("Labels") or {}
        if labels.get("com.docker.compose.project") == project_name:
            project_containers.append(c)

    if not project_containers:
        raise ValueError(f"No containers found for compose project '{project_name}'")

    for c in project_containers:
        try:
            if act == "restart":
                c.restart(timeout=10)
            elif act == "stop":
                c.stop(timeout=10)
            elif act == "start":
                c.start()
            elif act == "down":
                c.stop(timeout=10)
                c.remove(v=False)
            affected.append(c.name)
        except Exception as e:
            failures.append({"container": c.name, "error": str(e)})

    store.log_event("compose_action", f"Executed {act} on compose project {project_name} ({len(affected)} succeeded, {len(failures)} failed)", actor=actor)
    return {
        "status": "ok" if not failures else ("partial" if affected else "failed"),
        "action": act,
        "project": project_name,
        "affected": affected,
        "affected_containers": affected,
        "failures": failures,
    }


def deploy_container(
    image: str,
    name: str,
    ports: Dict[str, Any],
    env: Dict[str, str],
    volumes: List[str],
    restart_policy: str,
    store: Store,
    actor: str = "system"
) -> Dict[str, Any]:
    """Deploys a new Docker container with strict validation, port verification, and safe mode check."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    if not image or not image.strip():
        raise ValueError("Container image is required.")
    if not name or not name.strip():
        raise ValueError("Container name is required.")

    # Validate image and container name formats
    clean_image = image.strip()
    clean_name = name.strip()
    if not re.match(r'^[a-zA-Z0-9_\.\-\/\:]+$', clean_image):
        raise ValueError(f"Invalid image format '{clean_image}'")
    if not re.match(r'^[a-zA-Z0-9_\.\-]+$', clean_name):
        raise ValueError(f"Invalid container name '{clean_name}'. Only alphanumeric characters, dashes, dots, and underscores are allowed.")

    # Guard against dangerous host volume binds
    for v in volumes or []:
        host_path = v.split(":")[0].strip()
        lower_h = host_path.lower()
        if lower_h in ("/", "/var/run/docker.sock", "/proc", "/sys", "/etc", "c:\\", "c:\\windows"):
            raise PermissionError(f"Binding sensitive host path '{host_path}' is restricted in Portly.")

    # Validate ports
    formatted_ports = {}
    for c_port, h_port in (ports or {}).items():
        try:
            hp_int = int(h_port)
            chk = check_port_availability(hp_int, "0.0.0.0")
            if not chk["free"]:
                raise ValueError(f"Port {hp_int} is already in use: {chk.get('used_by')}")
            formatted_ports[c_port] = [{"HostIp": "0.0.0.0", "HostPort": str(hp_int)}]
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid port configuration: {e}")

    run_kwargs: Dict[str, Any] = {
        "image": clean_image,
        "name": clean_name,
        "detach": True,
        "ports": formatted_ports,
        "environment": env or {},
    }
    if volumes:
        run_kwargs["volumes"] = volumes
    if restart_policy:
        run_kwargs["restart_policy"] = {"Name": restart_policy}

    try:
        cont = client.containers.run(**run_kwargs)
        store.log_event("container_deploy", f"Deployed new container '{clean_name}' from image '{clean_image}'", actor=actor)
        return {
            "status": "deployed",
            "container": cont.name,
            "id": cont.id[:12] if cont.id else "",
        }
    except Exception as e:
        logger.error(f"Failed to deploy container {clean_name}: {e}")
        raise RuntimeError(f"Failed to deploy container {clean_name}: {e}")


def execute_stack_file_action(project_name: str, compose_yaml: str, action: str, data_dir: str = "data") -> Dict[str, Any]:
    """Writes stack YAML to disk and invokes docker compose CLI with output capture."""
    import subprocess
    import shutil

    stacks_dir = os.path.join(data_dir, "stacks", project_name)
    os.makedirs(stacks_dir, exist_ok=True)
    compose_path = os.path.join(stacks_dir, "docker-compose.yml")
    with open(compose_path, "w", encoding="utf-8") as f:
        f.write(compose_yaml)

    docker_bin = shutil.which("docker")
    if not docker_bin:
        return {"status": "error", "message": "Docker CLI binary not found in PATH for stack orchestration", "output": ""}

    cmd = [docker_bin, "compose", "-f", compose_path, "-p", project_name]
    act = action.lower().strip()
    if act == "up":
        cmd.extend(["up", "-d"])
    elif act == "down":
        cmd.append("down")
    elif act == "stop":
        cmd.append("stop")
    elif act == "restart":
        cmd.append("restart")
    else:
        return {"status": "error", "message": f"Unsupported action: {action}", "output": ""}

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        output = (proc.stdout + "\n" + proc.stderr).strip()
        if proc.returncode == 0:
            return {
                "status": "success",
                "message": f"Stack '{project_name}' {action} completed successfully.",
                "output": output,
                "exit_code": 0
            }
        else:
            return {
                "status": "error",
                "message": f"docker compose returned code {proc.returncode}",
                "output": output,
                "exit_code": proc.returncode
            }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "docker compose operation timed out (90s limit)", "output": ""}
    except Exception as e:
        return {"status": "error", "message": str(e), "output": ""}
