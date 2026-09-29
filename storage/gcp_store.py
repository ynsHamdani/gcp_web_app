from __future__ import annotations

"""PostgreSQL persistence for Ground Control Points.

This store matches the actual gcps table created by the database SQL schema.
It does not invent separate reference_crs/historical_crs columns; the
database has one shared ``crs`` column.
"""

from typing import Protocol

from database.db import SQLAlchemyPoolAdapter


class GCPStore(Protocol):
    def list(self) -> list[dict]: ...
    def create(self, record: dict) -> dict: ...
    def get(self, gcp_id: str | int) -> dict | None: ...
    def update(self, gcp_id: str | int, changes: dict) -> dict: ...
    def delete(self, gcp_id: str | int) -> None: ...


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
        crs = row["crs"]

        return {
            "gcp_id": cls._display_id(row["gcp_id"]),
            "crs": crs,
            "reference_layer_id": str(row["reference_layer_id"]),
            "historical_layer_id": str(row["historical_layer_id"]),
            "student_id": str(row["student_id"]),
            "reference": {
                "x": float(row["reference_x"]),
                "y": float(row["reference_y"]),
                "lon": float(row["reference_lon"]),
                "lat": float(row["reference_lat"]),
                "crs": crs,
            },
            "historical": {
                "pixel": float(row["historical_pixel"]),
                "line": float(row["historical_line"]),
                "x": float(row["historical_x"]),
                "y": float(row["historical_y"]),
                "lon": float(row["historical_lon"]),
                "lat": float(row["historical_lat"]),
                "crs": crs,
            },
            "offset_m": float(row["offset_m"]),
            "status": row["gcp_status"],
            "recorded_at": row["recorded_at"].isoformat(),
        }

    @staticmethod
    def _select_sql(extra_where: str = "") -> str:
        return f"""
            SELECT
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
            FROM gcps
            {extra_where}
        """

    def list(self) -> list[dict]:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(self._select_sql("ORDER BY gcp_id"))
                return [
                    self._row_to_record(row)
                    for row in cur.fetchall()
                ]

    def get(self, gcp_id: str | int) -> dict | None:
        db_id = self._db_id(gcp_id)

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(
                    self._select_sql("WHERE gcp_id = %s"),
                    (db_id,),
                )
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
                %s, %s,
                %s, %s, %s, %s,
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
                        record["status"],
                        record["recorded_at"],
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(
                        "INSERT returned no GCP ID."
                    )
                db_gcp_id = row[0]

        result = self.get(db_gcp_id)
        if result is None:
            raise RuntimeError(
                f"GCP {db_gcp_id} was inserted but could not be read back."
            )
        return result

    def update(self, gcp_id: str | int, changes: dict) -> dict:
        current = self.get(gcp_id)
        if current is None:
            raise KeyError(f"Unknown GCP: {gcp_id}")

        merged = {
            **current,
            "reference": {
                **current["reference"],
                **changes.get("reference", {}),
            },
            "historical": {
                **current["historical"],
                **changes.get("historical", {}),
            },
        }

        for key in ("student_id", "offset_m", "status", "crs"):
            if key in changes:
                merged[key] = changes[key]

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

    def delete(self, gcp_id: str | int) -> None:
        db_id = self._db_id(gcp_id)

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM gcps WHERE gcp_id = %s",
                    (db_id,),
                )

                if cur.rowcount != 1:
                    raise KeyError(f"Unknown GCP: {gcp_id}")
