# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Self-hosters, software engineers, devops practitioners, and homelab enthusiasts running diverse sets of local services, databases, development servers, and containerized stacks (Docker, Docker Compose, Podman) on Linux, macOS, or Windows hosts. They frequently lose track of listening ports, face port collision errors, and require instant glanceable control over runtime states.

## Product Purpose

Portly provides a unified, zero-overhead, real-time command dashboard that automatically discovers every listening port and container on the host system, visualizes live hardware telemetry with sparklines, and provides direct controls to organize, start, stop, change ports, check health, and stream logs without friction.

## Positioning

Unlike generic container dashboards (Portainer) or static bookmark launchpads (Homarr, Homepage), Portly actively reconciles raw OS network sockets (`psutil`, `netstat`, `lsof`) with container engine APIs (`docker.sock`). It uniquely detects port collisions before they happen, suggests next-available ports, and provides one-click safe port reassignment with automatic rollback snapshots.

## Operating Context

- **Local Desktop / Workstation Mode**: Single-command execution via `python -m portly run --port 5533` or `portly list`. Runs with zero mandatory dependencies beyond Python 3.10+ and standard build tools.
- **NAS / Server / Homelab Mode**: Containerized via Docker Compose with `network_mode: host` and `pid: host`, mounted to `/var/run/docker.sock` for full host and container visibility.
- **Network Boundaries**: Default loopback binding (`127.0.0.1`) for local desktop safety; protected setup and admin authentication when bound to `0.0.0.0` or accessed across subnets.

## Capabilities and Constraints

- **Host & Container Discovery**: Scans listening TCP/UDP sockets, deduplicating Docker-proxy bindings and raw processes; assigns persistent stable IDs (`docker:...`, `host:...`, `custom:...`).
- **Telemetry Engine**: Real-time 60-point ring buffers (~5-minute history) pushing CPU, RAM, Disk, Network bandwidth, and container metrics via Server-Sent Events (`/api/stream`).
- **Control & Safety**: Safe mode by default preventing accidental process termination; granular Start, Stop, Restart, Log Streaming, and Exec terminal sessions for containers.
- **Port Management**: Live socket binding checks, collision diagnosis, safe port migration with container recreation, rollback snapshots, and reverse proxy configuration generation (Caddy, Nginx, Traefik).
- **Custom Apps**: Support for external web dashboards, non-listening tasks, and custom process management with health probes.

## Brand Commitments

- **Identity**: Portly ⚓ — compact, tactile, industrial harbor aesthetic inspired by maritime logistics and modern observability tools.
- **Tone**: Focused, accurate, calm, low visual noise, information-dense without clutter.
- **Visual Stance**: Deep midnight surfaces (`#0A0B0F`), indigo and teal telemetry accents (`#8C9EFF`, `#5EEAD4`), crisp monospace typography for network coordinates, single-row un-wrapping status meters.

## Evidence on Hand

- Fully functional FastAPI backend with 110 automated tests passing (`tests/`).
- Modern React + Vite frontend built into `portly/frontend/dist` with real-time SSE streaming.
- Playwright E2E browser test suite validating user journeys, keyboard shortcuts, view switching, and telemetry drawers.
- Documented CLI (`portly --help`) and multi-arch Docker image specification.

## Product Principles

1. **Glanceable Density Over Decorative Space**: Every pixel serves comprehension. Metrics, statuses, and ports must be immediately readable at a glance without nesting or unnecessary layers.
2. **Never Break Runtime Context**: Toolbars and status bars never wrap. Single-row horizontal continuity ensures fixed mental landmarks across all viewport sizes.
3. **Safety First, Action Second**: Dangerous operations (port changes, process kills, container removal) always require verification, availability checking, and rollback pathways.
4. **Resilient Local-First Execution**: The application operates self-contained without external SaaS dependencies, analytics beacons, or remote telemetry tracking.

## Accessibility & Inclusion

- Compliance with WCAG 2.1 AA standards.
- Full keyboard navigation across all views (Table, Grid, List, Board) and global command palette (`Ctrl+K` / `Cmd+K`).
- Strict 4.5:1 text contrast on all text elements and interactive controls.
- Dedicated `color-scheme: dark` metadata and intentional `prefers-reduced-motion` modes preserving state change awareness without disorienting translation animations.
