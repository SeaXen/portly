---
name: Portly
description: High-performance, self-hosted port discovery and live telemetry dashboard
colors:
  primary: "#8C9EFF"
  primary-deep: "#6875DF"
  accent-teal: "#5EEAD4"
  accent-coral: "#FF8A8A"
  accent-amber: "#FBBF77"
  accent-rose: "#F5A3D0"
  accent-lime: "#B6E36B"
  neutral-bg: "#0A0B0F"
  surface-1: "#101218"
  surface-2: "#151821"
  surface-3: "#1C2030"
  border: "rgba(255, 255, 255, 0.07)"
  border-subtle: "rgba(255, 255, 255, 0.04)"
  text-primary: "#ECEEF3"
  text-muted: "#8D95A5"
  light-bg: "#F8FAFC"
  light-surface-1: "#FFFFFF"
  light-surface-2: "#F1F5F9"
  light-surface-3: "#E2E8F0"
  light-text: "#0F172A"
  light-muted: "#475569"
  light-accent: "#4F63D2"
  light-accent-deep: "#3B4EC0"
  light-success: "#0F766E"
  light-warning: "#B45309"
  light-danger: "#B91C1C"
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "0.84375rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "'JetBrains Mono', monospace"
    fontSize: "0.78125rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.02em"
rounded:
  sm: "6px"
  md: "9px"
  lg: "14px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-bg}"
    rounded: "{rounded.md}"
    padding: "7px 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-deep}"
  button-secondary:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "7px 12px"
  card:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "16px 16px"
  input:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
---

# Design System: Portly

## Overview

**Creative North Star: "The Obsidian Harbor"**

Portly is an industrial, precision-engineered observatory for local networks, containers, and background services. Built for operators who inspect dozens of concurrent workloads, its aesthetic rejects both the flat sterility of generic admin templates and the noisy neon oversaturation of hobbyist dashboards. Like the flight deck or shipping harbor control tower at night, the interface stays calm, deep, and dark, using light with surgical intention to communicate status, bandwidth flow, and system pressure.

Surfaces exist on a disciplined three-tier tonal scale: deep void black (`#0A0B0F`) for global canvases, midnight stone (`#101218`) for sidebar docks and toolbars, and elevated obsidian (`#151821`) for cards, dialog panels, and table rows. Accent colors are sparse and semantic: Periwinkle Harbor (`#8C9EFF`) anchors focus and primary actions, Seafoam Teal (`#5EEAD4`) signals verified healthy uptime, while Coral Red (`#FF8A8A`) and Amber Gold (`#FBBF77`) flag collisions and resource bottlenecks. A daylight variant (`light`) and a pure-black variant (`oled`) ship alongside the default dark theme; they remap the same semantic tokens rather than inventing a second visual language.

**Key Characteristics:**
- Un-wrapping horizontal telemetry strips with live 60-point inline vector sparklines.
- Dual-font typography hierarchy: humanistic sans (`Inter`) for controls and metadata; tabular monospaced figures (`JetBrains Mono`) for network sockets, ports, and metrics.
- High-contrast, tactile micro-interactions with visible focus rings (`#8C9EFF`) and restrained transition timings (120–180ms).
- Intentional density: Compact for high-volume sysadmin auditing, Comfy for glanceable wallboard displays.

## Colors

The palette is tuned for prolonged dark-room monitoring with zero eye strain. WCAG 2.1 AA text contrast is verified in dark and light themes by the axe audit (`portly/frontend/scripts/axe-audit.mjs`, serious/critical violations = 0 across all views).

### Primary
- **Periwinkle Harbor** (`#8C9EFF`): Used for primary action buttons, active tab indicators, selected item checkboxes, and command palette focus boundaries. Renders with high clarity against dark slate backdrops.
- **Deep Periwinkle** (`#6875DF`): Hover and pressed state for primary action controls.

### Secondary
- **Seafoam Teal** (`#5EEAD4`): Healthy container and socket status dots, positive health check latency sparklines, and database category tags.

### Tertiary
- **Amber Warning** (`#FBBF77`): Degraded health, resource thresholds above 80%, and monitoring service identifiers.
- **Coral Danger** (`#FF8A8A`): Port collisions, stopped containers, critical CPU/RAM saturation (>90%), and destructive confirmation dialogs.
- **Orchid Pink** (`#F5A3D0`): Automation workflows, cron jobs, and background workers.
- **Lime Spring** (`#B6E36B`): Core host infrastructure, proxy gateways, and network daemon categories.

### Neutral
- **Void Canvas** (`#0A0B0F`): Main application backdrop and global window fill.
- **Surface Dock** (`#101218`): Sidebar navigation panel, command palette interior, and dropdown menus.
- **Surface Card** (`#151821`): Table rows, grid tiles, kanban cards, and modal dialog surfaces.
- **Surface Hover** (`#1C2030`): Active row hover, segmented control backings, and pressed button states.
- **Crisp Text** (`#ECEEF3`): Primary headings, port numbers, and high-priority data points.
- **Muted Slate** (`#8D95A5`): Secondary descriptions, socket protocols, timestamps, and column header labels.
- **Hairline Border** (`rgba(255, 255, 255, 0.07)`): Single-pixel card and divider boundaries.

### Light Theme
The light variant keeps the same roles with daylight values: Harbor Mist (`#F8FAFC`) canvas, white docks and cards, Slate Ink (`#0F172A`) text, and a deepened indigo accent (`#4F63D2`) because periwinkle fails contrast on white. Semantic status colors deepen to `#0F766E` (success), `#B45309` (warning), `#B91C1C` (danger). Badge text on accent tints uses `#3B4EC0`. The light accent is fixed: user accent customization applies to dark/oled only. Category-colored text (`.cat-text`) darkens any user-picked category color via `color-mix(in srgb, var(--cat-color) 50%, #000)` so it stays ≥4.5:1 on the pale badge tint. `color-scheme` flips with the theme so native checkboxes, scrollbars, and form controls follow.

### Named Rules
**The Single-Voice Accent Rule.** Primary periwinkle (`#8C9EFF`) is reserved strictly for interactive state and primary affordances. It covers ≤5% of screen area at rest.
**The Status Sovereignty Rule.** Semantic colors (Teal, Amber, Coral) are never used for arbitrary aesthetic decoration. A red dot must always denote a dead process or port collision.
**The Semantic Token Rule.** Component text uses `var(--text)`, `var(--muted)`, `var(--accent)`, and the status tokens — never hard-coded palette hexes — so every theme remaps it correctly. Inline hex colors are a defect unless caught by a theme override.

## Typography

**Display Font:** Inter, -apple-system, system-ui, sans-serif
**Body Font:** Inter, -apple-system, system-ui, sans-serif
**Label/Mono Font:** JetBrains Mono, SF Mono, Consolas, monospace

**Character:** Balanced modern humanistic clarity paired with rigid tabular technical monospacing for ports, IP addresses, and byte statistics.

### Hierarchy
- **Display** (600, 24px / 1.5rem, line-height 1.2, letter-spacing -0.02em): Modal titles, main dashboard greeting, and hardware drawer headers.
- **Headline** (600, 18px / 1.125rem, line-height 1.3, letter-spacing -0.01em): Category headers, drawer titles, and confirmation dialog headings.
- **Title** (600, 15px / 0.9375rem, line-height 1.35): App card names, table row primary labels, and command palette search items.
- **Body** (400, 13.5px / 0.84375rem, line-height 1.45): Secondary descriptions, process command lines, drawer telemetry subtexts.
- **Label / Monospace** (500, 12.5px / 0.78125rem, letter-spacing 0.02em): Port tags (`:5533`), PID indicators, IP bind addresses (`0.0.0.0`), and bandwidth sparkline values with `tabular-nums`.

### Named Rules
**The Tabular Number Rule.** All numerical readouts (CPU %, RAM MB, port numbers, latency ms) strictly enforce `font-variant-numeric: tabular-nums` to guarantee jitter-free rendering during real-time streaming updates.
**The No-Kicker Rule.** Section titles and cards never display uppercase micro-eyebrows or kickers above headings. Headings communicate context directly.

## Layout

The spatial model uses an 8px modular baseline (`--space: 8px`) across all views.
- **Sidebar Navigation**: Fixed 220px dock (collapsible to 60px icon strip on compact screens).
- **One-Row Stats Strip**: A single horizontal flex container (`.c081`) with `flex-wrap: nowrap` and `overflow-x: auto`. Segments display real-time SVG sparklines alongside telemetry without wrapping. Below 900px it reflows to a 3×2 grid (D-6) so values stay legible.
- **Single-Row Toolbar**: Filter chips, view mode switches (Table, Grid, List, Board), density toggles, and sorting options sit on one bar with horizontal scroll overflow; control groups may wrap to a second row at narrow widths.
- **Viewports**:
  - Desktop (>1024px): Full multi-column table and responsive kanban grid.
  - Tablet (768px–1023px): Flexible 2-3 column tile grid, responsive table horizontal scrolling with frozen port columns.
  - Mobile (<768px): Sidebar collapses to a top icon rail, rows keep ≥44px click areas (name buttons get a 24px floor on coarse pointers), full-width cards. The footer status line wraps; the stats strip and tab bar never push the document wider than the viewport.

## Elevation & Depth

Portly employs clean tonal layering combined with crisp hairlines (`rgba(255, 255, 255, 0.07)`). Heavy diffuse drop shadows are rejected in favor of razor-sharp depth separation.

### Shadow Vocabulary
- **Elevated Card Rest**: `box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4)` — base table rows and grid tiles.
- **Hover Lift**: `box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(140, 158, 255, 0.3)` — interactive hover on cards and actionable items.
- **Modal Backdrop / Dialog**: `box-shadow: 0 20px 48px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1)` — modal content windows and command palette overlays.

### Named Rules
**The Boundary Hairline Rule.** Deep black overlays always feature an interior 1px semi-transparent border (`inset 0 1px 0 rgba(255, 255, 255, 0.08)`) simulating an illuminated edge.

## Shapes

- **Controls & Buttons**: 9px border radius (`--radius-control: 9px`). Compact, crisp, easily targeted.
- **Cards & Containers**: 14px border radius (`--radius-card: 14px`). Softened corners framing rich telemetry.
- **Status Pills & Chips**: Full capsule radius (`9999px`) with 4px internal padding.
- **Borders**: 1px solid `rgba(255, 255, 255, 0.07)` on dark mode; `rgba(0, 0, 0, 0.08)` on light mode.

## Components

### Buttons
- **Shape:** 9px border radius (`--radius-control`).
- **Primary Hero Button:** Background `#8C9EFF`, text `#0A0B0F`, font-weight 600, padding `7px 14px`. Hover shifts to `#6875DF`. In the light theme the fill is `#4F63D2` with white text (dark text fails contrast on the deeper fill).
- **Secondary Ghost Button:** Background `rgba(255, 255, 255, 0.04)`, text `#ECEEF3`, border `1px solid rgba(255, 255, 255, 0.08)`, padding `7px 12px`. Hover shifts to `rgba(255, 255, 255, 0.08)`.
- **Icon Actions:** 28px x 28px square buttons (`.row-action-btn`) with inline SVG iconography, stroke width 2px.

### Rows & Cards: Interaction Model
Table rows, grid tiles, list rows, and board cards open the detail modal on click, but the container carries **no interactive role** — nested checkboxes, action buttons, and links stay legal. The app name is a real button (`.app-name-btn`, ellipsized, inherits the row's type styles) and is the keyboard/AT path: Tab to it, Enter opens details; the click bubbles to the container handler. Grid card hover lift is CSS (`.c026:hover`), disabled under `prefers-reduced-motion`.

### Chips & Badges
- **Status Badges:** Circular 7px pulsing status dot + uppercase 11px monospaced text.
- **Category Badges:** Colored pill carrying subtle semi-transparent background (`rgba(color, 0.15)`) with matching solid border; label text uses `.cat-text` so the light theme darkens it automatically.

### Cards & Tiles
- **Grid Tile:** 14px border radius, 16px internal padding, prominent 22px port identifier typography in periwinkle accent.
- **Stats Strip Segment:** Direct interactive button (`.c082`), hover triggers subtle background glow, click opens hardware drawer.

### Inputs & Fields
- **Search & Filter Inputs:** Background `#101218`, border `1px solid rgba(255, 255, 255, 0.09)`, text `#ECEEF3`, height 34px. Focus visible introduces 2px outline in `#8C9EFF`.

### Navigation & Docks
- **Sidebar Nav Button:** Height 36px, border radius 8px, 12px horizontal padding. Active state: `rgba(140, 158, 255, 0.14)` background, 2.5px inset accent stripe on the leading edge, accent-colored icon; light theme swaps text to `#0F172A`. The Conflicts button's accessible name comes from its content (label + count badge) so visible text and name always match.

### Signature Component: Telemetry Sparkline
- **Inline SVG Sparkline:** 60px x 20px polyline rendered with smooth exponential curves, 1.8px stroke width, showing 60 data points of real-time utilization history.

## Do's and Don'ts

### Do:
- **Do** preserve single-line horizontal layouts for the stats strip and toolbar at all screen widths.
- **Do** use `font-variant-numeric: tabular-nums` for any container holding ports, PIDs, bytes, or percentages.
- **Do** verify port availability before prompting users with port change migration dialogs.
- **Do** respect `prefers-reduced-motion` by disabling translation animations while preserving subtle opacity transitions.
- **Do** maintain safe mode by default for all destructive process and container actions.
- **Do** route category-colored text through `.cat-text` and set `color-scheme` per theme so native controls follow.
- **Do** make the app name the keyboard-focusable button inside clickable rows/cards; keep containers role-free.

### Don't:
- **Don't** use decorative gradient text or multi-color glow halos outside semantic statuses.
- **Don't** hide critical telemetry behind hover tooltips; prioritize glanceable numbers with inline context.
- **Don't** wrap the stats strip or toolbars onto multiple vertical rows.
- **Don't** perform destructive Docker container recreation without an automatic rollback snapshot.
- **Don't** use raw emoji in place of authored, accessible SVG iconography.
- **Don't** put `role="button"` on a container that nests checkboxes, buttons, or links.
- **Don't** hard-code dark-palette hexes as component text colors; use the semantic tokens.
