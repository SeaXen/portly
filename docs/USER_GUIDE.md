# Portly User & Operator Guide

This guide walks new and experienced users through installing, configuring, and getting the most out of **Portly**.

---

## 1. Choosing an Installation Method

| Method | Best For | Setup Time |
|---|---|---|
| **Docker Compose (`docker-compose.yml`)** | Servers, NAS (Synology/TrueNAS/Unraid), Homelabs | ~2 min |
| **Local Python (`venv`)** | Workstations, laptops, macOS/Windows/Linux desktop use | ~2 min |
| **Systemd Service** | Dedicated bare-metal Linux VMs without Dockerized dashboard | ~3 min |

---

## 2. First-Run Setup & Login

### Desktop Mode (`127.0.0.1` loopback)
When started via `python -m portly run`, Portly defaults to **desktop mode** bound strictly to `127.0.0.1`:
1. Open `http://127.0.0.1:5533`.
2. Enter your desired **Admin Username** and **Password** (minimum **10 characters**).
3. Click **Create Admin Account** — you are logged in automatically.

### Server Mode (Docker / Network Exposure)
When run in Docker (`PORTLY_MODE=server`) or with `--mode server`:
1. On initial boot (when zero users exist), Portly prints a **single-use 32-character hex Setup Token** to container logs (`stderr`):
   ```bash
   docker compose logs portly
   ```
2. Open `http://<server-ip>:5533`.
3. Paste the **Setup Token**, choose an Admin username and password (min 10 chars), and submit.
4. **Forgot or lost token?** Run inside the container or virtualenv:
   ```bash
   docker compose exec portly python -m portly reset-setup-token
   ```
   Or pass a pre-seeded one-time token via `PORTLY_SETUP_TOKEN` before first boot.

---

## 3. Navigating the Dashboard

### Views & Layout
- **Overview:** System health KPIs, CPU/RAM/Disk/Net sparklines, category breakdown, and recent activity feed.
- **Ports (Table / Grid / List / Board):**
  - **Table View:** Full sortable columns, multi-select bulk actions, density switcher (`Compact` / `Comfy`), and inline Start/Stop/Logs triggers.
  - **Grid View:** Visual service tiles highlighting host port, live status indicator, CPU/RAM, TLS expiry badge, and direct **Open** link.
  - **List View:** Dense summary list for quick scanning.
  - **Board View:** Drag-and-drop Kanban columns grouped by Category (supports manual re-categorization).
- **Docker:** Filtered view showing only discovered Docker containers.
- **Stacks:** Create, preflight-check, edit, start (`up`), `restart`, `stop`, and tear down (`down`) managed `docker-compose.yml` stacks directly from Portly.
- **Conflicts:** Side-by-side port collision inspector plus **Reserved Ports** registry so teams don't accidentally assign colliding ports to future services.
- **History:** Live timeline of discovered port openings/closings, container state changes, and conflict resolution events.

### Custom Views, Tags & Categories
- Use the top **Saved Views** strip (`All ports`, `Dev only`, `Exposed 0.0.0.0`, `Docker`, or click **+ Save View**) to bookmark filtered/sorted workspaces.
- Open **Customize** (top bar / toolbar) to switch between **Dark**, **Light**, **OLED**, and **System** themes, pick custom accent colors, toggle visible columns, and configure **Auto-Categorization Rules**.

---

## 4. Safe Mode & Guardrails

**Safe Mode is ON by default.** While Safe Mode is active:
- Read-only inspection works freely (ports, logs, reverse proxy generation, TLS checks, preflight checks, container `ps`/`df`/`free`/`uptime` diagnostics).
- Mutating operations (starting/stopping/restarting containers, killing host processes, changing ports, running `compose down`, revealing secrets, editing custom app execution) are safely blocked with `403 SAFE_MODE`.

To make changes:
1. Click the **Safe Mode** toggle at the bottom-left of the Sidebar (or run **Toggle Safe Mode** in Command Palette `Ctrl/Cmd + K`).
2. Choose **Unlock for 5 minutes (Recommended)** (auto-relocks automatically with a live countdown badge) or unlock until manually re-enabled.

---

## 5. Managing Apps & Services

### Inspecting a Service
Click any app name to open its **Detail Modal**:
- **Logs:** Real-time log tailing with `auto-follow`, level filtering (`Info`, `Warn`, `Error`), regex search, line wrapping, and one-click download/copy.
- **Ports:** Check availability on `0.0.0.0` or `127.0.0.1` and remap Docker or Custom App host ports (with snapshot rollback support for Docker containers). *Note: raw unmanaged host OS processes cannot have their socket rewritten directly — adopt them as a Custom App first.*
- **Cloudflare / Tunnels:** Store a public `https://...` override URL so cards link directly to your exposed domain instead of `:port`.
- **Reverse Proxy:** Generate ready-to-paste snippets for **Caddy**, **Nginx**, **Traefik YAML**, **Traefik Docker Labels**, or **Cloudflare Tunnel**.
- **TLS / SSL:** Probe active HTTPS/TLS endpoints on the service port and monitor certificate expiry.
- **Terminal (`docker exec`):** Run safe read-only diagnostic presets (`ps aux`, `df -h`, `free -m`, `uptime`, `netstat -tuln`, `uname -a`) or custom commands (when Safe Mode is unlocked).
- **Env:** Inspect masked environment keys and reveal unmasked values (Admin confirmation + security audit logged).

### Adding or Adopting Services (**+ Add App**)
- **Custom App:** Register any service by host, port, health check endpoint (`/health`, expected HTTP codes), optional start/stop/update commands, working directory, and log path.
- **From Process / From Docker:** One-click pre-fill from an already-running local process or container.
- **External URL:** Bookmark remote dashboards or LAN appliances (`https://router.local`).
- **Deploy Container:** Launch a new Docker container (`image` tags or `@sha256:` digests, port mappings, volumes, environment variables, restart policy) with sensitive host paths automatically protected.
- **Preflight Collision Check:** Paste a `docker run` command, Compose YAML, or comma-separated port list; if a port collides, click **Use Free :<port>** to auto-remap only the colliding port safely.

---

## 6. Multi-User Access, Audit Logs & Backups

- Open the **User menu → Access & Security** drawer (Admins only) to:
  - Create **Admin** (full control) or **Viewer** (read-only monitoring) accounts.
  - Reset user passwords, update roles, or terminate/delete accounts.
  - Inspect the persistent security **Audit Logs** (with actor, action, timestamp, and target).
- Open **Customize → Backup & Notifications** to:
  - Export your complete configuration (categories, rules, custom apps, saved views, settings) as JSON — sensitive secrets (`token`, `secret`, `password`, `key`) are automatically masked on export and safely preserved on restore.
  - Configure webhook alerts for **Discord**, **Slack**, **Telegram**, **ntfy**, **Gotify**, or generic JSON endpoints.

---

## 7. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + K` / `Cmd + K` | Open Command Palette |
| `?` | Open Keyboard Shortcuts Reference |
| `/` | Jump to Search input |
| `Shift + K` | Toggle Kiosk / Wall Display Mode |
| `g` then `t` | Switch to Table view |
| `g` then `g` | Switch to Grid view |
| `g` then `b` | Switch to Board view |
| `g` then `l` | Switch to List view |
| `Escape` | Close top dialog/drawer/modal |
