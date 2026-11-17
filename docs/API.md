# Portly REST & SSE API Reference ⚓

Portly exposes a RESTful API and a Server-Sent Events (SSE) stream for real-time telemetry, discovery, and systems management.

---

## 🔒 Security & Client Headers

All state-changing requests (`POST`, `PATCH`, `DELETE`, `PUT`) from web clients must supply the custom client header:
```http
X-Portly-Client: 1
```
This requirement prevents Cross-Site Request Forgery (CSRF).

### Security Response Headers
Portly automatically injects strict HTTP response headers on every response:
- `Content-Security-Policy`: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';`
- `X-Frame-Options`: `DENY`
- `X-Content-Type-Options`: `nosniff`
- `Referrer-Policy`: `no-referrer`

---

## 🔑 Authentication & RBAC

Portly operates under two modes:
- **Desktop Mode (`PORTLY_MODE=desktop`)**: Default mode. Binds to `127.0.0.1`. Automatically grants administrative privileges to local callers without requiring login credentials.
- **Server Mode (`PORTLY_MODE=server`)**: Recommended for LAN/WAN/Docker deployments. Enforces setup token bootstrap and session authentication.

### Roles
- `admin`: Complete permissions, including starting/stopping services, remapping ports, executing diagnostic commands, revealing secrets, pruning Docker, managing users, and reading audit logs.
- `viewer`: Read-only permissions to view ports, telemetry, and service statuses. Mutating actions return `403 Forbidden`.

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/health` | Minimal public liveness/health check | None |
| `POST` | `/api/auth/setup` | Create initial admin account via setup token | Only when user count == 0 |
| `POST` | `/api/auth/login` | Authenticate and obtain session token (Rate limited to 5 attempts/15min) | None |
| `POST` | `/api/auth/logout` | Revoke active session | Yes |
| `GET` | `/api/auth/me` | Fetch active user identity, role, and setup status | Optional |

---

## 👥 User Management & Audit Logs (Admin Only)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/users` | Lists all users (`id`, `username`, `role`, `created_at`) |
| `POST` | `/api/users` | Creates a new user (`username`, `password`, `role`). Password min 10 chars |
| `DELETE` | `/api/users/{user_id}` | Deletes a user (cannot delete self) |
| `PATCH` | `/api/users/{user_id}/role` | Updates a user's role (`admin` or `viewer`) |
| `POST` | `/api/users/{user_id}/password` | Resets a user's password |
| `GET` | `/api/audit-logs` | Retrieves audit log entries (supports `limit=100` and `event_type`) |

---

## ⚡ Preflight Port Collision Engine

### `POST /api/ports/preflight`
Analyzes proposed `docker run` commands, `docker-compose.yml` declarations, or raw port lists for socket collisions before deployment.

**Request Body:**
```json
{
  "command": "docker run -d -p 8080:80 -p 5432:5432 postgres",
  "compose_content": "services:\n  web:\n    ports:\n      - '8080:80'",
  "ports": [8080, 5432]
}
```

**Response Body:**
```json
{
  "valid": false,
  "has_collision": true,
  "collisions": [
    {
      "port": 8080,
      "proto": "tcp",
      "bind": "0.0.0.0",
      "conflict_with": "host:nginx.exe:8080",
      "conflict_type": "port_in_use"
    }
  ],
  "checked_ports": [8080, 5432],
  "summary": "2 ports checked, 1 collision(s)"
}
```

---

## 📦 Apps & Discovery

### `GET /api/apps`
Returns all discovered host listening sockets, Docker containers, and custom apps. Sensitive environment variables are masked with `***REDACTED***` for non-admin viewers.

### `GET /api/apps/{app_id}`
Returns deep details for a single application including live HTTP/TCP health check, health history latency points, and Docker container inspection metadata.

### `PATCH /api/apps/{app_id}`
Updates custom metadata overrides for an app (name, category, tags, notes, pinned, hidden, url_override).

### `POST /api/apps/{app_id}/inspect/reveal-env`
**Admin Only**. Reveals unmasked environment variable values for a service. Audited in security logs.

---

## 🚀 App Lifecycle & Control

All mutating actions require **Admin** privileges and require **Safe Mode** to be unlocked.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/apps/{app_id}/start` | Starts a stopped custom app or Docker container |
| `POST` | `/api/apps/{app_id}/stop` | Stops an active custom app or Docker container |
| `POST` | `/api/apps/{app_id}/restart` | Restarts an application |
| `GET` | `/api/apps/{app_id}/logs` | Tails live output logs (supports `tail=500`, validates log directory allowlist) |
| `POST` | `/api/apps/{app_id}/exec` | Executes a safe allowlisted diagnostic command (`ps`, `df`, `top`, `env`, `cat`) with 256 KB output cap |

---

## 🐳 Docker System Management

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/docker/system` | Returns Docker system disk usage (`df`) |
| `GET` | `/api/docker/images` | Lists local Docker images and reclaimable sizes |
| `GET` | `/api/docker/volumes` | Lists Docker volumes and usage metadata |
| `POST` | `/api/docker/prune` | Executes `docker system prune` to reclaim disk space (Admin only) |
| `POST` | `/api/docker/compose/{project}/action` | Executes Compose stack action (`restart`, `stop`, `start`, `down`) |
| `POST` | `/api/docker/containers/deploy` | Deploys a new Docker container with port availability verification |

---

## 📡 Real-Time SSE Stream

### `GET /api/stream`
Server-Sent Events (SSE) stream broadcasting real-time updates.
- Bounded queue (max 32 items) dropping stale messages on slow consumers.
- Includes `docker_status`, `apps`, `conflicts`, `stats`, and `last_scan`.
- Heartbeat ping every 15 seconds.
