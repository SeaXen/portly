"""SQLite data store and persistence for Portly."""

from contextlib import contextmanager
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("portly.store")

DEFAULT_DATA_DIR = os.getenv("PORTLY_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"))
DEFAULT_DB_PATH = os.path.join(DEFAULT_DATA_DIR, "portly.db")

_store_instances: Dict[str, "Store"] = {}
_store_lock = threading.Lock()


def _hash_token(token: str) -> str:
    """Return SHA-256 hash of a session token for secure storage at rest."""
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store:
    def __new__(cls, db_path: str = DEFAULT_DB_PATH):
        norm_path = os.path.abspath(db_path)
        with _store_lock:
            if norm_path not in _store_instances:
                instance = super(Store, cls).__new__(cls)
                _store_instances[norm_path] = instance
                instance._initialized = False
            return _store_instances[norm_path]

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        if getattr(self, "_initialized", False):
            return
        self.db_path = os.path.abspath(db_path)
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()
        self._run_migrations()
        self._initialized = True

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            # apps override table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS apps (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                name TEXT,
                icon TEXT,
                category_id TEXT,
                tags TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                pinned INTEGER DEFAULT NULL,
                hidden INTEGER DEFAULT NULL,
                sort_order INTEGER DEFAULT 0,
                url_override TEXT,
                created_at REAL NOT NULL
            );
            """)

            # categories
            conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                color TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'auto',
                sort_order INTEGER DEFAULT 0
            );
            """)

            # auto categorization rules
            conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                field TEXT NOT NULL,
                operator TEXT NOT NULL,
                value TEXT NOT NULL,
                priority INTEGER DEFAULT 10
            );
            """)

            # custom apps
            conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_apps (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                host TEXT NOT NULL DEFAULT 'localhost',
                port INTEGER NOT NULL,
                health_path TEXT DEFAULT '/health',
                health_interval INTEGER DEFAULT 30,
                start_cmd TEXT,
                stop_cmd TEXT,
                workdir TEXT,
                log_file TEXT,
                start_on_boot INTEGER DEFAULT 0,
                env_json TEXT DEFAULT '{}',
                update_cmd TEXT,
                created_at REAL NOT NULL
            );
            """)

            # views
            conn.execute("""
            CREATE TABLE IF NOT EXISTS views (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                filters_json TEXT DEFAULT '{}',
                sort_json TEXT DEFAULT '{}',
                group_by TEXT DEFAULT 'none',
                view_type TEXT DEFAULT 'table',
                columns_json TEXT DEFAULT '[]'
            );
            """)

            # events
            conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                type TEXT NOT NULL,
                app_id TEXT,
                message TEXT NOT NULL,
                actor TEXT DEFAULT 'system'
            );
            """)

            # health history
            conn.execute("""
            CREATE TABLE IF NOT EXISTS health_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT NOT NULL,
                ts REAL NOT NULL,
                ok INTEGER NOT NULL,
                latency_ms REAL NOT NULL
            );
            """)

            # settings
            conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """)

            # users
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at REAL NOT NULL
            );
            """)

            # sessions
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            """)

            # port change snapshots for rollback
            conn.execute("""
            CREATE TABLE IF NOT EXISTS port_snapshots (
                app_id TEXT PRIMARY KEY,
                original_port INTEGER NOT NULL,
                new_port INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """)

            conn.commit()

            # Seed default categories if empty
            cur = conn.execute("SELECT COUNT(*) as cnt FROM categories")
            if cur.fetchone()["cnt"] == 0:
                defaults = [
                    ("development", "Development", "#8C9EFF", "auto", 1),
                    ("databases", "Databases", "#5EEAD4", "auto", 2),
                    ("monitoring", "Monitoring", "#FBBF77", "auto", 3),
                    ("automation", "Automation", "#F5A3D0", "manual", 4),
                    ("infrastructure", "Infrastructure", "#B6E36B", "manual", 5),
                    ("uncategorized", "Uncategorized", "#8D95A5", "auto", 6),
                ]
                conn.executemany(
                    "INSERT INTO categories (id, name, color, mode, sort_order) VALUES (?, ?, ?, ?, ?)",
                    defaults
                )

            # Seed default rules if empty
            cur = conn.execute("SELECT COUNT(*) as cnt FROM rules")
            if cur.fetchone()["cnt"] == 0:
                rule_defaults = [
                    ("r1", "databases", "image", "contains", "postgres", 10),
                    ("r2", "databases", "image", "contains", "redis", 10),
                    ("r3", "databases", "image", "contains", "mysql", 10),
                    ("r4", "databases", "image", "contains", "mongo", 10),
                    ("r5", "databases", "process", "contains", "postgres", 10),
                    ("r6", "databases", "process", "contains", "redis", 10),
                    ("r7", "databases", "process", "contains", "mysql", 10),
                    ("r8", "databases", "process", "contains", "mongod", 10),
                    ("r9", "monitoring", "image", "contains", "grafana", 10),
                    ("r10", "monitoring", "image", "contains", "prometheus", 10),
                    ("r11", "monitoring", "image", "contains", "influx", 10),
                    ("r12", "infrastructure", "image", "contains", "traefik", 10),
                    ("r13", "infrastructure", "image", "contains", "nginx", 10),
                    ("r14", "infrastructure", "image", "contains", "caddy", 10),
                    ("r15", "development", "cmdline", "contains", "vite", 20),
                    ("r16", "development", "cmdline", "contains", "webpack", 20),
                    ("r17", "development", "cmdline", "contains", "next", 20),
                ]
                conn.executemany(
                    "INSERT INTO rules (id, category_id, field, operator, value, priority) VALUES (?, ?, ?, ?, ?, ?)",
                    rule_defaults
                )

            # Seed default settings
            default_settings = {
                "safe_mode": "true",
                "refresh_interval": "3",
                "theme": "dark",
                "accent": "#8C9EFF",
                "density": "compact",
                "default_view": "table",
                "notify_new_ports": "true",
                "auto_refresh": "true",
                "public_host": "",
                "auto_relock_minutes": "0",
                "webhook_enabled": "false",
                "webhook_url": "",
                "webhook_type": "generic",
                "webhook_events": "port_opened,port_closed,container_state,port_conflict",
            }
            for k, v in default_settings.items():
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

            conn.commit()

    def _run_migrations(self):
        """Applies ordered schema migrations via PRAGMA user_version."""
        with self._get_connection() as conn:
            cur = conn.execute("PRAGMA user_version;")
            ver_row = cur.fetchone()
            current_ver = ver_row[0] if ver_row else 0

            if current_ver < 1:
                # Add indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_health_app_ts ON health_history(app_id, ts);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_category ON apps(category_id);")

                # Verify actor column in events
                cur = conn.execute("PRAGMA table_info(events);")
                cols = [c["name"] for c in cur.fetchall()]
                if "actor" not in cols:
                    conn.execute("ALTER TABLE events ADD COLUMN actor TEXT DEFAULT 'system';")

                conn.execute("PRAGMA user_version = 1;")
                conn.commit()

    # App overrides
    def get_app(self, app_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM apps WHERE id = ?", (app_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["tags"] = json.loads(res.get("tags") or "[]")
            res["pinned"] = bool(res["pinned"]) if res.get("pinned") is not None else None
            res["hidden"] = bool(res["hidden"]) if res.get("hidden") is not None else None
            return res

    def get_all_app_overrides(self) -> Dict[str, Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM apps")
            res = {}
            for row in cur.fetchall():
                d = dict(row)
                d["tags"] = json.loads(d.get("tags") or "[]")
                d["pinned"] = bool(d["pinned"]) if d.get("pinned") is not None else None
                d["hidden"] = bool(d["hidden"]) if d.get("hidden") is not None else None
                res[d["id"]] = d
            return res

    def upsert_app_override(self, app_id: str, **kwargs) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM apps WHERE id = ?", (app_id,))
            row = cur.fetchone()
            now = time.time()
            if row:
                d = dict(row)
                for k, v in kwargs.items():
                    if k in d or k in ("pinned", "hidden", "sort_order", "category_id", "name", "icon", "tags", "notes", "url_override"):
                        d[k] = v
                tags_str = json.dumps(d.get("tags") or []) if isinstance(d.get("tags"), list) else str(d.get("tags") or "[]")
                pinned_val = 1 if d.get("pinned") is True else (0 if d.get("pinned") is False else None)
                hidden_val = 1 if d.get("hidden") is True else (0 if d.get("hidden") is False else None)
                conn.execute("""
                    UPDATE apps SET
                        name = ?,
                        icon = ?,
                        category_id = ?,
                        tags = ?,
                        notes = ?,
                        pinned = ?,
                        hidden = ?,
                        sort_order = ?,
                        url_override = ?
                    WHERE id = ?
                """, (
                    d.get("name"),
                    d.get("icon"),
                    d.get("category_id"),
                    tags_str,
                    d.get("notes", ""),
                    pinned_val,
                    hidden_val,
                    d.get("sort_order", 0),
                    d.get("url_override"),
                    app_id
                ))
            else:
                source = kwargs.get("source", "host" if app_id.startswith("host:") else ("docker" if app_id.startswith("docker:") else "custom"))
                tags = kwargs.get("tags", [])
                tags_str = json.dumps(tags) if isinstance(tags, list) else str(tags)
                pinned_val = 1 if kwargs.get("pinned") is True else (0 if kwargs.get("pinned") is False else None)
                hidden_val = 1 if kwargs.get("hidden") is True else (0 if kwargs.get("hidden") is False else None)
                conn.execute("""
                    INSERT INTO apps (id, source, name, icon, category_id, tags, notes, pinned, hidden, sort_order, url_override, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    app_id,
                    source,
                    kwargs.get("name"),
                    kwargs.get("icon"),
                    kwargs.get("category_id"),
                    tags_str,
                    kwargs.get("notes", ""),
                    pinned_val,
                    hidden_val,
                    kwargs.get("sort_order", 0),
                    kwargs.get("url_override"),
                    now
                ))
            conn.commit()
            return self.get_app(app_id) or {}

    # Categories
    def get_categories(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM categories ORDER BY sort_order ASC, name ASC")
            return [dict(r) for r in cur.fetchall()]

    def upsert_category(self, cat_id: str, name: str, color: str, mode: str = "manual", sort_order: int = 0) -> Dict[str, Any]:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO categories (id, name, color, mode, sort_order)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    color = excluded.color,
                    mode = excluded.mode,
                    sort_order = excluded.sort_order
            """, (cat_id, name, color, mode, sort_order))
            conn.commit()
        return {"id": cat_id, "name": name, "color": color, "mode": mode, "sort_order": sort_order}

    def delete_category(self, cat_id: str):
        if cat_id == "uncategorized":
            raise ValueError("Cannot delete default 'uncategorized' category.")
        with self._get_connection() as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
            conn.execute("DELETE FROM rules WHERE category_id = ?", (cat_id,))
            conn.execute("UPDATE apps SET category_id = 'uncategorized' WHERE category_id = ?", (cat_id,))
            conn.commit()

    # Rules
    def get_rules(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM rules ORDER BY priority ASC, id ASC")
            return [dict(r) for r in cur.fetchall()]

    def add_rule(self, rule_id: str, category_id: str, field: str, operator: str, value: str, priority: int = 10) -> Dict[str, Any]:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO rules (id, category_id, field, operator, value, priority)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (rule_id, category_id, field, operator, value, priority))
            conn.commit()
        return {"id": rule_id, "category_id": category_id, "field": field, "operator": operator, "value": value, "priority": priority}

    def delete_rule(self, rule_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
            conn.commit()

    # Custom Apps
    def get_custom_apps(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM custom_apps ORDER BY created_at DESC")
            res = []
            for r in cur.fetchall():
                d = dict(r)
                d["env"] = json.loads(d.get("env_json") or "{}")
                d["start_on_boot"] = bool(d.get("start_on_boot"))
                res.append(d)
            return res

    def get_custom_app(self, app_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM custom_apps WHERE id = ?", (app_id,))
            r = cur.fetchone()
            if not r:
                return None
            d = dict(r)
            d["env"] = json.loads(d.get("env_json") or "{}")
            d["start_on_boot"] = bool(d.get("start_on_boot"))
            return d

    def upsert_custom_app(self, app_id: str, name: str, host: str, port: int, **kwargs) -> Dict[str, Any]:
        with self._get_connection() as conn:
            now = time.time()
            env_json = json.dumps(kwargs.get("env", {}))
            conn.execute("""
                INSERT INTO custom_apps (
                    id, name, host, port, health_path, health_interval,
                    start_cmd, stop_cmd, workdir, log_file, start_on_boot,
                    env_json, update_cmd, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    host = excluded.host,
                    port = excluded.port,
                    health_path = excluded.health_path,
                    health_interval = excluded.health_interval,
                    start_cmd = excluded.start_cmd,
                    stop_cmd = excluded.stop_cmd,
                    workdir = excluded.workdir,
                    log_file = excluded.log_file,
                    start_on_boot = excluded.start_on_boot,
                    env_json = excluded.env_json,
                    update_cmd = excluded.update_cmd
            """, (
                app_id,
                name,
                host,
                port,
                kwargs.get("health_path", "/health"),
                kwargs.get("health_interval", 30),
                kwargs.get("start_cmd"),
                kwargs.get("stop_cmd"),
                kwargs.get("workdir"),
                kwargs.get("log_file"),
                1 if kwargs.get("start_on_boot") else 0,
                env_json,
                kwargs.get("update_cmd"),
                now
            ))
            conn.commit()
        return self.get_custom_app(app_id) or {}

    def create_custom_app(self, app_id: str, name: str, port: int, host: str = "localhost", **kwargs) -> Dict[str, Any]:
        return self.upsert_custom_app(app_id=app_id, name=name, host=host, port=port, **kwargs)

    def save_custom_app(self, data: Dict[str, Any]) -> Dict[str, Any]:
        app_id = data.get("id") or f"custom_{int(time.time()*1000)}"
        return self.upsert_custom_app(
            app_id=app_id,
            name=data.get("name", "Custom App"),
            host=data.get("host", "localhost"),
            port=int(data.get("port", 80)),
            health_path=data.get("health_path"),
            health_interval=data.get("health_interval", 30),
            start_cmd=data.get("start_cmd"),
            stop_cmd=data.get("stop_cmd"),
            workdir=data.get("workdir"),
            log_file=data.get("log_file"),
            start_on_boot=bool(data.get("start_on_boot")),
            env=data.get("env") or {},
            update_cmd=data.get("update_cmd"),
        )

    def delete_custom_app(self, app_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM custom_apps WHERE id = ?", (app_id,))
            conn.execute("DELETE FROM apps WHERE id = ?", (app_id,))
            conn.commit()

    # Views
    def get_views(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM views")
            res = []
            for r in cur.fetchall():
                d = dict(r)
                d["filters"] = json.loads(d.get("filters_json") or "{}")
                d["sort"] = json.loads(d.get("sort_json") or "{}")
                d["columns"] = json.loads(d.get("columns_json") or "[]")
                res.append(d)
            return res

    def save_view(self, view_id: str, name: str, filters: Dict[str, Any], sort: Dict[str, Any], group_by: str, view_type: str, columns: List[str]) -> Dict[str, Any]:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO views (id, name, filters_json, sort_json, group_by, view_type, columns_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    filters_json = excluded.filters_json,
                    sort_json = excluded.sort_json,
                    group_by = excluded.group_by,
                    view_type = excluded.view_type,
                    columns_json = excluded.columns_json
            """, (
                view_id,
                name,
                json.dumps(filters),
                json.dumps(sort),
                group_by,
                view_type,
                json.dumps(columns)
            ))
            conn.commit()
        return {"id": view_id, "name": name, "filters": filters, "sort": sort, "group_by": group_by, "view_type": view_type, "columns": columns}

    def delete_view(self, view_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM views WHERE id = ?", (view_id,))
            conn.commit()

    # Events
    def log_event(self, event_type: str, message: str, app_id: Optional[str] = None, actor: str = "system", max_events: int = 1000) -> Dict[str, Any]:
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.execute("""
                INSERT INTO events (ts, type, app_id, message, actor)
                VALUES (?, ?, ?, ?, ?)
            """, (now, event_type, app_id, message, actor))
            conn.execute("""
                DELETE FROM events WHERE id NOT IN (
                    SELECT id FROM events ORDER BY id DESC LIMIT ?
                )
            """, (max_events,))
            conn.commit()
            return {"id": cur.lastrowid, "ts": now, "type": event_type, "app_id": app_id, "message": message, "actor": actor}

    def get_events(self, limit: int = 100, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if event_type:
                cur = conn.execute("SELECT * FROM events WHERE type = ? ORDER BY ts DESC LIMIT ?", (event_type, limit))
            else:
                cur = conn.execute("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_audit_logs(self, limit: int = 100, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.get_events(limit=limit, event_type=event_type)

    def log_audit_event(self, user: str, action: str, target: str, details: Any = None, success: bool = True):
        desc = f"{action} on {target}"
        if details:
            desc += f" ({details})"
        return self.log_event(action, desc, actor=user)

    def save_app_override(self, app_id: str, **kwargs):
        return self.upsert_app_override(app_id, **kwargs)

    # Health history
    def record_health(self, app_id: str, ok: bool, latency_ms: float, max_history: int = 200):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO health_history (app_id, ts, ok, latency_ms)
                VALUES (?, ?, ?, ?)
            """, (app_id, now, 1 if ok else 0, latency_ms))
            conn.execute("""
                DELETE FROM health_history WHERE app_id = ? AND id NOT IN (
                    SELECT id FROM health_history WHERE app_id = ? ORDER BY id DESC LIMIT ?
                )
            """, (app_id, app_id, max_history))
            conn.commit()

    def get_health_history(self, app_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT ts, ok, latency_ms FROM health_history
                WHERE app_id = ? ORDER BY ts DESC LIMIT ?
            """, (app_id, limit))
            rows = [dict(r) for r in cur.fetchall()]
            rows.reverse()
            return rows

    # Port snapshots for rollback
    def save_port_snapshot(self, app_id: str, original_port: int, new_port: int, config: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO port_snapshots (app_id, original_port, new_port, config_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (app_id, original_port, new_port, json.dumps(config), time.time()))
            conn.commit()

    def get_port_snapshot(self, app_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM port_snapshots WHERE app_id = ?", (app_id,))
            r = cur.fetchone()
            if not r:
                return None
            d = dict(r)
            d["config"] = json.loads(d.get("config_json") or "{}")
            return d

    def clear_port_snapshot(self, app_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM port_snapshots WHERE app_id = ?", (app_id,))
            conn.commit()

    # Settings
    def get_settings(self) -> Dict[str, str]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT key, value FROM settings")
            return {r["key"]: r["value"] for r in cur.fetchall()}

    def get_setting(self, key: str, default: str = "") -> str:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            r = cur.fetchone()
            return r["value"] if r else default

    def set_setting(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, value))
            conn.commit()

    # Users
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            r = cur.fetchone()
            return dict(r) if r else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            r = cur.fetchone()
            return dict(r) if r else None

    def get_user_count(self) -> int:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) as cnt FROM users")
            return cur.fetchone()["cnt"]

    def list_users(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at ASC")
            return [dict(r) for r in cur.fetchall()]

    def create_user(self, user_id: str, username: str, password_hash: str, role: str = "admin") -> Dict[str, Any]:
        with self._get_connection() as conn:
            now = time.time()
            conn.execute("""
                INSERT INTO users (id, username, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, password_hash, role, now))
            conn.commit()
            return {"id": user_id, "username": username, "role": role, "created_at": now}

    def delete_user(self, user_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()

    def update_user_password(self, user_id: str, new_password_hash: str):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
            conn.commit()

    def update_user_role(self, user_id: str, role: str):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            conn.commit()

    # Sessions
    def save_session(self, token: str, user_id: str, username: str, role: str, expires_at: float):
        now = time.time()
        token_hash = _hash_token(token)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (token, user_id, username, role, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (token_hash, user_id, username, role, now, expires_at))
            conn.commit()

    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        token_hash = _hash_token(token)
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM sessions WHERE token = ? OR token = ?", (token_hash, token))
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_session(self, token: str):
        token_hash = _hash_token(token)
        with self._get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ? OR token = ?", (token_hash, token))
            conn.commit()

    def delete_user_sessions(self, user_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()

    def prune_expired_sessions(self):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            conn.commit()
