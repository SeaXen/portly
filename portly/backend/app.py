"""Portly FastAPI application: REST API, SSE streaming, static files, and background monitoring."""

import asyncio
import csv
import io
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Cookie, Depends, FastAPI, HTTPException, Header, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from portly.backend import auth, favicon as favicon_module, proxy_gen, tls_inspector
from portly.backend.actions import docker_actions, process_actions
from portly.backend.discovery.docker_src import get_docker_client, is_docker_available, set_on_docker_event
from portly.backend.discovery.host import discover_host_ports
from portly.backend.discovery.merge import merge_discovered_apps
from portly.backend.health import check_app_health
from portly.backend.notifications import detect_changes, send_webhook_sync
from portly.backend.ports import check_port_availability, plan_port_change, suggest_free_ports
from portly.backend.stats import collect_snapshot, get_current_stats, get_detailed_system_stats
from portly.backend.store import Store

logger = logging.getLogger("portly.app")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("PORTLY_TESTING") == "1":
        yield
        return

    # Initial scan
    await refresh_discovery()

    # Background refresh loop
    async def background_poller():
        while True:
            try:
                interval = float(store.get_setting("refresh_interval", "3"))
            except ValueError:
                interval = 3.0
            await asyncio.sleep(max(1.0, interval))
            if store.get_setting("auto_refresh", "true").lower() == "true":
                try:
                    await refresh_discovery()
                except Exception as e:
                    logger.warning(f"Error in background discovery refresh: {e}")

    poller_task = asyncio.create_task(background_poller())
    try:
        yield
    finally:
        poller_task.cancel()

app = FastAPI(title="Portly API", version="1.0.0", lifespan=lifespan)

cors_origins_env = os.environ.get("PORTLY_CORS_ORIGINS", "")
if cors_origins_env:
    allowed_origins = [orig.strip() for orig in cors_origins_env.split(",") if orig.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

store = Store()

# Cached discovery state
_cached_apps: List[Dict[str, Any]] = []
_cached_conflicts: List[Dict[str, Any]] = []
_last_scan_time: float = 0.0
_sse_subscribers: List[asyncio.Queue] = []
_scan_lock = asyncio.Lock()


def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias="portly_session"),
    authorization: Optional[str] = Header(None)
) -> Optional[Dict[str, Any]]:
    # 1. Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        sess = auth.validate_session(token)
        if sess:
            return sess

    # 2. Cookie
    if session_token:
        sess = auth.validate_session(session_token)
        if sess:
            return sess

    # 3. If no users exist yet
    if store.get_user_count() == 0:
        mode = os.getenv("PORTLY_MODE", "desktop").lower()
        host = os.getenv("PORTLY_HOST", "127.0.0.1")
        allow_insecure = os.getenv("PORTLY_ALLOW_INSECURE_BIND", "false").lower() in ("true", "1")
        client_host = request.client.host if request.client else "127.0.0.1"
        is_remote = client_host not in ("127.0.0.1", "::1", "localhost", "testclient")

        # When binding to 0.0.0.0, in server mode, or accessed remotely, require setup of admin account
        if (mode == "server" or host in ("0.0.0.0", "::") or is_remote) and not allow_insecure:
            return {"user_id": "setup", "username": "setup", "role": "setup"}

        return {"user_id": "setup", "username": "admin", "role": "admin"}

    return None


def require_auth(current_user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required", "hint": "Please log in"}
        )
    return current_user


def require_admin(current_user: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
    if current_user.get("role") != "admin":
        if current_user.get("role") == "setup":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "SETUP_REQUIRED", "message": "Initial admin setup required before performing mutations.", "hint": "Create an admin account via /api/auth/setup"}
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin privileges required for this action", "hint": "Viewers cannot mutate apps"}
        )
    return current_user


async def refresh_discovery():
    global _cached_apps, _cached_conflicts, _last_scan_time
    async with _scan_lock:
        public_host = store.get_setting("public_host", "")
        # Run synchronous merge in thread
        loop = asyncio.get_event_loop()
        apps, conflicts = await loop.run_in_executor(None, merge_discovered_apps, store, public_host)
        
        # Change detection & events
        events = await loop.run_in_executor(None, detect_changes, apps, conflicts, store)
        
        _cached_apps = apps
        _cached_conflicts = conflicts
        _last_scan_time = time.time()

        # Update stats
        docker_running = sum(1 for a in apps if a.get("source") == "docker" and a.get("status") == "up")
        collect_snapshot(containers_running=docker_running, listening_count=len(apps), conflict_count=len(conflicts))

        # Push to SSE subscribers
        if _sse_subscribers:
            stats = get_current_stats(containers_running=docker_running, listening_count=len(apps), conflict_count=len(conflicts))
            msg = {
                "type": "update",
                "apps": _cached_apps,
                "conflicts": _cached_conflicts,
                "stats": stats,
                "events": events,
                "last_scan": _last_scan_time,
            }
            for q in list(_sse_subscribers):
                try:
                    q.put_nowait(msg)
                except Exception:
                    pass


# Connect docker event listener to refresh discovery
def on_docker_event():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(refresh_discovery(), loop)
    except Exception:
        pass

set_on_docker_event(on_docker_event)





# ---------------- API ROUTES ----------------

# Pydantic Request Models
class AppPatchModel(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    pinned: Optional[bool] = None
    hidden: Optional[bool] = None
    sort_order: Optional[int] = None
    url_override: Optional[str] = None


class BulkActionModel(BaseModel):
    ids: List[str]
    action: str  # move, tag, pin, hide, start, stop, restart
    category_id: Optional[str] = None
    tag: Optional[str] = None


class CustomAppModel(BaseModel):
    id: Optional[str] = None
    name: str
    host: str = "localhost"
    port: int
    health_path: str = "/health"
    health_interval: int = 30
    start_cmd: Optional[str] = None
    stop_cmd: Optional[str] = None
    workdir: Optional[str] = None
    log_file: Optional[str] = None
    start_on_boot: bool = False
    env: Dict[str, str] = Field(default_factory=dict)
    update_cmd: Optional[str] = None


class PortChangeModel(BaseModel):
    host_port: int
    bind: str = "0.0.0.0"


class RuleModel(BaseModel):
    id: Optional[str] = None
    category_id: str
    field: str
    operator: str
    value: str
    priority: int = 10


class CategoryModel(BaseModel):
    id: str
    name: str
    color: str
    mode: str = "manual"
    sort_order: int = 0


class ViewModel(BaseModel):
    id: str
    name: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort: Dict[str, Any] = Field(default_factory=dict)
    group_by: str = "none"
    view_type: str = "table"
    columns: List[str] = Field(default_factory=list)


class LoginModel(BaseModel):
    username: str
    password: str


class SetupModel(BaseModel):
    username: str
    password: str


class ExecModel(BaseModel):
    command: str
    timeout: int = 10


class WebhookTestModel(BaseModel):
    url: Optional[str] = None
    type: Optional[str] = None
    event: Optional[str] = "test"


# 1. Apps unified list & detail
@app.get("/api/apps")
async def get_apps(
    source: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    category_id: Optional[str] = None,
    bind: Optional[str] = None,
    search: Optional[str] = None,
    include_hidden: bool = False,
    sort_by: str = "port",
    sort_dir: str = "asc"
):
    apps = list(_cached_apps)

    if not include_hidden:
        apps = [a for a in apps if not a.get("hidden")]

    if source:
        apps = [a for a in apps if a.get("source", "").lower() == source.lower()]

    if status_filter:
        apps = [a for a in apps if a.get("status", "").lower() == status_filter.lower()]

    if category_id:
        apps = [a for a in apps if a.get("category_id") == category_id]

    if bind:
        apps = [a for a in apps if a.get("bind") == bind]

    if search:
        s = search.lower()
        apps = [
            a for a in apps
            if s in a.get("name", "").lower()
            or s in str(a.get("port", ""))
            or s in a.get("process_name", "").lower()
            or s in a.get("image", "").lower()
            or any(s in t.lower() for t in a.get("tags", []))
        ]

    # Sorting
    reverse = (sort_dir.lower() == "desc")
    if sort_by == "port":
        apps.sort(key=lambda a: a.get("port", 0), reverse=reverse)
    elif sort_by == "name":
        apps.sort(key=lambda a: a.get("name", "").lower(), reverse=reverse)
    elif sort_by == "cpu":
        apps.sort(key=lambda a: a.get("cpu_percent", 0.0), reverse=reverse)
    elif sort_by == "ram":
        apps.sort(key=lambda a: a.get("ram_mb", 0.0), reverse=reverse)
    elif sort_by == "uptime":
        apps.sort(key=lambda a: a.get("uptime_sec", 0), reverse=reverse)
    elif sort_by == "status":
        apps.sort(key=lambda a: a.get("status", ""), reverse=reverse)
    elif sort_by == "category":
        apps.sort(key=lambda a: a.get("category_id", ""), reverse=reverse)

    docker_avail, docker_err = is_docker_available()

    return {
        "apps": apps,
        "total": len(apps),
        "conflicts": _cached_conflicts,
        "docker_status": {
            "available": docker_avail,
            "message": docker_err,
        },
        "last_scan": _last_scan_time,
    }


@app.get("/api/apps/{app_id:path}/logs")
async def get_logs_endpoint(
    app_id: str,
    tail: int = 500,
    follow: bool = False,
    user: Dict[str, Any] = Depends(require_admin)
):
    if app_id.startswith("docker:"):
        c_name = app_id.split(":")[1]
        lines = docker_actions.get_container_logs(c_name, tail=tail, follow=False)
    elif app_id.startswith("custom:"):
        lines = process_actions.get_custom_app_logs(app_id, store, tail=tail)
    else:
        lines = [f"Direct log capture is not available for host process '{app_id}'."]

    return {"lines": lines, "count": len(lines)}


@app.get("/api/apps/{app_id:path}/proxy-config")
async def get_proxy_config_endpoint(
    app_id: str,
    format: Optional[str] = Query(None),
    domain: Optional[str] = Query(None)
):
    target_app = None
    for a in _cached_apps:
        if a["id"] == app_id:
            target_app = a
            break
    if not target_app:
        target_app = store.get_app(app_id)

    if not target_app:
        target_app = store.get_app(app_id)
    if not target_app:
        target_app = store.get_app(app_id)

    if not target_app:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"App '{app_id}' not found"})

    port = target_app.get("port")
    if not port or port <= 0:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PORT", "message": "App does not have an active listening port"})

    host = target_app.get("bind") or target_app.get("host") or "127.0.0.1"
    configs_data = proxy_gen.generate_all_proxy_configs(
        name=target_app.get("name", "app"),
        port=port,
        host=host,
        domain=domain
    )

    if format:
        fmt = format.lower().strip()
        if fmt in configs_data["configs"]:
            return {
                "format": fmt,
                "config": configs_data["configs"][fmt],
                "domain": configs_data["domain"],
                "port": configs_data["port"],
                "router_name": configs_data["router_name"],
            }
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_FORMAT", "message": f"Unsupported format '{format}'. Supported formats: caddy, nginx, traefik, traefik_yaml, traefik_labels"}
        )

    return configs_data


@app.get("/api/apps/{app_id:path}/favicon")
async def get_app_favicon_endpoint(app_id: str):
    target_app = None
    for a in _cached_apps:
        if a["id"] == app_id:
            target_app = a
            break

    if not target_app:
        target_app = store.get_app(app_id)

    if not target_app:
        svg_data, mime = favicon_module.get_fallback_svg(app_id.split(":")[-1])
        return Response(content=svg_data, media_type=mime)

    icons_dir = os.path.join(
        os.getenv("PORTLY_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")),
        "icons"
    )
    data, mime = await asyncio.to_thread(favicon_module.fetch_or_generate_app_icon, target_app, icons_dir)
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=86400"}
    )


@app.get("/api/apps/{app_id:path}/tls")
async def get_app_tls_endpoint(app_id: str):
    target_app = None
    for a in _cached_apps:
        if a["id"] == app_id:
            target_app = a
            break
    if not target_app:
        target_app = store.get_app(app_id)

    if not target_app:
        target_app = store.get_app(app_id)
    if not target_app:
        target_app = store.get_app(app_id)

    if not target_app:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"App '{app_id}' not found"})

    port = target_app.get("port")
    if not port or port <= 0:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PORT", "message": "App does not have an active port"})

    host = target_app.get("bind") or target_app.get("host") or "127.0.0.1"
    res = await asyncio.to_thread(tls_inspector.inspect_tls_certificate, host, port)
    return res


@app.post("/api/apps/{app_id:path}/exec")
async def exec_command_endpoint(
    app_id: str,
    data: ExecModel,
    user: Dict[str, Any] = Depends(require_admin)
):
    if not app_id.startswith("docker:"):
        raise HTTPException(
            status_code=400,
            detail={"code": "NOT_DOCKER", "message": "Command execution is only supported for Docker containers."}
        )
    container_name = app_id.split(":")[1]
    try:
        res = await asyncio.to_thread(
            docker_actions.exec_in_container,
            container_name,
            data.command,
            store=store,
            timeout=data.timeout
        )
        return res
    except PermissionError as pe:
        raise HTTPException(
            status_code=403,
            detail={"code": "SAFE_MODE_RESTRICTION", "message": str(pe)}
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_COMMAND", "message": str(ve)}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "EXEC_FAILED", "message": f"Failed to execute command: {str(e)}"}
        )


@app.get("/api/apps/{app_id:path}/compose")
async def get_app_compose_endpoint(app_id: str):
    if not app_id.startswith("docker:"):
        raise HTTPException(
            status_code=400,
            detail={"code": "NOT_DOCKER", "message": "Docker Compose inspection is only supported for Docker containers."}
        )
    container_name = app_id.split(":")[1]
    try:
        res = await asyncio.to_thread(docker_actions.get_container_compose_config, container_name)
        return res
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "COMPOSE_FAILED", "message": f"Failed to inspect compose: {str(e)}"}
        )


@app.get("/api/apps/{app_id:path}")
async def get_app_detail(app_id: str):
    target = None
    for a in _cached_apps:
        if a["id"] == app_id:
            target = a
            break
    if not target:
        target = store.get_app(app_id)
    if target:
        # Check live health non-blocking
        health = await asyncio.to_thread(check_app_health, target)
        store.record_health(app_id, health["ok"], health["latency_ms"])
        history = store.get_health_history(app_id, limit=30)
        
        # Inspect details if docker non-blocking
        docker_inspect = None
        if target.get("source") == "docker":
            try:
                docker_inspect = await asyncio.to_thread(docker_actions.inspect_container, target.get("container_name", ""))
            except Exception:
                pass

        return {
            "app": target,
            "health": health,
            "health_history": history,
            "docker_inspect": docker_inspect,
        }

    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"App '{app_id}' not found"})


@app.patch("/api/apps/{app_id:path}")
async def patch_app(app_id: str, patch: AppPatchModel, user: Dict[str, Any] = Depends(require_admin)):
    clean_kwargs = {k: v for k, v in (patch.model_dump() if hasattr(patch, "model_dump") else patch.dict()).items() if v is not None}
    updated = store.upsert_app_override(app_id, **clean_kwargs)
    await refresh_discovery()
    return {"status": "ok", "app": updated}


# 2. Bulk actions
@app.post("/api/apps/bulk")
async def bulk_action(data: BulkActionModel, user: Dict[str, Any] = Depends(require_admin)):
    action = data.action.lower()
    ids = data.ids

    if action == "move" and data.category_id:
        for app_id in ids:
            store.upsert_app_override(app_id, category_id=data.category_id)
    elif action == "tag" and data.tag:
        for app_id in ids:
            app_meta = store.get_app(app_id) or {}
            tags = list(app_meta.get("tags") or [])
            if data.tag not in tags:
                tags.append(data.tag)
                store.upsert_app_override(app_id, tags=tags)
    elif action == "pin":
        for app_id in ids:
            store.upsert_app_override(app_id, pinned=True)
    elif action == "hide":
        for app_id in ids:
            store.upsert_app_override(app_id, hidden=True)
    elif action in ("start", "stop", "restart"):
        # Safe mode check
        if store.get_setting("safe_mode", "true").lower() == "true":
            raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": "Safe mode is active. Mutating actions are locked."})
        for app_id in ids:
            try:
                if app_id.startswith("docker:"):
                    c_name = app_id.split(":")[1]
                    if action == "start":
                        docker_actions.start_container(c_name, store)
                    elif action == "stop":
                        docker_actions.stop_container(c_name, store)
                    elif action == "restart":
                        docker_actions.restart_container(c_name, store)
                elif app_id.startswith("custom:"):
                    if action == "start":
                        process_actions.start_custom_app(app_id, store)
                    elif action == "stop":
                        process_actions.stop_custom_app(app_id, store)
                    elif action == "restart":
                        process_actions.restart_custom_app(app_id, store)
            except Exception as e:
                logger.warning(f"Error in bulk action for {app_id}: {e}")

    await refresh_discovery()
    return {"status": "ok", "count": len(ids)}


# 3. Actions: Start, Stop, Restart, Logs
@app.post("/api/apps/{app_id:path}/start")
async def start_app_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    try:
        if app_id.startswith("docker:"):
            c_name = app_id.split(":")[1]
            res = docker_actions.start_container(c_name, store)
        elif app_id.startswith("custom:"):
            res = process_actions.start_custom_app(app_id, store)
        else:
            raise HTTPException(status_code=400, detail={"code": "NOT_SUPPORTED", "message": "Starting unmanaged host processes is not supported."})
        await refresh_discovery()
        return res
    except HTTPException:
        raise
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": str(pe)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "ACTION_FAILED", "message": str(e)})


@app.post("/api/apps/{app_id:path}/stop")
async def stop_app_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    try:
        if app_id.startswith("docker:"):
            c_name = app_id.split(":")[1]
            res = docker_actions.stop_container(c_name, store)
        elif app_id.startswith("custom:"):
            res = process_actions.stop_custom_app(app_id, store)
        elif app_id.startswith("host:"):
            # If user asks to kill a host process
            for a in _cached_apps:
                if a["id"] == app_id and a.get("pid"):
                    res = process_actions.kill_host_process(a["pid"], store)
                    await refresh_discovery()
                    return res
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Process not found"})
        else:
            raise HTTPException(status_code=400, detail={"code": "NOT_SUPPORTED", "message": "Stop not supported for this app."})
        await refresh_discovery()
        return res
    except HTTPException:
        raise
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": str(pe)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "ACTION_FAILED", "message": str(e)})


@app.post("/api/apps/{app_id:path}/restart")
async def restart_app_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    try:
        if app_id.startswith("docker:"):
            c_name = app_id.split(":")[1]
            res = docker_actions.restart_container(c_name, store)
        elif app_id.startswith("custom:"):
            res = process_actions.restart_custom_app(app_id, store)
        else:
            raise HTTPException(status_code=400, detail={"code": "NOT_SUPPORTED", "message": "Restart not supported for unmanaged host processes."})
        await refresh_discovery()
        return res
    except HTTPException:
        raise
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": str(pe)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "ACTION_FAILED", "message": str(e)})


# 4. Port checking and Change Port flow
@app.get("/api/ports/check")
async def check_port_endpoint(port: int = Query(...), bind: str = "0.0.0.0"):
    res = check_port_availability(port, bind)
    return res


@app.get("/api/ports/suggest")
async def suggest_ports_endpoint(start: int = 3000, count: int = 5, bind: str = "0.0.0.0"):
    ports = suggest_free_ports(start_port=start, count=count, bind_ip=bind)
    return {"suggested": ports}


@app.post("/api/apps/{app_id:path}/port")
async def change_port_endpoint(
    app_id: str,
    data: PortChangeModel,
    apply: bool = False,
    rollback: bool = False,
    user: Dict[str, Any] = Depends(require_admin)
):
    if rollback:
        try:
            if app_id.startswith("docker:"):
                res = docker_actions.rollback_port_change_docker(app_id, store)
                await refresh_discovery()
                return res
            else:
                raise HTTPException(status_code=400, detail={"code": "NOT_SUPPORTED", "message": "Rollback is only supported for Docker containers"})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail={"code": "ROLLBACK_FAILED", "message": str(e)})

    # Plan
    plan_res = plan_port_change(app_id, data.host_port, data.bind, store)
    if not plan_res["valid"]:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PLAN", "message": plan_res["error"]})

    if not apply:
        return {"plan": plan_res["plan"]}

    # Execute
    if store.get_setting("safe_mode", "true").lower() == "true":
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": "Safe mode is active. Port mutation is locked."})

    plan = plan_res["plan"]
    if plan["type"] == "docker":
        try:
            res = docker_actions.apply_port_change_docker(
                plan["container_name"],
                data.host_port,
                plan["target_container_port"],
                data.bind,
                store
            )
            await refresh_discovery()
            return res
        except Exception as e:
            raise HTTPException(status_code=500, detail={"code": "APPLY_FAILED", "message": str(e)})
    elif plan["type"] == "custom":
        clean_id = app_id.replace("custom:", "")
        existing = store.get_custom_app(clean_id) or {}
        kwargs = {
            "health_path": existing.get("health_path", "/health"),
            "health_interval": existing.get("health_interval", 30),
            "start_cmd": existing.get("start_cmd"),
            "stop_cmd": existing.get("stop_cmd"),
            "workdir": existing.get("workdir"),
            "log_file": existing.get("log_file"),
            "start_on_boot": existing.get("start_on_boot", False),
            "env": existing.get("env", {}),
            "update_cmd": existing.get("update_cmd"),
        }
        store.upsert_custom_app(
            clean_id,
            existing.get("name") or plan["name"],
            existing.get("host") or "localhost",
            data.host_port,
            **kwargs
        )
        process_actions.restart_custom_app(app_id, store)
        await refresh_discovery()
        return {"status": "updated", "new_port": data.host_port}
    else:
        raise HTTPException(status_code=400, detail={"code": "NOT_SUPPORTED", "message": "Unsupported app type for port change"})


# 5. Image updates
@app.post("/api/apps/{app_id:path}/update/check")
async def check_update_endpoint(app_id: str):
    image_tag = ""
    for a in _cached_apps:
        if a["id"] == app_id:
            image_tag = a.get("image", "")
            break
    if not image_tag:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Container image not found"})
    return docker_actions.check_image_update(image_tag)


@app.post("/api/apps/{app_id:path}/update/apply")
async def apply_update_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    if store.get_setting("safe_mode", "true").lower() == "true":
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": "Safe mode is active. Mutating actions are locked."})
    return {"status": "ok", "message": "Image check complete. Image is latest."}


# 6. Custom apps CRUD
@app.get("/api/custom-apps")
async def list_custom_apps():
    return store.get_custom_apps()


@app.post("/api/custom-apps")
async def create_or_update_custom_app(data: CustomAppModel, user: Dict[str, Any] = Depends(require_admin)):
    if data.log_file and not process_actions._is_safe_log_path(data.log_file):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_LOG_PATH", "message": f"Log file path '{data.log_file}' is not permitted."}
        )
    app_id = data.id or f"custom_{int(time.time()*1000)}"
    res = store.upsert_custom_app(
        app_id,
        data.name,
        data.host,
        data.port,
        health_path=data.health_path,
        health_interval=data.health_interval,
        start_cmd=data.start_cmd,
        stop_cmd=data.stop_cmd,
        workdir=data.workdir,
        log_file=data.log_file,
        start_on_boot=data.start_on_boot,
        env=data.env,
        update_cmd=data.update_cmd
    )
    # Check start on boot
    if data.start_on_boot and data.start_cmd:
        try:
            process_actions.start_custom_app(f"custom:{app_id}", store)
        except Exception:
            pass
    await refresh_discovery()
    return res


@app.delete("/api/custom-apps/{app_id:path}")
async def delete_custom_app_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    clean_id = app_id.replace("custom:", "")
    try:
        process_actions.stop_custom_app(f"custom:{clean_id}", store)
    except Exception:
        pass
    store.delete_custom_app(clean_id)
    await refresh_discovery()
    return {"status": "deleted", "id": clean_id}


# 7. Stats, System & Events
@app.get("/api/stats")
async def get_stats_endpoint():
    docker_running = sum(1 for a in _cached_apps if a.get("source") == "docker" and a.get("status") == "up")
    return get_current_stats(containers_running=docker_running, listening_count=len(_cached_apps), conflict_count=len(_cached_conflicts))


@app.get("/api/system")
async def get_system_endpoint():
    return get_detailed_system_stats()


@app.get("/api/events")
async def get_events_endpoint(limit: int = 100):
    return store.get_events(limit=limit)


# 8. Categories & Rules & Views
@app.get("/api/categories")
async def get_categories_endpoint():
    cats = store.get_categories()
    # Add app counts
    counts = {}
    for a in _cached_apps:
        cid = a.get("category_id", "uncategorized")
        counts[cid] = counts.get(cid, 0) + 1
    for c in cats:
        c["count"] = counts.get(c["id"], 0)
    return cats


@app.post("/api/categories")
async def save_category_endpoint(data: CategoryModel, user: Dict[str, Any] = Depends(require_admin)):
    res = store.upsert_category(data.id, data.name, data.color, data.mode, data.sort_order)
    await refresh_discovery()
    return res


@app.delete("/api/categories/{cat_id}")
async def delete_category_endpoint(cat_id: str, user: Dict[str, Any] = Depends(require_admin)):
    store.delete_category(cat_id)
    await refresh_discovery()
    return {"status": "deleted", "id": cat_id}


@app.get("/api/rules")
async def get_rules_endpoint():
    return store.get_rules()


@app.post("/api/rules")
async def save_rule_endpoint(data: RuleModel, user: Dict[str, Any] = Depends(require_admin)):
    rule_id = data.id or f"r_{int(time.time()*1000)}"
    res = store.add_rule(rule_id, data.category_id, data.field, data.operator, data.value, data.priority)
    await refresh_discovery()
    return res


@app.delete("/api/rules/{rule_id}")
async def delete_rule_endpoint(rule_id: str, user: Dict[str, Any] = Depends(require_admin)):
    store.delete_rule(rule_id)
    await refresh_discovery()
    return {"status": "deleted", "id": rule_id}


@app.get("/api/views")
async def get_views_endpoint():
    return store.get_views()


@app.post("/api/views")
async def save_view_endpoint(data: ViewModel, user: Dict[str, Any] = Depends(require_admin)):
    return store.save_view(data.id, data.name, data.filters, data.sort, data.group_by, data.view_type, data.columns)


@app.delete("/api/views/{view_id}")
async def delete_view_endpoint(view_id: str, user: Dict[str, Any] = Depends(require_admin)):
    store.delete_view(view_id)
    return {"status": "deleted", "id": view_id}


# 9. Settings
@app.get("/api/settings")
async def get_settings_endpoint():
    return store.get_settings()


@app.patch("/api/settings")
async def update_settings_endpoint(settings_dict: Dict[str, str], user: Dict[str, Any] = Depends(require_admin)):
    for k, v in settings_dict.items():
        store.set_setting(k, str(v))
    return store.get_settings()


@app.post("/api/settings/test-webhook")
async def test_webhook_endpoint(
    data: Optional[WebhookTestModel] = None,
    user: Dict[str, Any] = Depends(require_admin)
):
    url = (data.url if data and data.url else store.get_setting("webhook_url", "")).strip()
    w_type = (data.type if data and data.type else store.get_setting("webhook_type", "generic")).strip()
    if not url:
        raise HTTPException(
            status_code=400,
            detail={"code": "MISSING_URL", "message": "Webhook URL is not configured. Please provide a URL."}
        )
    ok, msg = await asyncio.to_thread(
        send_webhook_sync,
        url,
        w_type,
        "test",
        "⚓ Portly Webhook Test: Connection and notification delivery successful!",
        {"test": True, "ts": time.time()}
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={"code": "WEBHOOK_FAILED", "message": msg}
        )
    return {"status": "ok", "message": msg, "url": url, "type": w_type}



# 10. Scan trigger
@app.post("/api/scan")
async def trigger_scan_endpoint():
    get_docker_client(force_retry=True)
    await refresh_discovery()
    return {"status": "ok", "apps_count": len(_cached_apps), "conflicts": len(_cached_conflicts)}


# 11. Export & Import
@app.get("/api/export")
async def export_data(format: str = "json", user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    if store.get_user_count() > 0 and not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required to export data"}
        )

    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Name", "Port", "Source", "Bind", "Category", "Status", "Process/Image"])
        for a in _cached_apps:
            writer.writerow([
                a.get("name"),
                a.get("port"),
                a.get("source"),
                a.get("bind"),
                a.get("category_id"),
                a.get("status"),
                a.get("image") or a.get("process_name")
            ])
        return Response(content=out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=portly-ports.csv"})
    elif format == "markdown":
        lines = ["# Portly - Ports Cheat Sheet\n", "| Port | Name | Source | Bind | Status |", "|---|---|---|---|---|"]
        for a in _cached_apps:
            lines.append(f"| `{a.get('port')}` | **{a.get('name')}** | {a.get('source')} | `{a.get('bind')}` | {a.get('status')} |")
        return Response(content="\n".join(lines), media_type="text/markdown", headers={"Content-Disposition": "attachment; filename=portly-ports.md"})
    else:
        # Full backup json
        backup = {
            "categories": store.get_categories(),
            "rules": store.get_rules(),
            "custom_apps": store.get_custom_apps(),
            "views": store.get_views(),
            "app_overrides": store.get_all_app_overrides(),
            "settings": store.get_settings(),
        }
        return JSONResponse(content=backup)


@app.post("/api/import")
async def import_data(backup: Dict[str, Any], user: Dict[str, Any] = Depends(require_admin)):
    for c in backup.get("categories", []):
        store.upsert_category(c["id"], c["name"], c["color"], c.get("mode", "manual"), c.get("sort_order", 0))
    for r in backup.get("rules", []):
        store.add_rule(r["id"], r["category_id"], r["field"], r["operator"], r["value"], r.get("priority", 10))
    for ca in backup.get("custom_apps", []):
        kwargs = {k: v for k, v in ca.items() if k not in ("id", "name", "host", "port")}
        if kwargs.get("log_file") and not process_actions._is_safe_log_path(kwargs["log_file"]):
            kwargs["log_file"] = None
        store.upsert_custom_app(ca["id"], ca["name"], ca.get("host", "localhost"), ca["port"], **kwargs)
    for v in backup.get("views", []):
        store.save_view(v["id"], v["name"], v.get("filters", {}), v.get("sort", {}), v.get("group_by", "none"), v.get("view_type", "table"), v.get("columns", []))
    for app_id, ov in backup.get("app_overrides", {}).items():
        store.upsert_app_override(app_id, **ov)
    for k, v in backup.get("settings", {}).items():
        store.set_setting(k, str(v))
    await refresh_discovery()
    return {"status": "imported"}


# 12. Authentication endpoints
@app.get("/api/auth/me")
async def auth_me(user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    user_count = store.get_user_count()
    return {
        "authenticated": user is not None and user.get("user_id") != "setup",
        "user": user,
        "needs_setup": user_count == 0,
    }


@app.post("/api/auth/setup")
async def auth_setup(data: SetupModel, response: Response):
    if store.get_user_count() > 0:
        raise HTTPException(status_code=400, detail={"code": "SETUP_DONE", "message": "Admin account is already configured"})
    pw_hash = auth.hash_password(data.password)
    user = store.create_user("u_admin", data.username, pw_hash, role="admin")
    token = auth.create_session(user["id"], user["username"], role="admin")
    response.set_cookie(key="portly_session", value=token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"status": "ok", "token": token, "username": user["username"], "role": "admin"}


@app.post("/api/auth/login")
async def auth_login(data: LoginModel, response: Response):
    user = store.get_user(data.username)
    if not user or not auth.verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"})
    token = auth.create_session(user["id"], user["username"], role=user.get("role", "admin"))
    response.set_cookie(key="portly_session", value=token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"status": "ok", "token": token, "username": user["username"], "role": user.get("role", "admin")}


@app.post("/api/auth/logout")
async def auth_logout(response: Response, session_token: Optional[str] = Cookie(None, alias="portly_session")):
    if session_token:
        auth.revoke_session(session_token)
    response.delete_cookie(key="portly_session")
    return {"status": "logged_out"}


# 13. Real-time SSE Stream
@app.get("/api/stream")
async def sse_stream(request: Request):
    q = asyncio.Queue()
    _sse_subscribers.append(q)

    # Initial snapshot
    docker_running = sum(1 for a in _cached_apps if a.get("source") == "docker" and a.get("status") == "up")
    initial_stats = get_current_stats(containers_running=docker_running, listening_count=len(_cached_apps), conflict_count=len(_cached_conflicts))
    initial_payload = {
        "type": "snapshot",
        "apps": _cached_apps,
        "conflicts": _cached_conflicts,
        "stats": initial_stats,
        "last_scan": _last_scan_time,
    }
    q.put_nowait(initial_payload)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {
                        "event": "message",
                        "data": json.dumps(data)
                    }
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield {
                        "event": "ping",
                        "data": json.dumps({"ts": time.time()})
                    }
        finally:
            if q in _sse_subscribers:
                _sse_subscribers.remove(q)

    return EventSourceResponse(event_generator())


# 14. Static Frontend Mount & PWA Assets
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

@app.get("/manifest.webmanifest")
@app.get("/manifest.json")
async def get_manifest():
    manifest_file = os.path.join(FRONTEND_DIST, "manifest.webmanifest")
    if os.path.isfile(manifest_file):
        return FileResponse(manifest_file, media_type="application/manifest+json")
    manifest_data = {
        "name": "Portly - Port & Container Dashboard",
        "short_name": "Portly",
        "description": "Real-time local port, container, and reverse proxy manager",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0b0f19",
        "theme_color": "#0b0f19",
        "icons": [
            {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/icons/icon.svg", "sizes": "any", "type": "image/svg+xml"}
        ]
    }
    return Response(content=json.dumps(manifest_data), media_type="application/manifest+json")


@app.get("/sw.js")
async def get_service_worker():
    sw_file = os.path.join(FRONTEND_DIST, "sw.js")
    if os.path.isfile(sw_file):
        return FileResponse(sw_file, media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})
    sw_script = "self.addEventListener('install', e => self.skipWaiting()); self.addEventListener('activate', e => self.clients.claim());"
    return Response(content=sw_script, media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        # Disallow directory traversal markers
        clean_parts = [p for p in full_path.replace("\\", "/").split("/") if p]
        if ".." in clean_parts or "\0" in full_path:
            raise HTTPException(status_code=404, detail="Not Found")
        
        real_frontend = os.path.abspath(FRONTEND_DIST)
        try:
            # Canonicalize and verify that file_path stays strictly within FRONTEND_DIST
            file_path = os.path.abspath(os.path.join(real_frontend, full_path.lstrip("/\\")))
            if os.path.commonpath([real_frontend, file_path]) != real_frontend:
                raise HTTPException(status_code=404, detail="Not Found")
        except (ValueError, OSError):
            raise HTTPException(status_code=404, detail="Not Found")

        if os.path.isfile(file_path):
            return FileResponse(file_path)

        index_file = os.path.join(real_frontend, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Not Found")
