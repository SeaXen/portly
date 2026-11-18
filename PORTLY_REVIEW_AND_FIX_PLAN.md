# Portly — Review & Fix Plan (agent-ready, round 2)

> **Audience:** an AI coding agent or developer who will fix Portly.
> **Source reviewed:** `portly-main.zip` (Python/FastAPI backend, React 19 + Vite frontend, SQLite, Docker SDK).
> **Replaces:** the older `PORTLY_FIX_PLAN.md` in the repo. Most of that file is already fixed (login UI, UDP, `alert()` removal, fake sparklines, etc.). Do **not** use it. Delete or move it to `docs/archive/` (see item **T-5**).
> **How to use:** work top to bottom. Every item has an ID, a location, the problem, the fix and an acceptance test. Read "Rules for the agent" first.

---

## 0. Verdict

**Portly is not 10/10 yet. It is a strong, much-improved app (roughly 7.5/10 overall).** The big problems from the first review are fixed: there is now a setup/login UI, the setup token is single-use, sessions are hashed and DB-backed, CSRF checks Origin/Referer, SVG icons are sanitized, fake telemetry is gone, and there are about 198 test functions. What is left is a smaller number of **real bugs**, some **wrong numbers on multi-core / modern Docker hosts**, **default-deployment friction**, and **polish gaps**.

| Area | Score | Main reason it is not 10 |
|---|---|---|
| Backend logic | 7.5 / 10 | Route-shadowing bug, CPU/RAM math wrong on cgroup v2, custom apps default to "up" |
| Security | 7.5 / 10 | Good basics. `script-src 'unsafe-inline'`, very broad Docker mounts, plaintext setup token in DB, unauthenticated favicon route |
| Docker / deployment | 5.5 / 10 | Opening the app by LAN IP is likely blocked with `INVALID_HOST`; `./data` permissions for the non-root user are likely wrong |
| Data accuracy | 6.5 / 10 | Stats loop is serial (stale data with many containers); unknown metrics shown as `0` |
| Frontend function | 7.5 / 10 | Initial-load failure is silent; password change logs you out with no explanation |
| Design / UX polish | 7 / 10 | Toast ignores the theme (hard-coded dark colors), 3 drawers have no focus trap, 732 hard-coded hex colors in TSX |
| Accessibility | 6.5 / 10 | "WCAG 2.1 AA" is claimed but not measured |
| Tests / CI | 6.5 / 10 | No frontend tests, no linters, docs count tests wrongly (README 176, PRODUCT 170, actual ≈198) |
| Docs / repo hygiene | 6 / 10 | Version numbers disagree in 4 places; stale planning files shipped in the repo |

### Limits of this review (read this)
- **Static review only.** Python dependencies could not be installed in the review sandbox (no network), so the app and the tests were **not run**. `python -m compileall portly` **passed** (no syntax errors).
- Tags used below:
  - **[Verified]** — confirmed by reading the exact code path.
  - **[Verify first]** — strongly suspected, but reproduce on a real machine before changing anything. If it does not reproduce, note that in the commit and move on.
- Read in full: `auth.py`, `cli.py`, `Dockerfile`, `docker-compose.yml`, `index.html`, `sw.js`, the middleware and about 25 route handlers in `app.py`, the stats and health code, and the merge logic. Only scanned (grep level): most of `frontend/src/components/*.tsx`, the CSS and the tests.
- Design was judged from code, not from screenshots. Do a visual pass (item **D-6**).

---

## 1. Rules for the agent

1. **Reproduce before fixing** anything tagged *[Verify first]*.
2. **One item = one commit**, with the item ID in the message (e.g. `P0-2`). Add or update a test in the same commit.
3. **Never weaken Safe Mode, auth, CSRF or host validation.** If a fix needs a security trade-off, choose the safer option and write the decision in `CHANGELOG.md`.
4. **Keep API and UI in sync.** If a response shape changes, update `api.ts`, `types.ts`, `docs/API.md` and the tests together.
5. **No new runtime network dependencies** (CDNs, analytics, remote fonts). Portly is local-first.
6. `portly/frontend/dist` is committed. Rebuild it after any frontend change.
7. **Before every commit run:**
   ```bash
   pip install -r requirements.txt pytest-asyncio pytest-cov
   python -m compileall -q portly
   PORTLY_TESTING=1 python -m pytest tests -q --ignore=tests/e2e
   cd portly/frontend && npm ci && npm run build   # build runs tsc
   ```
8. Do not "clean up" unrelated code. Do not rename public env vars or API paths.

---

## 2. Phase 1 — P0 (fix first, in this order)

### P0-1 · Default Docker setup is probably unreachable by LAN IP (`INVALID_HOST`) **[Verified from code; confirm with curl]**
- **Where:** `portly/backend/app.py` ≈ lines 286-315 (host validation in `security_and_csrf_middleware`); `docker-compose.yml` (`PORTLY_ALLOW_INSECURE_BIND=false`, no `PORTLY_ALLOWED_HOSTS`); `portly/cli.py` prints `http://0.0.0.0:5533` as the setup URL.
- **Problem:** the allowed Host set is only `127.0.0.1, localhost, ::1` plus env/`public_host`. When bound to `0.0.0.0`, a user opening `http://192.168.1.20:5533` (or `http://myserver:5533`) gets **HTTP 400 `INVALID_HOST` on every request**, including the first page. Nothing in README, DEPLOYMENT.md or the compose file mentions `PORTLY_ALLOWED_HOSTS`. This blocks the exact scenario the compose file is built for.
- **Fix:**
  1. Keep DNS-rebinding protection for **hostnames**, but accept any **IP-literal** Host (IPv4 or bracketed IPv6) — an attacker cannot DNS-rebind to a bare IP, so this is safe.
  2. Parse the Host header properly (see **L-6**) instead of `split(":")[0]`.
  3. In server mode, if a request is rejected for a hostname, return a message that names the fix: `Host 'x' is not allowed. Set PORTLY_ALLOWED_HOSTS=x or set Public host in Settings.`
  4. Make the startup banner in `cli.py` print a usable URL (use the machine's primary LAN IP or `localhost` when host is `0.0.0.0`).
  5. Document `PORTLY_ALLOWED_HOSTS` in README, `docs/DEPLOYMENT.md` and the compose file (commented example).
- **Acceptance (add to tests):**
  - `GET /api/health` with `Host: 192.168.1.20:5533` → 200.
  - `GET /api/health` with `Host: evil.example.com` → 400 with the helpful message.
  - With `PORTLY_ALLOWED_HOSTS=nas.lan`, `Host: nas.lan:5533` → 200.

### P0-2 · `reveal-env` endpoint is unreachable (route shadowing) **[Verified from code; confirm with TestClient]**
- **Where:** `app.py` line ≈ 916 `@app.get("/api/apps/{app_id:path}")` is declared **before** line ≈ 972 `@app.get("/api/apps/{app_id:path}/inspect/reveal-env")`.
- **Problem:** `{app_id:path}` matches everything, including `docker:abc/inspect/reveal-env`, so the generic detail route wins and the reveal route never runs. The UI call `api.revealEnv()` will return 404 "app not found" or the wrong payload. (`/logs`, `/tls`, `/compose`, `/favicon`, `/proxy-config` are declared earlier, so they work.)
- **Fix:** move the `reveal-env` handler (and any other `GET /api/apps/{app_id:path}/<suffix>` route) **above** `get_app_detail`. Keep `get_app_detail` last among the GET `/api/apps/...` routes.
- **Acceptance:** new test in `tests/` that, for an admin session, requests `GET /api/apps/<id>/inspect/reveal-env` and expects 200 with an `env` payload; for a viewer expects 403. Add a generic regression test that loops over every registered `GET /api/apps/{app_id:path}/…` route and asserts it is declared before the bare detail route.

### P0-3 · `./data` bind mount is probably not writable by the non-root container user **[Verify first]**
- **Where:** `Dockerfile` (`USER portly`, `mkdir /app/data && chown`), `docker-compose.yml` (`./data:/app/data`).
- **Problem:** a bind-mounted host folder that Docker auto-creates is owned by `root`. The image's `chown` only affects the image layer, not the bind mount. The `portly` system user then cannot create the SQLite DB → restart loop on first run.
- **Fix (choose the first that works):**
  1. In `docker-compose.yml` use a **named volume** (`portly-data:/app/data`). Docker initialises it from the image with the right ownership.
  2. Or add an entrypoint script that, when started as root, `chown`s `/app/data` and then drops to `portly` (e.g. with `gosu`/`su-exec`).
  3. Print a clear error in `Store()` if the data dir is not writable, naming the fix.
- **Acceptance:** on a clean machine, `docker compose up -d` with no existing `./data` stays running, `/api/health` is 200, and the *Create admin* screen loads.

### P0-4 · Make the compose file build from this repo **[Verified]**
- **Where:** `docker-compose.yml` uses only `image: ghcr.io/seaxen/portly:latest`.
- **Problem:** someone who clones the repo and runs `docker compose up` gets whatever image is published (or a pull error), not the code they cloned.
- **Fix:** add `build: .` next to `image:` and remove the obsolete `version: "3.8"` line.
- **Acceptance:** `docker compose up --build` runs the local code.

---

## 3. Phase 2 — P1 logic and data correctness

### L-1 · Container CPU% and RAM are wrong on cgroup v2 hosts (most modern Linux) **[Verified from code; confirm on a real host]**
- **Where:** `portly/backend/discovery/docker_src.py` `_calculate_cpu_percent` (≈ line 123-135) and the stats worker (≈ line 160-168).
- **Problem:**
  - CPU core count comes from `cpu_usage.percpu_usage`, which **does not exist on cgroup v2**. The code falls back to `1`, so CPU% is under-reported on multi-core machines.
  - Memory subtracts `stats.cache`, which is a cgroup v1 field. On cgroup v2 the correct field is `inactive_file`, so RAM is over-reported.
- **Fix:**
  - Core count: `d["cpu_stats"].get("online_cpus")` → else `len(percpu_usage)` → else `psutil.cpu_count()`.
  - Memory: `usage - stats.get("inactive_file", stats.get("total_inactive_file", stats.get("cache", 0)))`, clamped at 0 (same formula `docker stats` uses).
- **Acceptance:** unit tests with two fixture dicts (v1 and v2 shape) that assert the expected CPU% and MB.

### L-2 · Stats collector is serial, so numbers go stale with many containers **[Verified from code]**
- **Where:** `docker_src.py` stats worker; `c.stats(stream=False)` is called one container at a time.
- **Problem:** each `stats(stream=False)` call takes about 1–2 s (Docker waits for a second sample). With 30 containers one loop takes 30–60 s, yet the UI treats the data as live.
- **Fix:** collect with a `ThreadPoolExecutor(max_workers=8)` (or a per-container streaming thread), keep a timestamp per cache entry, and expose `stats_age_sec` so the UI can grey out values older than ~15 s.
- **Acceptance:** test with a fake client whose `stats()` sleeps 0.2 s and 20 containers: one loop finishes in < 1.5 s.

### L-3 · Unknown metrics are shown as `0`; custom apps default to "up" **[Verified]**
- **Where:** `discovery/merge.py` ≈ lines 48-75 (`custom_status = "up"` default, `cpu_percent`/`ram_mb`/`uptime_sec` hard-coded to `0`); `discovery/host.py` (`0.0` on `AccessDenied`).
- **Problem:** a custom app that was never started or never health-checked shows green "up". Unknown CPU/RAM is shown as a real `0`. This is a visible honesty problem on a monitoring tool.
- **Fix:**
  - Default custom-app status to `"unknown"` until a health snapshot exists (or until the tracked PID is alive). Add `unknown` to the status type/badge in the frontend if it is missing.
  - Use `null` for metrics that could not be read; render `—` in the UI. For custom apps started by Portly, read CPU/RAM from the tracked PID via `psutil`.
- **Acceptance:** a custom app with no health data renders "Unknown"; a host process with `AccessDenied` renders `—`, not `0%`.

### L-4 · HTTP health checks follow redirects **[Verified from code]**
- **Where:** `portly/backend/health.py` `check_http_endpoint` (`urllib.request.urlopen`).
- **Problem:** `urllib` follows redirects automatically, so the default `expected_status` of `200,204,301,302` can never see a 301/302. A redirect to a broken page marks a healthy app down. A redirect can also point at a host that `_is_safe_health_host` would have blocked (SSRF guard bypass).
- **Fix:** build an opener with a handler that **does not follow redirects** (`HTTPRedirectHandler.redirect_request` returns `None`) so the 3xx status is returned as-is.
- **Acceptance:** test with a local server returning 302: result is `ok=True, status=302` when 302 is expected, and no request is made to the redirect target.

### L-5 · TCP health check is IPv4-only **[Verified]**
- **Where:** `health.py` `check_tcp_port` (`socket.AF_INET`).
- **Fix:** use `socket.create_connection((host, port), timeout)`; keep the safe-host check first.
- **Acceptance:** a service listening only on `::1` reports up.

### L-6 · Host header parsing breaks for IPv6 **[Verified]**
- **Where:** `app.py` ≈ line 289 `host_header = ...split(":")[0]`.
- **Problem:** `[::1]:5533` becomes `[`, so IPv6 access is rejected.
- **Fix:** write a small `_parse_host(header)` helper that handles `[v6]:port`, `host:port` and bare hosts; reuse it in CSRF `_same_host`.
- **Acceptance:** unit tests for `localhost:5533`, `127.0.0.1`, `[::1]:5533`, `[fe80::1]`, `example.com`.

### L-7 · Dummy bcrypt hash might be invalid **[Verify first]**
- **Where:** `auth.py` `DUMMY_BCRYPT_HASH` (hard-coded string).
- **Problem:** if the library rejects the string as a malformed hash, `bcrypt.checkpw` raises immediately, the `except` swallows it, and the timing equalisation for unknown usernames silently does nothing.
- **Fix:** generate it once at import: `DUMMY_BCRYPT_HASH = bcrypt.hashpw(b"portly-dummy", bcrypt.gensalt(rounds=10)).decode()`.
- **Acceptance:** test that `verify_dummy_password("x")` takes roughly the same time as a real failed check (within a loose factor), and does not raise internally.

### L-8 · Changing your own password logs you out with no explanation **[Verified from code; confirm UI]**
- **Where:** `app.py` `update_user_password_endpoint` calls `auth.revoke_all_sessions(user_id)` for the caller too.
- **Fix:** after a self-service change, revoke the user's *other* sessions, create a fresh session for the current browser and set the cookie. If you keep the full logout, the frontend must show a toast ("Password changed — please sign in again") and go to the login screen.
- **Acceptance:** changing your own password keeps you signed in (or lands on login with a clear message); old sessions on other browsers stop working.

### L-9 · Export is vulnerable to CSV formula injection and Markdown breakage **[Verified]**
- **Where:** `app.py` `export_data` (CSV and Markdown branches).
- **Problem:** container/process names are attacker-influenced. A name starting with `=`, `+`, `-` or `@` runs as a formula in Excel. A `|` in a name breaks the Markdown table.
- **Fix:** prefix such CSV cells with `'`; escape `|` and backticks in Markdown cells.
- **Acceptance:** test with an app named `=HYPERLINK("http://x","y")` and one named `a|b`.

### L-10 · Initial-load failure is silent **[Verified]**
- **Where:** `frontend/src/App.tsx` ≈ line 335 (`catch (e) { console.error(...) }`).
- **Problem:** if the backend is down or returns 500, the user sees an empty dashboard with no explanation.
- **Fix:** keep an `initialLoadError` state; when set (and the error is not 401, which AuthGate handles), show an error panel with the message and a **Retry** button. Also show a non-blocking "Connection lost — retrying" bar when the SSE stream is down.
- **Acceptance:** stop the backend while the page is open → error panel appears; restart → Retry loads data.

### L-11 · Host process discovery as non-root with `pid: host` **[Verify first]**
- **Where:** `Dockerfile` (`USER portly`), `docker-compose.yml` (`pid: host`, `network_mode: host`).
- **Problem:** `psutil` cannot read `cmdline`/`cwd`/connection owner of processes owned by other users when not root. Host rows may show blank names, and "stop process" will fail with permission errors.
- **Fix:** probe this at startup and show a clear "Limited host visibility (not running as root)" notice in the System drawer. Document the trade-off in `docs/DEPLOYMENT.md`: either run as root for full host visibility, or accept Docker-only plus limited host data.
- **Acceptance:** with the default compose file, the UI shows the notice instead of silently showing blank process names.

---

## 4. Phase 3 — Security hardening (P2)

| ID | Where | Problem | Fix |
|---|---|---|---|
| S-1 | `app.py` CSP header; `frontend/index.html` inline script | `script-src 'unsafe-inline'` is needed only because `index.html` has an inline service-worker script. It weakens XSS protection. | Move the SW registration into `src/main.tsx`; remove `'unsafe-inline'` from `script-src`. Keep it for `style-src` only if React inline styles need it. Test the built app loads with no CSP violations. |
| S-2 | CSP `connect-src 'self' ws: wss:` | Allows WebSocket connections to any host. The app uses SSE, not WebSockets. | Use `connect-src 'self'` (add the dev origin only when testing). |
| S-3 | `docker-compose.yml` | `/var/run/docker.sock:ro` looks safe but is **not**: a read-only socket still lets a client create privileged containers. `/:/hostfs:ro` + `pid: host` + `network_mode: host` is a very wide grant. | Mount only what `PORTLY_HOSTFS` really needs (check `stats.py` disk-usage use) instead of `/`. Add a "Security notes" section to DEPLOYMENT.md explaining the socket is root-equivalent and offering a socket-proxy option. Remove the misleading `:ro` comment/impression. |
| S-4 | `store.py` `setup_token.token_plain`, `auth.get_setup_token` | The setup token is stored in plaintext so it can be re-printed on restart. | Store only the hash; print the token once at creation. Add `portly reset-setup-token` to the CLI for the "I lost it" case. |
| S-5 | `GET /api/apps/{id}/favicon` has no auth | Anyone who can reach the server can trigger outbound icon fetches for known apps. | Require a session (the dashboard is same-origin so cookies are sent), or rate-limit it. |
| S-6 | `notifications.py` webhook sender | Webhook URL is admin-set but has no guard against internal addresses or redirects. | Reuse the safe-host logic from `health.py`; disable redirects; allow an explicit opt-in env var for internal webhooks. |
| S-7 | `process_actions.py` `shell=True` (start, stop, update commands) | Custom-app commands run in a shell. This is admin-only and Safe-Mode-gated, which is acceptable, but it is a remote-code-execution feature. | Keep it. Add a one-time warning in the UI when saving a custom command, record the full command in the audit log, and document it in SECURITY.md. |
| S-8 | `auth.py` | Session cookie flags and lockout look right. | Add a test that asserts `HttpOnly`, `SameSite=Lax/Strict`, and `Secure` when `PORTLY_COOKIE_SECURE=1`. |

---

## 5. Phase 4 — Design, UX and accessibility polish

| ID | Where | Problem | Fix |
|---|---|---|---|
| D-1 | `components/Toast.tsx` (≈ lines 60-80) | Colors are hard-coded dark (`#161B22`, `#ECEEF3`), so toasts look wrong in Light / System / OLED themes. `ConfirmDialog.tsx` also uses no CSS variables. | Use the design tokens (`var(--surface)`, `var(--text)`, status colors) so toasts and dialogs follow the theme and accent. |
| D-2 | `CustomizeDrawer.tsx`, `SystemDrawer.tsx`, `UserManagementDrawer.tsx` | No `useFocusTrap`; only 6 of ~9 overlays have `aria-modal`. Focus can escape and Esc may not close. | Give every drawer/modal: `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `useFocusTrap`, Esc to close, return focus to the opener. |
| D-3 | whole frontend | 732 hard-coded hex colors in TSX; two big overlapping stylesheets (`style.css`, `app.css`) | Replace hex values with tokens from `tokens.css`; delete duplicate rules; one source of truth for spacing and colors. Do it per component, in small commits. |
| D-4 | Accessibility claim in `PRODUCT.md` ("WCAG 2.1 AA") | Not measured. | Run axe (via Playwright) on login, overview, table, detail modal, add-app modal in dark **and** light themes; fix contrast failures; add the axe check to the e2e suite. Until it passes, soften the claim in PRODUCT.md. |
| D-5 | Empty / error / loading states | Initial load has none (see **L-10**). | Add skeletons for table/grid, a real empty state ("No services found yet — here's how discovery works"), and an error state with Retry. |
| D-6 | Visual pass | Design was not reviewed from screenshots. | Take screenshots at 360 px, 768 px, 1280 px, 1920 px in dark and light. Check: text truncation of long container names, table horizontal scroll on mobile, touch targets ≥ 44 px, focus rings visible on every control. |
| D-7 | Large files | `AppDetailModal.tsx` (1,893 lines), `AddAppModal.tsx` (1,208), `App.tsx` (1,230), `app.py` (2,371) | Split by feature (tabs of the detail modal into their own files; `app.py` into `routers/` per domain). Pure refactor, no behavior change, one commit per extraction, tests must stay green. |

---

## 6. Phase 5 — Features to add or improve (prioritized)

These are **recommendations**, not bugs. Do them after Phases 1–4.

1. **First-run diagnostics panel (high value).** One screen that answers "why can't I see X?": Docker socket reachable? Running as root? `pid: host` active? Host FS mounted? Docker API version? This removes most support questions and also solves **L-11** and **P0-3**.
2. **API tokens for automation.** The CLI (`list`, `start`, `stop`) opens the SQLite store directly, so it only works on the same machine. Add personal API tokens (hashed, scoped read/admin) and let the CLI talk to a remote Portly over HTTP.
3. **Port-change safety net.** The remap flow exists. Add an obvious "Undo / rollback" toast after apply, and show which dependents (compose `depends_on`, reverse-proxy configs) might break.
4. **Alert rules.** Webhooks exist. Add simple rules: "port X down for > N min", "new port opened on 0.0.0.0", "container restarted > N times in 1 h", with per-rule cooldown.
5. **Persisted history.** Keep 24 h–7 d of CPU/RAM/port-count samples in SQLite (downsampled) so the sparklines survive a restart.
6. **Optional 2FA (TOTP)** and **forward-auth / OIDC header support** for people who run Portly behind Authelia, Authentik or Caddy.
7. **Search and filters.** Saved filters exist; add "listening on 0.0.0.0 only" and "unhealthy only" quick filters and URL-persisted filter state.
8. **Backup UX.** Scheduled automatic export to `data/backups/` with retention, plus a restore preview ("this will change N items").
9. **Longer term:** multi-host agent mode. Only start this after everything above is solid.

---

## 7. Phase 6 — Tests, CI, docs and repo hygiene

| ID | Problem | Fix |
|---|---|---|
| T-1 | No frontend tests. | Add Vitest + React Testing Library. First tests: `AuthGate` (needs_setup / unauthenticated / authenticated), `ConfirmDialog` (focus trap, Esc), `Toast` (roles, theme), `api.request` 401 handling. Run in CI. |
| T-2 | No linters. | Add `ruff` (backend) and `eslint` + `@typescript-eslint` (frontend). Fix the 71 `any` usages gradually; turn on `noUnusedLocals` and `noUnusedParameters` in `tsconfig.json`. Add a real **Lint** job to all three CI files (`.github`, `.forgejo`, `.gitlab-ci.yml`). |
| T-3 | Route-order and security regressions can come back. | Add tests: route-shadowing (see **P0-2**), the full auth matrix for any new route, Host/CSRF edge cases (**P0-1**, **L-6**). |
| T-4 | Test counts in docs are wrong: README says 176, PRODUCT says 170 (149 + 21), the code has about 198 test functions. | Stop hard-coding counts. Remove the number from badges/text, or generate it in CI. |
| T-5 | Stale planning files shipped in the repo: `PORTLY_FIX_PLAN.md` (old, mostly fixed), `Portly-build-prompt.md`, `.impeccable/`, `reference/design/`, `docs/review/`, `docs/superpowers/`. Agents read these and waste time on already-fixed items. | Move them to `docs/archive/` (or delete). Keep `AGENTS.md`, README, DESIGN.md, PRODUCT.md, SECURITY.md, docs/API.md, docs/DEPLOYMENT.md. Put **this file** in `docs/` as the current plan. |
| T-6 | Version numbers disagree: `pyproject.toml` 0.1.1, FastAPI `version="0.1.1"`, `frontend/package.json` 1.0.0, CHANGELOG has `[1.1.0] 2026-11-17` listed **after** `[0.1.1] 2026-11-18`. | Pick one scheme (suggest SemVer). Use one source of truth (`portly/__init__.py`), read it in `pyproject.toml` and FastAPI; fix the CHANGELOG order. |
| T-7 | `docs/DEPLOYMENT.md` and the root compose file can drift. | Link to the root compose file instead of copying it, and mention `PORTLY_ALLOWED_HOSTS`, the data volume, and the socket-security notes. |
| T-8 | E2E tests are not in the default run. | Keep that, but make sure the e2e job runs on every PR and fails the build. Add a smoke test: fresh start → setup screen → create admin → dashboard loads. |

---

## 8. Suggested execution order

1. **P0-1 → P0-4** (deployment blockers and the shadowed route).
2. **L-1, L-2, L-3** (wrong numbers), then **L-4 … L-11**.
3. **T-3, T-5, T-6** (so regressions are caught and the repo stops confusing agents).
4. **S-1 … S-8**.
5. **D-1 … D-7** and **T-1, T-2, T-4, T-7, T-8**.
6. **Phase 5 features**, in the order listed.

---

## 9. Definition of done (all must be true)

- [ ] On a clean machine, `docker compose up -d --build` stays running; opening `http://<LAN-IP>:5533` loads; the Create-admin screen works with the printed token.
- [ ] `GET /api/apps/<id>/inspect/reveal-env` works for admins and is 403 for viewers.
- [ ] Container CPU% and RAM match `docker stats` within about 10% on a cgroup v2 host.
- [ ] No metric shows `0` when it is actually unknown; no custom app shows "up" without a health result.
- [ ] A 302 response counts as healthy when 302 is expected, and no redirect is followed.
- [ ] CSP has no `'unsafe-inline'` in `script-src`; the built app loads with zero CSP errors in the console.
- [ ] Every modal/drawer has `role="dialog"`, a focus trap, Esc to close, and follows the theme (including toasts).
- [ ] axe reports no serious or critical issues on the main screens in dark and light themes.
- [ ] All backend tests, frontend tests, lint, `tsc`, build and e2e smoke pass in CI.
- [ ] One version number everywhere; docs contain no hard-coded test counts; stale planning files are archived.

---

## Appendix A — Things already done well (keep them)

- Safe Mode on by default and enforced **server-side**; auto-relock timer.
- Sessions stored as SHA-256 hashes, DB-authoritative, role changes and logout take effect immediately; last admin cannot be demoted or deleted.
- Login lockout stored in SQLite; setup token is single-use and compared in constant time.
- CSRF checks Origin/Referer and `Sec-Fetch-Site`; CORS limited to configured origins.
- SVG favicon sanitization; icon responses sent with a locked-down CSP.
- Env-var masking with an audited admin-only reveal action (once **P0-2** is fixed).
- Atomic backup import in one transaction; SQLite WAL; parameterized SQL.
- UDP discovery, docker-proxy de-duplication, stable IDs (`docker:`, `host:`, `custom:`).
- Self-hosted fonts, no CDN, PWA service worker that excludes `/api` and the SSE stream.
- Wide test coverage including an auth matrix.

## Appendix B — Quick reproduction snippets

**P0-1 (Host blocking)** — run the app bound to `0.0.0.0` in server mode, then:
```bash
curl -i -H "Host: 192.168.1.20:5533" http://127.0.0.1:5533/api/health
# Expected today: 400 INVALID_HOST.  Expected after fix: 200.
```

**P0-2 (route shadowing)** — with the test client and an admin session cookie:
```python
from starlette.routing import Route
routes = [r.path for r in app.routes if isinstance(r, Route)]
i_detail = routes.index("/api/apps/{app_id:path}")
i_reveal = routes.index("/api/apps/{app_id:path}/inspect/reveal-env")
assert i_reveal < i_detail   # fails today (916 vs 972 in source order)
```

**L-1 (cgroup v2 CPU)** — fixture for the unit test:
```python
v2 = {
  "cpu_stats":    {"cpu_usage": {"total_usage": 2_000_000_000}, "system_cpu_usage": 40_000_000_000, "online_cpus": 8},
  "precpu_stats": {"cpu_usage": {"total_usage": 1_000_000_000}, "system_cpu_usage": 36_000_000_000},
}
# expected CPU% = (1e9 / 4e9) * 8 * 100 = 200.0   (no "percpu_usage" key in v2)
```

**L-4 (redirects)** — tiny local server that always answers `302 Location: http://127.0.0.1:1/` → with expected status `302` the check must return `(True, 302, …)` without connecting to port 1.
