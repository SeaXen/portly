# Portly — Review & Fix Plan (agent-ready)

> **Audience:** an AI coding agent (or developer) that will fix Portly.
> **Source reviewed:** `portly-main.zip` (Python/FastAPI backend, React 19 + Vite frontend, SQLite, Docker SDK).
> **How to use this file:** work top to bottom. Every item has an ID, location, evidence, fix, and an acceptance test. Do not skip the "Rules for the agent" section.

---

## 0. Verdict

**Portly is not 10/10 yet.** The foundation is good (safe mode by default, loopback by default, parameterized SQL, a path-traversal guard on static files, SSRF guards on the icon fetcher, ~147 tests, a rename-then-recreate rollback idea). But there are blockers that stop the default Docker setup from working, leave the web UI without a login screen, and leak secrets to unauthenticated users. There are also several features that look finished in the UI but are stubs or show fake data.

| Area | Score (approx.) | Main reason |
|---|---|---|
| Backend logic correctness | 6/10 | Fake/never-updated metrics, stub features, weak conflict detection |
| Security (if exposed beyond localhost) | 4/10 | Unauthenticated read endpoints leak env vars; safe-mode exec bypass; no login rate limit; CSRF/DNS-rebinding exposure |
| Docker / deployment readiness | 3/10 | Default `docker-compose.yml` exits on first run; non-root user cannot use `docker.sock` |
| Data accuracy (telemetry) | 4/10 | Container CPU/RAM never collected; host CPU always 0; synthetic sparkline points |
| Frontend functionality | 6/10 | No login/setup UI; saved views broken; stale Docker banner |
| Design / UX polish | 6–7/10 | Strong visual system on paper; native `alert()`s, no dialog semantics, external fonts |
| Accessibility | 5/10 | WCAG AA is claimed in `PRODUCT.md` but modals have no `role="dialog"`, no focus trap |
| Tests / CI | 6/10 | Many tests, but mock-heavy; no frontend tests; "Lint" job does not lint |
| Docs accuracy | 5/10 | README/PRODUCT claim UDP, 110 tests, "guarded endpoints" — not matching code |

**Overall: roughly 5–6 / 10 — a strong prototype, not yet production-grade.** Fixing Phase 1 and Phase 2 below would move it to roughly 8/10.

### Limits of this review (be honest with yourself about these)
- **Static review only.** Python dependencies were not installable in the review sandbox, so the app and the test suite were **not run**. Items are tagged:
  - **[Verified]** — confirmed by reading the exact code path and, where noted, by a small dependency-free script.
  - **[Verify first]** — strongly suspected from code and library behavior, but must be reproduced against a real Docker daemon / browser before fixing.
- **Read fully:** all of `portly/backend/**`, `cli.py`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `App.tsx`, `api.ts`, `sw.js`, `index.html`, `PRODUCT.md`, CI/deploy docs (partly).
- **Only scanned (grep-level):** `frontend/src/components/*.tsx` (~6,000 lines), CSS files, test contents, `reference/design/*`. A second pass on these is recommended (see Phase 5).
- Visual design was judged from code and `PRODUCT.md`/`DESIGN.md`, not from rendered screenshots.

---

## 1. Rules for the agent

1. **Reproduce before fixing** anything tagged *[Verify first]*. If it does not reproduce, note that in the PR and move on.
2. **One item = one commit/PR**, referencing its ID (e.g. `P0-3`). Add or update a test in the same commit.
3. **Never weaken Safe Mode.** It must stay ON by default and gate every mutating action server-side (the UI check is cosmetic only).
4. **Keep API and UI in sync.** When changing a response shape, update `portly/frontend/src/api.ts`, `types.ts`, `docs/API.md`, and tests together.
5. **No new runtime network dependencies** (fonts, CDNs, analytics). `PRODUCT.md` principle 4 says local-first.
6. **Commands to run before every commit**
   ```bash
   pip install -r requirements.txt
   PORTLY_TESTING=1 python -m pytest tests -q --ignore=tests/e2e
   cd portly/frontend && npm ci && npx tsc --noEmit && npm run build
   ```
7. If a fix needs a decision that is not in this file, choose the **safer** option and write the decision in `CHANGELOG.md`.

---

## 2. Phase 1 — P0 blockers (fix first, in this order)

### P0-1 · Default Docker Compose exits on first run  **[Verified]**
- **Where:** `docker-compose.yml:19` (`PORTLY_MODE=desktop`, `PORTLY_HOST=0.0.0.0`, `PORTLY_ALLOW_INSECURE_BIND=false`), `portly/cli.py:44-49`, `Dockerfile` CMD.
- **Problem:** `cli.py` refuses to bind `0.0.0.0` when `mode != "server"` and there are no users. A fresh `docker compose up` therefore prints `SECURITY ERROR…` and restart-loops. `docs/DEPLOYMENT.md` uses `PORTLY_MODE=server`, so the two files disagree.
- **Fix:**
  1. Set `PORTLY_MODE=server` in the root `docker-compose.yml` and in the Dockerfile `ENV`; pass `--mode` explicitly in `CMD`.
  2. Make the first-run experience work end to end together with **P0-2** (setup screen) and **S-3** (setup token).
  3. Keep one source of truth: generate the compose example in `docs/DEPLOYMENT.md` from the root file (or link to it).
- **Acceptance:** with an empty `./data`, `docker compose up -d` stays running, `GET /` serves the UI, and the UI shows the *Create admin* screen.

### P0-2 · The web UI has no login or setup screen  **[Verified]**
- **Where:** `frontend/src/api.ts:251-271` defines `getAuthMe`, `login`, `setupAdmin`, `logout`; **nothing in `App.tsx` or `components/` calls them** (grep for `password`, `getAuthMe`, `api.login` finds no UI usage).
- **Problem:** in server mode every mutation returns `403 SETUP_REQUIRED` and the user cannot create an account from the browser. After an account exists, a logged-out browser gets `401` on `/api/stream` and the app silently shows nothing (`loadInitialData` only does `console.error`).
- **Fix:**
  1. Add `AuthGate` around `<App/>`: call `getAuthMe()` on boot → `needs_setup` ⇒ `SetupScreen`; unauthenticated ⇒ `LoginScreen`; else render the app.
  2. In `api.ts` `request()`: on `401` dispatch a global `portly:unauthorized` event → AuthGate shows `LoginScreen` and stops SSE/polling.
  3. Add logout + current user/role in `Sidebar`/`TopBar`. Hide or disable mutating controls for `viewer`.
  4. Password rules: min 10 chars, show strength hint, confirm field. Autofocus, `autocomplete="username|current-password|new-password"`, Enter to submit, inline error text with `aria-live="polite"`.
- **Acceptance (Playwright):** fresh data dir → setup → lands in app; reload stays logged in; logout → login screen; wrong password shows an error; 401 mid-session returns to login.

### P0-3 · Unauthenticated endpoints leak secrets  **[Verified]**
- **Where (no auth dependency):** `app.py` — `GET /api/apps` (336), `GET /api/apps/{id}` (594), `…/proxy-config` (424), `…/favicon` (476), `…/tls` (503), `…/compose` (~575), `GET /api/custom-apps` (963), `/api/categories` (1035), `/api/rules` (1062), `/api/views` (1082), `/api/stats` (1014), `/api/ports/check|suggest`, `…/update/check`.
- **What leaks:**
  - `GET /api/apps/{id}` returns `docker_inspect.env` (container environment: DB passwords, API keys) from `docker_actions.inspect_container` (`docker_actions.py:67`).
  - `GET /api/custom-apps`, `GET /api/apps` and the SSE stream include each custom app's `env`, `start_cmd`, `workdir` (`merge.py:~60`), and Docker `labels`.
  - `…/compose` returns the compose file contents.
  - `GET /api/apps/{id}` also **writes** to the DB and probes the network on every call.
- **README claims** "Guarded System Endpoints … require authentication when users exist" — currently only some do.
- **Fix:**
  1. Apply a router-level dependency `Depends(require_auth)` to everything under `/api` **except** `/api/auth/setup`, `/api/auth/login`, `/api/auth/me`, and a new minimal `/api/health` (use it for the Docker `HEALTHCHECK` instead of `/api/stats`).
  2. Keep "no users yet + loopback" convenience only for desktop mode (already in `get_current_user`).
  3. **Redact by role:** for non-admins strip `env`, `start_cmd`, `stop_cmd`, `update_cmd`, `workdir`, `labels`, compose content, and mask values in `docker_inspect.env` (show keys only; admin gets a "reveal" action that is audit-logged).
  4. Remove `env`/`labels`/`start_cmd` from list payloads (`/api/apps`, SSE) for everyone; fetch them only in the detail call.
  5. `GET /api/apps/{id}` must not write; move health recording to the background poller (see P1-4).
- **Acceptance:** parametrized test enumerates `app.routes`; with a user created and no session, every route except the allow-list returns 401; a `viewer` never receives `env` values; SSE payload contains no `env`.

### P0-4 · Safe-mode `exec` can be bypassed  **[Verified by script]**
- **Where:** `docker_actions.py:446-475` (`SAFE_COMMAND_BINARIES`, `FORBIDDEN_OPERATORS`, `_validate_safe_command`).
- **Problem:** the denylist approach allows `env sh -c 'id'`, `env python3 -c '…'` (`env` runs programs), `cat /etc/shadow`, `printenv` (dumps secrets), `ip link set eth0 down` (mutates), `ls & id`. All passed validation in a test script. `top`/`tail -f` hang until timeout.
- **Fix:** replace with an **argv allowlist**:
  - Parse with `shlex.split`; execute the list form (never a shell string).
  - Allow only exact patterns, e.g. `ps`, `df -h`, `free -m`, `uptime`, `uname -a`, `whoami`, `id`, `date`, `hostname`, `ss -tlnp`, `ip addr show`, `ip route show`, `ls <path>` limited flags, `tail -n <≤1000> <file>` for files under configured log dirs.
  - Remove `env`, `printenv`, `cat`, `head`, `top`, `ifconfig`, bare `ip`.
  - Reject any argument containing newlines or NUL.
  - Enforce `timeout` server-side (clamp 1–30 s, see P1-25), cap output at ~256 KB, and write an audit event with the user.
- **Acceptance:** unit tests assert each bypass above is rejected while the allowed commands work; fuzz test with random shell metacharacters.

### P0-5 · Port change can leave the service down, and silently drops container config  **[Verified from code / Verify first on real Docker]**
- **Where:** `docker_actions.py:122-245` (`apply_port_change_docker`), `247-375` (multi), `377-445` (`rollback_port_change_docker`).
- **Problem A — failed recreate is not restored.** `client.containers.run()` = create + start. When start fails (the most common reason: port already taken), the *created* container keeps the name `container_name`. The `except` block then calls `container.rename(container_name)` which fails with a name conflict (error swallowed or logged as "Critical"), leaving the original stopped under `…_portly_bak_<ts>`. That is exactly the case the "safe rollback" promise should cover.
- **Problem B — config is lost.** Only image/env/cmd/entrypoint/labels/user/workdir/restart-policy/ports/binds are copied. These are **dropped**: `network_mode` (host/custom), `privileged`, `cap_add/cap_drop`, `devices`, memory/CPU limits, healthcheck, `extra_hosts`, `dns`, `sysctls`, `tmpfs`, `log_config`, `hostname`, `ipc/pid` mode, `security_opt`, `group_add`, network aliases / static IPs. A recreated container can silently become less/more privileged or lose networking.
- **Problem C — no post-start verification.** The plan text promises "Wait for container start and verify health" (`ports.py:~156`) but nothing does it.
- **Problem D — rollback keys.** Snapshots are stored under `docker:<name>:<cport>` or `docker:<name>:multi`; rollback parses `parts[2]`; make sure the UI passes the matching id (see test below). Snapshot is saved *before* the attempt, so a failed attempt leaves a stale snapshot.
- **Fix:**
  1. Build the new container with the low-level API (`client.api.create_container(**cfg, host_config=orig_host_config_with_new_PortBindings, networking_config=…)`) so the **entire** original `HostConfig` is preserved; only `PortBindings` changes. (Mind `network_mode: host` — port bindings are ignored there; the plan should refuse with a clear message.)
  2. On any failure after create: `new.remove(force=True)` **first**, then rename the original back and start it; assert the original is running before returning the error.
  3. After start: poll up to ~15 s for `State.Running`, `Health.Status != unhealthy`, and a TCP connect to the new host port; if it fails → automatic rollback + error.
  4. Save the snapshot only after the new container is verified; keep exactly one backup `…_portly_bak_` and remove it after success.
  5. Update the plan `steps` text in `ports.py` to match what really happens (rename → create → verify → remove backup).
- **Acceptance (integration, real Docker or an in-memory fake that mimics create/start/rename/remove):**
  - start failure ⇒ original container is running again under its original name, no leftover `created` container;
  - `privileged`, `NetworkMode`, `CapAdd`, `Devices`, `Memory`, `Healthcheck` survive the change;
  - rollback via the UI id works for both single and multi-port changes.

### P0-6 · Stopped containers probably vanish from the dashboard  **[Verify first]**
- **Where:** `discovery/docker_src.py:174` (`if not host_mappings: continue`) with ports read from `NetworkSettings.Ports`.
- **Problem:** for stopped (exited) containers Docker reports `NetworkSettings.Ports` as empty; the published ports remain in `HostConfig.PortBindings`. If so, a container disappears the moment it stops, so **Start** can never be clicked, `portly start <name>` cannot find it, `status: "down"` branches never run, and `detect_changes` reports "port closed" instead of a container state change. Containers without published ports are never listed at all.
- **Fix:** read `HostConfig.PortBindings` when `NetworkSettings.Ports` is empty; list containers with no published ports as an entry with `port: 0` and a "no published ports" badge so they can be started/stopped/logged. Ensure every consumer handles `port == 0`.
- **Acceptance:** integration test with a stopped container shows `status: "down"`, Start works; test with a container with no ports.

### P0-7 · Stored XSS through SVG favicons  **[Verified from code]**
- **Where:** `favicon.py:89-120` (`fetch_favicon_from_url`), `app.py:476-500` (serves bytes with the detected `image/svg+xml`).
- **Problem:** any local service can return an SVG containing `<script>`. Portly serves it from its own origin; opening `/api/apps/<id>/favicon` directly executes it with Portly's origin and cookies.
- **Fix:** send `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`, `X-Content-Type-Options: nosniff` on that endpoint; ideally rasterize or strip scripts/`on*` attributes/`foreignObject` from SVGs, or refuse SVG from probes. Also: do not follow redirects blindly (custom opener that re-validates each hop), pin the resolved IP (DNS-rebinding), and cache `.jpg/.gif` properly (`get_cached_icon` only looks up `.ico/.png/.svg/.webp`, so JPEG/GIF are re-fetched every time).
- **Acceptance:** test that an SVG with `<script>` is served with the CSP header (or sanitized); redirect to `169.254.169.254` is blocked.

### P0-8 · Docker image runs as non-root but needs `docker.sock` and host `/proc`  **[Verify first]**
- **Where:** `Dockerfile:41` (`USER portly`), `docker-compose.yml`.
- **Problem:** `/var/run/docker.sock` is normally `root:docker 660`; a non-root user inside the container usually cannot connect → "Docker daemon not reachable". With `pid: host`, a non-root user cannot read other users' `/proc/<pid>/fd`, so `psutil` returns no PIDs and every host listener becomes `System Listener`. `./data` bind mounts also hit UID mismatches. The `:ro` on the socket gives a false sense of safety (it does not restrict API calls). The systemd example in `DEPLOYMENT.md` uses `User=root`, which is inconsistent.
- **Fix:** choose and document one of: (a) run as root in the host-mode image (document the trade-off), or (b) `group_add: ["${DOCKER_GID}"]` + `cap_add: [SYS_PTRACE]` (and `cap_add: [DAC_READ_SEARCH]` if needed) with an entrypoint that `chown`s `/app/data`. Recommend a **docker-socket-proxy** for hardened setups. Remove `:ro` claims. Mount host `/` read-only (e.g. `/hostfs`) and compute disk usage from it so the Disk card reflects the host rather than the container overlay (`stats.py:~85`).
- **Acceptance:** on a clean Linux host, `docker compose up` shows containers and real process names for host listeners; disk numbers match `df -h /` on the host.

---

## 3. Phase 2 — P1 logic and data correctness

### P1-1 · Fabricated sparkline data  **[Verified]** — `stats.py:140-155`
When fewer than 5 samples exist, the code invents a ramp (`base_cpu-2, +1, -1, base`, `net*0.8, 1.1, 0.9`) and shows it as real telemetry.
**Fix:** return only real samples; the frontend renders a flat "collecting…" placeholder when `<2` points. Also sample on a **fixed cadence** from a dedicated task (`collect_snapshot` is currently called from `refresh_discovery`, which is also triggered by Docker events/patches, so spacing is irregular and net rate can spike) so 60 points really equal the documented ~5 minutes.

### P1-2 · Container CPU/RAM/network never collected  **[Verified]** — `docker_src.py:117`
`update_container_stats_cache` has no callers, so every Docker app shows 0 CPU / 0 RAM.
**Fix:** a background collector: for running containers use `container.stats(stream=False)` in a bounded thread pool (or one streaming thread per container), compute CPU% from `cpu_stats`/`precpu_stats` deltas, memory = usage − cache, clear entries for removed/stopped containers.

### P1-3 · Host process CPU% is always 0  **[Verified from code; standard psutil behavior]** — `host.py:48`
A **new** `psutil.Process` is created each scan and the cache is cleared every 3 s; `cpu_percent(interval=None)` on a fresh object returns `0.0`.
**Fix:** keep a `dict[pid] → psutil.Process` across scans (validate `create_time` to avoid PID reuse), prime once, read each scan, drop dead PIDs. Document whether the number is per-core or normalized.

### P1-4 · Custom apps are always "up"; health is not polled  **[Verified]** — `merge.py:56`, `app.py:604`
`status` is hard-coded `"up"` ("health checker updates this" — nothing does). `health_interval` is stored but unused. `check_app_health` only runs when someone opens the detail view.
**Fix:** background health poller honoring each app's `health_interval` (staggered, bounded concurrency, non-blocking), stores last result, drives `status` (`up|degraded|down`), records history, and emits events with debounce. Show PID/uptime/CPU/RAM for processes Portly started.

### P1-5 · Health check masks HTTP failures  **[Verified]** — `health.py:47-70`
If `health_path` is configured and returns 5xx or times out, the code falls through to a TCP check and reports `up` with a fabricated `code: 200`. Also inconsistent success rules (`<400` for normal responses vs `<500` for `HTTPError`).
**Fix:** if `health_path` is set, the HTTP result decides; report the real status code; add `degraded` (TCP ok, HTTP failing); TCP-only only when no path is configured.

### P1-6 · "Update check/apply" are stubs  **[Verified]** — `docker_actions.py:101-120`, `app.py:882-886`
`check_image_update` always returns `has_update: False, "Image is up to date"`; `apply` returns `"Image is latest."` without doing anything. Users are told their images are current.
**Fix:** implement (compare local `RepoDigests` with `client.images.get_registry_data(tag).id`, then pull + recreate via the P0-5 helper with automatic rollback), **or** hide the buttons and return `501 Not Implemented` until done. `update/check` must require auth.

### P1-7 · "Open" links always point to `localhost`  **[Verified]** — `merge.py:147`
`("localhost" if bind == "127.0.0.1" else "localhost")` — both branches identical. In NAS/server mode the browser opens the *viewer's* localhost. Scheme is always `http`.
**Fix:** build links in the frontend from `window.location.hostname` unless `public_host` or `url_override` is set; choose `https` for known TLS ports or after a TLS probe. Add an explicit `has_custom_url` boolean — `TableView.tsx:214` and `GridView.tsx:76` currently infer "tunnel URL" from `!open_url.includes('localhost')`, which breaks once links are fixed.

### P1-8 · Conflict detection is weaker than advertised  **[Verified]** — `merge.py:25-37`
Host listeners on a port that Docker also publishes are removed **before** conflicts are computed, so host-vs-Docker collisions are never reported; a stopped container's mapping can hide a running host process.
**Fix:** compute conflicts on the unfiltered set; only suppress host rows that belong to the container's `docker-proxy`/ proxy PID; compare binds with `ipaddress` (wildcard vs specific, v4/v6) and include protocol.

### P1-9 · Blocking Docker/process calls inside `async def` handlers  **[Verified]**
Calls such as `docker_actions.start_container/stop_container(timeout=10)/restart_container`, `bulk_action`, `apply_port_change_docker`, `prune`, `manage_compose_stack`, `deploy_container` (image pull can take minutes), `check_update_endpoint`, `process_actions.restart_custom_app` (`time.sleep`), and `is_docker_available()` inside `get_apps` run **directly on the event loop** (`app.py:636-960`). Everything — SSE, UI — freezes while they run.
**Fix:** wrap in `await asyncio.to_thread(...)` or declare these handlers as plain `def` (FastAPI runs them in the threadpool). Add a test where a fake slow Docker call must not delay `/api/health`.

### P1-10 · Safe log-path check blocks real logs, allows sensitive files  **[Verified by script]** — `process_actions.py:36-100`
Results: `/var/log/myapp/app.log` → **blocked**; `/home/me/samples/app.log` → **blocked** (substring `/sam`); `/home/me/projects/samba-tool/out.log` → **blocked**; `/home/me/.bash_history` → **allowed**.
**Fix:** switch from a denylist to an **allowlist of roots** (setting `PORTLY_LOG_DIRS`; defaults: `<data>/logs`, the app's `workdir`, `/var/log`), `realpath` + symlink resolution, regular files only, size cap, and read the tail with `seek` instead of `readlines()` (`get_custom_app_logs` loads the whole file into memory).

### P1-11 · Custom-app process lifecycle is fragile — `process_actions.py:137-260`, `app.py:991`
- `start_on_boot` starts the app **when you save it**, not when Portly boots; `lifespan` never starts anything.
- Processes are tracked only in memory: after Portly restarts, **Stop reports success but the process keeps running**, and Start can launch a duplicate.
- Stop escalates only to `terminate()`; children ignoring SIGTERM survive; `stop_cmd` runs without `cwd`/`env`; log buffer keeps stale lines from earlier runs; no reaping.
- **Fix:** start with `start_new_session=True`, persist `pid` + `create_time` (re-adopt on boot), kill the process group (SIGTERM → wait → SIGKILL), run `stop_cmd` with the app's cwd/env and a timeout that also kills its children, clear the log buffer on start, implement real `start_on_boot` in `lifespan`.

### P1-12 · `portly.hide` label is ignored once any override exists  **[Verified from code]** — `merge.py:123`
`override.get("hidden", item.get("hidden_by_label"))` never falls back because override rows always contain `hidden` (0 by default). **Fix:** treat `None`/missing as "no override"; store a tri-state or only store explicitly set fields. Same pattern for `pinned`.

### P1-13 · Host app ids are not unique or stable — `host.py:194`
`host:{process_name}:{port}` collides for multiple listeners (nginx/gunicorn workers share a socket, same process on two IPs) and `seen_ids` in `merge.py` silently drops all but the first (possibly a worker, so "Stop" kills the wrong PID). **Fix:** collapse to the parent/lowest PID per `(port, proto)`, include bind or exe path when needed, and keep overrides stable across restarts.

### P1-14 · README says TCP **and UDP**; code is TCP only — `host.py`, `ports.py`
Discovery uses `status == LISTEN` and `proto: "tcp"`; availability checks bind only TCP. **Fix:** add UDP (psutil UDP sockets have no LISTEN state) or correct the docs.

### P1-15 · Saved views are mostly non-functional — `App.tsx:303-325`
`handleSelectView` hard-codes only `all/dev/exposed/docker`; user-created views (`v_…`) change `activeViewId` and nothing else; saved filter keys (`category`) don't match the backend defaults (`category_id`, `bind`). **Fix:** apply `view.filters/sort/group_by/view_type` generically; one shared filter schema used by UI and API.

### P1-16 · Docker-unavailable banner never updates — `App.tsx:43,255`
`dockerAvailable` is set only at initial load; SSE messages don't carry `docker_status`. **Fix:** include `docker_status` in SSE/`/api/stats`, update state, auto-hide when Docker returns.

### P1-17 · Safe-mode toggle has no error handling — `App.tsx:284`
State flips locally before the request; on failure (401/403/network) the UI shows "unlocked" while the server is locked. **Fix:** `try/catch`, revert on failure, re-sync from server, show toast. Consider an **auto re-lock timer** (see F-10).

### P1-18 · Port availability check pitfalls — `ports.py:24-60`
- Non-root bind attempts on ports < 1024 report "not free" (permission denied) although the port is free.
- `SO_REUSEADDR` on Windows allows binding an in-use port ⇒ false "free".
- IPv6 binds with an `AF_INET` socket fail; `bind` strings are not validated (DNS lookup possible).
- Docker claims are looked up with a full `containers.list` per check (slow) — cache within a scan.
- **Fix:** validate `bind` with `ipaddress`, distinguish `EACCES` from `EADDRINUSE`, choose `AF_INET6` when needed, skip `SO_REUSEADDR` on Windows (`SO_EXCLUSIVEADDRUSE`), add UDP.

### P1-19 · Webhook payloads likely broken for some providers  **[Verify first]** — `notifications.py:31-88`
- **Telegram:** payload has no `chat_id`; `parse_mode: Markdown` with unescaped text can fail.
- **ntfy:** JSON body POSTed to a topic URL is delivered as the raw JSON text; ntfy expects plain text body + headers (headers are already set) or JSON to the server root with a `topic` field.
- No retry/backoff/cooldown ⇒ flapping ports spam channels; `_previous_ports` is keyed by port only, so two apps on one port collapse.
- **Fix:** per-provider tests against recorded request shapes, retry with backoff, per-event cooldown, key state by app id.

### P1-20 · Import/export & settings are unsafe — `app.py:1115,1160,1201`
- `/api/import` has no schema (`KeyError` ⇒ 500 after a **partial** import), can overwrite `safe_mode`, and imports `start_cmd`s.
- `/api/export` is available to any logged-in user (viewers) and includes `custom_apps[].env` and the raw `webhook_url`.
- `PATCH /api/settings` accepts arbitrary keys/values.
- **Fix:** Pydantic models, single DB transaction, size limit, settings **allowlist with types/ranges** (`refresh_interval` 1–60, etc.), export admin-only with secrets masked unless explicitly requested, import preview/dry-run.

### P1-21 · Bulk action hides failures — `app.py:636-680`
Errors are swallowed and the response is always `count = len(ids)`. **Fix:** return `{succeeded:[…], failed:[{id,error}]}`; UI shows per-item results.

### P1-22 · Destructive operations lack guards — `docker_actions.py:725-808`
`prune` removes stopped containers **and unused volumes** (permanent data loss) with only the safe-mode gate; compose `down` is destructive; compose actions return `ok` even when every container failed. **Fix:** separate options (images / containers / volumes), preview ("will delete N items, X MB"), typed confirmation for volumes and `down`, honest per-container results, never prune the volumes by default.

### P1-23 · Exec timeouts not enforced — `app.py:530-575`
`asyncio.wait_for` cancels the waiter but the thread/exec keeps running inside the container; `timeout` is user-controlled (negative/huge). **Fix:** clamp to 1–30 s, enforce inside the container (`timeout` binary / exec inspect + kill), cap output size.

### P1-24 · Regex category rules can freeze the server — `categories.py:55-60`
User-supplied regex runs on every app every scan (default 3 s). **Fix:** validate/compile on save, limit pattern length, use the `regex` module with a timeout, or drop regex support. Also prevent deleting the `uncategorized` category and handle rules pointing at deleted categories (`store.py:delete_category`).

### P1-25 · Docker events are not debounced — `docker_src.py:60-80`, `app.py:197`
Each `start/stop/die/create` triggers an immediate full rescan; `compose up` of 20 services ⇒ 20+ scans. **Fix:** coalesce events for ~500 ms; one scan per burst.

---

## 4. Phase 3 — Security hardening (P2)

| ID | Item | Where | Fix |
|---|---|---|---|
| S-1 | No login rate limiting; user enumeration by timing | `app.py:1244` | Per-IP + per-user throttle with backoff/lockout; compare against a dummy bcrypt hash when the user doesn't exist; same error text |
| S-2 | Sessions stored in plaintext; never pruned; cookie lacks `Secure`; token also returned in JSON | `store.py` (sessions), `auth.py`, `app.py:1239` | Store `sha256(token)`; call `prune_expired_sessions()` (currently never called); `Secure` when HTTPS/`X-Forwarded-Proto`; `SameSite=Strict` for the app cookie; stop returning the token unless requested; "log out everywhere" |
| S-3 | First-run setup race: anyone who can reach the port can claim admin | `app.py:1233` | Require a **one-time setup token** printed at startup (or `PORTLY_SETUP_TOKEN`) when not on loopback; fixed user id `u_admin` → generate ids |
| S-4 | CSRF and DNS-rebinding on localhost deployments | `app.py:70-90`, `get_current_user` | In desktop mode with no users, loopback requests are admin. Add: `TrustedHostMiddleware` / Host allow-list, `Origin` check on all non-GET requests, and require a custom header (e.g. `X-Portly-Client`) on mutating requests. Body-less POSTs (`/api/apps/{id}/stop`, `/api/docker/prune`, `/api/scan`) are "simple" cross-site requests |
| S-5 | Missing security headers | middleware | `Content-Security-Policy` (self only + inline styles you need), `frame-ancestors 'none'`/`X-Frame-Options: DENY` (clickjacking of a control panel), `X-Content-Type-Options`, `Referrer-Policy: no-referrer` |
| S-6 | Secrets at rest | `store.py`, DB | Restrict DB/data dir to `0600/0700`; mask `webhook_url` and `env` values in API; optional encryption key for secrets |
| S-7 | TLS inspector uses a private CPython API | `tls_inspector.py:67` (`ssl._ssl._test_decode_cert`) | Parse DER from `getpeercert(binary_form=True)` with `cryptography.x509`; send SNI; handle STARTTLS-less non-TLS ports quietly |
| S-8 | SSRF surface in health/webhook/favicon | `health.py`, `notifications.py`, `favicon.py` | Disable redirects or re-validate each hop; resolve once and connect to the resolved IP; keep link-local blocked |
| S-9 | No audit trail of who did what | `store.log_event` | Add `actor` to events for every mutation and exec; Audit view in UI |
| S-10 | Host process kill is thin | `process_actions.py:25,270-297` | Add `sshd`, `dockerd`, `containerd`, `portly` to protected names; verify cached `create_time` before killing (PID reuse); wait + escalate; confirmation step |
| S-11 | `deploy_container` accepts anything | `docker_actions.py:810-865`, `app.py:937` | Validate image/name regex, port range, env size; warn/deny binds of `/`, `/var/run/docker.sock`, `--privileged`-like options unless explicitly allowed; stream pull progress |
| S-12 | Frontend passes unencoded params | `api.ts` `checkPort`, `suggestPorts` | `encodeURIComponent` / `URLSearchParams` |

---

## 5. Phase 4 — Robustness & maintainability

- **R-1 SQLite:** a new connection + 3 PRAGMAs per call (`store.py:_get_connection`), many calls per request. Use a thread-local connection, `PRAGMA busy_timeout`, add indexes (`health_history(app_id, id)`, `events(ts)`), and **schema versioning** with `PRAGMA user_version` + ordered migrations (currently only `CREATE TABLE IF NOT EXISTS`; any column change will break upgrades). Two `Store()` instances exist (`app.py` and `auth._get_store`); share one.
- **R-2 SSE:** unbounded `asyncio.Queue` per client (slow clients grow memory); full app list (with labels/env today) sent every tick. Use `maxsize` + drop-oldest, send only changes or a trimmed payload, include `docker_status`, set `retry:`.
- **R-3 Dead/duplicated code:** triple `store.get_app()` (`app.py:431-436`, `507-512`); `asyncio.get_event_loop()` (`app.py:164,206`) → `get_running_loop()`; `prune_expired_sessions` unused; `follow` log param accepted but ignored; `get_container_logs(follow=True)` unused.
- **R-4 Docker client:** `get_docker_client()` has no lock (races in threads); `from_env(timeout=3)` retried every 4 s from request handlers (blocks the loop when `DOCKER_HOST` is remote).
- **R-5 Image/runtime:** `requirements.txt` includes pytest/httpx (dev) in the runtime image; `RUN npm ci || npm install` hides lockfile problems (`Dockerfile:5`); the Unix fallback uses `lsof` but the image installs only `net-tools`/`procps` (`netstat -ano -p tcp` is a Windows syntax). Pin Python deps (lock file), drop `python-multipart` if unused.
- **R-6 Repo hygiene:** `portly/frontend/dist/**` is committed (and required by `pyproject` package-data) — build it in the release workflow instead; remove `.impeccable/`, `docs/superpowers/`, `Portly-build-prompt.md`, `reference/` from release artifacts or move to `/docs/internal`; three CI files (GitHub, GitLab, Forgejo) — keep one canonical and test the same steps.
- **R-7 Docs:** `PRODUCT.md` says "110 tests" (there are ~147); README says UDP, "guarded endpoints", "WCAG 2.1 AA" — make them true or reword. Add `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`.

---

## 6. Phase 5 — Design, UX and accessibility polish

| ID | Item | Evidence | Fix |
|---|---|---|---|
| D-1 | Native `alert()`/`confirm()` | 15 `alert(` and 3 `confirm(` in `components/*`, `App.tsx` | Toast system (success/error/info, `aria-live`) + a reusable `ConfirmDialog` with typed confirmation for destructive actions (prune, down, kill, port change). Map error codes (`SAFE_MODE` → "Unlock Safe Mode" button) |
| D-2 | Modals lack dialog semantics | 0 occurrences of `role="dialog"`/`aria-modal`; no focus trap/return | Use `<dialog>` or a headless dialog; trap focus, restore focus, label with `aria-labelledby`; same for drawers/command palette. **Run axe** in Playwright; until then do not claim WCAG AA |
| D-3 | Mega components | `AppDetailModal.tsx` 1,565 lines, `AddAppModal.tsx` 868 | Split by tab/step into small components + hooks; lazy-load (`React.lazy`) — the single JS bundle is ~392 KB |
| D-4 | No loading/error/empty states | `App.tsx:242-266` only `console.error` | Skeleton rows, error banner with Retry, empty states ("No ports match"), "Live / Reconnecting…" pill tied to SSE state, stale-data indicator |
| D-5 | External Google Fonts | `index.html:15-17` | Self-host Inter + JetBrains Mono (e.g. `@fontsource`), `font-display: swap`, system fallbacks. Contradicts local-first principle and breaks offline/PWA |
| D-6 | Shortcuts | `App.tsx:110-112` | `Ctrl/⌘+K` is ignored while an input has focus (the `isInput` early return happens before the check); `/` focuses the first `input[type=text]` on the page — give the search box a ref/id; document shortcuts in the `?` modal |
| D-7 | Pinned/manual order ignored | `App.tsx` sort ignores `pinned` and `sort_order` | Sort pinned first; honor `sort_order`; drag-to-reorder |
| D-8 | CSS structure | `styles/style.css` (26 KB) + `app.css` (17 KB) + inline style objects + opaque class names (`c042`, `c067`) | Consolidate to tokens + component CSS; move inline styles (e.g. Docker banner) into classes; test the light theme for contrast |
| D-9 | Mobile | row action buttons are 28×28 px | Provide table→card layout under ~720 px, 44 px touch targets, test at 375 px; reconcile with the "toolbars never wrap" principle by defining mobile behavior |
| D-10 | Performance | filter/sort recomputed on every render, full list pushed each SSE tick | `useMemo` for `displayedApps`, `React.memo` rows, virtualize beyond ~200 rows, send diffs |
| D-11 | PWA | static `CACHE_NAME = 'portly-v1'`; offline fallback shows a stale, empty shell | Versioned cache, "New version available" prompt, explicit offline screen, maskable icons |
| D-12 | Safe-mode affordance | toggle flips instantly | Confirm when unlocking (list what unlocks), visible lock state in the top bar, auto re-lock (F-10) |
| D-13 | Light/dark + motion | `PRODUCT.md` promises `prefers-reduced-motion` | Verify with a Playwright run (`reducedMotion: 'reduce'`) |

---

## 7. Phase 6 — Features to add or improve (prioritized)

**Must-have for a 10/10 story**
- **F-1 User management:** create viewer/admin users, change password, delete, "log out everywhere", API tokens for CLI/automation (roles already exist in the model but there is no way to create a viewer).
- **F-2 Real image-update workflow** (see P1-6): check, notify, apply with automatic rollback, optional schedule.
- **F-3 Live log streaming:** SSE/WebSocket `follow` for Docker and custom apps, search/filter, download, pause (`follow` is ignored today).
- **F-4 Background health + uptime history:** per-app history graph, SLA %, alert on down/up with debounce and retries (builds on P1-4).
- **F-5 Pre-flight port check for compose/run commands:** paste a `docker-compose.yml` or `docker run` line → report conflicts and suggest free ports. This is the product's core promise ("detects port collisions before they happen") and is currently only reactive.

**Strong additions**
- **F-6 Port reservations:** reserve ports for planned services; alert when something else takes them.
- **F-7 Prometheus `/metrics`** (auth-protected) and an OpenAPI page gated behind login.
- **F-8 Backup/restore UI:** versioned export, scheduled DB backup, import preview/diff.
- **F-9 Env/secret viewer** with masking and audited "reveal".
- **F-10 Safe-mode auto re-lock** after N minutes of inactivity (configurable).
- **F-11 Adopt a host process as a Custom app** one click (the error text in `ports.py` already suggests it — verify it exists in `AddAppModal`).
- **F-12 Reverse-proxy awareness:** detect Traefik/Caddy/NPM routes and show the public domain next to each app; generated configs: add TLS (`websecure`, certresolver) variants and IPv6 bracket handling.
- **F-13 Audit log view** (needs S-9).
- **F-14 CLI parity:** `portly open|check-port|suggest|logs`, `--json` everywhere, shell completion.
- **F-15 Multi-host agents** (later): one dashboard for several machines.

---

## 8. Phase 7 — Tests and CI

- **T-1 Auth matrix test:** iterate `app.routes`; assert 401 without session (when a user exists), 403 for `viewer` on mutations, allow-list for `/api/auth/*` and `/api/health`.
- **T-2 Real-Docker integration job** (GitHub Actions with the runner's Docker): discovery incl. **stopped** container, port change success, forced failure (port in use) ⇒ original restored, HostConfig fields preserved, rollback, compose actions.
- **T-3 Unit tests for each bypass/false positive** found here: safe-mode exec, `_is_safe_log_path`, health fallback, conflict detection with host-vs-docker, `hidden` label override, host id collisions.
- **T-4 Blocking test:** a fake slow Docker call must not stall `/api/health` (P1-9).
- **T-5 Frontend tests:** Vitest + Testing Library (AuthGate, saved views, toasts, safe-mode toggle error path); Playwright flows for setup/login/logout and an **axe** accessibility scan on each view and modal.
- **T-6 CI hardening:** the job named "Backend Tests & Lint" only runs `compileall` — add `ruff` and a type check (`pyright`/`mypy`), `tsc --noEmit`, `npm run build`, `docker build` smoke test (container starts and `/api/health` returns 200), `pip-audit` and `npm audit`, coverage threshold, and run e2e on a schedule/PR label.

---

## 9. Suggested execution order

1. **Week 1 — make it runnable and safe:** P0-1, P0-2, P0-3, S-3, P0-8, then P0-4, P0-7.
2. **Week 2 — make it correct:** P0-5, P0-6, P1-1…P1-5, P1-7, P1-9, P1-12, P1-15…P1-17.
3. **Week 3 — harden and finish:** P1-6, P1-8, P1-10, P1-11, P1-13…P1-25, S-1/S-2/S-4/S-5, R-1/R-2.
4. **Week 4 — polish and grow:** D-1…D-13, F-1…F-5, T-1…T-6, docs (R-7).

---

## 10. Definition of done (all must be true)

- [ ] `docker compose up -d` on an empty data dir works; setup → login → dashboard in the browser; Docker containers and host process names visible; disk card matches the host.
- [ ] Auth matrix test passes; no secret (`env`, `start_cmd`, webhook URL) is returned to unauthenticated users or viewers.
- [ ] Safe mode cannot be bypassed via exec, import, settings PATCH, or CSRF.
- [ ] Stopped containers are listed and startable; port change failure always restores the original container; full HostConfig preserved.
- [ ] Every number on screen is real: no synthetic sparklines; container and host CPU/RAM populated; custom-app status reflects real health.
- [ ] No stubbed feature is presented as working (image update either works or is clearly marked/hidden).
- [ ] No event-loop stalls during Docker operations (test T-4).
- [ ] No native `alert()`/`confirm()`; modals have dialog semantics; axe scan has 0 serious/critical issues; fonts self-hosted.
- [ ] CI runs: lint, type check, backend tests, frontend build, docker build smoke test, integration job.
- [ ] README/PRODUCT/DEPLOYMENT match the code (UDP, tests count, auth claims, compose file).

---

### Appendix A — Things already done well (keep them)
Safe mode on by default; loopback default bind; bcrypt password hashing; all SQL parameterized (no injection found); static-file path-traversal guard in `serve_spa`; link-local/multicast blocking in the favicon fetcher; image magic-byte sniffing and size limits; compose-file read restricted to `.yml/.yaml` ≤ 1 MB; rename-then-recreate rollback concept; SSE with polling fallback and exponential backoff; command palette and keyboard-first navigation; thoughtful `PRODUCT.md`/`DESIGN.md`.

### Appendix B — Quick reproduction snippets
- **P0-1:** `PORTLY_MODE=desktop PORTLY_ALLOW_INSECURE_BIND=false python -m portly run --host 0.0.0.0` with an empty data dir → exits with `SECURITY ERROR`.
- **P0-4:** `POST /api/apps/docker:<name>:<port>/tcp/exec {"command":"env sh -c 'id'"}` with Safe Mode ON → executes.
- **P0-3:** `curl http://HOST:5533/api/apps/docker:<name>:<port>%2Ftcp` with no cookie → response contains `docker_inspect.env`.
- **P1-10:** `_is_safe_log_path('/var/log/myapp/app.log')` → `False`; `_is_safe_log_path('/home/me/.bash_history')` → `True`.
