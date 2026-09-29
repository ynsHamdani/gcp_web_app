from __future__ import annotations

"""PostgreSQL-backed persistence for Ground Control Points.

The application-facing record shape is deliberately kept independent of the
PostgreSQL column names. This implementation matches the current gcps schema:

    gcp_id, student_id, reference_layer_id, historical_layer_id,
    reference_x, reference_y, reference_lon, reference_lat,
    historical_pixel, historical_line,
    historical_x, historical_y, historical_lon, historical_lat,
    crs, offset_m, gcp_status, recorded_at

Deletion is ownership-aware in the storage layer:
- students may delete only their own GCPs;
- administrators may delete any GCP.
"""

from typing import Protocol

from database.db import SQLAlchemyPoolAdapter


class GCPStore(Protocol):
    """Persistence contract used by the GCP callbacks."""

    def list(self) -> list[dict]: ...

    def create(self, record: dict) -> dict: ...

    def get(self, gcp_id: str | int) -> dict | None: ...

    def update(self, gcp_id: str | int, changes: dict) -> dict: ...

    def delete(
        self,
        gcp_id: str | int,
        requester_id: int,
        requester_role: str = "student",
    ) -> None: ...


class PostgresGCPStore:
    """PostgreSQL implementation of the GCPStore contract."""

    def __init__(self, pool: SQLAlchemyPoolAdapter):
        self.pool = pool

    @staticmethod
    def _display_id(value: int) -> str:
        return f"GCP-{int(value):04d}"

    @staticmethod
    def _db_id(gcp_id: str | int) -> int:
        if isinstance(gcp_id, int):
            return gcp_id

        value = str(gcp_id).strip()

        if value.upper().startswith("GCP-"):
            value = value[4:]

        try:
            return int(value)
        except ValueError as exc:
            raise KeyError(f"Invalid GCP ID: {gcp_id}") from exc

    @classmethod
    def _row_to_record(cls, row: dict) -> dict:
        recorded_at = row["recorded_at"]

        return {
            "gcp_id": cls._display_id(row["gcp_id"]),
            "crs": row["crs"],
            "reference_layer_id": str(row["reference_layer_id"]),
            "historical_layer_id": str(row["historical_layer_id"]),
            "student_id": str(row["student_id"]),
            "reference": {
                "x": float(row["reference_x"]),
                "y": float(row["reference_y"]),
                "lon": float(row["reference_lon"]),
                "lat": float(row["reference_lat"]),
                "crs": row["crs"],
            },
            "historical": {
                "pixel": float(row["historical_pixel"]),
                "line": float(row["historical_line"]),
                "x": float(row["historical_x"]),
                "y": float(row["historical_y"]),
                "lon": float(row["historical_lon"]),
                "lat": float(row["historical_lat"]),
                "crs": row["crs"],
            },
            "offset_m": float(row["offset_m"]),
            "status": row["gcp_status"],
            "recorded_at": (
                recorded_at.isoformat()
                if hasattr(recorded_at, "isoformat")
                else str(recorded_at)
            ),
        }

    @staticmethod
    def _select_columns() -> str:
        return """
            gcp_id,
            student_id,
            reference_layer_id,
            historical_layer_id,
            reference_x,
            reference_y,
            reference_lon,
            reference_lat,
            historical_pixel,
            historical_line,
            historical_x,
            historical_y,
            historical_lon,
            historical_lat,
            crs,
            offset_m,
            gcp_status,
            recorded_at
        """

    def list(self) -> list[dict]:
        sql = f"""
            SELECT {self._select_columns()}
            FROM gcps
            ORDER BY gcp_id
        """

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql)
                return [
                    self._row_to_record(row)
                    for row in cur.fetchall()
                ]

    def get(self, gcp_id: str | int) -> dict | None:
        db_id = self._db_id(gcp_id)

        sql = f"""
            SELECT {self._select_columns()}
            FROM gcps
            WHERE gcp_id = %s
        """

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (db_id,))
                row = cur.fetchone()

                return (
                    self._row_to_record(row)
                    if row is not None
                    else None
                )

    def create(self, record: dict) -> dict:
        reference = record["reference"]
        historical = record["historical"]

        sql = """
            INSERT INTO gcps (
                student_id,
                reference_layer_id,
                historical_layer_id,
                reference_x,
                reference_y,
                reference_lon,
                reference_lat,
                historical_pixel,
                historical_line,
                historical_x,
                historical_y,
                historical_lon,
                historical_lat,
                crs,
                offset_m,
                gcp_status,
                recorded_at
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            RETURNING gcp_id
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        int(record["student_id"]),
                        int(record["reference_layer_id"]),
                        int(record["historical_layer_id"]),
                        reference["x"],
                        reference["y"],
                        reference["lon"],
                        reference["lat"],
                        historical["pixel"],
                        historical["line"],
                        historical["x"],
                        historical["y"],
                        historical["lon"],
                        historical["lat"],
                        record["crs"],
                        record["offset_m"],
                        record.get("status", "confirmed"),
                        record["recorded_at"],
                    ),
                )
                row = cur.fetchone()

                if row is None:
                    raise RuntimeError(
                        "GCP insert did not return a database ID."
                    )

                db_gcp_id = row[0]

        return self.get(db_gcp_id)

    def update(self, gcp_id: str | int, changes: dict) -> dict:
        """Update supported GCP fields using the current schema."""

        current = self.get(gcp_id)
        if current is None:
            raise KeyError(f"Unknown GCP: {gcp_id}")

        merged = dict(current)
        allowed_top = {"student_id", "offset_m", "status", "crs"}
        allowed_nested = {
            "reference": {"x", "y", "lon", "lat"},
            "historical": {
                "pixel",
                "line",
                "x",
                "y",
                "lon",
                "lat",
            },
        }

        for key, value in changes.items():
            if key in allowed_top:
                merged[key] = value
            elif key in allowed_nested:
                if not isinstance(value, dict):
                    raise ValueError(
                        f"{key} changes must be a dictionary."
                    )
                invalid = set(value) - allowed_nested[key]
                if invalid:
                    raise ValueError(
                        "Unsupported fields in "
                        f"{key}: {', '.join(sorted(invalid))}"
                    )
                merged[key] = {
                    **merged[key],
                    **value,
                }
            else:
                raise ValueError(f"Unsupported GCP field: {key}")

        reference = merged["reference"]
        historical = merged["historical"]
        db_id = self._db_id(gcp_id)

        sql = """
            UPDATE gcps
            SET
                student_id = %s,
                reference_x = %s,
                reference_y = %s,
                reference_lon = %s,
                reference_lat = %s,
                historical_pixel = %s,
                historical_line = %s,
                historical_x = %s,
                historical_y = %s,
                historical_lon = %s,
                historical_lat = %s,
                crs = %s,
                offset_m = %s,
                gcp_status = %s
            WHERE gcp_id = %s
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        int(merged["student_id"]),
                        reference["x"],
                        reference["y"],
                        reference["lon"],
                        reference["lat"],
                        historical["pixel"],
                        historical["line"],
                        historical["x"],
                        historical["y"],
                        historical["lon"],
                        historical["lat"],
                        merged["crs"],
                        merged["offset_m"],
                        merged["status"],
                        db_id,
                    ),
                )

                if cur.rowcount != 1:
                    raise KeyError(f"Unknown GCP: {gcp_id}")

        return self.get(db_id)

    def delete(
        self,
        gcp_id: str | int,
        requester_id: int,
        requester_role: str = "student",
    ) -> None:
        """Delete one GCP after checking the requester's ownership."""

        db_id = self._db_id(gcp_id)
        requester_id = int(requester_id)
        role = str(requester_role).strip().lower()

        if role == "admin":
            sql = """
                DELETE FROM gcps
                WHERE gcp_id = %s
                RETURNING gcp_id
            """
            params = (db_id,)
        else:
            sql = """
                DELETE FROM gcps
                WHERE gcp_id = %s
                  AND student_id = %s
                RETURNING gcp_id
            """
            params = (db_id, requester_id)

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                deleted = cur.fetchone()

                if deleted is not None:
                    return

                cur.execute(
                    "SELECT student_id FROM gcps WHERE gcp_id = %s",
                    (db_id,),
                )
                existing = cur.fetchone()

                if existing is None:
                    raise KeyError(f"Unknown GCP: {gcp_id}")

                raise PermissionError(
                    f"User {requester_id} is not allowed to delete "
                    f"GCP {self._display_id(db_id)}."
                )
