# All-in-One Docker & Port Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Portly into an all-in-one Docker and port management platform featuring first-class Cloudflare Tunnel URL configuration, `cloudflared` ingress generation, multi-port container remapping, Docker Compose stack actions, Docker system hygiene (image/volume inspection and pruning), and container deployment templates.

**Architecture:** Extend Portly's FastAPI backend and Docker Engine API integration with modular actions for multi-port recreation, system pruning, compose stacks, and container creation. Add Cloudflare Tunnel ingress generation to `proxy_gen.py`. Expand Portly's React frontend with an Access & Tunnels tab, multi-port remapping editor, Docker storage/hygiene controls in the System drawer, and a Deploy Container wizard in AddAppModal.

**Tech Stack:** Python 3.11+, FastAPI, Docker SDK for Python (`docker`), React 18, TypeScript, Vite, Playwright for E2E testing.

**Spec:** `docs/superpowers/specs/2026-11-16-all-in-one-docker-port-management-design.md`

## Global Constraints

- **Safe Mode**: All mutating actions (`recreate`, `prune`, `stack actions`, `deploy`) must be locked whenever Safe Mode is enabled, throwing HTTP 403 / PermissionError unless unlocked.
- **Non-Destructive Docker Changes**: Container recreation must always rename the original container as backup and preserve a rollback snapshot in SQLite before spinning up the new container.
- **Port Availability Pre-flight**: Every port change or container deployment must validate port availability against OS socket binding, host listening sockets, and existing Docker container bindings.
- **Design System Fidelity**: All new UI components must strictly adhere to Portly's dark aesthetic (`#0E1116` card backgrounds, `#8C9EFF` primary accents, `#5EEAD4` teal status accents, JetBrains Mono font for ports/hashes) as documented in `DESIGN.md`.

## Review Focus

1. **Conflicting Multi-Port Remapping**: Attempting to remap multiple ports where one port is already in use must fail gracefully before any container is stopped or removed.
2. **Safe Mode Enforcement on Docker Prune**: Attempting to trigger Docker system pruning while Safe Mode is ON must be blocked with an explicit error message.
3. **Invalid or Malformed Cloudflare Tunnel URLs**: Saving empty, malformed, or non-HTTP(S) URLs must be validated and sanitized.
4. **Missing Docker Socket**: When Docker is not running or socket is missing, all Docker hygiene and stack endpoints must return friendly error status without crashing the process.
5. **Rollback Integrity**: If recreation with multiple ports fails midway, the backup container must be restored immediately to prevent service downtime.

---

### Task 1: Cloudflare Tunnel & Ingress Generator (Backend)

**Files:**
- Modify: `portly/backend/proxy_gen.py`
- Modify: `portly/backend/app.py`
- Test: `tests/test_tunnels_and_proxy.py`

**Steps:**
- [x] Write failing test in `tests/test_tunnels_and_proxy.py` testing `generate_cloudflared_config` and `GET /api/apps/{app_id}/proxy-config?format=cloudflared`.
- [x] Implement `generate_cloudflared_config(domain: str, upstream_host: str, port: int) -> str` in `portly/backend/proxy_gen.py`.
- [x] Update `/api/apps/{app_id}/proxy-config` endpoint in `portly/backend/app.py` to support `format="cloudflared"`.
- [x] Run pytest to verify all proxy and tunnel tests pass.

---

### Task 2: Multi-Port Container Remapping (Backend)

**Files:**
- Modify: `portly/backend/actions/docker_actions.py`
- Modify: `portly/backend/app.py`
- Test: `tests/test_multi_port_change.py`

**Steps:**
- [x] Write failing test in `tests/test_multi_port_change.py` testing multi-port remapping, conflict validation, and rollback snapshots.
- [x] Implement `apply_multi_port_change_docker(container_name: str, mappings: List[Dict[str, Any]], store: Store)` in `portly/backend/actions/docker_actions.py`.
- [x] Add endpoint `POST /api/apps/{app_id:path}/ports-multi` in `portly/backend/app.py` that validates all new ports and executes the multi-port change.
- [x] Run pytest to ensure multi-port remapping and rollback operate cleanly.

---

### Task 3: Docker System Hygiene & Disk Pruning (Backend)

**Files:**
- Modify: `portly/backend/actions/docker_actions.py`
- Modify: `portly/backend/app.py`
- Test: `tests/test_docker_hygiene.py`

**Steps:**
- [x] Write failing test in `tests/test_docker_hygiene.py` testing image listing, volume listing, system df, and safe mode prune locking.
- [x] Implement `get_docker_system_df`, `list_docker_images`, `list_docker_volumes`, and `prune_docker_system` in `portly/backend/actions/docker_actions.py`.
- [x] Add REST endpoints in `portly/backend/app.py`:
  - `GET /api/docker/system`
  - `GET /api/docker/images`
  - `GET /api/docker/volumes`
  - `POST /api/docker/prune` (Safe Mode protected)
- [x] Run pytest to confirm all Docker hygiene endpoints pass.

---

### Task 4: Docker Compose Stack Controls & Container Deployment (Backend)

**Files:**
- Modify: `portly/backend/actions/docker_actions.py`
- Modify: `portly/backend/app.py`
- Test: `tests/test_docker_compose_and_deploy.py`

**Steps:**
- [x] Write failing test in `tests/test_docker_compose_and_deploy.py` testing stack lifecycle actions (`restart`, `stop`, `start`) and container deployment.
- [x] Implement `manage_compose_stack` and `deploy_container` in `portly/backend/actions/docker_actions.py`.
- [x] Add REST endpoints in `portly/backend/app.py`:
  - `POST /api/docker/compose/{project}/action`
  - `POST /api/docker/containers/deploy`
- [x] Run pytest to verify stack actions and container deployment endpoints pass.

---

### Task 5: Frontend API Client & Types

**Files:**
- Modify: `portly/frontend/src/api.ts`
- Modify: `portly/frontend/src/types.ts`

**Steps:**
- [x] Add TypeScript interfaces for Docker system df, images, volumes, multi-port mappings, and stack actions in `portly/frontend/src/types.ts`.
- [x] Add client methods in `portly/frontend/src/api.ts`:
  - `applyMultiPortChange`
  - `getDockerSystemDf`, `getDockerImages`, `getDockerVolumes`, `pruneDockerSystem`
  - `executeComposeAction`
  - `deployContainer`

---

### Task 6: Frontend - Access & Cloudflare Tunnels in AppDetailModal & Cards

**Files:**
- Modify: `portly/frontend/src/components/AppDetailModal.tsx`
- Modify: `portly/frontend/src/components/GridView.tsx`
- Modify: `portly/frontend/src/components/TableView.tsx`

**Steps:**
- [x] Add `cloudflared` to the Proxy Generator tab in `AppDetailModal.tsx` with copyable YAML configuration.
- [x] Add a dedicated **"Access & Tunnels"** section in `AppDetailModal.tsx` to set a Cloudflare Tunnel URL with direct test link.
- [x] Add a visible **Tunnel / Cloudflare badge** and direct external link to grid tiles and table rows when a tunnel URL is configured.

---

### Task 7: Frontend - Multi-Port Mapping Editor & Compose Stack Controls

**Files:**
- Modify: `portly/frontend/src/components/AppDetailModal.tsx`

**Steps:**
- [x] In `AppDetailModal.tsx` -> "Ports" tab, render all container port bindings with editable host port inputs, individual availability badges, and a "Save All Port Mappings" button.
- [x] In `AppDetailModal.tsx` -> "Compose" tab, add stack action buttons ("Restart Stack", "Stop Stack", "Start Stack") with status toasts.

---

### Task 8: Frontend - Docker System Hygiene in SystemDrawer & Container Deployer

**Files:**
- Modify: `portly/frontend/src/components/SystemDrawer.tsx`
- Modify: `portly/frontend/src/components/AddAppModal.tsx`

**Steps:**
- [x] In `SystemDrawer.tsx`, add a "Docker Engine Storage & Hygiene" panel with image count, volume count, reclaimable space indicator, and a "Prune Unused Resources" button.
- [x] In `AddAppModal.tsx`, add a "Deploy Container" tab with quick templates (PostgreSQL, Redis, Nginx, Uptime Kuma) and custom container deployment form.

---

### Task 9: Frontend Build, Pytest Suite & Browser E2E Verification

**Files:**
- Run: `npm run build` in `portly/frontend`
- Run: `python -m pytest tests/`
- Run: E2E Playwright verification script to verify UI rendering and interactions

**Steps:**
- [x] Compile frontend bundle with Vite (`npm run build`).
- [x] Run full test suite with pytest to ensure 100% pass rate.
- [x] Start Portly server and use headless browser / Playwright test to verify all views, modals, and new tabs visually and functionally.
