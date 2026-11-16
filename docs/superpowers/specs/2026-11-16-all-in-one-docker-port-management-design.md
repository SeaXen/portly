# All-in-One Docker & Port Management (with Cloudflare Tunnel & Multi-Port Remapping) Design

**Date:** 2026-11-16  
**Status:** Approved  
**Author:** Antigravity & User  
**Target Project:** Portly (⚓)

---

## 1. Intent & The Why

Portly began as an ultra-fast port discovery and monitoring dashboard with lightweight container actions. Homelab owners, developers, and DevOps engineers, however, need a **single unified pane of glass** that not only monitors listening ports, but also:
1. Gives full control over **Cloudflare Tunnel URLs and custom external domains** so local and containerized services can be reached securely from anywhere without exposing raw home IP addresses.
2. Generates **Cloudflare Tunnel (`cloudflared`) configuration blocks** alongside Caddy, Nginx, and Traefik.
3. Provides **Multi-Port container management** (editing, remapping, and verifying multiple TCP/UDP exposed ports in a single operation, not just a single primary port).
4. Delivers **Docker System Hygiene** (browsing Docker volumes, viewing local Docker images, and 1-click pruning of dangling images, unused volumes, and build cache to reclaim disk space).
5. Provides **Docker Compose Stack lifecycle management** (`up -d`, `down`, `restart`, compose configuration inspection/editing).
6. Provides **1-Click Container Deployment** (a dedicated container creation wizard with community presets like Postgres, Redis, Nginx, Uptime Kuma, etc.).

---

## 2. Goals, Non-Goals, Anti-Goals

### Goals
- **First-Class Cloudflare Tunnel URL & Remote Access**: Allow setting and managing a manual Cloudflare Tunnel URL (or custom domain) per application, showing dedicated tunnel badges and external links across Grid, Table, List, and Detail views.
- **Cloudflare Ingress Rule Generation**: Add `cloudflared` ingress YAML generation to Portly's 1-Click Reverse Proxy Generator.
- **Multi-Port Remapping**: Allow viewing and remapping multiple port mappings per container with live conflict checking and non-destructive snapshot recreation.
- **Docker Volume & Image Management**: Inspect volumes, view local images, and perform one-click system disk pruning (`docker system prune -f`).
- **Compose Stack Controls**: Run stack actions (`up -d`, `down`, `restart`) on containers tagged with `com.docker.compose.project`.
- **New Container Launch Wizard**: Launch new Docker containers directly from Portly with custom ports, env variables, volumes, and automatic port conflict prevention.
- **Polished UI & E2E Verification**: Dark-mode aesthetic consistent with Portly's DESIGN.md, mobile & desktop responsive, thoroughly tested with pytest and browser verification.

### Non-Goals
- Replacing Docker Engine or Kubernetes clustering (Portly targets single-node/host/homelab Docker Engine).
- Forcing automatic tunnel daemon installations (Portly supports manual URL configuration and YAML configuration generation, while leaving the choice of running `cloudflared` in Docker or on the host up to the user).

### Anti-Goals
- Do not introduce heavyweight dependencies or slow down Portly's instant <100ms discovery loop.
- Do not execute destructive Docker operations without explicit user confirmation or Safe Mode unlocking.

---

## 3. Approaches Considered & Selected

- **Approach 1 (Selected): Native Integrated Hub**: Integrate Cloudflare Tunnel URLs, multi-port mapping, system hygiene, and stack actions directly into Portly's FastAPI backend and React frontend.
- **Approach 2 (Rejected): External Subprocess Daemon**: Running background child processes for `cloudflared` directly inside Portly. Rejected due to cross-platform fragility (Windows vs Linux NAS), token permission security risks, and socket complexity.

---

## 4. Architectural Specifications

### 4.1. Cloudflare Tunnel & External Access
- **Data Model**: `url_override` in SQLite `apps` table and `portly.url` Docker label are preserved. In addition, introduce `tunnel_type` ("cloudflare", "tailscale", "custom") and `tunnel_url`.
- **Proxy Generator**: In `portly/backend/proxy_gen.py`, add `generate_cloudflared_config(domain: str, upstream_host: str, port: int) -> str`:
  ```yaml
  # Cloudflare Tunnel (cloudflared) Ingress Rule
  # Add to your ~/.cloudflared/config.yml or Docker cloudflared service:
  ingress:
    - hostname: {domain}
      service: http://{upstream_host}:{port}
    - service: http_status:404
  ```
- **UI Exposure**:
  - Add a dedicated **"Access & Tunnels"** tab in `AppDetailModal` to configure the Cloudflare Tunnel URL, copy ingress config, and test connectivity.
  - Surface an amber/cyan **Tunnel Badge** on app cards/rows with a 1-click external open button.

### 4.2. Multi-Port Remapping
- **Backend**: Extend `apply_port_change_docker` to accept a dictionary/list of port mappings:
  `mappings: List[{"container_port": "80/tcp", "host_port": 8080, "bind": "0.0.0.0"}]`.
  Recreates the container updating all specified bindings in `PortBindings` while keeping non-reassigned ports intact.
- **Frontend**: A multi-row port mapping editor in `AppDetailModal`'s Ports tab showing all exposed ports with individual conflict validators.

### 4.3. Docker System Hygiene (Images, Volumes & Pruning)
- **Backend Endpoints**:
  - `GET /api/docker/system` -> returns container count, image count, volume count, disk space used.
  - `GET /api/docker/images` -> list local Docker images (tag, size, ID, created).
  - `GET /api/docker/volumes` -> list volumes (name, driver, mountpoint, size/ref).
  - `POST /api/docker/prune` -> runs `docker system prune` / volume prune (guarded by Safe Mode).
- **Frontend**:
  - Docker Management section in `SystemDrawer` or dedicated Docker Hub modal with disk reclamation stats and 1-click Prune button.

### 4.4. Docker Compose Stack Management
- **Backend Endpoints**:
  - `POST /api/docker/compose/{project}/action` (`action`: `restart`, `stop`, `start`, `down`).
- **Frontend**:
  - In `AppDetailModal` -> Compose tab: add action buttons for the parent project stack.

### 4.5. Container Deployment Wizard
- **Backend Endpoints**:
  - `POST /api/docker/containers/deploy` -> accepts image, name, ports, env, volumes, restart_policy and runs `client.containers.run(...)`.
- **Frontend**:
  - Add "Deploy Container" tab in `AddAppModal` with common templates (Redis, Postgres, Nginx, Uptime Kuma, Nextcloud).
