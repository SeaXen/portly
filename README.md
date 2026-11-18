# Portly ⚓

<p align="center">
  <strong>A high-performance, self-hosted dashboard that automatically discovers every listening port, host process, and Docker container on your system.</strong><br>
  Live telemetry with real-time sparklines, 1-click reverse proxy generators, container terminal, Docker Compose management, multi-user RBAC, and unified lifecycle controls.
</p>

<p align="center">
  <a href="#-testing"><img src="https://img.shields.io/badge/tests-176%20unit%20%7C%20e2e%20separate-5EEAD4?style=flat-square&logo=pytest&logoColor=white" alt="Tests"></a>
  <a href="#-quickstart"><img src="https://img.shields.io/badge/port-5533-8C9EFF?style=flat-square" alt="Default Port"></a>
  <a href="#-architecture"><img src="https://img.shields.io/badge/backend-FastAPI%20%7C%20SQLite%20WAL-009688?style=flat-square" alt="Backend"></a>
  <a href="#-architecture"><img src="https://img.shields.io/badge/frontend-React%2019%20%7C%20Vite%20%7C%20CSS%20Tokens-61DAFB?style=flat-square" alt="Frontend"></a>
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

> **First Run in Server Mode:** On first launch, Portly outputs a single-use admin setup token to `docker compose logs`. Enter the setup token in the web interface to create your administrator account.

```yaml
services:
  portly:
    image: ghcr.io/seaxen/portly:latest
    container_name: portly
    network_mode: host
    pid: host
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /:/hostfs:ro
      - portly_data:/app/data
    environment:
      - PORTLY_PORT=5533
      - PORTLY_HOST=0.0.0.0
      - PORTLY_MODE=server
      - PORTLY_HOSTFS=/hostfs
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5533/api/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
```

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

## 💻 CLI Subcommands

Portly includes a dedicated CLI for terminal automation:

```bash
# List all discovered ports (add --json for raw JSON output)
portly list [--docker] [--host-only] [--json]

# Open web dashboard in default browser
portly open <app_id>

# Check port availability and diagnose conflicts
portly check-port 8080 [--bind 0.0.0.0]

# Suggest free ports for binding
portly suggest [--count 5] [--start 3000]

# View process or container logs
portly logs <app_id> [--tail 100]
```

---

## 🌟 Key Capabilities

### 1. Unified Real-Time Discovery & Intelligent Merge
- **Host Processes:** Automatically reads listening TCP and UDP sockets using `psutil` (with fallback to `netstat -ano` / `lsof`). Resolves PID, command line, working directory, process CPU %, and RSS memory.
- **Docker Containers:** Connects directly to the Docker Engine API to extract container names, images, health status, compose projects, published port mappings, CPU %, and memory limits.
- **Zero-False-Conflict Engine:** Eliminates duplicates between Docker-published ports and raw host `docker-proxy` processes. Only flags true collisions (overlapping interfaces or `0.0.0.0` wildcards) while allowing multi-homed binds (e.g. `127.0.0.1` and `192.168.1.50` on the same port).
- **Stable IDs:** Assigns persistent IDs (`docker:...`, `host:...`, `custom:...`) so custom names, categories, and tags survive machine reboots.

### 2. Multi-View Interactive Dashboard
- **Table View:** Sortable columns, checkboxes, density toggle (Compact / Comfy), quick action buttons (Start, Stop, Logs, More). Pinned apps stay on top across all views.
- **Grid View:** Homarr / Homepage style tiles featuring large accent port typography, status dots, and direct Open links.
- **List View:** High-density listing for minimalist monitoring.
- **Board View:** Interactive Kanban columns organized by category with drag-and-drop movement.
- **Overview View:** Aggregate KPI telemetry cards and category distribution breakdown meters.
- **Conflicts View:** Real-time port collision detector with side-by-side diagnosis.
- **History View:** Chronological change log and system event timeline tracking opened/closed ports.
- **Saved Views:** Instant tabs for `"All ports"`, `"Dev only"`, `"Exposed 0.0.0.0"`, `"Docker"`, and user-defined custom saved views.

### 3. Preflight Port Collision Detection
- Check port availability before running containers or compose stacks.
- Paste a `docker run` command or `docker-compose.yml` snippet in the web UI or CLI to diagnose port conflicts in advance.

### 4. Safe Mode with Auto-Relock Timers
- Enabled by default to prevent accidental mutations.
- One-click unlock for 5 minutes with live countdown banner and automatic re-locking.
- Replaced all browser `alert()` and `confirm()` prompts with accessible Focus-trapped Dialogs and Toasts.

### 5. Multi-User RBAC & Audit Logging
- Role-Based Access Control (`admin` vs `viewer`).
- Complete audit logging of all mutations (timestamp, actor, target, success).
- Admin-controlled environment variable revelation for container inspection.

### 6. Reverse Proxy Generation
- Instant reverse proxy configurations for Caddy, Nginx, Traefik (file & labels), and Cloudflare Tunnels.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `?` | Open Keyboard Shortcuts modal |
| `/` | Focus search bar |
| `Ctrl + K` / `Cmd + K` | Open Command Palette (works anywhere) |
| `Shift + K` | Toggle Kiosk / Wall Display mode |
| `g` then `t` | Switch to **Table** view |
| `g` then `g` | Switch to **Grid** view |
| `g` then `b` | Switch to **Board** view |
| `g` then `l` | Switch to **List** view |
| `Escape` | Close active modal, drawer, or dialog |

---

## 🧪 Testing

```bash
# Run unit & integration tests (176 passed)
python -m pytest tests --ignore=tests/e2e -q

# Run end-to-end Playwright tests (needs the frontend dev server)
python -m pytest -o addopts= tests/e2e -q
```

**176 unit tests; e2e suite separate** verify:
- Host discovery and stable ID formatting across Linux/macOS/Windows.
- Docker deduplication & multi-homed port conflict detection.
- Multi-user RBAC, timing-safe authentication, and rate limiting.
- Command execution boundaries, shell operator blocking, and output truncation.
- SQLite WAL mode concurrency stress testing and version pragma tracking.
- Safe Mode mutation locking and 5-minute auto-relock timers.
- Reverse proxy configuration generation for Caddy, Nginx, Traefik, and Cloudflare Tunnels.
- SSL/TLS certificate inspection and expiration calculation.
- SSRF filtering and image MIME detection.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details. Built by [SeaXen](https://github.com/SeaXen).
