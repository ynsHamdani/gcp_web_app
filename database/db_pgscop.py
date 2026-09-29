from __future__ import annotations

"""PostgreSQL connection-pool management.

The rest of the application does not open PostgreSQL connections directly.
Storage classes receive this pool and own their SQL statements.
"""

from pathlib import Path
from threading import Lock

import yaml
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from config import CONFIG_YAML_PATH


_pool: ConnectionPool | None = None
_pool_lock = Lock()


def _load_database_config() -> dict:
    """Read the local, git-ignored database configuration."""

    path = Path(CONFIG_YAML_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Database configuration file not found: {path}. "
            "Copy config.example.yaml to config.yaml and configure it."
        )

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    database = config.get("database")
    if not isinstance(database, dict):
        raise ValueError("config.yaml must contain a 'database' section.")

    required = ("host", "port", "name", "user", "password")
    missing = [key for key in required if database.get(key) in (None, "")]
    if missing:
        raise ValueError(
            "Missing database configuration values: "
            + ", ".join(missing)
        )

    return database


def get_db_pool() -> ConnectionPool:
    """Return the shared PostgreSQL connection pool."""

    global _pool

    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is not None:
            return _pool

        db = _load_database_config()

        conninfo = make_conninfo(
            host=db["host"],
            port=int(db["port"]),
            dbname=db["name"],
            user=db["user"],
            password=db["password"],
        )

        _pool = ConnectionPool(
            conninfo=conninfo,
            min_size=int(db.get("min_pool_size", 1)),
            max_size=int(db.get("max_pool_size", 5)),
            timeout=float(db.get("pool_timeout_seconds", 10)),
            open=True,
        )

    return _pool


def close_db_pool() -> None:
    """Close the shared PostgreSQL pool during application shutdown."""

    global _pool

    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
