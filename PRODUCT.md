# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Self-hosters, software engineers, DevOps practitioners, homelab operators, and systems administrators running diverse sets of local services, databases, development servers, and containerized stacks (Docker, Docker Compose, Podman). They require instant glanceable control over runtime states, proactive port collision prevention, and audit-logged operations.

## Product Purpose

Portly provides a unified, zero-overhead, real-time command dashboard that automatically discovers every listening port and container on the host system, visualizes live hardware telemetry with sparklines, and provides direct controls to organize, start, stop, change ports, check health, and stream logs without friction.

## Positioning

Unlike generic container dashboards (Portainer) or static bookmark launchpads (Homarr, Homepage), Portly actively reconciles raw OS network sockets (`psutil`, socket tables) with container engine APIs (`docker.sock`). It detects port collisions before they happen, suggests next-available ports, provides one-click safe port reassignment with automatic rollback snapshots, and enforces safe mode boundaries across mutating operations.

## Operating Context

- **Local Desktop / Workstation Mode**: Single-command execution via `python -m portly run --port 5533` or `portly list`. Runs with zero mandatory dependencies beyond Python 3.10+ and standard build tools.
- **NAS / Server / Homelab Mode**: Containerized via Docker Compose with `network_mode: host` and `pid: host`, mounted to `/var/run/docker.sock` and `/:/hostfs:ro` for accurate host telemetry and container control.
- **Network Boundaries & Authentication**:
  - Default loopback binding (`127.0.0.1`) for local desktop convenience.
  - Strict setup token bootstrap on `0.0.0.0` or server mode.
  - Multi-user RBAC (`admin` vs `viewer`) with Argon2id-equivalent PBKDF2-HMAC-SHA256 password hashing.
  - Rate-limited timing-safe authentication and CSRF/Host header verification.

## Capabilities and Features

- **Host & Container Discovery**: Scans listening TCP and UDP sockets, disambiguating Docker-proxy bindings from host processes; assigns persistent stable IDs (`docker:...`, `host:...`, `custom:...`).
- **Telemetry Engine**: Real-time 60-point ring buffers (~5-minute history) pushing CPU, RAM, Disk (via host filesystem mount), Network bandwidth, and container metrics via Server-Sent Events (`/api/stream`).
- **Safe Mode & Auto-Relock**: Enabled by default; locks all mutating actions (starts, stops, restarts, recreations, process terminations, prunes). Includes 5-minute temporary unlock countdowns with automatic re-locking.
- **Preflight Port Collision Engine**: Analyzes `docker run` commands, `docker-compose.yml` declarations, or raw port arrays to detect socket collisions before deployment.
- **Port Management & Rollback**: Safe port migration preserving container environment, labels, mounts, and network configurations; maintains rollback snapshots for 1-click restoration.
- **Multi-User RBAC & Audit Logging**: Admin and viewer roles; complete audit log tracking all mutations with timestamp, actor, target, and success status.
- **Zero External Network Dependencies**: Self-contained local-first architecture with system font stacks, embedded SVGs, and zero runtime CDNs.
- **Reverse Proxy Generator**: Instant config generation for Caddy, Nginx, Traefik (file & labels), and Cloudflare Tunnels.

## Brand Commitments

- **Identity**: Portly ⚓ — compact, tactile, industrial harbor aesthetic inspired by maritime logistics and modern observability tools.
- **Tone**: Focused, accurate, calm, low visual noise, information-dense without clutter.
- **Visual Stance**: Deep midnight surfaces (`#0A0B0F`), indigo and teal telemetry accents (`#8C9EFF`, `#5EEAD4`), crisp monospace typography for network coordinates, single-row un-wrapping status meters.

## Evidence on Hand

- **Backend & E2E**: The full pytest suite passes, including unit/integration and Playwright E2E tests (`tests/`).
- **Frontend**: Production React 19 + TypeScript + Vite build with zero bundle warnings and zero external runtime calls.
- **Security**: Timing-safe auth, SSRF-protected favicon & health checks, command execution allowlists, accessible dialog focus traps.

## Product Principles

1. **Glanceable Density Over Decorative Space**: Every pixel serves comprehension. Metrics, statuses, and ports must be immediately readable at a glance without nesting or unnecessary layers.
2. **Never Break Runtime Context**: Toolbars and status bars never wrap. Single-row horizontal continuity ensures fixed mental landmarks across all viewport sizes.
3. **Safety First, Action Second**: Dangerous operations (port changes, process kills, container removal) always require verification, availability checking, and rollback pathways.
4. **Resilient Local-First Execution**: The application operates self-contained without external SaaS dependencies, analytics beacons, or remote telemetry tracking.

## Accessibility & Inclusion

- Designed with WCAG 2.1 AA in mind; accessibility is an ongoing effort. An axe audit script (`portly/frontend/scripts/axe-audit.mjs`) checks serious/critical violations in dark and light themes; it does not yet pass cleanly.
- Full keyboard navigation across all views (Table, Grid, List, Board) and global command palette (`Ctrl+K` / `Cmd+K` accessible anywhere).
- Accessible Toasts (`role="status"`, `role="alert"`) and modal dialogs (`role="dialog"`, `aria-modal="true"`, focus trapped, ESC to dismiss).
- Strict 4.5:1 text contrast on all text elements and interactive controls.
