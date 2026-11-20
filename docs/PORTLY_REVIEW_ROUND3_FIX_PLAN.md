# Portly — Review & Fix Plan (agent-ready, round 3)

> **Audience:** an AI coding agent or developer who will fix Portly.
> **Source reviewed:** `portly-main_2.zip` (FastAPI backend, React 19 + Vite frontend, SQLite, Docker SDK), v1.1.0.
> **Replaces:** `PORTLY_REVIEW_AND_FIX_PLAN.md` (round 2) in the repo root. Almost everything in it is now fixed (see Section 2). **Do not redo those items.** Move the old file to `docs/archive/` when you add this one.
> **How to use:** read Section 1 (rules), then work Section 3 top to bottom. Every item has an ID, location, problem, fix and acceptance test.

---

## 0. Verdict

**Portly is not 10/10 yet. It is roughly 8.5 / 10 overall.** Round 2 found 4 deployment blockers, 11 logic bugs, 8 security items and 7 design items. The large majority are fixed (Section 2). What remains is a short list of real but smaller issues, a few hardening gaps, and design/feature polish.

| Area | Score | Why it is not 10 |
|---|---|---|
| Backend logic | 8.5 | SSE subscriber can leak; setup is not atomic; dummy bcrypt hash still hard-coded |
| Security | 8.5 | Host check is switched off by `ALLOW_INSECURE_BIND`; implicit subdomain wildcard; login lockout keyed by IP only (shared-IP lockout behind a proxy); session token returned in JSON body |
| Docker / deployment | 8.5 | Compose still mounts all of `/` read-only; cookie `Secure` flag depends on proxy headers |
| Data accuracy | 8.5 | Metrics history is in memory only (lost on restart) |
| Frontend function | 8.5 | `dist/` freshness not proven; 105 `any` types remain |
| Design / UX polish | 8 | 109 hard-coded hex colors left; three 1,200–1,900 line components; visual pass never done from screenshots |
| Accessibility | 8 | axe passes on the listed screens, but only the screens in `axe-audit.mjs`; no keyboard-only/screen-reader pass |
| Tests / CI | 8.5 | 254 test functions + lint in CI is good; no coverage gate, no test for items below |
| Docs / hygiene | 8.5 | Version string duplicated in `app.py`; stale files still in repo root |

### Limits of this review (read this)
- **Static review only.** The sandbox had no network, so Python and npm dependencies could not be installed. **The app, the tests, `tsc`, ESLint and the build were not run.** `python -m compileall -q portly` **passed**.
- Tags:
  - **[Verified]** — confirmed by reading the exact code path.
  - **[Verify first]** — strongly suspected; reproduce on a real machine before changing code. If it does not reproduce, say so in the commit and move on.
- Read in full: `auth.py`, the middleware, CORS/CSRF, all auth routes, the exec route, the SSE route and broadcaster, SPA mount, `health.py` (safe-host + redirects), `sw.js`, `Dockerfile`, `docker-compose.yml`, `tsconfig.json`, `package.json`, CI files. Spot-checked with grep: everything else. **Not read line by line:** most of `docker_actions.py`, `store.py` import/export, and most `frontend/src/components/*.tsx`. Treat those as *unreviewed*, not *clean*.

---

## 1. Rules for the agent

1. **Reproduce before fixing** anything tagged *[Verify first]*.
2. **One item = one commit**, item ID in the message (e.g. `N-1`). Add or update a test in the same commit.
3. **Never weaken Safe Mode, auth, CSRF or Host validation.** If a fix needs a security trade-off, choose the safer option and note the decision in `CHANGELOG.md`.
4. **Keep API and UI in sync.** If a response shape changes, update `api.ts`, `types.ts`, `docs/API.md` and tests together.
5. **No new runtime network dependencies** (CDNs, analytics, remote fonts). Portly is local-first.
6. `portly/frontend/dist` is committed. Rebuild after any frontend change.
7. **Before every commit run:**
   ```bash
   pip install -r requirements.txt pytest-asyncio pytest-cov ruff
   python -m compileall -q portly
   ruff check portly tests
   PORTLY_TESTING=1 python -m pytest tests -q --ignore=tests/e2e
   cd portly/frontend && npm ci && npm run lint && npm test && npm run build
   ```
8. Do not "clean up" unrelated code. Do not rename public env vars or API paths.
9. Trust the code over old planning docs (`docs/archive/*`).

---

## 2. Already fixed since round 2 — DO NOT REDO

Verified present in the code:

| Old ID | What is now in place |
|---|---|
| P0-1 / L-6 | `_parse_host` handles `[v6]:port`; IP-literal Hosts accepted; helpful `INVALID_HOST` message; `PORTLY_ALLOWED_HOSTS` documented in compose + DEPLOYMENT.md |
| P0-2 | `reveal-env` route (line ≈996) is declared before the bare `/api/apps/{app_id:path}` route (≈1020) |
| P0-3 / P0-4 | Compose uses a named volume `portly-data` and has `build: .` |
| L-1 | cgroup v2 CPU (`online_cpus`) and memory (`inactive_file`) handled |
| L-2 | Stats collected with `ThreadPoolExecutor`; `stats_age_sec` exposed |
| L-3 | Custom apps default to `unknown`; unreadable metrics are `None` |
| L-4 / L-5 | Health checks no longer follow redirects; TCP check uses `create_connection` (IPv6 works) |
| L-8 | Self password change keeps this browser signed in, revokes other sessions |
| L-9 | CSV formula injection and Markdown `\|` escaped in export |
| L-10 | `initialLoadError` state, Retry button, "Connection lost" bar |
| L-11 | "Limited host visibility (not running as root)" notice in System drawer |
| S-1 / S-2 | CSP is `script-src 'self'`, `connect-src 'self'` |
| S-4 | Setup token stored as hash only (migration v4 drops `token_plain`) |
| S-5 | Favicon route now requires auth |
| S-6 | Webhook sender blocks internal hosts and redirects (opt-in env var exists) |
| T-1 / T-2 | Vitest + ESLint + ruff exist and run in CI; `noUnusedLocals`/`noUnusedParameters` are on |
| T-4 | No hard-coded test counts in docs |
| D-1 / D-2 | Toast/ConfirmDialog use tokens (one hex left); all dialogs/drawers use `useFocusTrap` |

---

## 3. Work items

### Phase A — Real bugs and hardening (do first, in this order)

#### N-1 · SSE subscriber queue can leak and eventually lock everyone out **[Verify first]**
- **Where:** `portly/backend/app.py`, `sse_stream` (≈ lines 2423–2468).
- **Problem:** `_sse_subscribers.append(q)` runs **before** the `event_generator()` starts. The generator's `finally` (which removes the queue) only runs if the generator was started. If anything between the `append` and the first iteration raises (for example `get_current_stats(...)`, `is_docker_available()`, `redact_app_for_summary`) or the client disconnects before streaming begins, the queue stays in the list forever. The route refuses new streams at 64 subscribers (`SSE_LIMIT`), so repeated failures eventually make the live view return 503 until Portly restarts.
- **Fix:**
  1. Build the snapshot **first** (no registration yet).
  2. Register the queue **inside** `event_generator()` as its first statement, inside the same `try` whose `finally` removes it.
  3. Put the initial snapshot into the queue after registration.
  4. Keep the 64 cap check, but count only registered queues.
- **Acceptance:** unit test that monkeypatches `get_current_stats` to raise: call `sse_stream` 70 times; `len(_sse_subscribers)` stays 0 and the 71st valid call still succeeds.

#### N-2 · Host-header protection is fully disabled by `PORTLY_ALLOW_INSECURE_BIND`, and subdomains are accepted implicitly **[Verified]**
- **Where:** `app.py` `security_and_csrf_middleware` (≈ lines 354–381).
- **Problem:**
  - `PORTLY_ALLOW_INSECURE_BIND=true` means "I accept binding without an admin". The same flag also turns **off** DNS-rebinding protection for hostnames. Two unrelated safety checks share one switch. With zero users and this flag set, a rebinding page could reach an unauthenticated admin API.
  - `any(host_header.endswith(f".{ah}") ...)` silently allows **every subdomain** of every allowed host (so `PORTLY_ALLOWED_HOSTS=example.com` also allows `anything.example.com`). This is not documented, and a taken-over or dangling subdomain would be accepted.
- **Fix:**
  1. Remove the `ALLOW_INSECURE_BIND` exemption from the Host check. Keep only the `PORTLY_TESTING=1` exemption.
  2. Replace the implicit subdomain wildcard with an explicit syntax: only entries written as `*.example.com` in `PORTLY_ALLOWED_HOSTS` match subdomains. Document it in README, `docs/DEPLOYMENT.md` and the compose comment.
  3. Compute the allowed-host set once per request cheaply: cache `public_host` (see N-7) instead of reading SQLite on every request.
- **Acceptance (tests):**
  - `ALLOW_INSECURE_BIND=1`, `Host: evil.example.com` → 400 `INVALID_HOST`.
  - `PORTLY_ALLOWED_HOSTS=example.com`, `Host: a.example.com` → 400; with `*.example.com` → 200.
  - IP-literal Hosts still → 200.

#### N-3 · Login lockout is keyed by IP only, so one client behind a proxy can lock everyone out **[Verified]**
- **Where:** `app.py` `auth_login` (`auth.check_rate_limit(ip)`), `auth.py` `check_rate_limit` / `record_failed_attempt`.
- **Problem:** the key is the client IP only. If Portly is behind a reverse proxy and `PORTLY_TRUSTED_PROXIES` is not set, every request appears to come from the proxy's IP. Five wrong passwords from anyone lock **all users out for 15 minutes**. The setup-token check shares the same key and the same lockout. There is also no per-username limit, so a distributed attacker is not slowed.
- **Fix:**
  1. Rate-limit on **two** keys: `ip:<ip>` (looser, e.g. 20 / 15 min) and `user:<lowercased username>` (strict, e.g. 5 / 15 min). Block if either is exceeded.
  2. Use a different key prefix for setup attempts (`setup:<ip>`).
  3. If requests carry `X-Forwarded-For` but `PORTLY_TRUSTED_PROXIES` is empty, log a **one-time warning** at startup/first request and show it in the System drawer ("Behind a proxy? Set PORTLY_TRUSTED_PROXIES").
  4. Keep the generic error text (do not reveal which key blocked).
- **Acceptance:** 5 failures for user `a` from IP 1 do not block user `b` from IP 1; 5 failures for `a` from five different IPs block `a`.

#### N-4 · First-run setup is not atomic (two requests can both succeed) **[Verify first]**
- **Where:** `app.py` `auth_setup` (≈ lines 2229–2264).
- **Problem:** it checks `get_user_count() > 0`, verifies the setup token, creates the user, then consumes the token as separate steps. Two parallel requests with the same valid token can both pass the checks, giving two admin users (or one admin whose password the attacker chose).
- **Fix:** do "count == 0 → verify token → create admin → consume token" inside **one** SQLite transaction (e.g. `BEGIN IMMEDIATE`), or guard the whole function with a process-wide lock plus a re-check of the user count inside the lock.
- **Acceptance:** test that fires two concurrent `POST /api/auth/setup` calls (threads) with the same token; exactly one returns 200, the other returns 400 `SETUP_DONE`, and `list_users()` has one user.

#### N-5 · Dummy bcrypt hash is still a hard-coded string (round-2 item L-7, not fixed) **[Verify first]**
- **Where:** `portly/backend/auth.py` line ≈ 40 (`DUMMY_BCRYPT_HASH`), `verify_dummy_password` (≈155).
- **Problem:** the string looks hand-typed (the last digest character `3` is not a character a real bcrypt digest can end with). Depending on the `bcrypt` build, `checkpw` may raise "Invalid salt" immediately. `verify_dummy_password` swallows all exceptions, so the timing equalisation for unknown usernames could silently do nothing, and a login for a non-existent user would return faster than for an existing one.
- **Fix:** generate it at import time with the same cost as real hashes:
  ```python
  DUMMY_BCRYPT_HASH = bcrypt.hashpw(b"portly-dummy", bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()
  ```
  (use the same rounds constant as `hash_password`). Remove the bare `except Exception: pass` or at least log at debug level.
- **Acceptance:** test that `bcrypt.checkpw(b"x", DUMMY_BCRYPT_HASH.encode())` returns `False` without raising, and that `verify_dummy_password` takes within ~2× the time of a failed real check.

#### N-6 · Session token is returned in the JSON body of login/setup **[Verified]**
- **Where:** `app.py` `auth_login` and `auth_setup` (`return {"status": "ok", "token": token, ...}`).
- **Problem:** the cookie is `HttpOnly`, but the same token is also handed to JavaScript. Any XSS (or a malicious browser extension) can read it, which cancels the benefit of `HttpOnly`.
- **Fix:** return the token in the body **only** when the client explicitly asks for it (e.g. header `X-Portly-Client: cli` or `?return_token=1`), and keep the web UI cookie-only. Update `cli.py`, `api.ts`, `docs/API.md` and tests accordingly. (If the frontend does not read `token` today, simply drop it for browser calls.)
- **Acceptance:** a normal browser-style login response has no `token` key; the CLI path still gets one.

#### N-7 · SQLite query on every HTTP request in the middleware **[Verified]**
- **Where:** `app.py` middleware line ≈ 369 (`store.get_setting("public_host")`); also called for every `/assets/*` and SSE request.
- **Problem:** unnecessary per-request DB work, and it makes the middleware depend on DB availability.
- **Fix:** cache `public_host` in memory; refresh it when settings are saved (the settings PATCH handler) and at startup. Same for `_dashboard_origins()` inputs.
- **Acceptance:** test that 100 requests perform ≤ 1 `get_setting("public_host")` call (spy on `store.get_setting`), and that changing the setting takes effect on the next request.

#### N-8 · Security headers missing on early (400/403) responses **[Verified]**
- **Where:** `security_and_csrf_middleware`: the early `return JSONResponse(...)` branches skip the header block at the bottom.
- **Fix:** build one `_apply_security_headers(response)` helper and call it on every return path.
- **Acceptance:** a request rejected with `INVALID_HOST` or `CSRF_DETECTED` still carries `X-Content-Type-Options`, `X-Frame-Options` and the CSP header.

#### N-9 · `Cache-Control` for the SPA shell and service worker **[Verify first]**
- **Where:** `app.py` `serve_spa`, `get_service_worker`, `get_manifest` return `FileResponse` with no cache headers.
- **Problem:** without explicit headers, browsers may heuristically cache `index.html` and `sw.js`, so users can keep an old UI after an upgrade even though `sw.js` bumps its cache name.
- **Fix:** `index.html`, `sw.js`, `manifest.webmanifest` → `Cache-Control: no-cache`; `/assets/*` (hashed filenames) → `public, max-age=31536000, immutable`.
- **Acceptance:** tests assert those headers.

#### N-10 · Cookie `Secure` flag behind a TLS-terminating proxy **[Verify first]**
- **Where:** `app.py` (login, setup, password change): `is_secure = request.url.scheme == "https" or PORTLY_COOKIE_SECURE`.
- **Problem:** behind Caddy/nginx/Traefik terminating TLS, uvicorn sees `http`, so the cookie is **not** `Secure` unless `PORTLY_COOKIE_SECURE=1` is set. Nothing in the UI warns the admin.
- **Fix:** also honour `X-Forwarded-Proto: https` **only when the peer is in `PORTLY_TRUSTED_PROXIES`**; add a line to `docs/DEPLOYMENT.md` and `SECURITY.md`; add the warning from N-3 item 3 to the System drawer.
- **Acceptance:** with trusted-proxy config and `X-Forwarded-Proto: https`, `Set-Cookie` contains `Secure`; without trust, it does not.

#### N-11 · Compose still mounts the whole host filesystem (round-2 S-3) **[Verified]**
- **Where:** `docker-compose.yml` (`/:/hostfs:ro`, `pid: host`, `network_mode: host`, Docker socket).
- **Problem:** `/:/hostfs:ro` exposes every host file (including `/etc/shadow`, SSH keys if readable by the container user) to a container that also has the Docker socket. Disk-usage stats do not need that.
- **Fix:**
  1. Find what `PORTLY_HOSTFS` is really used for (`stats.py` disk usage). Mount only the specific paths needed (for example `/var/lib/docker:/hostfs/var/lib/docker:ro`, or use `statvfs` on a small mount), or make the full `/` mount an **opt-in** (commented) line.
  2. Add the "Docker socket is root-equivalent" warning near the volumes in the compose file and in `docs/DEPLOYMENT.md` (the `:ro` on the socket does not make it safe).
- **Acceptance:** default compose has no `/:/hostfs` line; System drawer still shows disk usage (or a clear "Host disk stats not mounted" message instead of wrong numbers).

#### N-12 · Version string is duplicated **[Verified]**
- **Where:** `app.py` line ≈ 269 `FastAPI(..., version="1.1.0")`; also `pyproject.toml`, `portly/__init__.py`, `frontend/package.json`.
- **Fix:** use `from portly import __version__` in `app.py`; use `[tool.setuptools.dynamic] version = {attr = "portly.__version__"}` in `pyproject.toml`. Add a test that `package.json` version equals `portly.__version__`.
- **Acceptance:** test passes; bumping `__init__.py` is the only edit needed for a release (plus `package.json`, which the test guards).

---

### Phase B — Frontend and design polish

| ID | Where | Problem | Fix | Acceptance |
|---|---|---|---|---|
| D-3 | `frontend/src/**/*.tsx` | **109** hard-coded hex colors remain (down from 732). `ConfirmDialog.tsx:93` uses `#0B1220`. Two overlapping stylesheets (`style.css`, `app.css`). | Replace each hex with a token from `tokens.css` (add tokens where missing). Remove duplicate rules between `style.css` and `app.css`. One component per commit. | `grep -rE "#[0-9A-Fa-f]{3,6}\b" frontend/src --include=*.tsx` returns only intentional brand/icon colors, each commented. All 4 themes (dark, light, OLED, system) look correct. |
| D-7 | `AppDetailModal.tsx` (1,914 lines), `AddAppModal.tsx` (1,220), `App.tsx` (1,325), `app.py` (2,532) | Files are too large to review or change safely; this is also why parts of them stayed unreviewed. | Pure refactor, **no behavior change**: split detail modal tabs into `components/detail/*.tsx`; split `app.py` into `routers/{apps,auth,users,settings,stream,export}.py` using `APIRouter` — **keep route declaration order** (see round-2 P0-2: the bare `/api/apps/{app_id:path}` route must stay last among GETs). One extraction per commit. | All tests green after each commit; add a test that fails if any `GET /api/apps/{app_id:path}/<suffix>` route is declared after the bare detail route. |
| D-8 | `tsconfig`/ESLint | 105 `any`/`as any` usages. | Replace with types from `types.ts` (add types for API responses). Turn on `@typescript-eslint/no-explicit-any` as `warn`, then `error` once at zero. | Lint passes with the rule at `error`. |
| D-6 | Visual pass | Design has never been checked from screenshots. | Screenshot at 360, 768, 1280, 1920 px in dark and light: long container names truncate with a tooltip, tables scroll horizontally on mobile, touch targets ≥ 44 px, focus ring visible on every control, no layout shift when the SSE snapshot arrives. | Screenshots committed to `docs/screenshots/` (or attached to the PR) and each defect fixed. |
| D-9 | `scripts/axe-audit.mjs`, e2e | axe covers a fixed list of screens only. | Add the **detail modal (all tabs)**, Customize drawer, System drawer, User Management drawer, Command Palette, login and setup screens, in dark and light. Run it in the Playwright e2e job. | axe: 0 serious/critical on every listed screen. |
| D-10 | Whole UI | No keyboard-only or screen-reader pass. | Tab through: login → grid → open detail → close → palette (`Ctrl/Cmd+K`) → drawers. Check focus returns to the opener, Esc closes the top-most layer only, toasts use `role="status"`/`role="alert"` correctly, live updates do not steal focus. | Written checklist in `docs/ACCESSIBILITY.md`, all items pass. |
| D-11 | `dist/` | Cannot prove the committed `dist/` matches the source. | Run `npm ci && npm run build`; commit the rebuilt `dist/`. Add a CI step that rebuilds and fails if `git diff --exit-code portly/frontend/dist` is non-empty. | CI step passes. |

---

### Phase C — Tests

| ID | Problem | Fix |
|---|---|---|
| T-9 | No tests for N-1 … N-12. | Add the acceptance tests listed in each item. |
| T-10 | No coverage gate (`pytest-cov` is installed but not enforced). | Add `--cov=portly --cov-fail-under=<current-5>` in CI for the backend; ratchet up over time. |
| T-11 | Route-order regression can return when `app.py` is split. | Add the route-order test from D-7. |
| T-12 | E2E smoke. | Ensure the e2e job covers: fresh start → setup screen → create admin → dashboard loads → logout → login → viewer account cannot see mutation controls. |
| T-13 | Old files. | Move `PORTLY_REVIEW_AND_FIX_PLAN.md` (round 2) to `docs/archive/`; keep this file in `docs/` as the current plan; keep `.impeccable/` out of the repo root or document it in `AGENTS.md`. |

---

## 4. Features to add or improve (recommendations, after Phases A–C)

Prioritized. These are **not bugs**.

1. **API tokens for automation (not present).** Personal tokens (hashed in SQLite, shown once, scopes `read` / `admin`, expiry, revoke). Let `cli.py` talk to a remote Portly over HTTP instead of opening the SQLite file directly.
2. **Persisted metrics history (not present).** Today CPU/RAM history lives in an in-memory `deque` (`stats.py`) and disappears on restart; only health history is in SQLite (`health_history`). Store downsampled samples (e.g. 1-min for 24 h, 15-min for 7 d) with retention cleanup.
3. **Alert rules (not present).** Webhooks exist, but only for fixed events. Add rules: "port X down > N min", "new port opened on `0.0.0.0`", "container restarted > N times in 1 h", with per-rule cooldown and a test-send button.
4. **Optional 2FA (TOTP)** and **forward-auth / OIDC header trust** (Authelia, Authentik, Caddy) behind `PORTLY_TRUSTED_PROXIES`. None exists yet.
5. **Session management.** List active sessions per user, "sign out other devices", sliding expiry (sessions are fixed 7 days).
6. **Scheduled backups.** Automatic export to `data/backups/` with retention, and a restore **preview** ("this will change N items") before applying.
7. **Quick filters and URL-persisted filter state:** "listening on `0.0.0.0` only", "unhealthy only", "changed in last hour".
8. **Port-change safety net (partly exists).** A rollback path exists in the code; make sure the UI shows an obvious **Undo** toast after a remap and lists likely dependents (compose `depends_on`, reverse-proxy configs generated by `proxy_gen.py`).
9. **First-run diagnostics panel.** One screen: Docker socket reachable? root or not? `pid: host` active? host FS mounted? Docker API version? Behind a proxy without `PORTLY_TRUSTED_PROXIES`? (Several of the N-items above would surface here.)
10. **Longer term:** multi-host agent mode — only after everything above is solid.

---

## 5. Suggested execution order

1. **N-1, N-4, N-5** (bugs), then **N-2, N-3, N-6** (security), then **N-7 … N-12**.
2. **T-9, T-11** right after each N-item (tests in the same commit).
3. **D-11**, **D-3**, **D-8**, then **D-7** (refactor last of the code items, with the route-order test already in place).
4. **D-6, D-9, D-10** (visual/accessibility passes) once the code is stable.
5. **T-10, T-12, T-13**.
6. Section 4 features, in order.

---

## 6. Definition of done (all must be true)

- [ ] `ruff`, `compileall`, backend tests, `npm run lint`, `npm test`, `tsc`/build and the e2e smoke test all pass in CI (GitHub, Forgejo, GitLab files kept aligned).
- [ ] Repeated failing/aborted `/api/stream` requests never reach the 64-subscriber cap (N-1).
- [ ] `PORTLY_ALLOW_INSECURE_BIND` no longer disables Host validation; subdomains need `*.` syntax (N-2).
- [ ] Lockout is per user and per IP; one client cannot lock out all users (N-3).
- [ ] Concurrent first-run setup yields exactly one admin (N-4).
- [ ] `DUMMY_BCRYPT_HASH` is generated at import and verified by a test (N-5).
- [ ] Browser login responses contain no session token in the body (N-6).
- [ ] Early error responses carry security headers; SPA shell/SW are `no-cache`, hashed assets are `immutable` (N-8, N-9).
- [ ] Default compose file does not mount `/` (N-11).
- [ ] One version source of truth, guarded by a test (N-12).
- [ ] `grep` for hex colors in `.tsx` shows only intentional, commented values (D-3); no `any` (D-8).
- [ ] axe: 0 serious/critical on all listed screens in dark and light (D-9); keyboard checklist passes (D-10).
- [ ] `dist/` is rebuilt and CI proves it matches the source (D-11).
- [ ] The old round-2 plan is archived; this file is the only active plan.

---

## Appendix A — Things already done well (keep them)

- Safe Mode on by default and enforced **server-side**, with auto-relock.
- Sessions stored as SHA-256 hashes, DB-authoritative; role changes, deletion and logout take effect immediately; last admin cannot be demoted or deleted.
- CSRF validates Origin/Referer and `Sec-Fetch-Site`; `Origin: null` is rejected; CORS limited to configured origins.
- Health checks: SSRF guard on hosts (including DNS-resolved addresses), redirects not followed.
- SVG favicon sanitization and a locked-down CSP on icon responses.
- Env-var masking with an audited, admin-only reveal.
- Atomic backup import; SQLite WAL; parameterized SQL.
- Docker stats: cgroup v1/v2 correct, concurrent collection, staleness exposed.
- Honest "unknown" state instead of fake zeros.
- Self-hosted fonts, no CDN; service worker excludes `/api` and the stream; bounded asset cache.
- Broad tests (254 functions incl. an auth matrix), lint and e2e jobs in CI.

## Appendix B — Quick reproduction snippets

**N-1 (SSE leak)**
```python
# tests/test_sse_leak.py
import pytest
from portly.backend import app as appmod

def test_sse_registration_not_leaked(monkeypatch, admin_client):
    monkeypatch.setattr(appmod, "get_current_stats", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    for _ in range(70):
        admin_client.get("/api/stream")           # expect 500, not a leak
    assert len(appmod._sse_subscribers) == 0       # fails today
```

**N-2 (Host check disabled by insecure flag)**
```bash
PORTLY_ALLOW_INSECURE_BIND=1 python -m portly run --port 5533 --host 0.0.0.0 &
curl -i -H "Host: evil.example.com" http://127.0.0.1:5533/api/health
# Today: 200 (host check skipped). Expected after fix: 400 INVALID_HOST.
```

**N-5 (dummy hash)**
```python
import bcrypt
from portly.backend import auth
try:
    print(bcrypt.checkpw(b"x", auth.DUMMY_BCRYPT_HASH.encode()))
except Exception as e:
    print("INVALID DUMMY HASH:", e)   # if this prints, the timing guard is a no-op today
```
