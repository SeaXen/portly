# Hindsight review — Portly publish readiness

Reviewer: hindsight (review-team fallback; no rig/project.yaml or authored review event present).
Question: "Is Portly 10/10 in all sectors and ready to publish?"
Method: review forward from source; reconstruct intent; ask "do contracts lie?". Findings grounded in code, callers, and observed commands.

## Observed (ran these)
- `PORTLY_TESTING=1 python -m pytest tests --ignore=tests/e2e -q` → 151 passed, 13 warnings (149 before the two regression tests below were added).
- `npx tsc --noEmit` + `npm run build` → clean; JS 458 kB / 118 kB gzip (plan: ~392 kB).
- `tests/e2e` not run locally (Playwright not installed here); CI does run it.

## Verdict
Not literally "10/10 in all sectors" — that is not measurable, and several surfaces were not audited (live browser QA, Lighthouse/a11y audit, dependency CVE scan, e2e execution). But the prior 5–6/10 verdict in PORTLY_FIX_PLAN.md is stale: essentially all P0/P1 items are now implemented, and every concrete finding in this review has since been fixed. Publishable; no MUST-FIX security blocker found.

## Fixes applied after this review (owner follow-up)
- MEDIUM localhost links: `frontend/src/api.ts` `resolveAppUrl()` rewrites localhost/127.0.0.1/[::1] hosts to `window.location.hostname` centrally in `getApps`/`getAppDetail` (skips explicit `url_override`). All link consumers (`GridView`, `AppDetailModal`) go through it; no frontend test runner exists, so `tsc` + `vite build` are the only checks.
- LOW CI name: `.github/workflows/ci.yml:18` and `.forgejo/workflows/ci.yml:18` renamed "Backend Tests & Lint" → "Backend Tests".
- LOW import validation: `app.py` `import_data` now pre-validates required keys/types per section before any write; malformed backup → 400 `INVALID_BACKUP`. Regression test in `tests/test_review_fixes.py` (swaps in a tmp `Store`, asserts categories unchanged). Note: pre-validation, not true multi-statement DB atomicity.
- LOW `ls` allowlist: removed `"ls"` from `SAFE_COMMAND_BINARIES` (`docker_actions.py:633`); regression test assert added in `tests/test_review_fixes.py`.

## Findings

### MEDIUM — Server-mode deep links open the viewer's localhost by default — FIXED
`merge.py:158-170` builds `http://localhost:{port}` for wildcard/loopback binds when no `url_override` and no `public_host`. `public_host` defaults to `""` (`store.py:295`, `app.py:53`) and is not set in `docker-compose.yml`. No `window.location.hostname` substitution exists anywhere in frontend src. In the documented `PORTLY_MODE=server` / `0.0.0.0` deployment, clicking a discovered app opens a port on the *viewer's* machine, not the host, until an admin sets `public_host`. Mitigation: set `public_host` in settings (or per-app url_override). This is the residual half of prior P1-7.

### LOW — CI job named "Backend Tests & Lint" does not lint — FIXED (renamed)
`.github/workflows/ci.yml:18` — job runs `compileall` + pytest only; no ruff/flake8/mypy. The older "only runs compileall" concern is outdated (pytest at :40-43 and e2e job at :63-98 both run). Misleading name, not a coverage gap.

### LOW — Import accepts raw, unvalidated dict with no rollback — FIXED (pre-validation; not full atomicity)
`app.py:1789` `import_data(backup: Dict[str, Any])` upserts categories/rules/custom apps/views sequentially. A malformed backup can partially apply, leaving inconsistent state. Admin-only, so trust boundary is narrow. Export masking (`app.py:1764-1773`) and `reveal_secrets` are implemented correctly; `require_admin` present on export/import.

### LOW / INFO — Residual hardening notes
- ~~`SAFE_COMMAND_BINARIES` in `docker_actions.py:633` still includes `ls`~~ — FIXED: `ls` removed.
- `docker-compose.yml` has no `cap_add: SYS_PTRACE`; with `/hostfs:ro` and process inspection, reading other users' `/proc` fields may be restricted. Acceptable for the threat model, worth documenting.
- JS bundle grew ~392 kB → 458 kB (118 kB gzip). Still modest.

## Confirmed fixed from prior plan (evidence)
P0-4 command exec (argv allowlist, timeout clamp :717, 256 kB cap :734, audit :738); P0-7 favicon CSP (`app.py:725-753`); P0-2/D-1/D-2/F-1 auth + dialog semantics + focus trap + no alert/confirm; P1-1 no synthetic ramp (`stats.py:37-61,134`); P1-2/P0-6 real docker stats + stopped fallback (`docker_src.py:160,227,268`); P1-3 cached process objects (`host.py:36-81`); P1-5 health HTTP/TCP semantics (`health.py:106-143`); P1-9 `asyncio.to_thread` throughout; P1-12 tri-state hidden (`merge.py:136-139`); P1-14 UDP discovery real (`host.py:189-191`, netstat fallback :118); P1-20 settings key/type validation (`app.py:1652-1679`, manual rather than Pydantic but equivalent). Router-level auth on essentially all /api endpoints (`app.py:371,385`).

## Not checked / residual risk
E2E not executed locally (CI covers it); no live-browser, Lighthouse/WCAG, or CVE scan; no check that README's "21 e2e passed" badge is currently accurate (149 unit + 21 = 170 is internally consistent). `resolveAppUrl()` has no unit test (no frontend test runner in `package.json`). Import pre-validation is not true multi-statement DB atomicity — a mid-apply store error could still partially write. The localhost-link defect that would have bitten a default server-mode user on day one is now fixed.
