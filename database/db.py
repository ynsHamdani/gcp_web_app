from __future__ import annotations

"""SQLAlchemy-based PostgreSQL connection management.

The existing storage modules use a small psycopg-style interface:
    pool.connection()
    connection.cursor(...)
    cursor.execute(...)
    cursor.fetchone()
    cursor.fetchall()

This module keeps that interface while using SQLAlchemy internally.

Neon is configured through config.yaml with:
    sslmode: require
    channel_binding: require

SQLAlchemy uses psycopg 3 as the PostgreSQL driver:
    postgresql+psycopg://...
"""

from threading import Lock
from typing import Any

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Connection, Engine

from config import get_database_config


_engine: Engine | None = None
_engine_lock = Lock()

_pool: SQLAlchemyPoolAdapter | None = None
_pool_lock = Lock()


def get_db_engine() -> Engine:
    """Return the shared SQLAlchemy PostgreSQL engine."""

    global _engine

    if _engine is not None:
        return _engine

    with _engine_lock:
        if _engine is not None:
            return _engine

        db = get_database_config()

        url = URL.create(
            drivername="postgresql+psycopg",
            username=str(db["user"]),
            password=str(db["password"]),
            host=str(db["host"]),
            port=int(db.get("port", 5432)),
            database=str(db["name"]),
        )

        min_pool_size = int(db.get("min_pool_size", 1))
        max_pool_size = int(db.get("max_pool_size", 5))
        pool_timeout = float(db.get("pool_timeout_seconds", 10))

        if min_pool_size < 0:
            raise ValueError(
                "database.min_pool_size must be >= 0."
            )

        if max_pool_size < 1:
            raise ValueError(
                "database.max_pool_size must be >= 1."
            )

        if min_pool_size > max_pool_size:
            raise ValueError(
                "database.min_pool_size cannot be greater than "
                "database.max_pool_size."
            )

        connect_args = {
            "sslmode": str(db.get("sslmode", "require")),
            "channel_binding": str(
                db.get("channel_binding", "require")
            ),
            "connect_timeout": int(
                db.get("connect_timeout_seconds", 10)
            ),
        }

        max_overflow = max_pool_size - min_pool_size

        _engine = create_engine(
            url,
            connect_args=connect_args,
            pool_size=min_pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,
        )

    return _engine


class _CursorAdapter:
    """Cursor facade compatible with the existing storage modules."""

    def __init__(
        self,
        connection: Connection,
        row_factory: Any = None,
    ) -> None:
        self._connection = connection
        self._row_factory = row_factory
        self._result = None

    def __enter__(self) -> _CursorAdapter:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def execute(
        self,
        statement: str,
        parameters: Any = None,
    ) -> _CursorAdapter:
        """Execute SQL using the existing storage parameter style."""

        if parameters is None:
            self._result = self._connection.exec_driver_sql(
                statement
            )
        else:
            self._result = self._connection.exec_driver_sql(
                statement,
                parameters,
            )

        return self

    def fetchone(self) -> Any:
        """Return one row, optionally as a dictionary."""

        if self._result is None:
            raise RuntimeError(
                "fetchone() called before execute()."
            )

        row = self._result.fetchone()

        if row is None:
            return None

        if self._row_factory is not None:
            return dict(row._mapping)

        return row

    def fetchall(self) -> list[Any]:
        """Return all rows, optionally as dictionaries."""

        if self._result is None:
            raise RuntimeError(
                "fetchall() called before execute()."
            )

        rows = self._result.fetchall()

        if self._row_factory is not None:
            return [dict(row._mapping) for row in rows]

        return list(rows)


class _ConnectionAdapter:
    """Connection facade compatible with the existing storage modules."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def __enter__(self) -> _ConnectionAdapter:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._connection.close()

    def cursor(self, row_factory: Any = None) -> _CursorAdapter:
        return _CursorAdapter(
            self._connection,
            row_factory=row_factory,
        )


class SQLAlchemyPoolAdapter:
    """Expose pool.connection() while using SQLAlchemy's pool."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def connection(self) -> _ConnectionAdapter:
        """Open a connection for the existing storage API."""

        connection = self.engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        )

        return _ConnectionAdapter(connection)

    def close(self) -> None:
        """Dispose of the SQLAlchemy connection pool."""

        self.engine.dispose()


def get_db_pool() -> SQLAlchemyPoolAdapter:
    """Return the shared SQLAlchemy-backed pool adapter."""

    global _pool

    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is not None:
            return _pool

        _pool = SQLAlchemyPoolAdapter(get_db_engine())

    return _pool


def test_db_connection() -> str:
    """Test the database and return the PostgreSQL server version."""

    engine = get_db_engine()

    with engine.connect() as connection:
        return str(
            connection.exec_driver_sql(
                "SELECT version()"
            ).scalar_one()
        )


def close_db_pool() -> None:
    """Dispose of the shared SQLAlchemy engine/pool."""

    global _pool, _engine

    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None

        if _engine is not None:
            _engine.dispose()
            _engine = None
