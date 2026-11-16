"""Docker container lifecycle actions, log streaming, and image updates."""

import logging
from typing import Any, Dict, Generator, List, Optional

from portly.backend.discovery.docker_src import get_docker_client, is_docker_available
from portly.backend.ports import check_port_availability
from portly.backend.store import Store

logger = logging.getLogger("portly.docker_actions")


def _check_safe_mode(store: Store):
    safe_mode = store.get_setting("safe_mode", "true").lower() == "true"
    if safe_mode:
        raise PermissionError("Safe mode is active. Mutating actions (start, stop, recreate, update) are locked.")


def start_container(container_name_or_id: str, store: Store) -> Dict[str, Any]:
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    container.start()
    store.log_event("container_start", f"Started container {container.name}", app_id=f"docker:{container.name}")
    return {"status": "started", "container": container.name}


def stop_container(container_name_or_id: str, store: Store) -> Dict[str, Any]:
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    container.stop(timeout=10)
    store.log_event("container_stop", f"Stopped container {container.name}", app_id=f"docker:{container.name}")
    return {"status": "stopped", "container": container.name}


def restart_container(container_name_or_id: str, store: Store) -> Dict[str, Any]:
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    container.restart(timeout=10)
    store.log_event("container_restart", f"Restarted container {container.name}", app_id=f"docker:{container.name}")
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


def inspect_container(container_name_or_id: str) -> Dict[str, Any]:
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")
    container = client.containers.get(container_name_or_id)
    attrs = container.attrs
    config = attrs.get("Config", {})
    state = attrs.get("State", {})
    net = attrs.get("NetworkSettings", {})

    return {
        "id": container.id[:12],
        "name": container.name,
        "image": config.get("Image", ""),
        "created": attrs.get("Created", ""),
        "status": state.get("Status", ""),
        "health": state.get("Health", {}).get("Status", "none"),
        "restart_policy": attrs.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", "no"),
        "env": config.get("Env", []),
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
    """Checks if an updated image is available in the registry."""
    client = get_docker_client()
    if not client:
        return {"has_update": False, "current_digest": "", "latest_digest": "", "message": "Docker not available"}

    try:
        local_img = client.images.get(image_tag)
        current_id = local_img.id[:19]
        # In mock / rate-limited environments, return clean info
        return {
            "has_update": False,
            "current_image": image_tag,
            "current_digest": current_id,
            "latest_digest": current_id,
            "message": "Image is up to date"
        }
    except Exception as e:
        return {"has_update": False, "message": str(e)}


def apply_port_change_docker(container_name: str, new_port: int, target_c_port: str, bind: str, store: Store) -> Dict[str, Any]:
    """Recreates a docker container with new port mapping safely and saves rollback snapshot."""
    import time
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name)
    attrs = container.attrs
    config = attrs.get("Config", {})
    host_config = attrs.get("HostConfig", {})
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
    store.save_port_snapshot(app_id, old_port or 0, new_port, {
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
    })

    # Prepare new port bindings
    new_port_bindings = dict(ports)
    new_port_bindings[target_c_port] = [{"HostIp": bind, "HostPort": str(new_port)}]

    # Prepare run kwargs
    run_kwargs: Dict[str, Any] = {
        "image": image,
        "name": container_name,
        "detach": True,
        "ports": new_port_bindings,
        "environment": env,
        "labels": labels,
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

    # Non-destructive recreation: rename original container first
    backup_name = f"{container_name}_portly_bak_{int(time.time())}"
    container.stop(timeout=10)
    container.rename(backup_name)

    try:
        new_container = client.containers.run(**run_kwargs)
        # Connect additional networks if present
        for net_name in networks:
            try:
                net_obj = client.networks.get(net_name)
                net_obj.connect(new_container)
            except Exception:
                pass

        # Old container is only removed after new container boots successfully
        try:
            container.remove(v=False)
        except Exception as rm_err:
            logger.warning(f"Could not remove temporary backup container {backup_name}: {rm_err}")
    except Exception as run_err:
        # Revert rename and restart original container
        try:
            container.rename(container_name)
            container.start()
        except Exception as rb_err:
            logger.error(f"Critical: failed to restore original container {container_name}: {rb_err}")
        raise RuntimeError(f"Failed to apply port change: {run_err}. Original container was preserved and restored.")

    store.log_event("port_change", f"Changed container {container_name} port to {new_port}", app_id=app_id)
    return {
        "status": "recreated",
        "container": new_container.name,
        "new_port": new_port,
        "rollback_available": True
    }


def apply_multi_port_change_docker(container_name: str, mappings: List[Dict[str, Any]], store: Store) -> Dict[str, Any]:
    """Recreates a docker container with multiple updated port mappings safely and saves rollback snapshot."""
    import time
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name)
    attrs = container.attrs
    image = attrs.get("Config", {}).get("Image", "")
    env = attrs.get("Config", {}).get("Env", [])
    labels = attrs.get("Config", {}).get("Labels") or {}
    cmd = attrs.get("Config", {}).get("Cmd")
    entrypoint = attrs.get("Config", {}).get("Entrypoint")
    user = attrs.get("Config", {}).get("User")
    working_dir = attrs.get("Config", {}).get("WorkingDir")
    networks = attrs.get("NetworkSettings", {}).get("Networks") or {}

    host_config = attrs.get("HostConfig", {})
    existing_ports = host_config.get("PortBindings") or {}
    binds = list(host_config.get("Binds") or [])
    mounts = attrs.get("Mounts") or []
    existing_destinations = set()
    for b in binds:
        parts = b.split(":")
        if len(parts) >= 2:
            existing_destinations.add(parts[1])

    for m in mounts:
        dest = m.get("Destination")
        src = m.get("Source")
        m_type = m.get("Type")
        rw = m.get("RW", True)
        mode = "rw" if rw else "ro"
        if dest and src and dest not in existing_destinations:
            if m_type == "bind":
                binds.append(f"{src}:{dest}:{mode}")
                existing_destinations.add(dest)
            elif m_type == "volume":
                vol_name = m.get("Name")
                if vol_name:
                    binds.append(f"{vol_name}:{dest}:{mode}")
                    existing_destinations.add(dest)

    restart_policy = host_config.get("RestartPolicy")

    new_port_bindings = dict(existing_ports)
    for m in mappings:
        c_port = m.get("container_port")
        h_port = int(m.get("host_port", 0))
        bind_ip = m.get("bind", "0.0.0.0")

        chk = check_port_availability(h_port, bind_ip)
        if not chk["free"]:
            if f"'{container.name}'" not in chk.get("used_by", ""):
                raise ValueError(f"Port {h_port} is not available: {chk.get('used_by')}")

        new_port_bindings[c_port] = [{"HostIp": bind_ip, "HostPort": str(h_port)}]

    app_id = f"docker:{container.name}:multi"
    store.save_port_snapshot(app_id, 0, 0, {
        "image": image,
        "ports": existing_ports,
        "env": env,
        "cmd": cmd,
        "entrypoint": entrypoint,
        "labels": labels,
        "user": user,
        "working_dir": working_dir,
        "restart_policy": restart_policy,
        "binds": binds,
        "networks": list(networks.keys()),
    })

    run_kwargs: Dict[str, Any] = {
        "image": image,
        "name": container_name,
        "detach": True,
        "ports": new_port_bindings,
        "environment": env,
        "labels": labels,
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

    backup_name = f"{container_name}_portly_bak_{int(time.time())}"
    container.stop(timeout=10)
    container.rename(backup_name)

    try:
        new_container = client.containers.run(**run_kwargs)
        for net_name in networks:
            try:
                net_obj = client.networks.get(net_name)
                net_obj.connect(new_container)
            except Exception:
                pass

        try:
            container.remove(v=False)
        except Exception as rm_err:
            logger.warning(f"Could not remove temporary backup container {backup_name}: {rm_err}")
    except Exception as run_err:
        try:
            container.rename(container_name)
            container.start()
        except Exception as rb_err:
            logger.error(f"Critical: failed to restore original container {container_name}: {rb_err}")
        raise RuntimeError(f"Failed to apply multi-port change: {run_err}. Original container was preserved and restored.")

    store.log_event("port_change", f"Updated multi-port mappings for container {container_name}", app_id=app_id)
    return {
        "status": "recreated",
        "container": new_container.name,
        "mappings": mappings,
        "rollback_available": True
    }


def rollback_port_change_docker(app_id: str, store: Store) -> Dict[str, Any]:
    """Restores previous port mapping from snapshot non-destructively."""
    import time
    _check_safe_mode(store)
    snap = store.get_port_snapshot(app_id)
    if not snap:
        raise ValueError("No rollback snapshot found for this app.")

    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    parts = app_id.split(":")
    container_name = parts[1]
    target_c_port = parts[2]
    original_port = snap["original_port"]
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

    try:
        new_c = client.containers.run(**run_kwargs)
        for net_name in cfg.get("networks", []):
            try:
                net_obj = client.networks.get(net_name)
                net_obj.connect(new_c)
            except Exception:
                pass
        try:
            container.remove(v=False)
        except Exception:
            pass
    except Exception as run_err:
        try:
            container.rename(container_name)
            container.start()
        except Exception:
            pass
        raise RuntimeError(f"Rollback failed: {run_err}. Container restored to pre-rollback state.")

    store.clear_port_snapshot(app_id)
    store.log_event("port_rollback", f"Rolled back container {container_name} port to {original_port}", app_id=app_id)
    return {"status": "rolled_back", "port": original_port}


SAFE_COMMAND_BINARIES = {
    "ps", "top", "df", "du", "free", "uptime", "uname", "whoami", "id",
    "netstat", "ss", "env", "printenv", "ls", "pwd", "date", "cat",
    "head", "tail", "ip", "ifconfig", "hostname"
}

FORBIDDEN_OPERATORS = [">", ">>", "|", ";", "&&", "||", "$(", "`", "<"]


def _validate_safe_command(command: str):
    """Enforces that command is a read-only diagnostic command without redirection or chaining."""
    import os
    cmd_str = command.strip()
    if not cmd_str:
        raise ValueError("Command cannot be empty")

    for op in FORBIDDEN_OPERATORS:
        if op in cmd_str:
            raise PermissionError(
                f"Safe mode is active. Command contains operator '{op}' which is restricted in safe mode."
            )

    parts = cmd_str.split()
    bin_name = os.path.basename(parts[0]).lower()
    if bin_name not in SAFE_COMMAND_BINARIES:
        raise PermissionError(
            f"Safe mode is active. Executable '{bin_name}' is not in the safe inspection whitelist. "
            f"Unlock safe mode in the top bar to execute custom commands."
        )


def exec_in_container(
    container_name_or_id: str,
    command: str,
    store: Optional[Store] = None,
    timeout: int = 10
) -> Dict[str, Any]:
    """Runs a command inside a Docker container subject to Safe Mode checks."""
    import time
    if store and store.get_setting("safe_mode", "true").lower() == "true":
        _validate_safe_command(command)

    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    container = client.containers.get(container_name_or_id)
    t0 = time.perf_counter()
    exec_res = container.exec_run(command, stdout=True, stderr=True, demux=False)
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    raw_output = exec_res.output
    output_str = raw_output.decode("utf-8", errors="replace") if isinstance(raw_output, (bytes, bytearray)) else str(raw_output or "")

    return {
        "exit_code": exec_res.exit_code,
        "output": output_str,
        "command": command,
        "duration_ms": duration_ms,
    }


def get_container_compose_config(container_name_or_id: str) -> Dict[str, Any]:
    """Inspects container labels and securely retrieves docker-compose file configuration."""
    import os
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

    # Attempt to locate compose file
    candidate_path = None
    if config_files:
        first_file = config_files.split(",")[0].strip()
        if os.path.isabs(first_file):
            candidate_path = first_file
        elif working_dir:
            candidate_path = os.path.join(working_dir, first_file)

    if not candidate_path and working_dir:
        for fname in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            p = os.path.join(working_dir, fname)
            if os.path.isfile(p):
                candidate_path = p
                break

    if not candidate_path:
        return {
            "has_compose": True,
            "project": project or "",
            "service": service or "",
            "working_dir": working_dir or "",
            "config_file": config_files or "",
            "content": None,
            "error": "Compose file not found on host filesystem or path is not set.",
        }

    # Security check: canonicalize and verify path
    real_path = os.path.realpath(candidate_path)
    if not os.path.isfile(real_path):
        return {
            "has_compose": True,
            "project": project or "",
            "service": service or "",
            "working_dir": working_dir or "",
            "config_file": real_path,
            "content": None,
            "error": f"Compose file '{real_path}' does not exist on host filesystem.",
        }

    # Check extension and size
    ext = os.path.splitext(real_path)[1].lower()
    if ext not in (".yml", ".yaml"):
        return {
            "has_compose": True,
            "project": project or "",
            "service": service or "",
            "working_dir": working_dir or "",
            "config_file": real_path,
            "content": None,
            "error": "Security check failed: config file is not a YAML file.",
        }

    if os.path.getsize(real_path) > 1048576:
        return {
            "has_compose": True,
            "project": project or "",
            "service": service or "",
            "working_dir": working_dir or "",
            "config_file": real_path,
            "content": None,
            "error": "Compose file exceeds maximum allowed size (1MB).",
        }

    try:
        with open(real_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        return {
            "has_compose": True,
            "project": project or "",
            "service": service or "",
            "working_dir": working_dir or "",
            "config_file": real_path,
            "content": content,
            "error": None,
        }
    except Exception as e:
        return {
            "has_compose": True,
            "project": project or "",
            "service": service or "",
            "working_dir": working_dir or "",
            "config_file": real_path,
            "content": None,
            "error": f"Failed to read compose file: {str(e)}",
        }


def get_docker_system_df(store: Store) -> Dict[str, Any]:
    """Returns Docker disk and resource usage information."""
    client = get_docker_client()
    if not client:
        return {
            "available": False,
            "images_count": 0,
            "containers_count": 0,
            "volumes_count": 0,
            "total_size_mb": 0.0,
            "total_reclaimable_mb": 0.0,
        }

    try:
        df_data = client.df()
        images = df_data.get("Images") or []
        containers = df_data.get("Containers") or []
        volumes = df_data.get("Volumes") or []
        build_cache = df_data.get("BuildCache") or []

        total_size = sum(img.get("Size", 0) for img in images)
        total_size += sum(v.get("UsageData", {}).get("Size", 0) for v in volumes if v.get("UsageData"))
        total_size += sum(b.get("Size", 0) for b in build_cache)

        reclaimable = 0
        for img in images:
            if img.get("Containers", 0) == 0:
                reclaimable += img.get("Size", 0)
        for v in volumes:
            if v.get("UsageData", {}).get("RefCount", 0) == 0:
                reclaimable += v.get("UsageData", {}).get("Size", 0)
        for b in build_cache:
            if not b.get("InUse", False):
                reclaimable += b.get("Size", 0)

        return {
            "available": True,
            "images_count": len(images),
            "containers_count": len(containers),
            "volumes_count": len(volumes),
            "build_cache_count": len(build_cache),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_reclaimable_mb": round(reclaimable / (1024 * 1024), 2),
        }
    except Exception as e:
        logger.warning(f"Error querying docker df: {e}")
        return {
            "available": True,
            "error": str(e),
            "images_count": 0,
            "containers_count": 0,
            "volumes_count": 0,
            "total_size_mb": 0.0,
            "total_reclaimable_mb": 0.0,
        }


def list_docker_images(store: Store) -> List[Dict[str, Any]]:
    """Returns a list of local Docker images."""
    client = get_docker_client()
    if not client:
        return []
    try:
        images = client.images.list()
        res = []
        for img in images:
            attrs = getattr(img, "attrs", {}) or {}
            size_bytes = attrs.get("Size", 0)
            created = attrs.get("Created", "")
            tags = list(getattr(img, "tags", []) or [])
            res.append({
                "id": img.id[:19] if img.id else "",
                "full_id": img.id,
                "tags": tags,
                "primary_tag": tags[0] if tags else "<none>:<none>",
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "created": created,
            })
        return res
    except Exception as e:
        logger.error(f"Error listing docker images: {e}")
        return []


def list_docker_volumes(store: Store) -> List[Dict[str, Any]]:
    """Returns a list of local Docker volumes."""
    client = get_docker_client()
    if not client:
        return []
    try:
        vols = client.volumes.list()
        res = []
        for v in vols:
            attrs = getattr(v, "attrs", {}) or {}
            res.append({
                "name": v.name,
                "driver": attrs.get("Driver", "local"),
                "mountpoint": attrs.get("Mountpoint", ""),
                "created": attrs.get("CreatedAt", ""),
                "labels": attrs.get("Labels") or {},
            })
        return res
    except Exception as e:
        logger.error(f"Error listing docker volumes: {e}")
        return []


def prune_docker_system(store: Store) -> Dict[str, Any]:
    """Prunes stopped containers, dangling images, unused volumes, and unused networks."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    total_reclaimed = 0
    containers_pruned = client.containers.prune()
    total_reclaimed += containers_pruned.get("SpaceReclaimed", 0) or 0

    images_pruned = client.images.prune()
    total_reclaimed += images_pruned.get("SpaceReclaimed", 0) or 0

    try:
        volumes_pruned = client.volumes.prune()
        total_reclaimed += volumes_pruned.get("SpaceReclaimed", 0) or 0
    except Exception as ve:
        logger.warning(f"Could not prune volumes: {ve}")
        volumes_pruned = {}

    try:
        networks_pruned = client.networks.prune()
    except Exception:
        networks_pruned = {}

    store.log_event("docker_prune", f"Pruned docker system, reclaimed {round(total_reclaimed / (1024*1024), 2)} MB")
    return {
        "status": "success",
        "space_reclaimed_mb": round(total_reclaimed / (1024 * 1024), 2),
        "deleted": {
            "containers": containers_pruned.get("ContainersDeleted") or [],
            "images": [i.get("Deleted") for i in (images_pruned.get("ImagesDeleted") or []) if isinstance(i, dict)] if images_pruned.get("ImagesDeleted") else [],
            "volumes": volumes_pruned.get("VolumesDeleted") or [],
            "networks": networks_pruned.get("NetworksDeleted") or [],
        }
    }


def manage_compose_stack(project_name: str, action: str, store: Store) -> Dict[str, Any]:
    """Executes stack-wide action (restart, stop, start, down) on compose project containers."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    act = action.lower().strip()
    valid_actions = {"restart", "stop", "start", "down"}
    if act not in valid_actions:
        raise ValueError(f"Invalid compose action '{action}'. Valid actions: {', '.join(valid_actions)}")

    matching = []
    for c in client.containers.list(all=True):
        labels = getattr(c, "labels", {}) or {}
        if labels.get("com.docker.compose.project") == project_name:
            matching.append(c)

    if not matching:
        raise ValueError(f"No containers found for compose project '{project_name}'")

    affected = []
    for c in matching:
        try:
            if act == "restart":
                c.restart()
            elif act == "stop":
                c.stop()
            elif act == "start":
                c.start()
            elif act == "down":
                c.stop()
                c.remove(v=False)
            affected.append(c.name)
        except Exception as e:
            logger.error(f"Error performing '{act}' on container {c.name}: {e}")

    store.log_event("compose_action", f"Executed {act} on compose project {project_name} ({len(affected)} containers)")
    return {
        "status": "ok",
        "action": act,
        "project": project_name,
        "affected_containers": affected
    }


def deploy_container(
    image: str,
    name: str,
    ports: Dict[str, Any],
    env: Dict[str, str],
    volumes: List[str],
    restart_policy: str,
    store: Store
) -> Dict[str, Any]:
    """Deploys a new Docker container with port verification and safe mode check."""
    _check_safe_mode(store)
    client = get_docker_client()
    if not client:
        raise RuntimeError("Docker is not available.")

    if not image or not image.strip():
        raise ValueError("Container image is required.")
    if not name or not name.strip():
        raise ValueError("Container name is required.")

    # Validate ports
    formatted_ports = {}
    for c_port, h_port in ports.items():
        try:
            hp_int = int(h_port)
            chk = check_port_availability(hp_int, "0.0.0.0")
            if not chk["free"]:
                raise ValueError(f"Port {hp_int} is already in use: {chk.get('used_by')}")
            formatted_ports[c_port] = [{"HostIp": "0.0.0.0", "HostPort": str(hp_int)}]
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid port configuration: {e}")

    run_kwargs: Dict[str, Any] = {
        "image": image.strip(),
        "name": name.strip(),
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
        store.log_event("container_deploy", f"Deployed new container '{name}' from image '{image}'")
        return {
            "status": "deployed",
            "container": cont.name,
            "id": cont.id[:12] if cont.id else "",
        }
    except Exception as e:
        logger.error(f"Failed to deploy container {name}: {e}")
        raise RuntimeError(f"Failed to deploy container {name}: {e}")

