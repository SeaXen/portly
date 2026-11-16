# Portly REST & SSE API Reference ⚓

Portly exposes a RESTful API and a Server-Sent Events (SSE) stream for real-time telemetry and management.

---

## Authentication & Authorization

Portly supports two execution modes:
- **Desktop Mode (`PORTLY_MODE=desktop`)**: Default mode. Binds to `127.0.0.1`. Automatically grants administrative privileges to local callers without requiring login credentials.
- **Server Mode (`PORTLY_MODE=server`)**: Recommended for LAN/WAN deployments. Requires administrative account creation and session authentication via Bearer token header or `portly_session` cookie.

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/auth/setup` | Create initial admin account | Only when user count == 0 |
| `POST` | `/api/auth/login` | Authenticate and obtain session token | None |
| `POST` | `/api/auth/logout` | Revoke active session | Yes |
| `GET` | `/api/auth/me` | Fetch active user identity and role | Optional |

---

## Apps & Discovery

### `GET /api/apps`
Returns all discovered host listening sockets, Docker containers, and custom apps.

**Query Parameters:**
- `source`: Filter by source (`host`, `docker`, `custom`).
- `status`: Filter by status (`up`, `down`, `conflict`).
- `category_id`: Filter by category.
- `bind`: Filter by bind address (`0.0.0.0`, `127.0.0.1`).
- `search`: Search query string matching name, port, or process.
- `include_hidden`: Boolean flag (`true`/`false`) to include hidden apps.
- `sort_by`: Sort column (`port`, `name`, `source`, `cpu_percent`, `ram_mb`).
- `sort_dir`: Sort order (`asc` or `desc`).

### `GET /api/apps/{app_id}`
Returns deep details for a single application including live HTTP/TCP health check, health history latency points, and Docker container inspection metadata.

### `PATCH /api/apps/{app_id}`
Updates custom metadata overrides for an app:
```json
{
  "name": "Custom Service Name",
  "icon": "globe",
  "category_id": "development",
  "tags": ["frontend", "internal"],
  "notes": "Primary development frontend",
  "pinned": true,
  "hidden": false,
  "url_override": "https://service.local"
}
```

### `POST /api/apps/bulk`
Executes batch operations on multiple applications:
```json
{
  "ids": ["host:node.exe:3000", "docker:redis:6379/tcp"],
  "action": "pin",
  "category_id": "databases"
}
```

---

## App Actions & Lifecycle

All mutating actions require **Admin** privileges and require **Safe Mode** to be unlocked in settings.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/apps/{app_id}/start` | Starts a stopped custom app or Docker container |
| `POST` | `/api/apps/{app_id}/stop` | Stops an active custom app or Docker container |
| `POST` | `/api/apps/{app_id}/restart` | Restarts an application |
| `GET` | `/api/apps/{app_id}/logs` | Tails live output logs (supports `tail=500`) |
| `POST` | `/api/apps/{app_id}/exec` | Executes a diagnostic command inside a Docker container |

---

## Port Management & Remapping

### `GET /api/ports/check`
Validates port availability via socket bind test, socket table lookup, and Docker mapping checks.
- **Parameters:** `port` (int), `bind` (optional string, defaults to `0.0.0.0`).

### `GET /api/ports/suggest`
Finds the next N free available ports starting from a base port.
- **Parameters:** `start` (int, defaults to 3000), `count` (int, defaults to 5), `bind` (string).

### `POST /api/apps/{app_id}/port`
Plans (dry-run) or executes a single port change for a Docker container or custom app.
```json
{
  "new_port": 8081,
  "bind": "0.0.0.0",
  "dry_run": false
}
```

### `POST /api/apps/{app_id}/ports-multi`
Remaps multiple port bindings simultaneously for a Docker container.
```json
{
  "mappings": [
    {"target_c_port": "80/tcp", "new_host_port": 8080, "bind": "0.0.0.0"},
    {"target_c_port": "443/tcp", "new_host_port": 8443, "bind": "0.0.0.0"}
  ]
}
```

---

## Reverse Proxy & TLS Inspection

### `GET /api/apps/{app_id}/proxy-config`
Generates reverse proxy configuration snippets.
- **Parameters:** `format` (`caddy`, `nginx`, `traefik_yaml`, `traefik_labels`, `cloudflared`), `domain` (optional hostname).

### `GET /api/apps/{app_id}/tls`
Inspects TLS/SSL certificate on the app's target port. Returns subject CN, issuer, validity window, days remaining, SAN list, and expiration warnings.

---

## Docker System Management

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/docker/system` | Returns Docker system disk usage (`df`) |
| `GET` | `/api/docker/images` | Lists local Docker images and reclaimable sizes |
| `GET` | `/api/docker/volumes` | Lists Docker volumes and usage metadata |
| `POST` | `/api/docker/prune` | Executes `docker system prune` to reclaim disk space |
| `POST` | `/api/docker/compose/{project}/action` | Executes Compose stack action (`restart`, `stop`, `start`, `down`) |
| `POST` | `/api/docker/containers/deploy` | Deploys a new Docker container with port availability verification |

---

## Real-Time SSE Stream

### `GET /api/stream`
Server-Sent Events (SSE) stream broadcasting real-time updates.

**Event Payloads:**
- `type: "snapshot"`: Emitted immediately on connection with current apps, conflicts, and system metrics.
- `type: "update"`: Emitted on state changes with updated apps, conflict lists, and system telemetry.
- `event: "ping"`: Keep-alive heartbeat every 15 seconds.
