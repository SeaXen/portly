# Changelog ⚓

All notable changes to Portly are documented in this file.

## [Unreleased]

### ⚡ Feature Enhancements
- **Themes**: Added System (follows OS colour scheme) and OLED (true-black) themes alongside Dark/Light, with a theme selector in the Customize drawer.
- **Custom Accent**: Added a custom accent colour picker; accent now recolours buttons, active states, rings and scrollbars instead of only the focus ring.
- **Bundled Fonts**: Inter and JetBrains Mono are self-hosted, so the designed typography works offline.

### 🩹 Fixes
- Accent and density now persist in settings and apply on load instead of resetting on reload.
- Serialized settings writes so rapid theme switching cannot save an older value last.

## [0.1.1] - 2026-11-18

### ⚡ Feature Enhancements
- **Unhide Support**: Added a `Hidden (N)` toggle in the toolbar to reveal hidden ports, plus an `Unhide` bulk action (`{"action":"unhide"}` on `POST /api/apps/bulk`). The dashboard now fetches with `include_hidden=true` and filters client-side so the toggle is instant.
- **Image Update Repair**: Image checks now compare registry digests with the image's `RepoDigests`, show an honest "Not checked"/"Unknown" state, and offer a working Apply button. Admin-configured `update_cmd` can now be run for custom apps via `POST /api/apps/{id}/update/custom`.
- **Webhook Settings**: `webhook_enabled` and the Telegram webhook type can now be saved from the Alerts drawer.
- **Backup Restore**: Added "Restore Backup" to the Export menu, wired to `POST /api/import`.
- **Viewer Role Gating**: Viewer accounts no longer see bulk/quick mutation controls; mutating modal actions are disabled.
- **Toolbar Filters & Sorting**: Added tag filtering and status, category and manual-order sorting.
- **Bulk Feedback**: Bulk actions now report succeeded/failed items in toasts instead of silently discarding failures.
- **Live Docker Status**: The Docker-unavailable banner now clears/updates from SSE events.

### 🩹 Fixes
- Corrected misleading "Tunnel URL" badges to use the app's actual URL override.
- `start_on_boot` and save-time custom-app starts now bypass the interactive safe-mode gate.
- Detail views read the last polled health snapshot instead of probing the network on every open; the poller honours per-app `health_interval` and checks due apps concurrently.
- Bumped the service-worker cache version so updated UI assets are picked up.
- Aligned `docs/API.md` with the implemented endpoints, exec allowlist and rate-limit window.

## [1.1.0] - 2026-11-17

### 🚨 Critical Fixes & Stability (P0)
- **First-Run Stability (P0-1)**: Fixed first-run crash on `0.0.0.0` in Docker by defaulting `PORTLY_MODE=server`, generating single-use setup token to `stderr`, and adding minimal `/api/health` healthcheck endpoint.
- **Port Remap Recreate Crash (P0-4)**: Fixed missing HostConfig parameters on container port remap recreation by preserving mounts, network mode, environment, and labels.
- **Compose Multi-Container Crash (P0-5)**: Fixed multi-container Compose down/start actions by inspecting `com.docker.compose.project` labels and managing the entire stack correctly.
- **Docker Client Reconnection (P0-6)**: Fixed thread lock and background reconnection runaway in `docker_src.py`; added testing guard to prevent mock memory exhaustion.
- **Degraded Status Bug (P0-7)**: Fixed HTTP health probes to correctly classify non-2xx/3xx responses as degraded/down rather than active.
- **Synthetic Metric Padding (P0-8)**: Removed fake synthetic CPU ramp telemetry; wired `PORTLY_HOSTFS` for true host filesystem metrics.

### 🛡️ Security Hardening (S)
- **Timing-Safe Auth & Dummy Verification (S-1)**: Replaced raw string password comparisons with timing-safe HMAC digests and executed dummy password verification to eliminate timing attacks on invalid usernames.
- **Rate Limiting (S-1)**: Added in-memory rate limiting locking out IPs/usernames after 5 failed attempts for 15 minutes (HTTP 429).
- **Session Token Hashing (S-2)**: Persisted session tokens as SHA-256 hashes; raw tokens are never saved to SQLite.
- **Password Strength Validation (S-3)**: Enforced minimum 10 characters for user passwords.
- **Host Filesystem Isolation (S-4)**: Updated Docker Compose mount to `/:/hostfs:ro` and configured `PORTLY_HOSTFS=/hostfs`.
- **Sensitive Environment Variable Masking (S-5)**: Redacted passwords, tokens, API keys, and secret values in container env displays; added admin-only audit-logged reveal endpoint (`/api/apps/{id}/inspect/reveal-env`).
- **Audit Logging Engine (S-6)**: Created structured audit logging tracking all administrative mutations.
- **DER x509 TLS Inspection (S-7)**: Rewrote TLS certificate parsing with `cryptography.x509` and SNI extension support.
- **SVG Sanitization (S-8)**: Stripped `<script>` tags, inline event handlers (`onload`, `onerror`), and `javascript:` URIs from SVG favicons.
- **Process Log Traversal Protection (S-10)**: Enforced strict directory allowlist on process log reading, blocking `/etc/passwd` and system files.
- **Command Injection Prevention (S-11)**: Enforced safe command allowlist for container `exec` with 256 KB output truncation and shell operator blocking.
- **CSRF & Security Headers (S-12)**: Required `X-Portly-Client: 1` header for mutating requests; injected CSP, HSTS, X-Frame-Options, and Referrer-Policy headers.

### ⚡ Feature Enhancements (F)
- **User & RBAC Management (F-1)**: Implemented full user CRUD (`GET/POST /api/users`, `DELETE /api/users/{id}`, `PATCH /api/users/{id}/role`, `POST /api/users/{id}/password`) and added User Management Drawer in UI.
- **CLI Subcommands (F-4, F-6)**: Added `portly open`, `portly check-port`, `portly suggest`, and `portly logs` subcommands.
- **Preflight Port Collision Engine (F-5)**: Added `POST /api/ports/preflight` and interactive UI tab in Add App modal to validate ports declared in `docker run` or `docker-compose.yml` before launching.
- **Safe Mode Auto-Relock (F-10)**: Added temporary 5-minute unlock timer with visible countdown banner and automatic re-locking.

### 🎨 Design & Accessibility Polish (D)
- **Accessible Dialogs & Toasts (D-1, D-2)**: Completely eliminated browser `alert()` and `confirm()` calls; replaced with accessible focus-trapped `ConfirmDialog` and `Toast` notifications.
- **Pinned Items Sort Order (D-4, P1-20)**: Memoized `displayedApps` to ensure pinned services stay pinned to the top across all views (Table, Grid, List, Board).
- **Zero External CDNs (D-5)**: Removed external Google Fonts links; converted to modern system typography stack.
- **Global Command Palette Shortcut (D-6)**: Fixed `Ctrl+K` / `Cmd+K` keydown listener to trigger from anywhere, including when text inputs have focus.
- **Saved Views Restoration (P1-15)**: Enhanced view tabs to load saved filters, sorting, grouping, and view type dynamically.

### 🧪 Test Coverage & Reliability (R, T)
- **Comprehensive Auth Matrix Tests (T-1)**: Created `tests/test_auth_matrix.py` testing RBAC enforcement across all endpoints.
- **Security Boundaries Tests (T-2, T-3, T-5, T-6)**: Created `tests/test_security_p0.py` verifying SSRF protections, command allowlists, log allowlists, and protocol disambiguation.
- **Concurrency & SQLite Stress Tests (T-4)**: Created `tests/test_store_concurrency.py` verifying multi-threaded concurrent writes and PRAGMA user_version migrations.
- **Total Tests Passing**: 136 tests passing (100% pass rate).
