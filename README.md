# Portly ⚓

> A high-performance, self-hosted dashboard that automatically discovers every listening port and container on your system, displays live system telemetry with sparklines, and provides unified controls to organize, start, stop, change ports, and inspect logs.

[![Tests](https://img.shields.io/badge/tests-101%20passed-5EEAD4?style=flat-square)](#testing)
[![Port](https://img.shields.io/badge/port-5533-8C9EFF?style=flat-square)](#quickstart)
[![Theme](https://img.shields.io/badge/theme-premium%20dark-151821?style=flat-square)](#design-system)

---

## ⚡ Quickstart (Under 2 Minutes)

### Option 1: Direct Local Execution (Python + Built Frontend)

Portly runs natively on **Windows**, **Linux**, and **macOS**.

1. **Install Python requirements**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Launch Portly on port 5533**:
   ```bash
   python -m portly run --port 5533
   ```

3. Open **[http://localhost:5533](http://localhost:5533)** in your browser.

---

### Option 2: Docker Compose (Server / NAS Mode)

```bash
docker compose up -d
```

Open **[http://localhost:5533](http://localhost:5533)**.

> **Note for Docker environments:** Portly requires `network_mode: host` and `pid: host` in `docker-compose.yml` along with the Docker socket mount (`/var/run/docker.sock`) to discover both host network sockets and container ports.

---

## 🛠️ CLI Usage

Portly includes a built-in CLI:

```bash
# List all discovered ports, process names, and auto-categories in terminal
python -m portly list

# Output formatted JSON
python -m portly list --json

# Filter only Docker containers
python -m portly list --docker

# Start or stop an application by name or ID
python -m portly start "Billing API"
python -m portly stop "Billing API"

# Run on a custom port and host
python -m portly run --port 5533 --host 127.0.0.1
```

---

## 🌟 Key Features

### 1. Automatic Discovery & Intelligent Deduplication
- **Host Processes:** Automatically reads listening TCP and UDP sockets using `psutil` (with fallback to `netstat -ano` / `lsof`). Resolves PID, command line, working directory, process CPU %, and RSS memory.
- **Docker Containers:** Connects via Docker Engine API to extract container names, images, health status, compose projects, published port mappings, CPU %, and memory limits.
- **Merge & Conflict Resolution:** Eliminates duplicates between Docker-published ports and raw host `docker-proxy` processes. Detects and flags conflicting apps claiming the same host port.
- **Stable IDs:** Assigns persistent IDs (`docker:...`, `host:...`, `custom:...`) so names, categories, and tags survive restarts.

### 2. Premium Glanceable Dark UI (4 Interactive Views + Dedicated Dashboards)
- **Table View:** Sortable columns, checkboxes, density toggle (Compact / Comfy), quick action buttons (Start, Stop, Logs, More).
- **Grid View:** Homarr / Homepage style tiles featuring large accent port typography, status dots, and direct Open links.
- **List View:** Ultra-compact view for high-density monitoring.
- **Board View:** Interactive Kanban columns organized by category with drag-and-drop movement.
- **Overview View:** Aggregate KPI telemetry cards and category distribution breakdown meters.
- **Conflicts View:** Real-time port collision detector with side-by-side diagnosis.
- **History View:** Chronological change log and system event timeline tracking opened/closed ports.
- **Saved Views:** Instant tabs for `"All ports"`, `"Dev only"`, `"Exposed 0.0.0.0"`, `"Docker"`, and custom user-created views.
- **Keyboard Shortcuts:** Built-in cheatsheet (`?`), search focus (`/`), Command Palette (`Ctrl+K`), and view shortcuts (`g` then `t`/`g`/`b`/`l`).

### 3. One-Line Stats Strip
- Single horizontal strip that **never wraps**:
  - **CPU:** Percent utilization, core count, 60-point live SVG sparkline (~5 minutes history).
  - **Memory:** GB used, total GB, live SVG sparkline.
  - **Disk:** GB used, total storage capacity, live bar.
  - **Network:** Real-time download and upload bandwidth rate with live SVG sparkline.
  - **Containers:** Active running container count.
  - **Listening:** Active listening ports and conflict indicator.
- Clicking any segment opens the **System Telemetry Drawer** with per-core CPU bars, swap metrics, mount points, and network interface IPs.

### 4. Port Management & Rollback
- **Check Availability:** Live socket binding and port reservation validation before making changes.
- **Suggest Free Port:** Suggests next available safe ports with one click.
- **Docker Port Reassignment:** Inspects, stops, removes, and recreates containers with updated port bindings, verifies health, and stores an automatic rollback snapshot.
- **Custom Apps:** Automatically updates configuration and restarts with `PORT` environment variables.

### 5. Custom App Management & Adoption
- "Add App" dialog with 4 modes: **Custom app**, **From Docker**, **From running process** (1-click adoption of detected host processes), and **External URL**.
- Configurable health check endpoints, intervals, start/stop commands, working directories, and log file paths.

### 6. Live Log Streaming
- Live streaming tail buffer with real-time level filtering (`All`, `Info`, `Warn`, `Error`), follow switch, text wrapping, ANSI color formatting, and log file download.

### 7. Security & Safe Mode
- **Safe Mode ON by default:** Locks all mutating actions (start, stop, recreate, kill) until explicitly unlocked via confirmation.
- **Server Mode:** Enforces user authentication and password hashing when binding to external interfaces (`0.0.0.0`).

### 8. 1-Click Reverse Proxy Config Generator
- Instantly generates production-ready reverse proxy blocks for **Caddy**, **Nginx**, **Traefik YAML**, and **Traefik Docker Labels**.
- Supports custom domains (e.g. `vault.homelab.arpa`) with automatic sanitization and WebSocket upgrade headers.

### 9. SSL / TLS Certificate Inspector
- Live certificate inspection for HTTPS/TLS ports.
- Decodes certificate subject, issuer (e.g. Let's Encrypt), SAN alternative names, valid date windows, and days remaining until expiration.

### 10. In-Browser Container Terminal
- Built-in container command executor (`docker exec`) with Safe Mode whitelisting of diagnostic commands (`ps`, `top`, `df`, `env`, `netstat`, `uname`, `free`, `uptime`, etc.).
- Execution timing benchmarks and clear terminal output formatting.

### 11. Docker Compose Inspector
- Automatically parses container compose labels to locate compose files on disk and renders the active service configuration directly in the app detail modal.

### 12. Webhooks & Alerting
- Real-time event notifications dispatched to **Discord**, **Telegram**, **Slack**, and **Generic / Ntfy / Gotify** webhooks.
- Background asynchronous dispatcher ensures alerts never block discovery.
- In-app test alert button in Customize drawer.

### 13. Kiosk / Wall Display Mode & Progressive Web App (PWA)
- Fullscreen distraction-free monitoring mode toggled via **`Shift + K`** or top bar monitor icon.
- Full PWA support (`manifest.webmanifest`, service worker, vector icons) for installability on desktop and mobile.

---

## 🏗️ Architecture

```
portly/
  backend/
    app.py                FastAPI application, REST endpoints, SSE stream, static SPA serving
    store.py              SQLite persistence (data/portly.db), migrations, defaults
    stats.py              Ring buffer metrics, sparkline SVG generation, system stats
    health.py             HTTP & TCP health checks, latency measurement
    categories.py         Rules engine, priority evaluation, manual overrides
    ports.py              Port availability checks, suggestion, migration planning
    notifications.py      Real-time change detection, conflict events, webhook alerts
    auth.py               Admin/viewer session management, bcrypt password hashing
    proxy_gen.py          Reverse proxy generators (Caddy, Nginx, Traefik)
    favicon.py            SSRF-safe favicon fetcher with magic byte detection & SVG fallback
    tls_inspector.py      SSL/TLS certificate validator & expiration countdown
    discovery/
      host.py             psutil listening sockets with netstat/lsof fallback
      docker_src.py       Docker Engine container discovery & event listener
      merge.py            Deduplication, conflict detection, stable ID assignment
    actions/
      docker_actions.py   Container start/stop/restart/recreate/logs/exec with Safe Mode guards
      process_actions.py  Subprocess launcher, log tailing, process termination
  frontend/
    src/
      App.tsx             Main application controller, SSE listener & Kiosk mode
      api.ts              Typed backend API client
      types.ts            Data models & interfaces
      components/
        Sidebar.tsx       Navigation, categories, safe mode switch
        TopBar.tsx        Search, theme toggle, export, scan, add app, kiosk toggle
        StatsStrip.tsx    One-line non-wrapping sparkline metrics
        Toolbar.tsx       View switcher, filters, sort, group, density
        TableView.tsx     Data table with sticky header, favicons & row actions
        GridView.tsx      Homepage-style tiles with favicons
        ListView.tsx      Compact density listing
        BoardView.tsx     Kanban board by category with drag & drop
        OverviewView.tsx  Aggregate telemetry & category breakdown
        ConflictsView.tsx Port collision detector & resolution
        HistoryView.tsx   Audit change log & socket event timeline
        AppDetailModal.tsx Logs, port editor, proxy generator, TLS inspector, terminal, compose
        AddAppModal.tsx   4-tab custom app & process adoption dialog
        CustomizeDrawer.tsx Layout, accent color, rules manager, webhooks & alerting
        SystemDrawer.tsx  Deep hardware and mount point telemetry
        CommandPalette.tsx Ctrl+K keyboard command palette
        KeyboardShortcutsModal.tsx '?' Cheatsheet modal with Shift+K shortcut
        BulkActionBar.tsx Floating multi-select actions
        AppIcon.tsx       Dynamic favicon and initial vector badge renderer
```

---

## 🧪 Testing

Run the full pytest suite:

```bash
python -m pytest tests/
```

All 17 test suites (101 automated tests) verify:
- Host discovery and stable ID formatting
- Docker deduplication & port conflict detection
- Categorization rule priority and manual overrides
- Port availability checking and free port suggestion
- Safe mode blocking mutating actions and command injection
- Reverse proxy snippet generation (Caddy, Nginx, Traefik)
- SSL/TLS certificate inspection and expiration calculation
- SSRF filtering and image MIME detection
- Webhook alert payload formatting for Discord, Slack, and generic webhooks
- Complete API endpoints, custom app CRUD, and export formats (JSON, CSV, Markdown)
