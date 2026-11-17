"""SQLite concurrency and stress tests (T-4)."""

import pytest
import concurrent.futures
from portly.backend.store import Store


def test_concurrent_store_writes(tmp_path):
    """Verify Store handles high-concurrency writes without 'database is locked' errors (T-4)."""
    db_path = str(tmp_path / "concurrent_stress.db")
    store = Store(db_path)

    def write_task(worker_id: int):
        for i in range(20):
            app_id = f"custom:worker_{worker_id}_task_{i}"
            store.save_app_override(
                app_id=app_id,
                category_id="development",
                tags=[f"tag_{worker_id}", "concurrent"],
                pinned=True,
            )
            store.log_audit_event(
                user="stress_tester",
                action="create_override",
                target=app_id,
                details={"worker": worker_id, "iteration": i},
                success=True,
            )

    # Launch 8 parallel threads executing 160 writes and 160 audit log writes
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(write_task, w) for w in range(8)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    # Verify all records persisted
    logs = store.get_audit_logs(limit=500)
    assert len(logs) == 160

    overrides = store.get_all_app_overrides()
    assert len(overrides) == 160


def test_schema_migration_version_pragma(tmp_path):
    """Verify user_version PRAGMA tracks migrations correctly (T-4, R-1)."""
    db_path = str(tmp_path / "schema_version.db")
    store = Store(db_path)

    with store._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version;")
        ver = cur.fetchone()[0]
        assert ver >= 1
