from __future__ import annotations

"""PostgreSQL persistence for layer metadata.

This module matches the actual PostgreSQL ``layers`` table exactly.

Database columns:
    layer_id
    layer_type
    source_type
    layer_filename
    sha256
    crs
    extent_xmin
    extent_ymin
    extent_xmax
    extent_ymax
    width
    height
    created_at

Database access is provided through the SQLAlchemy-backed pool in
``database.db``. No direct ``psycopg_pool`` usage is required here.
"""

from typing import Protocol

from database.db import SQLAlchemyPoolAdapter


class LayerStore(Protocol):
    """Persistence contract used by the raster/application layer."""

    def list(self) -> list[dict]: ...

    def get(self, layer_id: str | int) -> dict | None: ...

    def upsert(self, record: dict) -> dict: ...


class PostgresLayerStore:
    """PostgreSQL implementation of the LayerStore contract."""

    def __init__(self, pool: SQLAlchemyPoolAdapter):
        self.pool = pool

    @staticmethod
    def _row_to_record(row: dict) -> dict:
        """Convert a PostgreSQL row to the application layer representation."""

        return {
            "layer_id": str(row["layer_id"]),
            "layer_type": row["layer_type"],
            "source_type": row["source_type"],
            "filename": row["layer_filename"],
            "sha256": row["sha256"],
            "crs": row["crs"],
            "extent": [
                float(row["extent_xmin"]),
                float(row["extent_ymin"]),
                float(row["extent_xmax"]),
                float(row["extent_ymax"]),
            ],
            "width": int(row["width"]) if row["width"] is not None else None,
            "height": int(row["height"]) if row["height"] is not None else None,
            "created_at": row["created_at"].isoformat(),
        }

    @staticmethod
    def _select_columns() -> str:
        """Return the exact layer column list from the database schema."""

        return """
            layer_id,
            layer_type,
            source_type,
            layer_filename,
            sha256,
            crs,
            extent_xmin,
            extent_ymin,
            extent_xmax,
            extent_ymax,
            width,
            height,
            created_at
        """

    def list(self) -> list[dict]:
        """Return all registered layers."""

        sql = f"""
            SELECT
                {self._select_columns()}
            FROM layers
            ORDER BY layer_id
        """

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql)

                return [
                    self._row_to_record(row)
                    for row in cur.fetchall()
                ]

    def get(self, layer_id: str | int) -> dict | None:
        """Return one layer by its database layer_id."""

        try:
            db_layer_id = int(layer_id)
        except (TypeError, ValueError) as exc:
            raise KeyError(
                f"Invalid layer ID: {layer_id}"
            ) from exc

        sql = f"""
            SELECT
                {self._select_columns()}
            FROM layers
            WHERE layer_id = %s
        """

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (db_layer_id,))
                row = cur.fetchone()

                return (
                    self._row_to_record(row)
                    if row is not None
                    else None
                )

    def upsert(self, record: dict) -> dict:
        """Insert a layer or reuse an existing file with the same SHA-256.

        Uploaded raster files have a SHA-256 and are deduplicated through the
        UNIQUE constraint on ``layers.sha256``.

        Basemap records may have ``sha256 = NULL``. PostgreSQL allows multiple
        NULL values under a normal UNIQUE constraint, so each basemap instance
        can be represented separately when explicitly registered.
        """

        extent = record.get("extent")

        if not isinstance(extent, (list, tuple)) or len(extent) != 4:
            raise ValueError(
                "Layer extent must contain "
                "[xmin, ymin, xmax, ymax]."
            )

        xmin, ymin, xmax, ymax = extent

        layer_type = record.get("layer_type")
        source_type = record.get("source_type")
        filename = record.get("filename")
        sha256 = record.get("sha256")
        crs = record.get("crs")
        width = record.get("width")
        height = record.get("height")

        if not layer_type:
            raise ValueError("layer_type is required.")

        if not source_type:
            raise ValueError("source_type is required.")

        if not filename:
            raise ValueError("filename is required.")

        if not crs:
            raise ValueError("crs is required.")

        if source_type == "uploaded":
            if not sha256:
                raise ValueError(
                    "Uploaded layers require a SHA-256 hash."
                )

            if width is None or height is None:
                raise ValueError(
                    "Uploaded layers require width and height."
                )

        if sha256 is None:
            # Basemap/non-file source: no SHA-256 conflict handling.
            sql = """
                INSERT INTO layers (
                    layer_type,
                    source_type,
                    layer_filename,
                    sha256,
                    crs,
                    extent_xmin,
                    extent_ymin,
                    extent_xmax,
                    extent_ymax,
                    width,
                    height
                )
                VALUES (
                    %s, %s, %s, NULL, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                RETURNING
                    layer_id,
                    layer_type,
                    source_type,
                    layer_filename,
                    sha256,
                    crs,
                    extent_xmin,
                    extent_ymin,
                    extent_xmax,
                    extent_ymax,
                    width,
                    height,
                    created_at
            """

            parameters = (
                layer_type,
                source_type,
                filename,
                crs,
                xmin,
                ymin,
                xmax,
                ymax,
                width,
                height,
            )

        else:
            # Uploaded file: reuse/update the existing row having the same
            # SHA-256, preserving the same database layer_id.
            sql = """
                INSERT INTO layers (
                    layer_type,
                    source_type,
                    layer_filename,
                    sha256,
                    crs,
                    extent_xmin,
                    extent_ymin,
                    extent_xmax,
                    extent_ymax,
                    width,
                    height
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (sha256)
                DO UPDATE SET
                    layer_type = EXCLUDED.layer_type,
                    source_type = EXCLUDED.source_type,
                    layer_filename = EXCLUDED.layer_filename,
                    crs = EXCLUDED.crs,
                    extent_xmin = EXCLUDED.extent_xmin,
                    extent_ymin = EXCLUDED.extent_ymin,
                    extent_xmax = EXCLUDED.extent_xmax,
                    extent_ymax = EXCLUDED.extent_ymax,
                    width = EXCLUDED.width,
                    height = EXCLUDED.height
                RETURNING
                    layer_id,
                    layer_type,
                    source_type,
                    layer_filename,
                    sha256,
                    crs,
                    extent_xmin,
                    extent_ymin,
                    extent_xmax,
                    extent_ymax,
                    width,
                    height,
                    created_at
            """

            parameters = (
                layer_type,
                source_type,
                filename,
                sha256,
                crs,
                xmin,
                ymin,
                xmax,
                ymax,
                width,
                height,
            )

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, parameters)
                row = cur.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Layer upsert did not return a database row."
                    )

                return self._row_to_record(row)
