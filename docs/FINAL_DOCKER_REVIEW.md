# Portly — Final Pre-Docker Review & Remediation Plan

**Date:** 2026-11-27  
**Target Baseline:** `main` @ `ef09a9c` (`v1.1.0`)

## Executive Summary

Portly's baseline test suites pass cleanly (`264` backend unit/integration tests, `22` Playwright E2E tests, `12` Vitest tests, `ruff`, `compileall`, and committed `dist` build parity). However, a full-stack pre-Docker audit identified **1 Docker deployment blocker**, **4 backend correctness bugs**, **7 frontend logic/state bugs**, and several **UI design-token, accessibility, and lint hygiene gaps** that should be resolved before shipping and deploying in Docker.

---

## Findings

### 1. Docker & Container Runtime Readiness
1. **Missing `docker-cli` and `docker-compose` in runtime image (`Dockerfile`):**  
   `portly/backend/actions/docker_actions.py` invokes `shutil.which("docker")` and `docker compose` for the **Stacks** view (`up`/`down`/`restart`/`logs`/`pull`). The final runtime stage only installed `procps`, `net-tools`, and `curl`, causing all Compose stack actions to fail inside Docker.
2. **Undetermined non-root UID/GID (`Dockerfile` vs `docs/DEPLOYMENT.md`):**  
   `docs/DEPLOYMENT.md` documents container UID/GID `1000:1000`, whereas `Dockerfile` used `groupadd -r` / `useradd -r` (assigning dynamic system IDs like `999`/`101`).
3. **Explicit `PORTLY_DATA_DIR` in container environment (`Dockerfile`, `docker-compose.yml`):**  
   Setting `PORTLY_DATA_DIR=/app/data` explicitly aligns container `ENV` and `docker-compose.yml` with the `/app/data` volume mount instead of relying on relative working-directory defaults.

### 2. Backend Logic & Validation
1. **Unvalidated `app_id.split(":")[1]` in `portly/backend/app.py`:**  
   Nine endpoints parse `docker:<container>` without validating that the container name segment is non-empty, turning malformed IDs such as `"docker:"` into unhandled errors or ambiguous calls instead of HTTP `400 INVALID_ID`.
2. **Multi-port conflict check ignores per-mapping bind IP (`portly/backend/app.py`):**  
   `change_multi_ports_endpoint` checked availability against `"0.0.0.0"` even when a mapping specifies a narrower `bind` IP (e.g., `127.0.0.1`).
3. **Unsafe `int(hp)` cast in `list_compose_stacks_endpoint` (`portly/backend/app.py`):**  
   Malformed or unexpected `HostPort` metadata could raise `ValueError`/`TypeError`.
4. **Image digest & reservation bypass in `deploy_container` (`portly/backend/actions/docker_actions.py`):**  
   - The image validation regex omitted `@`, rejecting pinned digest images such as `nginx@sha256:...`.
   - `check_port_availability(hp_int, "0.0.0.0")` omitted `store=store`, bypassing Portly's reserved-port tracking.
   - `restart_policy` was not validated against Docker's supported set (`no`, `always`, `unless-stopped`, `on-failure`).

### 3. Frontend Logic & State Bugs
1. **Blank Audit Log Timestamps (`UserManagementDrawer.tsx`):**  
   Reads `log.timestamp`, whereas the backend `/api/audit-logs` (`events` table) returns `ts`. Every audit log timestamp rendered empty.
2. **Invalid CSS variable strings stored/sent as hex colors (`App.tsx`, `CustomizeDrawer.tsx`):**  
   Initial state and color swatches used `'var(--accent)'` / `'var(--success)'` / `'var(--warning)'`. The backend `/api/settings` rejects non-`#RRGGBB` values with HTTP `400`, `<input type="color">` rejects CSS `var(...)`, setting `--accent: var(--accent)` creates a cyclic CSS variable, and category pills append alpha suffixes like `var(--success)35` (invalid CSS).
3. **Environment variable truncation & missing custom env display (`AppDetailModal.tsx`):**  
   - `e.split('=', 2)` in JavaScript discards anything after the second `=` (corrupting database URLs, JWTs, base64 tokens, etc. on reveal).
   - Custom app environment variables returned in `d.app.env` were not rendered unless revealed separately.
4. **Exec Terminal Safe-Mode mismatches (`AppDetailModal.tsx`):**  
   Quick presets included `env` and `cat /etc/hosts`, which are rejected by Safe Mode's binary allowlist.
5. **Unmanaged host process port remap confusion (`AppDetailModal.tsx`):**  
   Allowing submission on the Ports tab for raw `host` processes without explaining adoption constraints results in avoidable errors; should display clear guidance and disable Apply for `host` sources.
6. **Substring port corruption in preflight remap (`AddAppModal.tsx`):**  
   `preflightInput.split(oldP).join(newP)` corrupts overlapping ports such as `80:8080` → `8081:808180`. Also Windows-specific placeholders (`C:\projects\my-app`) should use cross-platform Linux-friendly paths.
7. **Stale Stack selection & AppDetailModal state (`StacksView.tsx`, `App.tsx`):**  
   `loadStacks()` refreshed the list without syncing `selectedStack` (or selecting newly created stacks), and `<AppDetailModal>` lacked `key={detailApp.id}` when switching apps directly from the Command Palette.

### 4. Design Polish, Contrast & Accessibility
1. **Raw emojis in UI chrome (`DESIGN.md` / `IMPECCABLE_AUDIT.md` compliance):**  
   Raw emojis (`⚓`, `🗑`, `👁️`, `⏸`, `🧹`, `☁`) appear across `LoginScreen`, `SetupScreen`, `AuthGate`, `SystemDrawer`, `StacksView`, `AppDetailModal`, `TableView`, and `GridView`. Replace with crisp SVG icons via `Icon.tsx`.
2. **Semantic theme tokens & contrast fixes (`tokens.css`, `app.css`, TSX inline styles):**  
   Migrate hard-coded dark-surface hexes and low-contrast `#64748B` labels to semantic tokens (`--muted`, `--surface-1..3`, `--surface-input`, `--surface-terminal`, `--on-accent`, `--border-subtle`, `--border-strong`) with proper dark/light/OLED overrides.
3. **Missing accessible names & accurate tooltips:**  
   Add `aria-label` on `StacksView` Delete button, `AppDetailModal` toast dismiss button, and `Toolbar` sort-direction toggle; update `TopBar` theme toggle tooltip for the 4-mode cycle (`dark → light → oled → system`).
4. **ESLint `react-hooks/exhaustive-deps` warnings:**  
   Resolve all 7 remaining hook dependency warnings across `App.tsx`, `AppDetailModal.tsx`, `StacksView.tsx`, `SystemDrawer.tsx`, and `UserManagementDrawer.tsx`.

---

## Remediation Plan

1. **Docker & Compose (`Dockerfile`, `docker-compose.yml`):** Install `docker-cli` and `docker-compose`, pin `portly` UID/GID to `1000:1000`, and set explicit `PORTLY_DATA_DIR=/app/data`.
2. **Backend Fixes (`app.py`, `docker_actions.py`):** Add `_docker_container_name` validation helper, honor `m.bind` in multi-port conflict checking, guard `int(hp)` in compose stack parsing, allow `@` digests, validate `restart_policy`, and pass `store=store` to `check_port_availability` in `deploy_container`.
3. **Design Tokens & Icons (`tokens.css`, `app.css`, `Icon.tsx`):** Add semantic surface/border/foreground tokens and extend `Icon.tsx` with `anchor`, `trash`, `eye`, `pause`, `cloud`.
4. **Frontend Logic & UI Polish:** Fix all 7 frontend bugs, eliminate raw UI emojis and hard-coded dark-surface/low-contrast colors, add missing `aria-label` attributes, and clear all ESLint warnings.
5. **Regression Tests & Bundle Sync:** Add targeted backend (`pytest`) and frontend (`vitest`) tests covering each fix, then rebuild and verify `portly/frontend/dist`.
6. **Full Verification & Real Docker Smoke Test:** Run `ruff`, `compileall`, backend `pytest` (with coverage), Playwright E2E, `npm test`, `npm run lint`, `npm run build`, and boot a live `docker build` + container health/CLI verification.
7. **Git Commit & Push:** Verify clean staging (no DB/coverage artifacts), commit all changes including rebuilt `dist`, and push to configured remotes.
