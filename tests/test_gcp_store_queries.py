from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from storage.gcp_store import PostgresGCPStore


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, row_factory=None):
        assert row_factory is True
        return self.cursor_instance


class FakePool:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.connection_instance = FakeConnection(self.rows)

    def connection(self):
        return self.connection_instance


def sample_row():
    return {
        "gcp_id": 7,
        "student_id": 3,
        "student_username": "dev_student",
        "student_email": "dev_student@gcp.local",
        "reference_layer_id": 2,
        "reference_layer_name": "Orthophoto",
        "reference_layer_source_type": "uploaded",
        "reference_layer_sha256": "a" * 64,
        "historical_layer_id": 8,
        "historical_layer_name": "Map 1890",
        "historical_layer_source_type": "uploaded",
        "historical_layer_sha256": "b" * 64,
        "reference_x": 500000.0,
        "reference_y": 6200000.0,
        "reference_lon": 10.2,
        "reference_lat": 56.1,
        "historical_pixel": 123.5,
        "historical_line": 456.5,
        "historical_x": 500002.0,
        "historical_y": 6200001.0,
        "historical_lon": 10.2001,
        "historical_lat": 56.1001,
        "crs": "EPSG:25832",
        "offset_m": 2.24,
        "gcp_status": "confirmed",
        "recorded_at": datetime(2026, 10, 13, tzinfo=timezone.utc),
    }


def test_student_query_is_scoped_and_joins_names():
    pool = FakePool([sample_row()])
    store = PostgresGCPStore(pool)

    records = store.list_for_student(3)

    cursor = pool.connection_instance.cursor_instance
    assert "g.student_id = %s" in cursor.sql
    assert cursor.params == (3,)
    assert "JOIN users u" in cursor.sql
    assert "JOIN layers rl" in cursor.sql
    assert "JOIN layers hl" in cursor.sql
    assert records[0]["student_username"] == "dev_student"
    assert records[0]["reference_layer_name"] == "Orthophoto"
    assert records[0]["historical_layer_name"] == "Map 1890"
    assert records[0]["reference"]["x"] == 500000.0


def test_admin_query_filters_by_student_and_historical_layer():
    pool = FakePool([sample_row()])
    store = PostgresGCPStore(pool)

    store.list_for_admin(student_id=3, historical_layer_id=8)

    cursor = pool.connection_instance.cursor_instance
    assert "g.student_id = %s" in cursor.sql
    assert "g.historical_layer_id = %s" in cursor.sql
    assert cursor.params == (3, 8)


def test_admin_query_without_filters_returns_all_gcp_rows():
    pool = FakePool([])
    store = PostgresGCPStore(pool)

    assert store.list_for_admin() == []
    cursor = pool.connection_instance.cursor_instance
    assert "JOIN users u" in cursor.sql
    assert "WHERE" not in cursor.sql
