<p align="center">
  <img src="portly/frontend/public/icons/icon.svg" width="84" height="84" alt="Portly Logo">
</p>

<h1 align="center">Portly</h1>

<p align="center">
  <strong>Lightweight, self-hosted port, host process, and Docker container dashboard.</strong><br>
  Real-time port &amp; conflict discovery, live container &amp; host telemetry, Compose Stack management, 1-click reverse proxy generators, container terminal, and multi-user RBAC in one fast single-process binary/container.
</p>

<p align="center">
  <a href="#-installation--setup"><img src="https://img.shields.io/badge/port-5533-8C9EFF?style=flat-square" alt="Default Port 5533"></a>
  <a href="#-architecture--low-resource-design"><img src="https://img.shields.io/badge/backend-FastAPI%20%7C%20SQLite%20WAL-5EEAD4?style=flat-square" alt="FastAPI and SQLite WAL"></a>
  <a href="#-architecture--low-resource-design"><img src="https://img.shields.io/badge/frontend-React%2019%20%7C%20Vite-61DAFB?style=flat-square" alt="React 19 and Vite"></a>
  <a href="docs/USER_GUIDE.md"><img src="https://img.shields.io/badge/docs-User%20Guide-FBBF77?style=flat-square" alt="User Guide"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-B6E36B?style=flat-square" alt="MIT License"></a>
</p>

---

## 📋 Table of Contents

- [Requirements](#-requirements)
- [Installation & Setup](#-installation--setup)
  - [Option 1: Docker Compose (Recommended for Servers & Homelabs)](#option-1-docker-compose-recommended-for-servers--homelabs)
  - [Option 2: Single Docker Container](#option-2-single-docker-container)
  - [Option 3: Local Python Install (Linux / macOS / Windows)](#option-3-local-python-install-linux--macos--windows)
  - [Option 4: Developer Mode (Hot Reload)](#option-4-developer-mode-hot-reload)
- [First-Time Setup & Basic Usage](#-first-time-setup--basic-usage)
- [CLI Commands](#-cli-commands)
- [Architecture & Low-Resource Design](#-architecture--low-resource-design)
- [Documentation Index](#-documentation-index)
- [Troubleshooting](#-troubleshooting)
- [Testing](#-testing)

---

## ✅ Requirements

- **Python deployment:** Python **3.10+** (tested on Python 3.12 & 3.13) on Linux, macOS, or Windows.
- **Docker deployment:** Docker Engine **20.10+** and Docker Compose **v2+**.
- **Docker monitoring (optional):** Portly works seamlessly even without Docker installed (it will automatically monitor host TCP/UDP sockets and managed Custom Apps).

---

## 🚀 Installation & Setup

### Option 1: Docker Compose (Recommended for Servers & Homelabs)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/SeaXen/portly.git
   cd portly
   ```

2. **Pass your host's `docker` group ID so the non-root container (`portly`, UID/GID `1000:1000`) can read `/var/run/docker.sock`:**
   ```bash
   export DOCKER_GID=$(getent group docker | cut -d: -f3)
   ```
   *(If you do not use Docker integration or run rootless Docker, check `docker-compose.yml` and remove or adjust `group_add`.)*

3. **Start Portly in detached mode:**
   ```bash
   docker compose up -d --build
   ```

4. **Retrieve your single-use First-Run Setup Token:**
   ```bash
   docker compose logs portly
   ```
   Look for the banner:
   ```text
   PORTLY INITIAL ADMIN SETUP REQUIRED
   Setup Token: <your-one-time-token>
   ```

5. **Open Portly in your browser:**  
   Visit **[http://localhost:5533](http://localhost:5533)** (or `http://<your-server-ip>:5533`).  
   If you access Portly through a **DNS hostname or reverse proxy** (e.g. `https://portly.example.com`), uncomment and set `PORTLY_ALLOWED_HOSTS` in [`docker-compose.yml`](docker-compose.yml):
   ```yaml
   - PORTLY_ALLOWED_HOSTS=portly.example.com,*.example.com
   ```
   For production reverse proxies, `docker-socket-proxy`, systemd units, and TLS checklists, see the full [**Deployment Guide**](docs/DEPLOYMENT.md).

---

### Option 2: Single Docker Container

If you prefer a single `docker run` command without editing Compose files:

```bash
docker build -t portly:local .

docker run -d \
  --name portly \
  --restart unless-stopped \
  --network host \
  --pid host \
  --group-add $(getent group docker | cut -d: -f3) \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v portly-data:/app/data \
  -e PORTLY_MODE=server \
  -e PORTLY_HOST=0.0.0.0 \
  -e PORTLY_PORT=5533 \
  -e PORTLY_DATA_DIR=/app/data \
  portly:local
```

Then inspect the logs to copy your first-run setup token:
```bash
docker logs portly
```

---

### Option 3: Local Python Install (Linux / macOS / Windows)

Run Portly directly on your workstation or laptop without Docker:

```bash
# 1. Clone the repository
git clone https://github.com/SeaXen/portly.git
cd portly

# 2. Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1

# 3. Install Portly and its dependencies
pip install -r requirements.txt
pip install -e .

# 4. Launch Portly (desktop mode binds to 127.0.0.1:5533)
portly run --port 5533
```

Open **[http://127.0.0.1:5533](http://127.0.0.1:5533)**.
- In **desktop** mode (default on `127.0.0.1`), create your admin user directly in the welcome screen — no CLI setup token is required.
- To expose Portly on your LAN (`--host 0.0.0.0`), add `--mode server` so Portly enforces a setup token printed to your terminal.

---

### Option 4: Developer Mode (Hot Reload)

Only Node 20+ and Python 3.10+ are needed to hack on Portly:

```bash
# Terminal 1 — Backend API (runs on :5533)
.venv/bin/python -m portly run --port 5533

# Terminal 2 — Frontend Dev Server (runs on :5173 and proxies /api -> :5533)
cd portly/frontend
npm install
npm run dev
```

After making frontend edits, rebuild the static bundle served by the backend:
```bash
npm --prefix portly/frontend run build
```

---

## 🧭 First-Time Setup & Basic Usage

1. **Create Admin Account:** On first boot, fill out the Welcome screen (username, 10+ char password, and the setup token if running in `server` mode).
2. **Understand Safe Mode (On by Default):** Portly locks mutating operations (starting/stopping containers, killing processes, editing ports, `compose down`, `exec` writes) until you unlock **Safe Mode** from the bottom-left sidebar. Timed unlocks (5 min default) automatically re-lock.
3. **Explore Views:** Switch between **Table**, **Grid**, **List**, **Board (Kanban)**, **Overview**, **Stacks**, **Conflicts**, and **History** using the sidebar, toolbar, or `g` chords.
4. **Inspect Any Service:** Click any row/card to open the Service Detail modal:
   - Live ANSI-colorized Logs with Regex & level filtering
   - Port Remapping & Multi-Port Container Recreation (with automatic rollback snapshots)
   - Cloudflare Tunnel URL overrides & 1-click Reverse Proxy configs (Caddy, Nginx, Traefik, Cloudflared)
   - Container Diagnostic Terminal (`ps`, `df`, `free`, `uptime`, `netstat`, `uname`) &masked/unmasked Env vars
5. **Preflight Before Deploying:** Open **Add App → Preflight Collision Check** and paste a `docker run` command, `docker-compose.yml`, or port list to detect conflicts before launching.

Read the complete [**User Guide**](docs/USER_GUIDE.md) for detailed workflows, RBAC user management, backups, and shortcuts.

---

## 💻 CLI Commands

*(Requires `pip install -e .`; otherwise replace `portly` with `python -m portly`.)*

```bash
portly run [--port 5533] [--host 127.0.0.1] [--mode desktop|server]
portly list [--docker] [--host-only] [--json]
portly open <app_id>
portly check-port 8080 [--bind 0.0.0.0]
portly suggest [--count 5] [--start 3000]
portly start <app_id>
portly stop <app_id>
portly logs <app_id> [--tail 100]
portly reset-setup-token
```

---

## ⚡ Architecture & Low-Resource Design

Portly is engineered to run unobtrusively alongside your workloads with minimal CPU, RAM, and disk I/O:

- **Single-process serving:** FastAPI serves both REST/SSE APIs and the pre-built static Vite bundle (`portly/frontend/dist`) on a single port (`5533`) — zero separate Nginx/Node runtime processes needed in production.
- **SQLite WAL + Targeted Indexes:** All state lives in SQLite (`WAL` mode + `NORMAL` sync) with covering indexes on `events(ts)`, `events(type, id)`, `health_history(app_id, ts)`, `health_history(app_id, id)`, `sessions(expires_at)`, and `port_reservations(port, proto)`. Custom app health snapshots load in a single batch query (`get_all_latest_health()`).
- **Idle-Aware Background Polling:** When dashboard tabs/SSE streams are connected, discovery refreshes every `3s` (configurable) and container stats every `4s`. When **no UI clients are connected**, background discovery and Docker stats automatically scale down polling frequency to cut idle CPU & Docker daemon load while preserving live freshness.
- **Shared Bounded Thread Pools, Zero N+1 Docker Calls & `/proc` Caching:** Docker container discovery resolves `Config.Image` inline without firing per-container `/images/{id}/json` HTTP calls (`~10x` faster on multi-container hosts), and only starts background stats/event threads in long-lived server mode so CLI subcommands exit immediately. Host discovery caches static `(name, cmdline, cwd)` metadata per verified `(pid, create_time)`.
- **Fast Code-Split & Offline-First Frontend:** React components are route/modal code-split via `React.lazy`, fonts (`Inter` & `JetBrains Mono`) are vendored locally (zero external CDN calls), API responses >1 KB are GZip-compressed (excluding unbuffered SSE), and Vite hashed assets are cached immutably (`max-age=31536000`).

---

## 📚 Documentation Index

| Document | Audience & Purpose |
|---|---|
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | Step-by-step usage walkthrough, first-time setup, Safe Mode, Stacks, RBAC, Backups & Shortcuts |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Production Docker Compose, non-root `DOCKER_GID`, `docker-socket-proxy`, `systemd`, Caddy/Nginx/Cloudflared & Env Reference |
| [`docs/API.md`](docs/API.md) | REST endpoints, SSE `/api/stream` events, Prometheus `/api/metrics`, and authentication payloads |
| [`SECURITY.md`](SECURITY.md) | Threat model, CSRF/Host header enforcement, Safe Mode boundaries, and socket risk tradeoffs |
| [`docs/FINAL_DOCKER_REVIEW.md`](docs/FINAL_DOCKER_REVIEW.md) | Pre-Docker audit findings, bug fixes, and verification report |

---

## 🛠 Troubleshooting

| Symptom | Fix |
|---|---|
| **`400 INVALID_HOST` when opening via domain/LAN DNS** | Add your hostname(s) to `PORTLY_ALLOWED_HOSTS=portly.example.com,*.example.com` and restart. |
| **Container starts but no Docker containers appear** | Ensure `/var/run/docker.sock` is mounted and `DOCKER_GID` matches `getent group docker \| cut -d: -f3`. |
| **Lost initial Setup Token in server mode** | Run `portly reset-setup-token` (or `docker exec -it portly python -m portly reset-setup-token`) to generate a fresh one-time token. |
| **Actions fail with `403 SAFE_MODE`** | Toggle **Safe Mode** off in the bottom-left Sidebar (or via Command Palette `Ctrl/Cmd+K`) to unlock live mutations. |
| **Host Disk card shows container overlay size inside Docker** | Mount `- /:/hostfs:ro` and set `PORTLY_HOSTFS=/hostfs` in `docker-compose.yml` (opt-in; exposes host files read-only to container). |

---

## 🧪 Testing

```bash
# Backend unit & integration tests
python -m pytest tests --ignore=tests/e2e -q

# Frontend lint, unit tests & production build check
npm --prefix portly/frontend run lint
npm --prefix portly/frontend test -- --run
npm --prefix portly/frontend run build

# End-to-End Playwright tests (launches isolated server against built dist)
pip install pytest-playwright playwright && playwright install chromium
python -m pytest -o addopts= tests/e2e -q
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details. Built by [SeaXen](https://github.com/SeaXen).
