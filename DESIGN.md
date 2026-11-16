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

Surfaces exist on a disciplined three-tier tonal scale: deep void black (`#0A0B0F`) for global canvases, midnight stone (`#101218`) for sidebar docks and toolbars, and elevated obsidian (`#151821`) for cards, dialog panels, and table rows. Accent colors are sparse and semantic: Periwinkle Harbor (`#8C9EFF`) anchors focus and primary actions, Seafoam Teal (`#5EEAD4`) signals verified healthy uptime, while Coral Red (`#FF8A8A`) and Amber Gold (`#FBBF77`) flag collisions and resource bottlenecks.

**Key Characteristics:**
- Un-wrapping horizontal telemetry strips with live 60-point inline vector sparklines.
- Dual-font typography hierarchy: humanistic sans (`Inter`) for controls and metadata; tabular monospaced figures (`JetBrains Mono`) for network sockets, ports, and metrics.
- High-contrast, tactile micro-interactions with visible focus rings (`#8C9EFF`) and restrained transition timings (120–180ms).
- Intentional density: Compact for high-volume sysadmin auditing, Comfy for glanceable wallboard displays.

## Colors

The palette is tuned for prolonged dark-room monitoring with zero eye strain, exceeding WCAG 2.1 AA text contrast across all states.

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

### Named Rules
**The Single-Voice Accent Rule.** Primary periwinkle (`#8C9EFF`) is reserved strictly for interactive state and primary affordances. It covers ≤5% of screen area at rest.
**The Status Sovereignty Rule.** Semantic colors (Teal, Amber, Coral) are never used for arbitrary aesthetic decoration. A red dot must always denote a dead process or port collision.

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
- **One-Row Stats Strip**: A single horizontal flex container (`.c081`) with `flex-wrap: nowrap` and `overflow-x: auto`. Segments display real-time SVG sparklines alongside telemetry without wrapping.
- **Single-Row Toolbar**: Filter chips, view mode switches (Table, Grid, List, Board), density toggles, and sorting options sit on a single non-wrapping bar with horizontal scroll overflow.
- **Viewports**:
  - Desktop (>1024px): Full multi-column table and responsive kanban grid.
  - Tablet (768px–1023px): Flexible 2-3 column tile grid, responsive table horizontal scrolling with frozen port columns.
  - Mobile (<768px): Sidebar collapses into bottom drawer/header menu, touch target floors enforced at 44px, full-width cards.

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
- **Primary Hero Button:** Background `#8C9EFF`, text `#0A0B0F`, font-weight 600, padding `7px 14px`. Hover shifts to `#6875DF`.
- **Secondary Ghost Button:** Background `rgba(255, 255, 255, 0.04)`, text `#ECEEF3`, border `1px solid rgba(255, 255, 255, 0.08)`, padding `7px 12px`. Hover shifts to `rgba(255, 255, 255, 0.08)`.
- **Icon Actions:** 30px x 30px square buttons (`.row-action-btn`) with inline SVG iconography, stroke width 2px.

### Chips & Badges
- **Status Badges:** Circular 7px pulsing status dot + uppercase 11px monospaced text.
- **Category Badges:** Colored pill carrying subtle semi-transparent background (`rgba(color, 0.15)`) with matching solid border and label.

### Cards & Tiles
- **Grid Tile:** 14px border radius, 16px internal padding, prominent 22px port identifier typography in periwinkle accent.
- **Stats Strip Segment:** Direct interactive button (`.c082`), hover triggers subtle background glow, click opens hardware drawer.

### Inputs & Fields
- **Search & Filter Inputs:** Background `#101218`, border `1px solid rgba(255, 255, 255, 0.09)`, text `#ECEEF3`, height 34px. Focus visible introduces 2px outline in `#8C9EFF`.

### Navigation & Docks
- **Sidebar Nav Button:** Height 36px, border radius 8px, 12px horizontal padding, active state displays `#8C9EFF` text with `rgba(140, 158, 255, 0.12)` background.

### Signature Component: Telemetry Sparkline
- **Inline SVG Sparkline:** 60px x 20px polyline rendered with smooth exponential curves, 1.8px stroke width, showing 60 data points of real-time utilization history.

## Do's and Don'ts

### Do:
- **Do** preserve single-line horizontal layouts for the stats strip and toolbar at all screen widths.
- **Do** use `font-variant-numeric: tabular-nums` for any container holding ports, PIDs, bytes, or percentages.
- **Do** verify port availability before prompting users with port change migration dialogs.
- **Do** respect `prefers-reduced-motion` by disabling translation animations while preserving subtle opacity transitions.
- **Do** maintain safe mode by default for all destructive process and container actions.

### Don't:
- **Don't** use decorative gradient text or multi-color glow halos outside semantic statuses.
- **Don't** hide critical telemetry behind hover tooltips; prioritize glanceable numbers with inline context.
- **Don't** wrap the stats strip or toolbars onto multiple vertical rows.
- **Don't** perform destructive Docker container recreation without an automatic rollback snapshot.
- **Don't** use raw emoji in place of authored, accessible SVG iconography.
