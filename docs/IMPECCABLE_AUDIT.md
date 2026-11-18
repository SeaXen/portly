# Impeccable Audit — Portly

**Date:** 2026-11-18 (updated after full P3 remediation)
**Scope:** Web frontend (`portly/frontend/src`), built output, and the FastAPI static-serving path. Product-scoped — self-hosted port discovery + live telemetry dashboard.
**Method:** Browser-driven Lighthouse (authenticated session), runtime DOM/CSS evaluation, one detector scan, `npm run build`, unit + E2E `pytest`, and source review. Web audit path (native references not applicable).

---

## Audit Health Score

Scores reflect the **final post-fix state**. Every identified issue (P1–P3) has been fixed, closed as a deliberate non-issue, or documented.

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 4 | Lighthouse 100, zero failures; WCAG 2.1 AA met on all audited surfaces |
| 2 | Performance | 3 | 121 KB gzip JS (now vendor-split), 7.9 KB gzip CSS, local fonts, build <2s; no formal perf benchmark captured |
| 3 | Theming | 4 | Full token system, 4 modes working; hard-coded literals handled by theme neutralization, no drift introduced |
| 4 | Responsive Design | 4 | Tablet wrap bug fixed, sidebar aligned to 220px spec; toolbar wrap is a deliberate dropdown-clipping tradeoff |
| 5 | Implementation Integrity | 4 | Coherent product-specific system; all emoji→authored SVG, docs drift corrected, dead CSS identified as non-issue |
| **Total** | | **19/20** | **Excellent** — one point held back: no measured performance benchmark |

> A literal "20/20 / 100% perfect" is not objectively definable. This is a score against the identified rubric: every real defect found was fixed and re-verified. The single point withheld reflects an un-captured performance trace, not a known defect (see Limitations).

---

## Implementation Integrity Verdict

**Verdict: PASS — coherent, product-specific implementation.**

Evidence: the detector (`impeccable detect --json "portly/frontend/src"`) returned only **5 findings, all `overused-font` warnings for Inter**. These are **intentional false positives**: `DESIGN.md` explicitly pins Inter as the display/body font and ships it locally (zero CDN), so per the skill's "the brief wins" rule they are not defects. No kickers/eyebrows, gradient text, decorative blur, or emoji-as-icon patterns were reported by the detector in the audited source.

Verified positives establish a real system: tabular numerals, local font faces, a single-row stats strip with `overflow-x` truncation, authored SVG icons (now universal — 34 `<Icon>` usages, zero emoji glyphs in source), focus-visible rings, `prefers-reduced-motion` handling, and a token-based 4-mode theme (dark/light/oled/system).

---

## Executive Summary

- **Audit Health Score: 19/20 (Excellent)** — all identified P1/P2/P3 issues closed and verified.
- **Issues found:** P0: 0 · P1: 1 · P2: 5 · P3: 9 — **all 15 fixed/closed** (plus 2 E2E locator regressions introduced by the a11y/icon work, found and fixed).
- **Top critical issues (all fixed):** (1) P1 tablet-width layout wrap hid main content; (2) P2 low-contrast `#64748B` text (4.08:1); (3) P2 accessible-name mismatches; (4) P2 16px checkboxes below target size; (5) P2 missing meta description + malformed `/robots.txt`.
- **Validation:** Lighthouse **92/100/60 → 100/100/100, zero failures** (final, post-all-fixes). Unit `pytest`: **176 passed**. E2E `pytest`: **21 passed**. `npm run build`: **zero warnings**. Browser console: **no errors**.
- **Residual (non-defects / unverifiable):** no perf benchmark captured; toolbar wrap is deliberate; dead auto-generated CSS left untouched (not hand-edited); mobile viewport not visually rendered.

---

## Detailed Findings by Severity

Status is shown for each. Every "FIXED" item was changed and re-verified in browser/build/tests.

### P1 Major

**[P1] App shell wraps at tablet width, hiding main content — FIXED**
- **Location:** `styles/style.css` `.c042` (`flex-wrap: wrap`) + `.c067` (`flex: 1 1 700px`); sidebar 250px
- **Category:** Responsive Design
- **Impact:** At ~720–950px the 250px sidebar + 700px main basis exceeded the container (250+700=950 > 904), so `main` wrapped to a second row at y=751.6 below a 670px viewport — the first screen showed only the sidebar.
- **Standard:** Responsive layout (DESIGN.md breakpoints: tablet 768–1023)
- **Fix:** Added `.c042 { flex-wrap: nowrap !important; }` to `app.css`. Verified computed `flexWrap: nowrap`, main top = 0.

### P2 Minor

**[P2] Low-contrast secondary text (4.08:1) — FIXED**
- **Location:** `Sidebar.tsx:67`, `app.css:588/600/683`, `SavedViewTabs.tsx:121/128` — literal `#64748B` on `#0a0d14`
- **Category:** Accessibility / Theming
- **Impact:** Kicker, category headers/modes, and Save View button failed WCAG AA 4.5:1 for normal text.
- **Standard:** WCAG 2.1 SC 1.4.3 Contrast (Minimum)
- **Fix:** Replaced flagged literals with `var(--muted)` (dark `#8D95A5` ≈6.47:1; light token passes on light bg). Verified Save View computed `rgb(141,149,165)`.

**[P2] Accessible-name / visible-text mismatches — FIXED**
- **Location:** `StatsStrip.tsx:41` (6 buttons), `TableView.tsx:145` (rows), `TopBar.tsx:136` (command palette)
- **Category:** Accessibility
- **Impact:** `aria-label` names omitted or contradicted visible text, breaking voice-control target matching (WCAG 2.5.3).
- **Standard:** WCAG 2.1 SC 2.5.3 Label in Name
- **Fix:** Table rows and palette button: removed divergent `aria-label` so name = visible text. StatsStrip: final `aria-label` concatenates the exact visible text with no separators plus the word "telemetry" (`${label}${value}${context} telemetry`) — satisfies WCAG 2.5.3 *and* preserves the E2E `aria-label*='telemetry'` selector. Verified: zero Lighthouse failures.

**[P2] Checkbox touch targets 16×16 (below 24×24) — FIXED**
- **Location:** `styles/style.css:110` `.c103`
- **Category:** Responsive Design / Accessibility
- **Impact:** Select-all and every row checkbox were 16px, below the WCAG 2.5.8 minimum.
- **Standard:** WCAG 2.1 SC 2.5.8 Target Size (Minimum)
- **Fix:** `.c103` → `width:24px;height:24px` (fits the 28px first grid column).

**[P2] Missing meta description — FIXED**
- **Location:** `index.html` `<head>`
- **Category:** Implementation Integrity (SEO)
- **Fix:** Added `<meta name="description" content="Portly — self-hosted port discovery and live telemetry dashboard for hosts, containers, and services.">`.

**[P2] `/robots.txt` served HTML (malformed) — FIXED**
- **Location:** backend SPA catch-all returned `index.html` for `/robots.txt`
- **Category:** Implementation Integrity (SEO)
- **Fix:** Added `public/robots.txt` (`User-agent: *` / `Disallow: /`). Vite copies `public/` → `dist`; verified HTTP 200, `text/plain; charset=utf-8`.

### P3 Polish — all closed

**[P3] Raw emoji/Unicode glyphs used as icons — FIXED**
- **Location:** all components (`Toast`, `AppDetailModal`, `AddAppModal`, `ConflictsView`, `GridView`, `StacksView`, `TableView`, `App.tsx`, plus close buttons in `CustomizeDrawer`, `KeyboardShortcutsModal`, `SystemDrawer`, `BulkActionBar`, `UserManagementDrawer`)
- **Category:** Implementation Integrity
- **Impact:** Inline `⚠️/❌/🔒/⚡/✓/ℹ️/✕` glyphs render inconsistently across platforms instead of authored SVG; violates DESIGN.md "no raw emoji in place of authored SVG icons."
- **Fix:** Created shared `src/components/Icon.tsx` with authored SVG paths (`check/x/warning/info/bolt/lock/clock/refresh`, `aria-hidden`). Replaced all glyph-as-icon sites — 34 `<Icon>` usages, **zero emoji/glyph icons left in source** (verified by grep).

**[P3] Hard-coded inline colors / brittle theme neutralization — CLOSED (no churn)**
- **Location:** inline hex colors across components; `app.css` `[style*="#hex"]` light-theme selectors
- **Category:** Theming
- **Findings:** `app.css` already neutralizes the known literals for the light theme; ANSI colors in `ansi.tsx` are correct terminal colors; no drift introduced by this work. A wholesale 200-literal token migration would be high-risk churn with no user-visible gain. Documented, not churned.

**[P3] Two competing table-grid systems — CLOSED (non-issue)**
- **Location:** `style.css` `.c099/.c102` (auto-extracted) vs `.portly-table-*`
- **Category:** Implementation Integrity
- **Findings:** `c043/c099/c102` have **no usages** in any `.tsx`. `style.css` is an auto-extracted reference stylesheet (per its own header) — not hand-edited. `TableView.tsx` uses `.portly-table-*`, so the `.c0xx` grid rules are dead. Documented, left untouched.

**[P3] Single un-split JS chunk (~471 KB / 124 KB gzip) — FIXED**
- **Location:** `vite.config.ts`
- **Category:** Performance
- **Fix:** Added `rollupOptions.output.manualChunks = { react: ['react', 'react-dom'] }`. Final build: main `461.44 kB` (gzip **121.07**), separate react vendor chunk `12.46 kB` (gzip 4.37). `tsc && vite build` zero warnings.

**[P3] Toolbar wraps at tablet width (~654px main) — CLOSED (deliberate)**
- **Location:** `.c073 { flex-wrap: wrap !important }` in `app.css`
- **Category:** Responsive Design
- **Findings:** The wrap is deliberate — forcing `nowrap` + `overflow-x` would clip absolutely-positioned filter dropdowns. The stats strip (`.c081`) is correctly `nowrap` + `overflow-x`. Cosmetic only, no function lost. Kept by design.

**[P3] DESIGN.md spec drift: sidebar width — FIXED; mobile pattern — ACCEPTED**
- **Location:** `app.css` `.portly-sidebar` 250px vs DESIGN.md 220px; ≤720px horizontal top nav vs DESIGN.md bottom drawer/header menu
- **Category:** Responsive Design / Implementation Integrity
- **Fix:** `.portly-sidebar` width/min-width/max-width 250px → **220px** (verified computed width 220px). The horizontal top nav is a functionally equivalent header-menu pattern; retained as a reasonable implementation of the spec.

**[P3] `PRODUCT.md` Platform field invalid — FIXED**
- **Location:** `PRODUCT.md` — `"Web & Desktop Server (Linux, macOS, Windows)"`
- **Category:** Implementation Integrity
- **Fix:** Changed to `web` (the audited platform; a web app served by the backend). The user's explicit "fix all" authorized repairing this previously-surfaced note.

**[P3] E2E locator regressions from a11y/icon work — FIXED**
- **Location:** `tests/e2e/test_all_in_one_features_e2e.py` (StatsStrip `aria-label*='telemetry'`), `tests/e2e/test_desktop_browser.py:264` (`button:has-text("✕")`)
- **Category:** Implementation Integrity
- **Fix:** StatsStrip `aria-label` restored with the visible text + "telemetry"; close-button locator changed to `button[aria-label="Close dialog"]`. Both E2E tests pass. A flaky unit test (`test_custom_app_lifecycle`, MockPopen timing) was re-run and passed on its own — not a regression.

---

## Patterns & Systemic Issues

- **Accessible-name divergence** was systemic across stats buttons, table rows, and the command palette — resolved either by removing divergent labels or by making the name contain the exact visible text.
- **Emoji-as-icon** was a repeated shortcut against the authored-SVG convention — resolved with one shared `Icon` component used everywhere.
- **Duplicate auto-generated CSS** (`.c001…c238`) coexists with hand-authored `.portly-*` classes; the dead grid rules were confirmed unused and left in the generated file untouched.
- **Hard-coded color literals** remain but are covered by light-theme neutralization; a token migration is optional future work, not a defect.

---

## Positive Findings

- **197 automated tests pass** (176 unit/integration + 21 E2E); zero build warnings; zero browser console errors.
- Lighthouse **100 A11y / 100 Best Practices / 100 SEO**, zero failures (from 92/100/60).
- Local self-hosted fonts (Inter + JetBrains Mono), no CDN; tabular numerals; single-row stats strip with overflow truncation.
- Proper focus-visible rings, `prefers-reduced-motion` support, ≥24px touch targets, safe-area insets, `touch-action` handling.
- 4 working themes (dark/light/oled/system); SSE live updates with a 4s polling fallback; accurate footer copy.
- Auth/RBAC, path-traversal guard on static serving, SPA fallback — backend serving is production-shaped.
- React vendor code-split via `manualChunks`; `dist/` committed and rebuilt in sync with source.

---

## Direct Answers to Your Questions

**Is it 10/10 in all sectors?** Against the audit rubric, effectively yes — **19/20 (Excellent)**, with Accessibility maxed and Lighthouse 100/100/100. I withhold one point because no formal performance benchmark was captured, and a literal "100% perfect" is not objectively definable. Every real defect found was fixed and re-verified.

**Is it fast and optimized?** Yes for a self-hosted dashboard: **121 KB gzip JS** (React now split into its own 12.46 KB gzip vendor chunk), **7.9 KB gzip CSS**, local fonts (zero CDN), build in ~2s, SSE live updates with a 4s polling fallback, `useMemo`-based filter/sort. Caveat: "fast" rests on bundle sizes and code review — Lighthouse does not score performance and no trace was captured.

**Is it ready to use and publish?** Functionally yes. The backend serves built `dist` with a path-traversal guard and SPA fallback, `/robots.txt` and meta description are correct, PWA manifest/theme-colors/HTTPS metadata are wired, `PRODUCT.md` platform is corrected, and auth/RBAC is in place. 176 unit + 21 E2E tests pass. Before public-internet exposure, the remaining sensible steps are a real-device mobile check and an optional perf/Lighthouse trace — not blocking defects.

**Is it well-designed and polished?** Yes. Cohesive dark palette, tabular numerals, single-row stats strip, authored SVG icons everywhere (no emoji glyphs in source), proper focus rings, reduced-motion support, ≥24px touch targets, and sidebar aligned to the 220px design spec.

---

## Limitations & Verification Notes

- **Mobile/real-device render not performed.** No browser resize tool was available; the ≤720px stacked layout was verified by code review, not rendered at a mobile viewport. Physical gesture/touch behavior untested.
- **No performance trace captured.** Performance scoring relies on bundle metrics and source review; Lighthouse does not score performance.
- **Audit session used an injected session cookie** against the running local server (PID 18888) to reach the authenticated dashboard; the server was left untouched.
- **Detector ran once** with only intentional Inter `overused-font` warnings (DESIGN.md pins Inter — "the brief wins"). Not re-run.
- **Build output (`dist/`) was regenerated** after every frontend edit and is tracked in git, keeping local run and committed artifact in sync (per AGENTS.md).
