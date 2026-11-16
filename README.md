# Portly ⚓

<p align="center">
  <strong>A high-performance, self-hosted dashboard that automatically discovers every listening port, host process, and Docker container on your system.</strong><br>
  Live telemetry with real-time sparklines, 1-click reverse proxy generators, container terminal, Docker Compose management, and unified lifecycle controls.
</p>

<p align="center">
  <a href="#-testing"><img src="https://img.shields.io/badge/tests-146%20passed-5EEAD4?style=flat-square&logo=pytest&logoColor=white" alt="Tests"></a>
  <a href="#-quickstart"><img src="https://img.shields.io/badge/port-5533-8C9EFF?style=flat-square" alt="Default Port"></a>
  <a href="#-architecture"><img src="https://img.shields.io/badge/backend-FastAPI%20%7C%20SQLite%20WAL-009688?style=flat-square" alt="Backend"></a>
  <a href="#-architecture"><img src="https://img.shields.io/badge/frontend-React%2018%20%7C%20Vite%20%7C%20Tailwind-61DAFB?style=flat-square" alt="Frontend"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-B6E36B?style=flat-square" alt="License"></a>
  <a href="DESIGN.md"><img src="https://img.shields.io/badge/design-Obsidian%20Harbor-151821?style=flat-square" alt="Design System"></a>
</p>

---

## ⚡ Quickstart

### Option 1: Docker Compose (Server / Homelab / NAS)

```bash
docker compose up -d
```
Open **[http://localhost:5533](http://localhost:5533)**.

> **Note for Docker hosts:** Portly uses `network_mode: host` and `pid: host` in `docker-compose.yml` alongside the `/var/run/docker.sock` volume mount to discover host socket tables and Docker container states simultaneously.

---

### Option 2: Direct Local Run (Python 3.10+)

Portly runs natively on **Linux**, **macOS**, and **Windows**:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch Portly on port 5533
python -m portly run --port 5533
```
Open **[http://localhost:5533](http://localhost:5533)** in your browser.

---

### Option 3: Full Development Mode (Live Hot-Reload)

```bash
# Terminal 1: Backend
pip install -e .
python -m portly run --port 5533

# Terminal 2: Frontend (Vite dev server)
cd portly/frontend
npm install
npm run dev
```

---

## 🌟 Key Capabilities

### 1. Unified Real-Time Discovery & Intelligent Merge
- **Host Processes:** Automatically reads listening TCP and UDP sockets using `psutil` (with fallback to `netstat -ano` / `lsof`). Resolves PID, command line, working directory, process CPU %, and RSS memory.
- **Docker Containers:** Connects directly to the Docker Engine API to extract container names, images, health status, compose projects, published port mappings, CPU %, and memory limits.
- **Zero-False-Conflict Engine:** Eliminates duplicates between Docker-published ports and raw host `docker-proxy` processes. Only flags true collisions (overlapping interfaces or `0.0.0.0` wildcards) while allowing multi-homed binds (e.g. `127.0.0.1` and `192.168.1.50` on the same port).
- **Stable IDs:** Assigns persistent IDs (`docker:...`, `host:...`, `custom:...`) so custom names, categories, and tags survive machine reboots.

### 2. Multi-View Interactive Dashboard
- **Table View:** Sortable columns, checkboxes, density toggle (Compact / Comfy), quick action buttons (Start, Stop, Logs, More).
- **Grid View:** Homarr / Homepage style tiles featuring large accent port typography, status dots, and direct Open links.
- **List View:** High-density listing for minimalist monitoring.
- **Board View:** Interactive Kanban columns organized by category with drag-and-drop movement.
- **Overview View:** Aggregate KPI telemetry cards and category distribution breakdown meters.
- **Conflicts View:** Real-time port collision detector with side-by-side diagnosis.
- **History View:** Chronological change log and system event timeline tracking opened/closed ports.
- **Saved Views:** Instant tabs for `"All ports"`, `"Dev only"`, `"Exposed 0.0.0.0"`, `"Docker"`, and custom user-created views.

### 3. One-Line Glanceable Stats Strip & Telemetry Drawer
- Single horizontal strip that **never wraps**:
  - **CPU:** Utilization percent, logical core count, live 60-point SVG sparkline (~5 minutes history).
  - **Memory:** GB used, total GB, memory percent, live SVG sparkline.
  - **Disk:** GB used, total storage capacity, utilization bar.
  - **Network:** Real-time download and upload bandwidth rate with live SVG sparkline.
  - **Containers:** Active running container count.
  - **Listening:** Active listening ports and conflict indicator.
- Clicking any metric opens the **System Telemetry Drawer** displaying per-core CPU bars, swap metrics, mount points, and network interface IP addresses.

### 4. Non-Destructive Port Reassignment & Rollback
- **Pre-Flight Validation:** Socket binding validation and port conflict checks before mutating services.
- **One-Click Suggestions:** Scans for next available clean ports via single-pass socket probes.
- **Multi-Port Remapping:** Remap multiple container port mappings simultaneously with individual port conflict validation.
- **Safe Docker Recreation:** Takes snapshots of current container settings, environment, binds, and networks, recreates container with updated port bindings, and keeps automatic rollback snapshots in SQLite.

### 5. 1-Click Container Deployment & Custom Apps
- **Add App Wizard with 5 Modes:** **Custom app**, **From Docker**, **From running process** (1-click adoption of detected host processes), **External URL**, and **Deploy Container**.
- **Deploy Container Templates:** 1-click quick-deploy templates (PostgreSQL, Redis, Nginx, Uptime Kuma, Nextcloud) and custom container deployment with live port availability verification.
- Configurable health check endpoints, intervals, start/stop commands, working directories, and log file paths.

### 6. Cloudflare Tunnel & Remote Access Integration
- **Manual Cloudflare Tunnel URLs:** Assign public Cloudflare Zero Trust tunnel URLs (e.g. `https://app.yourdomain.com` or `*.trycloudflare.com`), Tailscale Funnel, or custom domains.
- **Visual Tunnel Badges:** Direct external links and amber/cyan `☁ Tunnel` badges on Grid and Table views.
- **Cloudflare Ingress Rule Generator:** Generates production-ready `cloudflared` ingress YAML blocks alongside Caddy, Nginx, and Traefik in the 1-Click Reverse Proxy Generator.

### 7. Docker Compose Stack Controls & System Hygiene
- **Compose Stack Controls:** Direct 1-click Stack lifecycle actions (`Restart Stack`, `Stop Stack`, `Start Stack`, `Down Stack`) for Compose projects.
- **Docker Storage & Hygiene:** Deep inspection of Docker images, volumes, and reclaimable disk space with 1-click system pruning in the System Drawer.

### 8. Live Log Streaming
- Live streaming tail buffer with real-time level filtering (`All`, `Info`, `Warn`, `Error`), follow switch, text wrapping, ANSI color formatting, and log file download.

### 9. Production Security & Safe Mode
- **Safe Mode ON by Default:** Locks all mutating actions (start, stop, recreate, kill, prune) until explicitly unlocked via top bar confirmation.
- **Server vs Desktop Mode:** In desktop mode (localhost), operates with zero-friction local convenience. In server mode (`--mode server`), requires administrative account setup and session authentication.
- **Guarded System Endpoints:** Diagnostic and telemetry endpoints require authentication when users exist, and webhook credentials are automatically masked from non-admin viewers.
- **Persistent SQLite Sessions:** Multi-worker compatible authentication sessions stored in SQLite with WAL journal mode.
- **SSRF & Injection Hardened:** Subprocess log file restrictions, strict reverse proxy domain regex sanitization (`^[a-zA-Z0-9.-]+$`), and protected IP filters.

### 10. 1-Click Reverse Proxy Config Generator
- Instantly generates production-ready reverse proxy blocks for **Caddy**, **Nginx**, **Traefik YAML**, **Traefik Docker Labels**, and **Cloudflare Tunnel (`cloudflared`)**.
- Supports custom domains (e.g. `vault.homelab.arpa`) with automatic sanitization and WebSocket upgrade headers.

### 11. SSL / TLS Certificate Inspector
- Live certificate inspection for HTTPS/TLS ports.
- Decodes certificate subject, issuer (e.g. Let's Encrypt), SAN alternative names, valid date windows, and days remaining until expiration.

### 12. In-Browser Container Terminal
- Built-in container command executor (`docker exec`) with Safe Mode whitelisting of diagnostic commands (`ps`, `top`, `df`, `env`, `netstat`, `uname`, `free`, `uptime`, etc.).
- Execution timing benchmarks and strict timeout handling (HTTP 408 on stall) to prevent worker starvation.

### 13. Docker Compose Inspector
- Automatically parses container compose labels to locate compose files on disk and renders the active service configuration directly in the app detail modal.

### 14. Webhooks & Alerting
- Real-time event notifications dispatched to **Discord**, **Telegram**, **Slack**, and **Generic / Ntfy / Gotify** webhooks.
- Background asynchronous dispatcher ensures alerts never block discovery.
- In-app test alert button in Customize drawer.

### 15. Kiosk / Wall Display Mode & Progressive Web App (PWA)
- Fullscreen distraction-free monitoring mode toggled via **`Shift + K`** or top bar monitor icon.
- Full PWA support (`manifest.webmanifest`, service worker, vector icons) for installability on desktop and mobile.

---

## 🛠️ CLI Reference

Portly includes a powerful command-line interface:

```bash
# Run Portly dashboard on custom host and port
python -m portly run --port 5533 --host 127.0.0.1 --mode desktop

# Enforce authentication for LAN / WAN access
python -m portly run --port 5533 --host 0.0.0.0 --mode server

# List all discovered ports, process names, and auto-categories in terminal
python -m portly list

# Filter only Docker containers
python -m portly list --docker

# Filter only host processes
python -m portly list --host-only

# Output machine-readable JSON
python -m portly list --json

# Start or stop an application by name or ID
python -m portly start "Billing API"
python -m portly stop "docker:redis-cache:6379/tcp"
```

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORTLY_HOST` | `127.0.0.1` | Host address to bind (use `0.0.0.0` for all interfaces). |
| `PORTLY_PORT` | `5533` | HTTP listening port. |
| `PORTLY_MODE` | `desktop` | `desktop` (local access) or `server` (enforces authentication). |
| `PORTLY_DATA_DIR` | `./data` | Directory where `portly.db` (SQLite) is stored. |
| `PORTLY_CORS_ORIGINS` | `""` | Comma-separated list of allowed CORS origins. |
| `PORTLY_ALLOW_INSECURE_BIND` | `false` | Set to `true` to allow binding to `0.0.0.0` in desktop mode without auth. |

---

## 🏗️ Architecture

```
                       ┌──────────────────────────────────────────────┐
                       │            Browser / PWA Client              │
                       │   React 18 + TypeScript + Tailwind + Vite   │
                       └──────────────────────┬───────────────────────┘
                                              │ REST API & Live SSE (/api/stream)
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Portly FastAPI Backend                             │
│                                                                             │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌──────────────────┐ │
│  │   Discovery Engine    │  │   Actions & Proxy     │  │  Notifications   │ │
│  │ • Host (psutil/lsof)  │  │ • Safe Mode Guard     │  │ • Discord/Slack  │ │
│  │ • Docker Engine API   │  │ • Docker Recreation   │  │ • Telegram/Ntfy  │ │
│  │ • Dedup & Merge       │  │ • Caddy/Nginx/Traefik │  │ • Conflict Alerts│ │
│  └───────────┬───────────┘  └───────────┬───────────┘  └────────┬─────────┘ │
│              │                          │                       │           │
│              └──────────────────────────┼───────────────────────┘           │
│                                         ▼                                   │
│                        ┌─────────────────────────────────┐                  │
│                        │       SQLite Store (WAL)        │                  │
│                        │ • App Overrides & Categories    │                  │
│                        │ • Persistent Sessions & History │                  │
│                        │ • Auto-Pruning & Snapshots      │                  │
│                        └─────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `?` | Open Keyboard Shortcuts modal |
| `/` | Focus search bar |
| `Ctrl + K` / `Cmd + K` | Open Command Palette |
| `Shift + K` | Toggle Kiosk / Wall Display mode |
| `g` then `t` | Switch to **Table** view |
| `g` then `g` | Switch to **Grid** view |
| `g` then `b` | Switch to **Board** view |
| `g` then `l` | Switch to **List** view |
| `Escape` | Close active modal, drawer, or dialog |

---

## 🧪 Testing

Portly maintains high test coverage across unit, security, and integration layers:

```bash
# Run the complete test suite
python -m pytest tests/
```

146 automated tests verify:
- Host discovery and stable ID formatting across Linux/macOS/Windows.
- Docker deduplication & multi-homed port conflict detection.
- Categorization rule priority and manual overrides.
- Single-pass port availability checking and free port suggestion.
- Safe Mode mutation locking and command injection prevention.
- Container exec timeout handling and thread pool protection.
- Persistent SQLite session management across restarts.
- Automatic SQLite health history and event table retention pruning.
- Reverse proxy configuration generation for Caddy, Nginx, Traefik, and Cloudflare Tunnels.
- SSL/TLS certificate inspection and expiration calculation.
- SSRF filtering and image MIME detection.
- Webhook alert payload formatting for Discord, Slack, Telegram, Ntfy, and Gotify.
- Complete REST API endpoints, custom app CRUD, and export formats (JSON, CSV, Markdown).

---

## 📐 Design & Product Authority

- [PRODUCT.md](PRODUCT.md) — Product positioning, operating context, capabilities, and principles.
- [DESIGN.md](DESIGN.md) — Canonical design system specification, Obsidian Harbor visual direction, tokens, typography, and guardrails.
- [.impeccable/design.json](.impeccable/design.json) — Extension tokens, component shadows, and UI component styling.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details. Built by [SeaXen](https://github.com/SeaXen).
