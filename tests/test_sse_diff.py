"""Tests for SSE snapshot fingerprinting used to skip redundant broadcasts."""

from portly.backend.app import _sse_snapshot_fingerprint


def test_sse_fingerprint_ignores_fresh_stats_age_ticks():
    app_t1 = [{"id": "docker:web", "name": "web", "port": 8080, "cpu_percent": 1.2, "stats_age_sec": 2.1}]
    app_t2 = [{"id": "docker:web", "name": "web", "port": 8080, "cpu_percent": 1.2, "stats_age_sec": 5.4}]

    k1 = _sse_snapshot_fingerprint(app_t1, [], True, "")
    k2 = _sse_snapshot_fingerprint(app_t2, [], True, "")
    assert k1 == k2


def test_sse_fingerprint_detects_staleness_and_field_changes():
    fresh = [{"id": "docker:web", "name": "web", "port": 8080, "cpu_percent": 1.2, "stats_age_sec": 12.0}]
    stale = [{"id": "docker:web", "name": "web", "port": 8080, "cpu_percent": 1.2, "stats_age_sec": 18.0}]
    cpu_changed = [{"id": "docker:web", "name": "web", "port": 8080, "cpu_percent": 4.5, "stats_age_sec": 12.0}]

    k_fresh = _sse_snapshot_fingerprint(fresh, [], True, "")
    k_stale = _sse_snapshot_fingerprint(stale, [], True, "")
    k_cpu = _sse_snapshot_fingerprint(cpu_changed, [], True, "")

    assert k_fresh != k_stale
    assert k_fresh != k_cpu
