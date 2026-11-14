# Portly: Build Prompt

You are a senior full-stack engineer. Build **Portly**, a self-hosted dashboard that automatically discovers every port in use on my machine (localhost processes and Docker containers), shows live system stats, and lets me organize, edit, start, stop, update and read logs of my apps from one place.

Work in the stages listed at the end. After each stage, run the app, run the tests, summarize what works, and wait for my confirmation before continuing. If a requirement is ambiguous, pick the simplest reasonable option, state it in one line, and continue.

---

## 1. Problem and goals

- I run many apps on different ports (dev servers, databases, Docker containers) and cannot remember which is which.
- Portly must detect them **automatically**, keep the list live, and give each a name, category, health status and quick actions.
- It must feel like Homepage / Homarr / Portainer: simple, fast, glanceable, premium dark UI.
- It runs either directly on the host (one command) or in Docker.

## 2. Tech stack (defaults, change only with a reason)

- **Backend:** Python 3.11+ with FastAPI + Uvicorn, `psutil` for processes and system stats, `docker` (docker-py) for the Docker Engine API. (Node + Fastify + `systeminformation` + `dockerode` is an acceptable alternative; do not mix.)
- **Realtime:** Server-Sent Events (`/api/stream`) pushing snapshots and change events. Fallback: polling every 5s.
- **Storage:** SQLite via SQLAlchemy or `sqlite3` (single file `data/portly.db`).
- **Frontend:** Vite + TypeScript + Preact or Svelte, plain CSS with CSS variables (no heavy UI kit). Must build to static files served by the backend.
- **Packaging:** `Dockerfile`, `docker-compose.yml`, and a single-command local run (`make dev` or `python -m portly`). Linux first; macOS and Windows should work for host process discovery.
- **Tests:** `pytest` for backend, Vitest for frontend logic, one Playwright smoke test.

## 3. Architecture

```
portly/
  backend/
    app.py                FastAPI app, routes, SSE
    discovery/
      host.py             listening sockets via psutil (port, proto, bind, pid, process)
      docker_src.py       containers, published ports, labels, stats
      merge.py            unify, de-duplicate, assign stable IDs
    stats.py              CPU, RAM, disk, network, sparkline history (ring buffer)
    actions/
      docker_actions.py   start, stop, restart, recreate, pull, logs, inspect
      process_actions.py  start/stop/restart custom + local apps, log tailing
    health.py             HTTP/TCP checks, history
    categories.py         auto rules engine + manual overrides
    ports.py              port availability checks, "suggest free port", port change
    store.py              SQLite models + migrations
    notifications.py      change detection, event log
  frontend/               UI (see section 8)
  data/                   SQLite db, uploaded icons
  tests/
  Dockerfile  docker-compose.yml  README.md
```

### Stable identity
Every entry has a stable `id` so custom names, categories and order survive restarts:
- Docker: `docker:<container_name>:<container_port>/<proto>` (fall back to compose `project/service`).
- Host process: `host:<process_name>:<port>` (not PID, PIDs change).
- Custom app: `custom:<uuid>`.

### Core data model (SQLite)
`apps(id, source, name, icon, category_id, tags, notes, pinned, hidden, sort_order, url_override, created_at)`
`categories(id, name, color, mode[auto|manual], sort_order)`
`rules(id, category_id, field, operator, value, priority)`
`custom_apps(id, name, host, port, health_path, health_interval, start_cmd, stop_cmd, workdir, log_file, start_on_boot, env_json)`
`views(id, name, filters_json, sort_json, group_by, view_type, columns_json)`
`events(id, ts, type, app_id, message)`
`health_history(app_id, ts, ok, latency_ms)`
`settings(key, value)`

## 4. Discovery (automatic)

**Host:** read listening TCP and UDP sockets (`psutil.net_connections(kind="inet")` filtered to `LISTEN`; on macOS/Windows handle permission errors and fall back to `lsof -iTCP -sTCP:LISTEN -P -n` / `netstat -ano`). Capture: port, protocol, bind address (`127.0.0.1` vs `0.0.0.0` vs `::`), PID, process name, command line, working directory, start time. Resolve per-process CPU % and RSS memory.

**Docker:** connect to `/var/run/docker.sock` (or `DOCKER_HOST`). For every container capture: name, image + tag, state, health, published `host:container/proto` mappings, compose project/service labels, start time, per-container CPU %, memory usage/limit, network and block I/O (use the streaming stats API and cache).

**Merge rules**
- A port published by Docker must not also appear as a raw host process (match `docker-proxy` or port + container mapping).
- If two different apps claim the same host port, mark both `conflict` and create a conflict event.
- Dedupe IPv4/IPv6 duplicates of the same listener.
- Rescan every 3-5s (setting), and immediately on Docker events (`start`, `stop`, `die`, `destroy`) via the Docker events stream.

**Running in Docker:** to see host ports the container needs `network_mode: host` and `pid: host`; mount the Docker socket (read-only by default). Document this in the README and detect when it is missing, showing a clear banner instead of an empty list.

## 5. Features

### 5.1 Stats (single compact line)
One slim strip, **one row, never wrapping** (horizontal scroll if narrow): CPU, Memory, Disk, Network up/down, running containers, listening ports. Each segment: label, big value, one line of context, and a 60px sparkline of the last ~5 minutes. Per-app CPU, RAM and uptime appear in rows/cards. Clicking a segment opens a detail drawer with larger charts.

### 5.2 Views and layout
- **Table, Grid (tiles), List (ultra compact), Board (kanban by category).** Switch instantly; remember the choice.
- Table: sortable columns, show/hide/reorder/resize columns, sticky header, checkboxes, bulk actions, density toggle (Compact / Comfortable).
- **Saved views** as tabs (e.g. "Dev only", "Exposed 0.0.0.0", "Docker") with "Save view".
- **Toolbars are single-line** (view switcher, filter chips, sort, group, columns, density). Overflow scrolls horizontally, it never wraps.

### 5.3 Categories (auto + manual)
- Auto-categorize with a rules engine: image name contains X, port range, process name, compose project, label. Ship defaults: Development, Databases, Monitoring, Automation, Infrastructure, plus Uncategorized.
- Manual categories: create, rename, recolor, reorder, delete.
- Each category is labelled **Auto** or **Manual**. Manually moving an item overrides rules for that item permanently.
- Rules editor with live preview of which apps each rule matches; rules have priority order.

### 5.4 Move, sort, filter, search
- Drag and drop to reorder and to move between categories (grab handle, drop placeholder, keyboard alternative: select, press `M`, choose category).
- Multi-select bulk actions: move to category, add tag, pin, hide, start, stop, restart.
- Sort by port, name, CPU, RAM, uptime, status, category; multi-level sort; manual order.
- Filters: source (Local/Docker), status (Up/Down/Conflict), category, tag, bind address, port range. Saved as views.
- Group by: none, category, source, tag, compose project, status.
- Global search + command palette (`Ctrl/Cmd+K`): find apps/ports and run actions (scan, switch view, open, start, stop, add app).

### 5.5 Change an app's port
From the app detail page and the row menu ("Change port"):
1. User enters a new host port. The backend checks availability (`ports.py`: try to bind, check the socket table, check other containers' mappings) and shows "Port N is free" or the conflicting app. Provide **Suggest free port**.
2. **Docker containers:** Docker cannot change published ports on a running container. Implement as inspect, stop, remove and recreate with the same config (image, env, volumes, networks, labels, restart policy, command) and the new port mapping. Preserve the container name. If the container belongs to a compose project, instead offer to edit the compose file's port mapping and run `docker compose up -d <service>`. Always show a confirmation dialog listing exactly what will happen and the expected downtime. Keep a snapshot of the old config so the user can **roll back**.
3. **Custom/local apps:** stop the app, restart it with the `PORT` env var (and a configurable `{port}` placeholder in the start command), then re-run the health check. If the app was not started by Portly, explain that Portly can only change the port of apps it launched, and offer to adopt it as a custom app.
4. Update stored references (URL, history) and write an event to the change log.

### 5.6 Custom apps
"Add app" dialog with tabs: **Custom app / From Docker / From running process / External URL.**
Fields: name, icon (upload or built-in set), host, port (with free/in-use check and live URL preview), category (Auto-detect or pick), tags, health check path and interval, start command, stop command (default: terminate process), working directory, env vars, log file path, start on boot, pin, notify when down.
Custom apps appear in all views exactly like discovered ones and support the same actions. "From running process" adopts a detected listener and prefills command line and working dir.

### 5.7 App control: check, update, start, stop, logs
All actions are available from the row actions, the bulk bar, the detail page, and the command palette. **Safe mode** is ON by default (read-only); turning it off requires a confirmation. Destructive actions always confirm.
- **Check:** live health (HTTP status + latency or TCP connect), uptime history sparkline, state (Up / Down / Conflict / Unhealthy).
- **Start / Stop / Restart:** Docker via the Engine API; custom/local apps via their configured commands (spawn detached, capture PID, stream output to a log buffer). Show progress and result, never block the UI.
- **Logs:** live tail over SSE/WebSocket (Docker `logs --follow`, custom apps from captured output or `log_file`). UI: filter text, level chips (All / Info / Warn / Error), follow toggle, wrap, download, clear view, timestamps, ANSI color support, 5,000-line client buffer.
- **Update (Docker):** compare local image digest with the registry digest for the tag (cache results, rate-limit). Show "Update available" with current vs latest tag/digest. Actions: **Check now**, **Pull and recreate** (pull image, recreate container with identical config, health check, auto-rollback to the previous image on failure). Per-app update policy: Notify only (default) / Manual / Auto (opt-in, with a schedule).
- **Update (custom apps):** optional "update command" field (e.g. `git pull && npm ci`) run on demand with streamed output.
- Extra: inspect (env, mounts, networks), open a shell (`docker exec`) behind an explicit toggle, kill a local process (confirm, off by default).

### 5.8 Customization
Theme (dark default, light, system), accent color picker, density, corner radius, font size; choose card/column fields (port, source, CPU/RAM, bind, uptime, process); custom name, icon, color, notes, tags per app; pin, hide; column visibility/order/width; collapsible sidebar; refresh interval; default view; import/export all settings and layout as JSON.

### 5.9 Monitoring, history, extras
- Events/notifications (in-app, optional desktop): new port opened, port closed, container stopped, conflict, CPU/RAM over threshold, update available. Timestamped change log ("port 5173 opened by vite").
- **Exposed ports** view highlighting anything bound to `0.0.0.0`.
- Export port list as JSON, CSV or Markdown ("ports cheat sheet"), copy URL/port.
- REST API + CLI (`portly list --docker --json`, `portly start <name>`).
- Docker label autodiscovery: honor labels like `portly.name`, `portly.icon`, `portly.category`, `portly.url`, `portly.hide`.
- Reverse-proxy/custom URL per app, favicon fetch as automatic icon fallback.
- Keyboard shortcuts (`/` search, `g t`/`g b` switch view, `e` edit, `m` move, `?` help).
- Later: multi-host agents, tags-based dashboards, SSO.

Feature ideas deliberately borrowed from similar apps: Docker autodiscovery via labels and built-in service status checks (Homepage, Dashy), drag-and-drop layout and multiple boards (Homarr), live container logs (Dozzle), start/stop/restart/update with real-time progress (Dockge), container management UI (Portainer), uptime history (Uptime Kuma), system stats (Glances, Beszel).

## 6. API (REST + SSE)

```
GET    /api/apps                    unified list (filters, sort, group via query)
GET    /api/apps/{id}               detail, config, history
PATCH  /api/apps/{id}               name, icon, category, tags, notes, pinned, hidden, order
POST   /api/apps/bulk               {ids[], action: move|tag|pin|hide|start|stop|restart}
POST   /api/apps/{id}/start|stop|restart
GET    /api/apps/{id}/logs?follow=1 SSE log stream
POST   /api/apps/{id}/port          {host_port, bind} -> plan; ?apply=1 executes; ?rollback=1
GET    /api/ports/check?port=5433   {free, used_by}
GET    /api/ports/suggest           next free port(s)
POST   /api/apps/{id}/update/check  and /update/apply
POST   /api/custom-apps             create/update/delete custom apps
GET    /api/stats                   current + history
GET    /api/events                  change log
GET/POST /api/categories, /api/rules, /api/views
GET    /api/export  POST /api/import
GET    /api/stream                  SSE: snapshot + change events
```
Return typed errors (`{code, message, hint}`). Validate every input.

## 7. Security (required)
- Desktop mode: bind to `127.0.0.1` by default. Server/NAS mode (section 12) binds to `0.0.0.0` but **requires auth**; refuse to start on any non-loopback address without it.
- Docker socket mounted read-only by default; **Safe mode** blocks every mutating action until disabled.
- No telemetry, no external calls except optional registry checks for image updates (toggle).
- Commands for custom apps run only as the current user, never through unsanitized shell interpolation; store them as argument lists where possible; validate paths.
- CSRF protection on mutating routes; strict CORS; rate-limit action endpoints.
- Log and event content is rendered as text, never as HTML.

## 8. UI and design spec

Premium, minimal, dark-first. Reference designs (provided as a design canvas): Table view, Board view + Customize panel, App detail (logs / update / change port), Add custom app dialog.

**Tokens:** background `#0A0B0F`; surfaces `#101218` / `#151821` / `#1C2030`; hairline border `rgba(255,255,255,.07)`; text `#ECEEF3`; muted `#8D95A5`; accent `#8C9EFF`; success `#5EEAD4`; danger `#FF8A8A`; warning `#FBBF77`. Category colors: Development `#8C9EFF`, Databases `#5EEAD4`, Monitoring `#FBBF77`, Automation `#F5A3D0`, Infrastructure `#B6E36B`, Uncategorized `#8D95A5`. Fonts: Inter (UI), JetBrains Mono (ports, numbers, logs, tabular figures). Controls 34px high, 9px radius, 14px card radius, 8px spacing grid.

**Layout:** left sidebar (Overview, Ports, Docker, System, Conflicts, History, Categories with count + Auto/Manual label, New category, Safe mode switch), top bar (title + live status, search with `Ctrl K`, theme, Export, Add app, Scan now), **one-line stats strip**, saved-view tabs, **one-line toolbar**, content view, floating bulk-action bar.

**Row/card content:** icon, name + process/image, `:port` in mono accent, Local/Docker chip, category chip (+ auto/manual), bind address, status (text + dot, never color alone), CPU bar + value, RAM, uptime, row actions (Start or Stop, Logs, More).

**Detail page:** header with name, chips, status, buttons (Open, Start, Stop, Restart, More); one-line stats strip for that app; tabs (Logs, Ports, Environment, Volumes, Health, Settings); right column cards (Image update, Port mapping editor, Details).

**Quality bar:** responsive (sidebar collapses on narrow screens, tables scroll inside their container), accessible (real buttons, labels, visible focus rings, 4.5:1 contrast, icon buttons have `aria-label`), no layout shift on live updates, empty/loading/error states for everything, no emoji in the UI.

## 9. Acceptance criteria
1. Starting the app shows all listening host ports and Docker containers within 5 seconds, with no configuration.
2. Starting/stopping a container or dev server updates the UI within 5 seconds (Docker events within 1s).
3. A Docker-published port appears once, not twice; two apps on one port show **Conflict**.
4. Renaming, recategorizing, reordering and hiding persist across restarts and container recreation.
5. Stats strip and toolbars never wrap onto a second line at 1100px and up.
6. Changing a container's port recreates it with identical config and a working health check, and rollback restores the old mapping.
7. A custom app can be added, started, stopped, health-checked, and its logs viewed.
8. With Safe mode ON, no endpoint can start, stop, recreate, update or kill anything (verified by tests).
9. Logs stream live, filter by level/text, and download.
10. The README lets a new user run it locally and in Docker in under 5 minutes.

## 10. Stages (stop and report after each)
1. **Discovery + stats API:** host and Docker discovery, merge, stats, SSE, tests, CLI `list`.
2. **UI shell + Table view:** sidebar, one-line stats, toolbar, table, search, live updates.
3. **Persistence + categories:** SQLite, custom names/icons/tags, rules engine, drag-and-drop move, saved views, filters, sort, group.
4. **Other views + customization:** Grid, List, Board, Customize panel, themes, columns, import/export.
5. **Control:** Safe mode, start/stop/restart, logs streaming, health checks, custom apps dialog, port checking and change-port flow with rollback.
6. **Updates + monitoring:** image update checks and apply with rollback, events/notifications, exposed-ports view, REST API docs, polish, Docker packaging and README.
7. **Server / NAS mode:** accounts and roles, correct LAN links, NAS-oriented stats, optional multi-host agents (section 12).

## 11. Ground rules
- Do not add features beyond this spec without asking; do not skip Safe mode or confirmations.
- Keep functions small and typed; add tests for discovery merge, rules engine, port check, and the change-port plan.
- Prefer boring, well-known libraries. No telemetry.
- When finished with a stage, show: what changed, how to run it, how to test it, and known limitations.

## 12. Server / NAS homepage mode

Portly must work as the **start page of a home server or NAS**: open from any phone, laptop or TV on the LAN or VPN, see every app and its stats, and launch each app with one click.

### Deployment
- Ship a `docker-compose.yml` for servers: `network_mode: host`, `pid: host`, `/var/run/docker.sock:/var/run/docker.sock:ro`, `./data:/app/data`, `restart: unless-stopped`, env `PORTLY_MODE=server`, `PORTLY_PORT=7000`.
- Also supply a systemd unit for non-Docker installs.
- Document NAS notes (Synology, QNAP, Unraid, TrueNAS Scale, plain Linux): where the Docker socket lives, extra mounts (`/proc`, `/sys`, `/mnt`) for disk and sensor stats, and any limits when `pid: host` is unavailable (then show Docker apps only, with a clear banner).

### Auth and roles (required in this mode)
- First-run setup creates an **admin** account; passwords hashed (argon2/bcrypt), session cookies (`HttpOnly`, `SameSite`, `Secure` behind HTTPS), login rate limiting.
- Roles: **admin** (all actions), **viewer** (read-only dashboard, no start/stop/edit/logs of sensitive apps). Safe mode still applies to everyone.
- Optional: API tokens for the CLI, and trusted-proxy header auth (Authelia/Authentik/Cloudflare Access) behind an explicit allowlist.
- Optional "guest board": a public, read-only, no-login page showing chosen apps only (off by default).

### Links must work from other devices
- Never emit `localhost` links in server mode. Build each app's Open URL from the host the browser used to reach Portly (or a configured **Public host / base URL**), plus the app's port, unless the app has a **URL override** (reverse-proxy or subdomain URL).
- Show a **Local only** badge on apps bound to `127.0.0.1` because other devices cannot reach them, with a hint to rebind.
- Support `http` and `https` per app, and trust `X-Forwarded-*` headers only from configured proxies.

### NAS-oriented stats
- Per-disk and per-mount usage, pool/array health where available (ZFS, mdadm/RAID, btrfs), SMART status and temperatures (optional, via `smartctl` or `/sys/class/hwmon`), per-core CPU, load average, swap, per-interface network, uptime.
- Alerts for low disk space, degraded array, high temperature (thresholds in settings).
- All stats keep the **one-line strip** layout; extra detail lives in the System page.

### Start-page features
- Serve at `/` so it can be set as the browser home page; installable as a PWA; mobile layout.
- Optional bookmarks section for non-detected links (router, NAS admin UI, external sites), custom title/logo/background, and a **wall display / kiosk mode** (large type, auto-refresh, no controls).
- Optional **multi-host**: a lightweight read-only agent (`portly --agent --token ...`) lets one dashboard show several servers, with a host selector in the sidebar.

### Acceptance criteria (server mode)
1. From another device on the LAN, `http://<server>:7000` shows the login page, then the full app list.
2. Every Open link works from that device (no `localhost` URLs); loopback-only apps show **Local only**.
3. A viewer account cannot start, stop, recreate, update or edit anything (tests prove it).
4. The server refuses to start on `0.0.0.0` with auth disabled.
5. After a server reboot Portly comes back automatically and keeps all names, categories, layout and settings.
