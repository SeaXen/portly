"""Portly FastAPI application: REST API, SSE streaming, static files, and background monitoring."""

import asyncio
import csv
import hmac
import io
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import Cookie, Depends, FastAPI, HTTPException, Header, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
from portly.backend.ports import check_port_availability, check_preflight_collisions, plan_port_change, suggest_free_ports
from portly.backend.stats import collect_snapshot, get_current_stats, get_detailed_system_stats
from portly.backend.store import Store

logger = logging.getLogger("portly.app")
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

from contextlib import asynccontextmanager

store = Store()

# Cached discovery state
_cached_apps: List[Dict[str, Any]] = []
_cached_conflicts: List[Dict[str, Any]] = []
_last_scan_time: float = 0.0
_sse_subscribers: List[asyncio.Queue] = []
_scan_lock = asyncio.Lock()
_safe_mode_unlocked_at: Optional[float] = None


async def refresh_discovery():
    global _cached_apps, _cached_conflicts, _last_scan_time
    async with _scan_lock:
        public_host = store.get_setting("public_host", "")
        loop = asyncio.get_event_loop()
        apps, conflicts = await loop.run_in_executor(None, merge_discovered_apps, store, public_host)
        events = await loop.run_in_executor(None, detect_changes, apps, conflicts, store)

        _cached_apps = apps
        _cached_conflicts = conflicts
        _last_scan_time = time.time()

        # Update stats
        docker_running = sum(1 for a in apps if a.get("source") == "docker" and a.get("status") == "up")
        collect_snapshot(containers_running=docker_running, listening_count=len(apps), conflict_count=len(conflicts))

        # Push to SSE subscribers with bounded queues
        if _sse_subscribers:
            stats = get_current_stats(containers_running=docker_running, listening_count=len(apps), conflict_count=len(conflicts))
            docker_avail, docker_err = is_docker_available()
            
            # Redact apps for general broadcast
            safe_apps = [redact_app_for_summary(a) for a in _cached_apps]
            msg = {
                "type": "update",
                "apps": safe_apps,
                "conflicts": _cached_conflicts,
                "stats": stats,
                "docker_status": {
                    "available": docker_avail,
                    "message": docker_err,
                },
                "events": events,
                "last_scan": _last_scan_time,
            }
            for q in list(_sse_subscribers):
                try:
                    if q.full():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    q.put_nowait(msg)
                except Exception:
                    pass


def redact_app_for_summary(app_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Strip or redact sensitive execution info (env, start_cmd) for summary payloads."""
    clean = dict(app_dict)
    if "env" in clean:
        clean["env_keys"] = list(clean["env"].keys()) if isinstance(clean["env"], dict) else []
        clean.pop("env", None)
    clean.pop("start_cmd", None)
    clean.pop("stop_cmd", None)
    clean.pop("update_cmd", None)
    return clean


def mask_sensitive_env(env_dict: Dict[str, Any]) -> Dict[str, str]:
    """Mask sensitive environment variable values."""
    if not isinstance(env_dict, dict):
        return {}
    sensitive_patterns = ("pass", "secret", "key", "token", "auth", "pwd", "credential")
    masked = {}
    for k, v in env_dict.items():
        v_str = str(v)
        k_lower = k.lower()
        if any(p in k_lower for p in sensitive_patterns) or len(v_str) > 30:
            masked[k] = "********"
        else:
            masked[k] = v_str
    return masked


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_event_loop
    try:
        _main_event_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if os.getenv("PORTLY_TESTING") == "1":
        yield
        return

    # Initial scan
    await refresh_discovery()

    # Auto-start on boot custom apps
    for ca in store.get_custom_apps():
        if ca.get("start_on_boot") and ca.get("start_cmd"):
            try:
                await asyncio.to_thread(process_actions.start_custom_app, f"custom:{ca['id']}", store)
            except Exception as e:
                logger.warning(f"Failed to auto-start custom app {ca['id']} on boot: {e}")

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

    # Background custom app health poller
    async def background_health_poller():
        while True:
            await asyncio.sleep(10.0)
            try:
                custom_apps = store.get_custom_apps()
                for ca in custom_apps:
                    res = await asyncio.to_thread(check_app_health, ca)
                    if res:
                        app_id = f"custom:{ca['id']}"
                        store.record_health(app_id, bool(res.get("ok", False)), float(res.get("latency_ms", 0.0)))
            except Exception as e:
                logger.debug(f"Error in background health poller: {e}")

    # Background session and safe-mode auto-relock maintenance
    async def background_maintenance():
        maintenance_tick = 0
        while True:
            await asyncio.sleep(5)  # Check every 5 seconds for responsive auto-relock
            maintenance_tick += 1

            # Auto-relock check
            global _safe_mode_unlocked_at
            if _safe_mode_unlocked_at is not None:
                current_mode = store.get_setting("safe_mode", "true").lower()
                if current_mode == "false":
                    try:
                        relock_sec = int(store.get_setting("auto_relock_seconds", "900"))
                    except (ValueError, TypeError):
                        relock_sec = 900
                    if relock_sec > 0 and (time.time() - _safe_mode_unlocked_at) >= relock_sec:
                        store.set_setting("safe_mode", "true")
                        _safe_mode_unlocked_at = None
                        store.log_audit_event(
                            user="system",
                            action="auto_relock_safe_mode",
                            target="Safe mode automatically re-locked after inactivity/timeout"
                        )
                        logger.info("Safe mode automatically re-locked.")
                else:
                    _safe_mode_unlocked_at = None

            # Expired session pruning (every 5 minutes = 60 ticks * 5s)
            if maintenance_tick % 60 == 0:
                try:
                    await asyncio.to_thread(auth.prune_expired_sessions)
                except Exception as e:
                    logger.warning(f"Error pruning expired sessions: {e}")

    poller_task = asyncio.create_task(background_poller())
    health_task = asyncio.create_task(background_health_poller())
    maint_task = asyncio.create_task(background_maintenance())
    try:
        yield
    finally:
        poller_task.cancel()
        health_task.cancel()
        maint_task.cancel()


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


# Security Headers & CSRF / Host Validation Middleware
@app.middleware("http")
async def security_and_csrf_middleware(request: Request, call_next):
    # 1. Host Validation
    host_header = request.headers.get("host", "").split(":")[0].strip().lower()
    allowed_hosts = {"127.0.0.1", "localhost", "::1", "testserver", "testclient"}
    
    env_allowed = os.getenv("PORTLY_ALLOWED_HOSTS", "")
    if env_allowed:
        for h in env_allowed.split(","):
            if h.strip():
                allowed_hosts.add(h.strip().lower())
    
    bind_host = os.getenv("PORTLY_HOST", "")
    if bind_host and bind_host not in ("0.0.0.0", "::"):
        allowed_hosts.add(bind_host.lower())

    pub_host = store.get_setting("public_host", "").strip()
    if pub_host:
        pub_parsed = urlparse(f"//{pub_host}").hostname
        if pub_parsed:
            allowed_hosts.add(pub_parsed.lower())

    if host_header and host_header not in allowed_hosts and not any(host_header.endswith(f".{ah}") for ah in allowed_hosts if "." in ah):
        # Allow loopback/local networks if insecure bind allowed or testing
        if os.getenv("PORTLY_ALLOW_INSECURE_BIND", "").lower() not in ("true", "1") and os.getenv("PORTLY_TESTING") != "1":
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_HOST", "message": f"Host '{host_header}' is not in allowed hosts."}
            )

    # 2. CSRF Protection on Mutating Requests
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Explicit Portly client header bypasses browser CSRF
        client_header = request.headers.get("x-portly-client")
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        sec_site = request.headers.get("sec-fetch-site")

        if client_header != "1":
            if sec_site and sec_site.lower() == "cross-site":
                return JSONResponse(
                    status_code=403,
                    content={"code": "CSRF_DETECTED", "message": "Cross-site request blocked."}
                )
            if origin:
                if origin.lower().strip() == "null":
                    return JSONResponse(
                        status_code=403,
                        content={"code": "CSRF_DETECTED", "message": "Origin 'null' is not authorized."}
                    )
                origin_host = urlparse(origin).hostname
                if not origin_host or (origin_host.lower() not in allowed_hosts and not any(origin_host.lower().endswith(f".{ah}") for ah in allowed_hosts if "." in ah)):
                    return JSONResponse(
                        status_code=403,
                        content={"code": "CSRF_DETECTED", "message": f"Origin '{origin}' is not authorized."}
                    )
            elif referer:
                referer_host = urlparse(referer).hostname
                if not referer_host or (referer_host.lower() not in allowed_hosts and not any(referer_host.lower().endswith(f".{ah}") for ah in allowed_hosts if "." in ah)):
                    return JSONResponse(
                        status_code=403,
                        content={"code": "CSRF_DETECTED", "message": f"Referer '{referer}' is not authorized."}
                    )

    response = await call_next(request)

    # 3. Security Headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss:; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "frame-ancestors 'none';"
    )
    return response


def get_client_ip(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


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

        # When binding to 0.0.0.0, in server mode, or accessed remotely, require setup
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
    if current_user.get("role") == "setup":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "SETUP_REQUIRED", "message": "Initial admin setup required before performing mutations.", "hint": "Create an admin account via /api/auth/setup"}
        )
    return current_user


def require_admin(current_user: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin privileges required for this action", "hint": "Viewers cannot mutate apps"}
        )
    return current_user


# Connect docker event listener to refresh discovery
def on_docker_event():
    try:
        global _main_event_loop
        loop = _main_event_loop
        if not loop or not loop.is_running():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = None
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(refresh_discovery(), loop)
    except Exception as e:
        logger.warning(f"Error dispatching docker event to event loop: {e}")

set_on_docker_event(on_docker_event)


# ---------------- API MODELS ----------------

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
    expected_status: Optional[str] = "200,204,301,302"
    custom_headers: Dict[str, str] = Field(default_factory=dict)


class PortChangeModel(BaseModel):
    host_port: int
    bind: str = "0.0.0.0"


class MultiPortItem(BaseModel):
    container_port: str
    host_port: int
    bind: str = "0.0.0.0"


class MultiPortChangeModel(BaseModel):
    mappings: List[MultiPortItem]


class ComposeActionModel(BaseModel):
    action: str = "restart"


class DeployContainerModel(BaseModel):
    image: str
    name: str
    ports: Dict[str, Any] = {}
    env: Dict[str, str] = {}
    volumes: List[str] = []
    restart_policy: str = "unless-stopped"


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
    setup_token: Optional[str] = None


class UserCreateModel(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserRoleModel(BaseModel):
    role: str


class UserPasswordModel(BaseModel):
    new_password: str
    current_password: Optional[str] = None


class PreflightModel(BaseModel):
    compose_content: Optional[str] = None
    command: Optional[str] = None


class ExecModel(BaseModel):
    command: str
    timeout: int = 10


class WebhookTestModel(BaseModel):
    url: Optional[str] = None
    type: Optional[str] = None
    event: Optional[str] = "test"


class PortReservationModel(BaseModel):
    port: int = Field(..., ge=1, le=65535)
    proto: str = Field(default="tcp")
    name: str = Field(..., min_length=1)
    service: Optional[str] = Field(default="")
    description: Optional[str] = Field(default="")


class ComposeStackModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    compose_yaml: str = Field(..., min_length=1)
    force: bool = False


class StackActionModel(BaseModel):
    action: str = Field(..., pattern=r"^(up|down|restart|stop)$")


# ---------------- API ROUTES ----------------

# Minimal Health Endpoint (P0-1 & Docker HEALTHCHECK)
@app.get("/api/health")
async def healthcheck_endpoint():
    return {"status": "ok", "time": time.time()}


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
    sort_dir: str = "asc",
    user: Dict[str, Any] = Depends(require_auth)
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

    # Redact sensitive execution params from list
    safe_apps = [redact_app_for_summary(a) for a in apps]
    docker_avail, docker_err = is_docker_available()

    return {
        "apps": safe_apps,
        "total": len(safe_apps),
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
        lines = await asyncio.to_thread(docker_actions.get_container_logs, c_name, tail=tail, follow=False)
    elif app_id.startswith("custom:"):
        lines = await asyncio.to_thread(process_actions.get_custom_app_logs, app_id, store, tail=tail)
    else:
        lines = [f"Direct log capture is not available for host process '{app_id}'."]

    return {"lines": lines, "count": len(lines)}


@app.get("/api/apps/{app_id:path}/proxy-config")
async def get_proxy_config_endpoint(
    app_id: str,
    format: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_auth)
):
    target_app = None
    for a in _cached_apps:
        if a["id"] == app_id:
            target_app = a
            break
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
            detail={"code": "INVALID_FORMAT", "message": f"Unsupported format '{format}'. Supported formats: caddy, nginx, traefik, traefik_yaml, traefik_labels, cloudflared"}
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
        return Response(
            content=svg_data,
            media_type=mime,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                "X-Content-Type-Options": "nosniff",
            }
        )

    icons_dir = os.path.join(
        os.getenv("PORTLY_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")),
        "icons"
    )
    data, mime = await asyncio.to_thread(favicon_module.fetch_or_generate_app_icon, target_app, icons_dir)
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "X-Content-Type-Options": "nosniff",
        }
    )


@app.get("/api/apps/{app_id:path}/tls")
async def get_app_tls_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_auth)):
    target_app = None
    for a in _cached_apps:
        if a["id"] == app_id:
            target_app = a
            break
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
    exec_timeout = max(1, min(60, int(data.timeout or 10)))
    try:
        res = await asyncio.wait_for(
            asyncio.to_thread(
                docker_actions.exec_in_container,
                container_name,
                data.command,
                store=store,
                timeout=exec_timeout
            ),
            timeout=float(exec_timeout)
        )
        return res
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail={"code": "TIMEOUT", "message": f"Command timed out after {exec_timeout} seconds."}
        )
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
async def get_app_compose_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
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
async def get_app_detail(app_id: str, user: Dict[str, Any] = Depends(require_auth)):
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

        app_copy = dict(target)
        # Redact/mask environment variables
        is_admin = user.get("role") == "admin"
        if "env" in app_copy and isinstance(app_copy["env"], dict):
            app_copy["env"] = mask_sensitive_env(app_copy["env"])

        if docker_inspect and isinstance(docker_inspect.get("env"), dict) and not is_admin:
            docker_inspect["env"] = mask_sensitive_env(docker_inspect["env"])

        return {
            "app": app_copy,
            "health": health,
            "health_history": history,
            "docker_inspect": docker_inspect,
        }

    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"App '{app_id}' not found"})


@app.get("/api/apps/{app_id:path}/inspect/reveal-env")
async def reveal_env_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    """Admin-only audit-logged endpoint to reveal unmasked environment variables."""
    store.log_event("app.reveal_env", f"User '{user['username']}' revealed environment variables for {app_id}", actor=user.get("username", "admin"))
    
    if app_id.startswith("custom:"):
        ca = store.get_custom_app(app_id.replace("custom:", ""))
        if not ca:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Custom app not found"})
        return {"env": ca.get("env", {})}
    elif app_id.startswith("docker:"):
        c_name = app_id.split(":")[1]
        insp = await asyncio.to_thread(docker_actions.inspect_container, c_name)
        return {"env": insp.get("env", {})}
    
    return {"env": {}}


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
    succeeded = []
    failed = []

    if action == "move" and data.category_id:
        for app_id in ids:
            store.upsert_app_override(app_id, category_id=data.category_id)
            succeeded.append(app_id)
    elif action == "tag" and data.tag:
        for app_id in ids:
            app_meta = store.get_app(app_id) or {}
            tags = list(app_meta.get("tags") or [])
            if data.tag not in tags:
                tags.append(data.tag)
                store.upsert_app_override(app_id, tags=tags)
            succeeded.append(app_id)
    elif action == "pin":
        for app_id in ids:
            store.upsert_app_override(app_id, pinned=True)
            succeeded.append(app_id)
    elif action == "hide":
        for app_id in ids:
            store.upsert_app_override(app_id, hidden=True)
            succeeded.append(app_id)
    elif action in ("start", "stop", "restart"):
        if store.get_setting("safe_mode", "true").lower() == "true":
            raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": "Safe mode is active. Mutating actions are locked."})
        for app_id in ids:
            try:
                if app_id.startswith("docker:"):
                    c_name = app_id.split(":")[1]
                    if action == "start":
                        await asyncio.to_thread(docker_actions.start_container, c_name, store)
                    elif action == "stop":
                        await asyncio.to_thread(docker_actions.stop_container, c_name, store)
                    elif action == "restart":
                        await asyncio.to_thread(docker_actions.restart_container, c_name, store)
                elif app_id.startswith("custom:"):
                    if action == "start":
                        await asyncio.to_thread(process_actions.start_custom_app, app_id, store)
                    elif action == "stop":
                        await asyncio.to_thread(process_actions.stop_custom_app, app_id, store)
                    elif action == "restart":
                        await asyncio.to_thread(process_actions.restart_custom_app, app_id, store)
                succeeded.append(app_id)
            except Exception as e:
                logger.warning(f"Error in bulk action for {app_id}: {e}")
                failed.append({"id": app_id, "error": str(e)})

    await refresh_discovery()
    return {"status": "ok", "succeeded": succeeded, "failed": failed, "count": len(succeeded)}


# 3. Actions: Start, Stop, Restart
@app.post("/api/apps/{app_id:path}/start")
async def start_app_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    try:
        if app_id.startswith("docker:"):
            c_name = app_id.split(":")[1]
            res = await asyncio.to_thread(docker_actions.start_container, c_name, store)
        elif app_id.startswith("custom:"):
            res = await asyncio.to_thread(process_actions.start_custom_app, app_id, store)
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
            res = await asyncio.to_thread(docker_actions.stop_container, c_name, store)
        elif app_id.startswith("custom:"):
            res = await asyncio.to_thread(process_actions.stop_custom_app, app_id, store)
        elif app_id.startswith("host:"):
            for a in _cached_apps:
                if a["id"] == app_id and a.get("pid"):
                    res = await asyncio.to_thread(process_actions.kill_host_process, a["pid"], store)
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
            res = await asyncio.to_thread(docker_actions.restart_container, c_name, store)
        elif app_id.startswith("custom:"):
            res = await asyncio.to_thread(process_actions.restart_custom_app, app_id, store)
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
async def check_port_endpoint(port: int = Query(...), bind: str = "0.0.0.0", user: Dict[str, Any] = Depends(require_auth)):
    res = check_port_availability(port, bind, store=store)
    return res


@app.get("/api/ports/suggest")
async def suggest_ports_endpoint(start: int = 3000, count: int = 5, bind: str = "0.0.0.0", user: Dict[str, Any] = Depends(require_auth)):
    ports = suggest_free_ports(start_port=start, count=count, bind_ip=bind)
    return {"suggested": ports}


@app.post("/api/ports/preflight")
async def preflight_port_collisions_endpoint(data: PreflightModel, user: Dict[str, Any] = Depends(require_admin)):
    """Preflight check Docker Compose YAML or docker run commands for port collisions."""
    try:
        res = check_preflight_collisions(compose_content=data.compose_content, command=data.command, store=store)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail={"code": "PREFLIGHT_ERROR", "message": str(e)})


@app.get("/api/ports/reservations")
async def list_port_reservations_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    reservations = store.get_port_reservations()
    # Check for collisions with active listeners
    active_ports = { (a.get("port"), a.get("proto", "tcp").lower()): a for a in _cached_apps if a.get("port", 0) > 0 }
    for r in reservations:
        key = (r["port"], r.get("proto", "tcp").lower())
        if key in active_ports:
            r["is_colliding"] = True
            r["colliding_app"] = active_ports[key].get("name")
        else:
            r["is_colliding"] = False
            r["colliding_app"] = None
    return {"reservations": reservations}


@app.post("/api/ports/reservations")
async def create_port_reservation_endpoint(data: PortReservationModel, user: Dict[str, Any] = Depends(require_admin)):
    res_data = {
        "port": data.port,
        "proto": data.proto.lower(),
        "name": data.name,
        "service": data.service or "",
        "description": data.description or "",
        "created_by": user.get("username", "admin"),
    }
    saved = store.create_port_reservation(res_data)
    store.log_audit_event(user=user.get("username", "admin"), action="create_port_reservation", target=f"Port {data.port}/{data.proto} reserved for '{data.name}'")
    return saved


@app.delete("/api/ports/reservations/{res_id}")
async def delete_port_reservation_endpoint(res_id: str, user: Dict[str, Any] = Depends(require_admin)):
    existing = store.get_port_reservation(res_id)
    if not existing:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Reservation not found"})
    store.delete_port_reservation(res_id)
    store.log_audit_event(user=user.get("username", "admin"), action="delete_port_reservation", target=f"Reservation {res_id} (Port {existing.get('port')}) deleted")
    return {"status": "success", "message": f"Reservation '{existing.get('name')}' deleted"}


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
                res = await asyncio.to_thread(docker_actions.rollback_port_change_docker, app_id, store)
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
            res = await asyncio.to_thread(
                docker_actions.apply_port_change_docker,
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
        await asyncio.to_thread(process_actions.restart_custom_app, app_id, store)
        await refresh_discovery()
        return {"status": "updated", "new_port": data.host_port}
    else:
        raise HTTPException(status_code=400, detail={"code": "NOT_SUPPORTED", "message": "Unsupported app type for port change"})


@app.post("/api/apps/{app_id:path}/ports-multi")
async def change_multi_ports_endpoint(
    app_id: str,
    data: MultiPortChangeModel,
    user: Dict[str, Any] = Depends(require_admin)
):
    if not app_id.startswith("docker:"):
        raise HTTPException(status_code=400, detail={"code": "NOT_SUPPORTED", "message": "Multi-port remapping is only supported for Docker containers"})

    parts = app_id.split(":")
    container_name = parts[1] if len(parts) > 1 else ""
    if not container_name:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ID", "message": "Invalid container app id"})

    mappings_dicts = [m.model_dump() for m in data.mappings]
    try:
        res = await asyncio.to_thread(docker_actions.apply_multi_port_change_docker, container_name, mappings_dicts, store)
        await refresh_discovery()
        return res
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "PORT_CONFLICT", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "RECREATION_FAILED", "message": str(e)})


# 5. Image updates
@app.post("/api/apps/{app_id:path}/update/check")
async def check_update_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_auth)):
    image_tag = ""
    for a in _cached_apps:
        if a["id"] == app_id:
            image_tag = a.get("image", "")
            break
    if not image_tag:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Container image not found"})
    return await asyncio.to_thread(docker_actions.check_image_update, image_tag)


@app.post("/api/apps/{app_id:path}/update/apply")
async def apply_update_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    if store.get_setting("safe_mode", "true").lower() == "true":
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": "Safe mode is active. Mutating actions are locked."})
    if not app_id.startswith("docker:"):
        raise HTTPException(status_code=400, detail={"code": "NOT_DOCKER", "message": "Image updates are only supported for Docker containers."})
    c_name = app_id.split(":")[1]
    client = get_docker_client()
    if not client:
        return {"status": "ok", "message": "Docker is not available on this host. Image update skipped."}
    try:
        res = await asyncio.to_thread(docker_actions.apply_image_update, c_name, store)
        await refresh_discovery()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "UPDATE_FAILED", "message": str(e)})


# 5b. Docker System Hygiene & Storage endpoints
@app.get("/api/docker/system")
async def get_docker_system_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    return await asyncio.to_thread(docker_actions.get_docker_system_df, store)


@app.get("/api/docker/images")
async def get_docker_images_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    return await asyncio.to_thread(docker_actions.list_docker_images, store)


@app.get("/api/docker/volumes")
async def get_docker_volumes_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    return await asyncio.to_thread(docker_actions.list_docker_volumes, store)


@app.post("/api/docker/prune")
async def prune_docker_endpoint(user: Dict[str, Any] = Depends(require_admin)):
    try:
        return await asyncio.to_thread(docker_actions.prune_docker_system, store)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "PRUNE_FAILED", "message": str(e)})


@app.post("/api/docker/compose/{project:path}/action")
async def execute_compose_action_endpoint(
    project: str,
    data: ComposeActionModel,
    user: Dict[str, Any] = Depends(require_admin)
):
    try:
        return await asyncio.to_thread(docker_actions.manage_compose_stack, project, data.action, store)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ACTION", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "STACK_ACTION_FAILED", "message": str(e)})


# Compose Stacks Management
@app.get("/api/stacks")
async def list_compose_stacks_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    stacks = store.get_compose_stacks()
    client = get_docker_client()
    for s in stacks:
        running_count = 0
        ports_list = []
        if client:
            try:
                conts = await asyncio.to_thread(
                    client.containers.list,
                    all=True,
                    filters={"label": f"com.docker.compose.project={s['name']}"}
                )
                for c in conts:
                    if c.status == "running":
                        running_count += 1
                    for port_spec, maps in (c.attrs.get("NetworkSettings", {}).get("Ports") or {}).items():
                        if maps:
                            for m in maps:
                                hp = m.get("HostPort")
                                if hp and int(hp) not in ports_list:
                                    ports_list.append(int(hp))
            except Exception:
                pass
        s["containers_running"] = running_count
        s["ports"] = sorted(ports_list)
        s["status"] = "running" if running_count > 0 else "stopped"
    return {"stacks": stacks}


@app.get("/api/stacks/{name}")
async def get_compose_stack_endpoint(name: str, user: Dict[str, Any] = Depends(require_auth)):
    stack = store.get_compose_stack(name)
    if not stack:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Stack '{name}' not found"})
    return stack


@app.post("/api/stacks")
async def save_compose_stack_endpoint(data: ComposeStackModel, user: Dict[str, Any] = Depends(require_admin)):
    preflight = check_preflight_collisions(compose_content=data.compose_yaml, store=store)
    if preflight.get("has_conflicts") and not data.force:
        return JSONResponse(
            status_code=409,
            content={
                "code": "PORT_COLLISION",
                "message": f"Stack has {len(preflight.get('collisions', []))} port collision(s)",
                "preflight": preflight,
            }
        )
    saved = store.save_compose_stack(data.name, data.compose_yaml)
    store.log_audit_event(user=user.get("username", "admin"), action="save_compose_stack", target=f"Stack '{data.name}' saved")
    return {"status": "saved", "stack": saved, "preflight": preflight}


@app.delete("/api/stacks/{name}")
async def delete_compose_stack_endpoint(name: str, user: Dict[str, Any] = Depends(require_admin)):
    stack = store.get_compose_stack(name)
    if not stack:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Stack '{name}' not found"})
    client = get_docker_client()
    if client:
        try:
            conts = await asyncio.to_thread(
                client.containers.list,
                filters={"label": f"com.docker.compose.project={name}"}
            )
            if conts:
                raise HTTPException(status_code=400, detail={"code": "STACK_RUNNING", "message": f"Stack '{name}' is running. Stop it before deleting."})
        except HTTPException:
            raise
        except Exception:
            pass
    store.delete_compose_stack(name)
    store.log_audit_event(user=user.get("username", "admin"), action="delete_compose_stack", target=f"Stack '{name}' deleted")
    return {"status": "deleted", "message": f"Stack '{name}' removed"}


@app.post("/api/stacks/{name}/action")
async def execute_stack_action_endpoint(name: str, data: StackActionModel, user: Dict[str, Any] = Depends(require_admin)):
    action = data.action.lower().strip()
    stack = store.get_compose_stack(name)
    if not stack:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Stack '{name}' not found"})
    
    if store.get_setting("safe_mode", "true").lower() == "true":
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": "Safe mode is ON. Unlock safe mode to execute stack actions."})

    res = await asyncio.to_thread(docker_actions.execute_stack_file_action, name, stack["compose_yaml"], action)
    await refresh_discovery()
    store.log_audit_event(user=user.get("username", "admin"), action="stack_action", target=f"Stack '{name}' action '{action}': {res.get('status')}")
    return res


@app.post("/api/docker/containers/deploy")
async def deploy_container_endpoint(
    data: DeployContainerModel,
    user: Dict[str, Any] = Depends(require_admin)
):
    try:
        res = await asyncio.to_thread(
            docker_actions.deploy_container,
            image=data.image,
            name=data.name,
            ports=data.ports,
            env=data.env,
            volumes=data.volumes,
            restart_policy=data.restart_policy,
            store=store
        )
        await refresh_discovery()
        return res
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={"code": "SAFE_MODE", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "DEPLOY_ERROR", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "DEPLOY_FAILED", "message": str(e)})


# 6. Custom apps CRUD
@app.get("/api/custom-apps")
async def list_custom_apps(user: Dict[str, Any] = Depends(require_auth)):
    apps = store.get_custom_apps()
    # Mask env variables
    safe_apps = []
    for ca in apps:
        ca_copy = dict(ca)
        if "env" in ca_copy and isinstance(ca_copy["env"], dict):
            ca_copy["env"] = mask_sensitive_env(ca_copy["env"])
        safe_apps.append(ca_copy)
    return safe_apps


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
        update_cmd=data.update_cmd,
        expected_status=data.expected_status,
        custom_headers=data.custom_headers,
    )
    if data.start_on_boot and data.start_cmd:
        try:
            await asyncio.to_thread(process_actions.start_custom_app, f"custom:{app_id}", store)
        except Exception:
            pass
    await refresh_discovery()
    return res


@app.delete("/api/custom-apps/{app_id:path}")
async def delete_custom_app_endpoint(app_id: str, user: Dict[str, Any] = Depends(require_admin)):
    clean_id = app_id.replace("custom:", "")
    try:
        await asyncio.to_thread(process_actions.stop_custom_app, f"custom:{clean_id}", store)
    except Exception:
        pass
    store.delete_custom_app(clean_id)
    await refresh_discovery()
    return {"status": "deleted", "id": clean_id}


# 7. Stats, System & Events
@app.get("/api/stats")
async def get_stats_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    docker_running = sum(1 for a in _cached_apps if a.get("source") == "docker" and a.get("status") == "up")
    return get_current_stats(containers_running=docker_running, listening_count=len(_cached_apps), conflict_count=len(_cached_conflicts))


@app.get("/api/metrics")
async def prometheus_metrics_endpoint(
    request: Request,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    """
    Prometheus exposition metrics endpoint:
    Accepts:
    1. Logged in user session cookie or standard Bearer token
    2. Explicit query param ?token=<metrics_token> or Bearer <metrics_token> matching settings or env
    3. Loopback convenience in desktop mode with no users
    """
    authenticated = False
    
    # Check metrics scrape token
    configured_token = os.getenv("PORTLY_METRICS_TOKEN") or store.get_setting("metrics_token", "")
    if configured_token:
        if token and hmac.compare_digest(token, configured_token):
            authenticated = True
        elif authorization and authorization.startswith("Bearer "):
            bearer = authorization.split(" ", 1)[1]
            if hmac.compare_digest(bearer, configured_token):
                authenticated = True

    if not authenticated and current_user and current_user.get("role") != "setup":
        authenticated = True

    if not authenticated:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Valid metrics token or session required"})

    docker_running = sum(1 for a in _cached_apps if a.get("source") == "docker" and a.get("status") == "up")
    docker_stopped = sum(1 for a in _cached_apps if a.get("source") == "docker" and a.get("status") == "down")
    tcp_listeners = sum(1 for a in _cached_apps if a.get("proto", "tcp").lower() == "tcp")
    udp_listeners = sum(1 for a in _cached_apps if a.get("proto", "tcp").lower() == "udp")
    conflicts_count = len(_cached_conflicts)
    reservations_count = len(store.get_port_reservations())

    stats = get_current_stats(containers_running=docker_running, listening_count=len(_cached_apps), conflict_count=conflicts_count)
    cpu_percent = stats.get("cpu", {}).get("percent", 0.0)
    ram_mb = stats.get("memory", {}).get("used_mb", 0.0)
    ram_total_mb = stats.get("memory", {}).get("total_mb", 0.0)
    disk_percent = stats.get("disk", {}).get("percent", 0.0)
    net_rx_rate = stats.get("network", {}).get("rx_rate", 0.0)
    net_tx_rate = stats.get("network", {}).get("tx_rate", 0.0)

    lines = [
        "# HELP portly_active_listeners_total Number of listening ports detected by protocol",
        "# TYPE portly_active_listeners_total gauge",
        f'portly_active_listeners_total{{proto="tcp"}} {tcp_listeners}',
        f'portly_active_listeners_total{{proto="udp"}} {udp_listeners}',
        "",
        "# HELP portly_containers_total Total Docker containers discovered by status",
        "# TYPE portly_containers_total gauge",
        f'portly_containers_total{{status="up"}} {docker_running}',
        f'portly_containers_total{{status="down"}} {docker_stopped}',
        "",
        "# HELP portly_port_conflicts_total Total number of detected port collisions",
        "# TYPE portly_port_conflicts_total gauge",
        f'portly_port_conflicts_total {conflicts_count}',
        "",
        "# HELP portly_port_reservations_total Total number of active port reservations",
        "# TYPE portly_port_reservations_total gauge",
        f'portly_port_reservations_total {reservations_count}',
        "",
        "# HELP portly_host_cpu_percent Host CPU utilization percent",
        "# TYPE portly_host_cpu_percent gauge",
        f'portly_host_cpu_percent {cpu_percent}',
        "",
        "# HELP portly_host_memory_bytes Host memory utilization in bytes",
        "# TYPE portly_host_memory_bytes gauge",
        f'portly_host_memory_bytes{{type="used"}} {int(ram_mb * 1024 * 1024)}',
        f'portly_host_memory_bytes{{type="total"}} {int(ram_total_mb * 1024 * 1024)}',
        "",
        "# HELP portly_host_disk_percent Host primary disk utilization percent",
        "# TYPE portly_host_disk_percent gauge",
        f'portly_host_disk_percent {disk_percent}',
        "",
        "# HELP portly_host_network_bytes_per_sec Host network rate in bytes per second",
        "# TYPE portly_host_network_bytes_per_sec gauge",
        f'portly_host_network_bytes_per_sec{{direction="rx"}} {net_rx_rate}',
        f'portly_host_network_bytes_per_sec{{direction="tx"}} {net_tx_rate}',
        "",
        "# HELP portly_up Process uptime status",
        "# TYPE portly_up gauge",
        "portly_up 1",
    ]
    content = "\n".join(lines) + "\n"
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/system")
async def get_system_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    return await asyncio.to_thread(get_detailed_system_stats)


@app.get("/api/events")
async def get_events_endpoint(limit: int = 100, user: Dict[str, Any] = Depends(require_auth)):
    return store.get_events(limit=limit)


# 8. Categories & Rules & Views
@app.get("/api/categories")
async def get_categories_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    cats = store.get_categories()
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
    try:
        store.delete_category(cat_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CATEGORY", "message": str(e)})
    await refresh_discovery()
    return {"status": "deleted", "id": cat_id}


@app.get("/api/rules")
async def get_rules_endpoint(user: Dict[str, Any] = Depends(require_auth)):
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
async def get_views_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    return store.get_views()


@app.post("/api/views")
async def save_view_endpoint(data: ViewModel, user: Dict[str, Any] = Depends(require_admin)):
    return store.save_view(data.id, data.name, data.filters, data.sort, data.group_by, data.view_type, data.columns)


@app.delete("/api/views/{view_id}")
async def delete_view_endpoint(view_id: str, user: Dict[str, Any] = Depends(require_admin)):
    store.delete_view(view_id)
    return {"status": "deleted", "id": view_id}


# 9. Settings
ALLOWED_SETTINGS_KEYS = {
    "refresh_interval", "auto_refresh", "safe_mode", "auto_relock_seconds",
    "public_host", "webhook_url", "webhook_type", "webhook_events",
    "theme", "default_view"
}

@app.get("/api/settings")
async def get_settings_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    settings = store.get_settings()
    if user.get("role") != "admin" and settings.get("webhook_url"):
        url = settings["webhook_url"]
        if len(url) > 10:
            settings["webhook_url"] = url[:8] + "..." + url[-4:]
    return settings


@app.patch("/api/settings")
async def update_settings_endpoint(settings_dict: Dict[str, Any], user: Dict[str, Any] = Depends(require_admin)):
    # Validate keys and types
    for k, v in settings_dict.items():
        if k not in ALLOWED_SETTINGS_KEYS:
            raise HTTPException(status_code=400, detail={"code": "INVALID_SETTING_KEY", "message": f"Setting '{k}' is not recognized."})
        
        # Specific validations
        if k == "refresh_interval":
            try:
                val = float(v)
                if not (1.0 <= val <= 300.0):
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail={"code": "INVALID_VALUE", "message": "refresh_interval must be a number between 1 and 300."})
        elif k in ("auto_refresh", "safe_mode"):
            if str(v).lower() not in ("true", "false", "1", "0"):
                raise HTTPException(status_code=400, detail={"code": "INVALID_VALUE", "message": f"{k} must be 'true' or 'false'."})
        elif k == "auto_relock_seconds":
            try:
                val = int(v)
                if not (0 <= val <= 86400):
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail={"code": "INVALID_VALUE", "message": "auto_relock_seconds must be between 0 and 86400."})
        elif k == "webhook_type":
            if str(v).lower() not in ("generic", "slack", "discord"):
                raise HTTPException(status_code=400, detail={"code": "INVALID_VALUE", "message": "webhook_type must be generic, slack, or discord."})
        elif k == "theme":
            if str(v).lower() not in ("dark", "light", "system"):
                raise HTTPException(status_code=400, detail={"code": "INVALID_VALUE", "message": "theme must be dark, light, or system."})

    global _safe_mode_unlocked_at
    for k, v in settings_dict.items():
        val_str = str(v).lower() if k in ("auto_refresh", "safe_mode") else str(v)
        store.set_setting(k, val_str)
        if k == "safe_mode":
            if val_str in ("false", "0"):
                _safe_mode_unlocked_at = time.time()
            else:
                _safe_mode_unlocked_at = None
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
async def trigger_scan_endpoint(user: Dict[str, Any] = Depends(require_auth)):
    get_docker_client(force_retry=True)
    await refresh_discovery()
    return {"status": "ok", "apps_count": len(_cached_apps), "conflicts": len(_cached_conflicts)}


# 11. Export & Import
@app.get("/api/export")
async def export_data(
    format: str = "json",
    reveal_secrets: bool = False,
    user: Dict[str, Any] = Depends(require_admin)
):
    actor = user.get("username", "admin")
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
        store.log_event("export_data", f"Exported ports configuration in CSV format", actor=actor)
        return Response(content=out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=portly-ports.csv"})
    elif format == "markdown":
        lines = ["# Portly - Ports Cheat Sheet\n", "| Port | Name | Source | Bind | Status |", "|---|---|---|---|---|"]
        for a in _cached_apps:
            lines.append(f"| `{a.get('port')}` | **{a.get('name')}** | {a.get('source')} | `{a.get('bind')}` | {a.get('status')} |")
        store.log_event("export_data", f"Exported ports configuration in Markdown format", actor=actor)
        return Response(content="\n".join(lines), media_type="text/markdown", headers={"Content-Disposition": "attachment; filename=portly-ports.md"})
    else:
        custom_apps = store.get_custom_apps()
        settings = store.get_settings()

        if not reveal_secrets:
            sanitized_apps = []
            for ca in custom_apps:
                item = dict(ca)
                if "env" in item and isinstance(item["env"], dict):
                    item["env"] = {k: "********" for k in item["env"]}
                sanitized_apps.append(item)
            custom_apps = sanitized_apps
            if "webhook_url" in settings and settings["webhook_url"]:
                settings["webhook_url"] = "https://********"

        store.log_event("export_data", f"Exported full system backup (reveal_secrets={reveal_secrets})", actor=actor)

        backup = {
            "categories": store.get_categories(),
            "rules": store.get_rules(),
            "custom_apps": custom_apps,
            "views": store.get_views(),
            "app_overrides": store.get_all_app_overrides(),
            "settings": settings,
        }
        return JSONResponse(content=backup)


@app.post("/api/import")
async def import_data(backup: Dict[str, Any], user: Dict[str, Any] = Depends(require_admin)):
    # Validate every section before writing so a malformed backup cannot leave
    # a half-imported database.
    required = {
        "categories": ("id", "name", "color"),
        "rules": ("id", "category_id", "field", "operator", "value"),
        "custom_apps": ("id", "name", "port"),
        "views": ("id", "name"),
    }
    for section, keys in required.items():
        entries = backup.get(section, [])
        if not isinstance(entries, list) or any(
            not isinstance(e, dict) or any(k not in e for k in keys) for e in entries
        ):
            raise HTTPException(status_code=400, detail={"code": "INVALID_BACKUP", "message": f"Invalid {section} section in backup."})
    for section in ("app_overrides", "settings"):
        if not isinstance(backup.get(section, {}), dict):
            raise HTTPException(status_code=400, detail={"code": "INVALID_BACKUP", "message": f"Invalid {section} section in backup."})

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
        if k in ALLOWED_SETTINGS_KEYS:
            store.set_setting(k, str(v))
    await refresh_discovery()
    return {"status": "imported"}


# 12. Authentication & User Management Endpoints
@app.get("/api/auth/me")
async def auth_me(user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    user_count = store.get_user_count()
    return {
        "authenticated": user is not None and user.get("role") != "setup",
        "user": user if (user and user.get("role") != "setup") else None,
        "needs_setup": user_count == 0,
    }


@app.post("/api/auth/setup")
async def auth_setup(data: SetupModel, request: Request, response: Response):
    if store.get_user_count() > 0:
        raise HTTPException(status_code=400, detail={"code": "SETUP_DONE", "message": "Admin account is already configured"})

    # Setup token verification if in server mode or remote access
    mode = os.getenv("PORTLY_MODE", "desktop").lower()
    host = os.getenv("PORTLY_HOST", "127.0.0.1")
    allow_insecure = os.getenv("PORTLY_ALLOW_INSECURE_BIND", "false").lower() in ("true", "1")
    client_host = request.client.host if request.client else "127.0.0.1"
    is_remote = client_host not in ("127.0.0.1", "::1", "localhost", "testclient")

    if (mode == "server" or host in ("0.0.0.0", "::") or is_remote) and not allow_insecure:
        if not data.setup_token or not auth.verify_setup_token(data.setup_token):
            raise HTTPException(
                status_code=403,
                detail={"code": "INVALID_SETUP_TOKEN", "message": "Valid setup token is required to initialize server mode."}
            )

    # Password validation (min 10 chars)
    pw_ok, pw_err = auth.validate_password(data.password)
    if not pw_ok:
        raise HTTPException(status_code=400, detail={"code": "WEAK_PASSWORD", "message": pw_err})

    pw_hash = auth.hash_password(data.password)
    user_id = f"u_{uuid.uuid4().hex[:12]}"
    user = store.create_user(user_id, data.username, pw_hash, role="admin")
    token = auth.create_session(user["id"], user["username"], role="admin")
    
    is_secure = request.url.scheme == "https" or os.getenv("PORTLY_COOKIE_SECURE", "").lower() in ("true", "1")
    response.set_cookie(key="portly_session", value=token, httponly=True, samesite="lax", secure=is_secure, max_age=86400 * 7, path="/")
    return {"status": "ok", "token": token, "username": user["username"], "role": "admin"}


@app.post("/api/auth/login")
async def auth_login(data: LoginModel, request: Request, response: Response):
    ip = get_client_ip(request)
    
    # Rate limit check (S-1)
    if not auth.check_rate_limit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Too many failed login attempts. Please wait 15 minutes."}
        )

    user = store.get_user(data.username)
    if not user:
        # Constant-time dummy verify to prevent user enumeration
        auth.verify_dummy_password(data.password)
        auth.record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"})

    if not auth.verify_password(data.password, user["password_hash"]):
        auth.record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"})

    auth.clear_failed_attempts(ip)
    token = auth.create_session(user["id"], user["username"], role=user.get("role", "admin"))
    is_secure = request.url.scheme == "https" or os.getenv("PORTLY_COOKIE_SECURE", "").lower() in ("true", "1")
    response.set_cookie(key="portly_session", value=token, httponly=True, samesite="lax", secure=is_secure, max_age=86400 * 7, path="/")
    return {"status": "ok", "token": token, "username": user["username"], "role": user.get("role", "admin")}


@app.post("/api/auth/logout")
async def auth_logout(response: Response, session_token: Optional[str] = Cookie(None, alias="portly_session")):
    if session_token:
        auth.revoke_session(session_token)
    response.delete_cookie(key="portly_session", path="/")
    return {"status": "logged_out"}


# User Management Endpoints (S-5)
@app.get("/api/users")
async def list_users_endpoint(user: Dict[str, Any] = Depends(require_admin)):
    return store.list_users()


@app.post("/api/users")
async def create_user_endpoint(data: UserCreateModel, user: Dict[str, Any] = Depends(require_admin)):
    pw_ok, pw_err = auth.validate_password(data.password)
    if not pw_ok:
        raise HTTPException(status_code=400, detail={"code": "WEAK_PASSWORD", "message": pw_err})

    role = data.role.lower()
    if role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail={"code": "INVALID_ROLE", "message": "Role must be 'admin' or 'viewer'"})

    existing = store.get_user(data.username)
    if existing:
        raise HTTPException(status_code=400, detail={"code": "USER_EXISTS", "message": f"User '{data.username}' already exists."})

    user_id = f"u_{uuid.uuid4().hex[:12]}"
    pw_hash = auth.hash_password(data.password)
    created = store.create_user(user_id, data.username, pw_hash, role=role)
    store.log_event("user.create", f"Created user {data.username} with role {role}", actor=user["username"])
    return {"status": "ok", "user": created}


@app.delete("/api/users/{user_id}")
async def delete_user_endpoint(user_id: str, user: Dict[str, Any] = Depends(require_admin)):
    if user_id == user.get("user_id"):
        raise HTTPException(status_code=400, detail={"code": "CANNOT_DELETE_SELF", "message": "You cannot delete your own account."})

    target_user = store.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found."})

    store.delete_user(user_id)
    auth.revoke_all_sessions(user_id)
    store.log_event("user.delete", f"Deleted user {target_user['username']} ({user_id})", actor=user["username"])
    return {"status": "deleted", "id": user_id}


@app.patch("/api/users/{user_id}/role")
async def update_user_role_endpoint(user_id: str, data: UserRoleModel, user: Dict[str, Any] = Depends(require_admin)):
    role = data.role.lower()
    if role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail={"code": "INVALID_ROLE", "message": "Role must be 'admin' or 'viewer'"})

    target_user = store.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found."})

    store.update_user_role(user_id, role)
    store.log_event("user.role_change", f"Changed role of user {target_user['username']} to {role}", actor=user["username"])
    return {"status": "updated", "id": user_id, "role": role}


@app.post("/api/users/{user_id}/password")
async def update_user_password_endpoint(
    user_id: str,
    data: UserPasswordModel,
    user: Dict[str, Any] = Depends(require_auth)
):
    is_admin = user.get("role") == "admin"
    if not is_admin and user.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "You can only update your own password."})

    target_user = store.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found."})

    # If updating self, verify current password
    if not is_admin:
        if not data.current_password or not auth.verify_password(data.current_password, target_user["password_hash"]):
            raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD", "message": "Current password is incorrect."})

    pw_ok, pw_err = auth.validate_password(data.new_password)
    if not pw_ok:
        raise HTTPException(status_code=400, detail={"code": "WEAK_PASSWORD", "message": pw_err})

    pw_hash = auth.hash_password(data.new_password)
    store.update_user_password(user_id, pw_hash)
    auth.revoke_all_sessions(user_id)
    store.log_event("user.password_change", f"Password changed for user {target_user['username']}", actor=user["username"])
    return {"status": "updated"}


# Audit Logs Endpoint (S-6)
@app.get("/api/audit-logs")
async def get_audit_logs_endpoint(
    limit: int = 100,
    event_type: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_admin)
):
    return store.get_events(limit=limit, event_type=event_type)


# 13. Real-time SSE Stream
@app.get("/api/stream")
async def sse_stream(request: Request, user: Dict[str, Any] = Depends(require_auth)):
    q = asyncio.Queue(maxsize=32)
    _sse_subscribers.append(q)

    # Initial snapshot
    docker_running = sum(1 for a in _cached_apps if a.get("source") == "docker" and a.get("status") == "up")
    initial_stats = get_current_stats(containers_running=docker_running, listening_count=len(_cached_apps), conflict_count=len(_cached_conflicts))
    docker_avail, docker_err = is_docker_available()

    initial_payload = {
        "type": "snapshot",
        "apps": [redact_app_for_summary(a) for a in _cached_apps],
        "conflicts": _cached_conflicts,
        "stats": initial_stats,
        "docker_status": {
            "available": docker_avail,
            "message": docker_err,
        },
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

        clean_parts = [p for p in full_path.replace("\\", "/").split("/") if p]
        if ".." in clean_parts or "\0" in full_path:
            raise HTTPException(status_code=404, detail="Not Found")

        real_frontend = os.path.abspath(FRONTEND_DIST)
        try:
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
