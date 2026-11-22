# AGENTS.md — Portly

## What this is
Self-hosted port/process/container dashboard. One Python package (`portly`) with a React frontend at `portly/frontend/` that is **served by the backend** from `portly/frontend/dist` (FastAPI SPA catch-all + `/assets` mount in `backend/app.py`). No separate web server in production.

## Commands (exact)
- Setup: `pip install -r requirements.txt` then `pip install -e .`; frontend: `cd portly/frontend && npm install`.
- Run backend: `python -m portly run --port 5533` (uvicorn target `portly.backend.app:app`; default host `127.0.0.1`, mode `desktop`).
- Run frontend dev: `cd portly/frontend && npm run dev` — Vite on `:5173`, proxies `/api` → `http://127.0.0.1:5533`.
- Build frontend: `npm --prefix portly/frontend run build` → `tsc && vite build`, output to `portly/frontend/dist`.
  - **`portly/frontend/dist` is committed to git.** Rebuild after any frontend source edit so local `python -m portly run` and the committed artifact stay in sync. Docker/CI rebuild it fresh.
- Unit/integration tests: `python -m pytest tests --ignore=tests/e2e -q`. `pyproject.toml` already sets `addopts = ... --ignore=tests/e2e`.
  - `tests/conftest.py` sets `PORTLY_TESTING=1` and `PORTLY_DATA_DIR=tests/test_data_dir` **before app import** — do not set these manually for unit tests (CI sets `PORTLY_TESTING=1` redundantly).
  - Single test: `python -m pytest tests/test_auth.py -q`.
- E2E tests (separate, not in the default run): need `pip install pytest-playwright playwright` + `playwright install chromium` and a built frontend. Run `python -m pytest -o addopts= tests/e2e -q` (`-o addopts=` clears the default e2e ignore). Skipped entirely if playwright is not installed.
  - `tests/e2e/conftest.py` **removes** `PORTLY_TESTING`, starts a real server on a random port with a temp SQLite DB pre-seeded with an admin session cookie; no Docker needed.
- CI parity extras **not in requirements.txt**: `pytest-asyncio`, `pytest-cov` (backend); `pytest-playwright`, `playwright` (e2e). `python -m compileall -q portly` is a CI syntax gate.
- CI exists in three places: `.github/workflows/ci.yml`, `.forgejo/workflows/ci.yml`, and `.gitlab-ci.yml` — all run lint + backend + frontend + e2e. Keep them aligned when changing test/build steps.
- Forgejo Actions runs on an `act` runner where `actions/setup-python@v5` cannot resolve Python 3.12 for the OS ("version not found"). Keep `.forgejo/workflows/ci.yml` on its python3-venv/apt bootstrap; only GitHub/GitLab use pinned setup actions.

## Structure / entrypoints
- CLI: `portly/cli.py:main` — console script `portly` and `python -m portly`; subcommands `run`, `list`, `start`, `stop`, `open`, `check-port`, `suggest`, `logs`.
- Backend: `backend/app.py` (~2300 lines) holds all API routes, security middleware, and the SPA mount. Supporting modules: `store.py` (SQLite, WAL), `auth.py` (sessions/RBAC/setup token), `discovery/{host,docker_src,merge}.py` (ports, stable IDs, conflict merge), `actions/{docker_actions,process_actions}.py` (mutations), plus `proxy_gen.py`, `tls_inspector.py`, `stats.py`, `health.py`, `favicon.py`, `categories.py`, `notifications.py`.
- Frontend: `src/App.tsx` is the shell, `src/api.ts` the API client, `src/components/*` the views. Styling layers: `src/styles/tokens.css` (design tokens) → `style.css` → `app.css`. TypeScript `strict: true` but `noUnusedLocals`/`noUnusedParameters` are off.
- Data: SQLite DB, snapshots, icons, certs live in `PORTLY_DATA_DIR` (default repo `data/`, gitignored, plus `*.db*`). Never commit DB files.

## Environment variables that change behavior
- `PORTLY_PORT` (5533), `PORTLY_HOST` (127.0.0.1), `PORTLY_MODE` (`desktop`|`server`). Server mode with zero users prints a **single-use setup token to stderr**; admin is created in the UI.
- Binding `0.0.0.0`/`::` with no admin in non-server mode exits unless `PORTLY_ALLOW_INSECURE_BIND=1`.
- `PORTLY_TESTING=1` skips lifespan discovery/auto-start/background pollers, relaxes CORS + host validation, and disables Docker event/stats threads. Set by unit conftest; e2e intentionally unsets it.
- Others: `PORTLY_DATA_DIR`, `PORTLY_HOSTFS` (host root inside Docker for disk stats), `PORTLY_LOG_DIRS`, `PORTLY_SETUP_TOKEN`, `PORTLY_METRICS_TOKEN`, `PORTLY_CORS_ORIGINS`, `PORTLY_ALLOWED_HOSTS`, `PORTLY_TRUSTED_PROXIES`, `PORTLY_COOKIE_SECURE`.
- CSRF + Host-header validation middleware applies to all `POST/PUT/PATCH/DELETE`.

## Conventions / gotchas
- Safe Mode is on by default and gates mutations; new mutating endpoints/actions must respect it (see `tests/test_actions_safe_mode.py`, `tests/test_audit_backend_fixes.py`).
- CSRF middleware rejects mutating requests carrying neither `Origin` nor `Referer` outside `PORTLY_TESTING` (non-browser clients must send `Origin`). Vite's `:5173` origins are trusted only when `PORTLY_TESTING`/`PORTLY_DEV` is set.
- Overlays (modals/drawers) render inside `#portly-app-root`; `useFocusTrap` must inert only background siblings, never the root — root-wide inert disables the dialogs themselves and broke 7 e2e tests.
- UI must not use `alert()`/`confirm()` — use `Toast` / `ConfirmDialog` with ARIA roles and `useFocusTrap`.
- Local-first/offline: no external CDN fonts, styles, or scripts; fonts are vendored in `portly/frontend/public/fonts`.
- Discovery is cross-platform: `discovery/host.py` falls back to `netstat -ano` / `lsof`; keep stable ID prefixes `docker:`, `host:`, `custom:`.
- Docker discovery degrades gracefully when no daemon is reachable; tests mock it — do not depend on a live Docker socket in tests.
- `PORTLY_FIX_PLAN.md`, `Portly-build-prompt.md`, and `docs/review/` are historical planning/review notes, not authoritative specs. Trust code and config over them.
