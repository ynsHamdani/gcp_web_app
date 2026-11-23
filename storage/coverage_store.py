from __future__ import annotations

"""PostgreSQL/PostGIS persistence for versioned coverage layers."""

import json
import re
from typing import Any

from sqlalchemy import text


_LAYER_NAME_RE = re.compile(r"^[^\x00]{2,160}$")


class CoverageStore:
    """Store versioned polygon layers independently of the GCP tables.

    ``publish_import`` uses one SQLAlchemy transaction for the registry row and
    all features. A failed feature insert therefore cannot leave a partially
    published layer behind.
    """

    def __init__(self, pool) -> None:
        self.pool = pool
        self.engine = getattr(pool, "engine", None)
        if self.engine is None:
            raise TypeError("CoverageStore requires the SQLAlchemy-backed database pool.")

    @staticmethod
    def validate_layer_metadata(layer_name: str, notes: str | None = None) -> tuple[str, str]:
        name = str(layer_name or "").strip()
        normalized_notes = str(notes or "").strip()
        if not name:
            raise ValueError("Enter a name for this coverage layer.")
        if not _LAYER_NAME_RE.fullmatch(name):
            raise ValueError("Coverage layer names must contain 2–160 characters.")
        if normalized_notes and len(normalized_notes) > 2000:
            raise ValueError("Notes must not exceed 2,000 characters.")
        if "\x00" in name or "\x00" in normalized_notes:
            raise ValueError("Coverage layer name and notes cannot contain null characters.")
        return name, normalized_notes

    def list_layers(self) -> list[dict[str, Any]]:
        """Return all published versions, newest first within each layer name."""
        sql = """
            SELECT
                l.coverage_layer_id,
                l.layer_name,
                l.version,
                l.source_filename,
                l.source_format,
                l.source_layer_name,
                l.source_crs,
                l.target_srid,
                l.geometry_type,
                l.feature_count,
                l.source_sha256,
                l.notes,
                l.is_active,
                l.imported_at,
                u.username AS imported_by_username,
                COUNT(f.coverage_feature_id) AS stored_feature_count
            FROM coverage_layers AS l
            LEFT JOIN coverage_features AS f
                ON f.coverage_layer_id = l.coverage_layer_id
            LEFT JOIN users AS u
                ON u.user_id = l.imported_by
            GROUP BY l.coverage_layer_id, u.username
            ORDER BY LOWER(l.layer_name), l.version DESC
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            imported_at = item.get("imported_at")
            item["imported_at"] = imported_at.isoformat(timespec="minutes") if imported_at else ""
            item["coverage_layer_id"] = str(item["coverage_layer_id"])
            for key in ("version", "target_srid", "feature_count", "stored_feature_count"):
                item[key] = int(item[key]) if item.get(key) is not None else 0
            item["is_active"] = bool(item.get("is_active"))
            result.append(item)
        return result

    def publish_import(
        self,
        *,
        layer_name: str,
        notes: str,
        import_data,
        imported_by: int,
    ) -> dict[str, Any]:
        """Publish a fully validated import as a new immutable layer version."""
        name, normalized_notes = self.validate_layer_metadata(layer_name, notes)
        if not getattr(import_data, "features", None):
            raise ValueError("The validated import does not contain any polygon features.")
        if int(import_data.feature_count) != len(import_data.features):
            raise ValueError("The import feature count does not match the prepared feature records.")

        insert_layer_sql = text("""
            INSERT INTO coverage_layers (
                layer_name, version, source_filename, source_format,
                source_layer_name, source_crs, target_srid, geometry_type,
                feature_count, source_sha256, notes, imported_by, is_active
            ) VALUES (
                :layer_name, :version, :source_filename, :source_format,
                :source_layer_name, :source_crs, :target_srid, :geometry_type,
                :feature_count, :source_sha256, :notes, :imported_by, TRUE
            )
            RETURNING coverage_layer_id
        """)
        insert_feature_sql = text("""
            INSERT INTO coverage_features (
                coverage_layer_id, source_feature_key, feature_label,
                source_index, attributes, geom
            ) VALUES (
                :coverage_layer_id, :source_feature_key, :feature_label,
                :source_index, CAST(:attributes_json AS jsonb),
                ST_Multi(
                    ST_SetSRID(
                        ST_GeomFromWKB(decode(:geometry_wkb_hex, 'hex')),
                        :target_srid
                    )
                )
            )
        """)

        with self.engine.begin() as connection:
            # Serialize version assignment for the same case-insensitive name.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
                {"lock_name": name.casefold()},
            )
            duplicate = connection.execute(
                text("""
                    SELECT version
                    FROM coverage_layers
                    WHERE LOWER(layer_name) = LOWER(:layer_name)
                      AND source_sha256 = :source_sha256
                    ORDER BY version DESC
                    LIMIT 1
                """),
                {"layer_name": name, "source_sha256": import_data.source_sha256},
            ).scalar_one_or_none()
            if duplicate is not None:
                raise ValueError(
                    f"This exact file is already registered for '{name}' as version {int(duplicate)}. "
                    "Upload a revised file or choose another layer name."
                )

            version = connection.execute(
                text("""
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM coverage_layers
                    WHERE LOWER(layer_name) = LOWER(:layer_name)
                """),
                {"layer_name": name},
            ).scalar_one()

            # Previous versions remain available but are no longer active.
            connection.execute(
                text("""
                    UPDATE coverage_layers
                    SET is_active = FALSE
                    WHERE LOWER(layer_name) = LOWER(:layer_name)
                      AND is_active = TRUE
                """),
                {"layer_name": name},
            )

            layer_id = connection.execute(insert_layer_sql, {
                "layer_name": name,
                "version": int(version),
                "source_filename": import_data.filename,
                "source_format": import_data.source_format,
                "source_layer_name": import_data.source_layer_name,
                "source_crs": import_data.source_crs,
                "target_srid": int(import_data.target_srid),
                "geometry_type": import_data.geometry_type,
                "feature_count": int(import_data.feature_count),
                "source_sha256": import_data.source_sha256,
                "notes": normalized_notes,
                "imported_by": int(imported_by),
            }).scalar_one()

            # Batch insert keeps memory bounded and all writes stay in the same transaction.
            batch_size = 500
            for start in range(0, len(import_data.features), batch_size):
                batch = import_data.features[start:start + batch_size]
                params = [{
                    "coverage_layer_id": int(layer_id),
                    "source_feature_key": feature.source_feature_key,
                    "feature_label": feature.feature_label,
                    "source_index": int(feature.source_index),
                    "attributes_json": json.dumps(
                        feature.attributes, ensure_ascii=False, allow_nan=False
                    ),
                    "geometry_wkb_hex": feature.geometry_wkb_hex,
                    "target_srid": int(import_data.target_srid),
                } for feature in batch]
                connection.execute(insert_feature_sql, params)

        return {
            "coverage_layer_id": str(layer_id),
            "layer_name": name,
            "version": int(version),
            "feature_count": int(import_data.feature_count),
            "is_active": True,
        }
