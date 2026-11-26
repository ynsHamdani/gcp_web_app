from __future__ import annotations

"""PostgreSQL/PostGIS persistence for versioned coverage layers and analysis."""

import json
import re
import uuid
from typing import Any

from sqlalchemy import text

_LAYER_NAME_RE = re.compile(r"^[^\x00]{2,160}$")

_MATCH_CTE = """
WITH gcp_matches AS (
    SELECT
        g.gcp_id,
        g.context_category_id,
        COUNT(m.coverage_feature_id)::integer AS match_count,
        MIN(m.coverage_feature_id) AS matched_feature_id
    FROM gcps AS g
    CROSS JOIN LATERAL (
        SELECT ST_SetSRID(ST_MakePoint(g.reference_x, g.reference_y), 25832) AS point_geom
    ) AS p
    LEFT JOIN LATERAL (
        SELECT f.coverage_feature_id
        FROM coverage_features AS f
        WHERE f.coverage_layer_id = :layer_id
          AND f.geom && p.point_geom
          AND ST_Covers(f.geom, p.point_geom)
    ) AS m ON TRUE
    GROUP BY g.gcp_id, g.context_category_id
)
"""


class CoverageStore:
    """Coverage registry, transactional publication, assignments and map queries.

    Existing GCP records are read-only from this store. Spatial assignment is
    computed on demand; no GCP columns or persistent GCP-to-feature relation is
    introduced.
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

    @staticmethod
    def _positive_id(value) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Select a valid coverage-layer version.") from exc
        if result <= 0:
            raise ValueError("Select a valid coverage-layer version.")
        return result

    @staticmethod
    def _layer_summary(row: dict) -> dict[str, Any]:
        item = dict(row)
        imported_at = item.get("imported_at")
        item["imported_at"] = imported_at.isoformat(timespec="minutes") if imported_at else ""
        for key in ("coverage_layer_id", "version", "target_srid", "feature_count", "stored_feature_count"):
            if item.get(key) is not None:
                item[key] = int(item[key])
        item["coverage_layer_id"] = str(item["coverage_layer_id"])
        item["is_active"] = bool(item.get("is_active"))
        item["is_suppressed"] = bool(item.get("is_suppressed"))
        return item

    def list_layers(self) -> list[dict[str, Any]]:
        sql = """
            SELECT l.coverage_layer_id, l.layer_name, l.version,
                   l.source_filename, l.source_format, l.source_layer_name,
                   l.source_crs, l.target_srid, l.geometry_type,
                   l.feature_count, l.source_sha256, l.notes,
                   l.is_active, l.is_suppressed, l.imported_at,
                   u.username AS imported_by_username,
                   COUNT(f.coverage_feature_id) AS stored_feature_count
            FROM coverage_layers AS l
            LEFT JOIN coverage_features AS f
                ON f.coverage_layer_id = l.coverage_layer_id
            LEFT JOIN users AS u ON u.user_id = l.imported_by
            GROUP BY l.coverage_layer_id, u.username
            ORDER BY LOWER(l.layer_name), l.version DESC
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql)
                return [self._layer_summary(row) for row in cur.fetchall()]

    def get_layer(self, layer_id: str | int) -> dict[str, Any] | None:
        db_id = self._positive_id(layer_id)
        sql = """
            SELECT l.coverage_layer_id, l.layer_name, l.version,
                   l.source_filename, l.source_format, l.source_layer_name,
                   l.source_crs, l.target_srid, l.geometry_type,
                   l.feature_count, l.source_sha256, l.notes,
                   l.is_active, l.is_suppressed, l.imported_at,
                   u.username AS imported_by_username,
                   (SELECT COUNT(*) FROM coverage_features f
                    WHERE f.coverage_layer_id = l.coverage_layer_id) AS stored_feature_count
            FROM coverage_layers l
            LEFT JOIN users u ON u.user_id = l.imported_by
            WHERE l.coverage_layer_id = %s
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, (db_id,))
                row = cur.fetchone()
        return self._layer_summary(row) if row else None

    def list_selectable_layers(self) -> list[dict[str, Any]]:
        return [item for item in self.list_layers() if item["is_active"] and not item["is_suppressed"]]

    @staticmethod
    def _publication_result(row) -> dict[str, Any]:
        if row is None:
            return None
        item = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        return {
            "coverage_layer_id": str(item["coverage_layer_id"]),
            "layer_name": item["layer_name"],
            "version": int(item["version"]),
            "feature_count": int(item["feature_count"]),
            "is_active": bool(item["is_active"]),
            "already_published": True,
        }

    def get_publication(self, publish_token: str) -> dict[str, Any] | None:
        token = str(uuid.UUID(str(publish_token)))
        sql = text("""
            SELECT coverage_layer_id, layer_name, version, feature_count, is_active
            FROM coverage_layers WHERE publish_token = CAST(:token AS uuid)
        """)
        with self.engine.connect() as connection:
            row = connection.execute(sql, {"token": token}).mappings().first()
        return self._publication_result(row) if row else None

    def publish_import(
        self,
        *,
        layer_name: str,
        notes: str,
        import_data,
        imported_by: int,
        publish_token: str,
    ) -> dict[str, Any]:
        """Publish a staged/validated import atomically and idempotently.

        A unique token is locked and checked before any insertion. Retrying a
        completed request returns its existing registry result. Feature batches
        are streamed from a staging file when the object provides
        ``iter_feature_batches``; normal in-memory imports remain supported.
        """
        name, normalized_notes = self.validate_layer_metadata(layer_name, notes)
        token = str(uuid.UUID(str(publish_token)))
        feature_count = int(import_data.feature_count)
        if feature_count <= 0:
            raise ValueError("The validated import does not contain any polygon features.")
        if int(import_data.target_srid) != 25832:
            raise ValueError("The prepared import does not use the configured EPSG:25832 storage CRS.")

        insert_layer_sql = text("""
            INSERT INTO coverage_layers (
                layer_name, version, source_filename, source_format,
                source_layer_name, source_crs, target_srid, geometry_type,
                feature_count, source_sha256, notes, imported_by,
                is_active, is_suppressed, publish_token
            ) VALUES (
                :layer_name, :version, :source_filename, :source_format,
                :source_layer_name, :source_crs, :target_srid, :geometry_type,
                :feature_count, :source_sha256, :notes, :imported_by,
                TRUE, FALSE, CAST(:publish_token AS uuid)
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
                ST_Multi(ST_SetSRID(ST_GeomFromWKB(decode(:geometry_wkb_hex, 'hex')), :target_srid))
            )
        """)

        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": "coverage-publish:" + token},
            )
            existing = connection.execute(text("""
                SELECT coverage_layer_id, layer_name, version, feature_count, is_active
                FROM coverage_layers WHERE publish_token = CAST(:token AS uuid)
            """), {"token": token}).mappings().first()
            if existing is not None:
                result = self._publication_result(existing)
                result["already_published"] = True
                return result

            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": "coverage-layer-name:" + name.casefold()},
            )
            duplicate = connection.execute(text("""
                SELECT version FROM coverage_layers
                WHERE LOWER(layer_name) = LOWER(:layer_name)
                  AND source_sha256 = :source_sha256
                ORDER BY version DESC LIMIT 1
            """), {"layer_name": name, "source_sha256": import_data.source_sha256}).scalar_one_or_none()
            if duplicate is not None:
                raise ValueError(
                    f"This exact file is already registered for '{name}' as version {int(duplicate)}. "
                    "Upload a revised file or choose another layer name."
                )

            version = int(connection.execute(text("""
                SELECT COALESCE(MAX(version), 0) + 1
                FROM coverage_layers WHERE LOWER(layer_name) = LOWER(:layer_name)
            """), {"layer_name": name}).scalar_one())
            connection.execute(text("""
                UPDATE coverage_layers SET is_active = FALSE
                WHERE LOWER(layer_name) = LOWER(:layer_name) AND is_active = TRUE
            """), {"layer_name": name})

            layer_id = connection.execute(insert_layer_sql, {
                "layer_name": name,
                "version": version,
                "source_filename": import_data.filename,
                "source_format": import_data.source_format,
                "source_layer_name": import_data.source_layer_name,
                "source_crs": import_data.source_crs,
                "target_srid": int(import_data.target_srid),
                "geometry_type": import_data.geometry_type,
                "feature_count": feature_count,
                "source_sha256": import_data.source_sha256,
                "notes": normalized_notes,
                "imported_by": int(imported_by),
                "publish_token": token,
            }).scalar_one()

            if hasattr(import_data, "iter_feature_batches"):
                batches = import_data.iter_feature_batches(batch_size=500)
            else:
                features = tuple(import_data.features)
                if len(features) != feature_count:
                    raise ValueError("The import feature count does not match its prepared feature records.")
                batches = (features[start:start + 500] for start in range(0, len(features), 500))

            inserted = 0
            for batch in batches:
                params = [{
                    "coverage_layer_id": int(layer_id),
                    "source_feature_key": feature.source_feature_key,
                    "feature_label": feature.feature_label,
                    "source_index": int(feature.source_index),
                    "attributes_json": json.dumps(feature.attributes, ensure_ascii=False, allow_nan=False),
                    "geometry_wkb_hex": feature.geometry_wkb_hex,
                    "target_srid": int(import_data.target_srid),
                } for feature in batch]
                if params:
                    connection.execute(insert_feature_sql, params)
                    inserted += len(params)
            if inserted != feature_count:
                raise ValueError(f"Prepared import contains {inserted:,} features; expected {feature_count:,}.")
            connection.execute(text("""
                UPDATE coverage_layers
                SET extent = (
                    SELECT ST_SetSRID(ST_Envelope(ST_Extent(geom)), 25832)
                    FROM coverage_features
                    WHERE coverage_layer_id = :coverage_layer_id
                )
                WHERE coverage_layer_id = :coverage_layer_id
            """), {"coverage_layer_id": int(layer_id)})

        return {
            "coverage_layer_id": str(layer_id),
            "layer_name": name,
            "version": version,
            "feature_count": feature_count,
            "is_active": True,
            "already_published": False,
        }

    def suppress_layer(self, layer_id: str | int) -> dict:
        db_id = self._positive_id(layer_id)
        with self.engine.begin() as connection:
            name = connection.execute(text("""
                SELECT layer_name FROM coverage_layers WHERE coverage_layer_id = :layer_id
            """), {"layer_id": db_id}).scalar_one_or_none()
            if name is None:
                raise KeyError(f"Coverage version {db_id} was not found.")
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": "coverage-layer-name:" + str(name).casefold()},
            )
            row = connection.execute(text("""
                UPDATE coverage_layers
                SET is_active = FALSE, is_suppressed = TRUE
                WHERE coverage_layer_id = :layer_id
                RETURNING coverage_layer_id, layer_name, version
            """), {"layer_id": db_id}).mappings().first()
            if row is None:
                raise KeyError(f"Coverage version {db_id} was not found.")
        return dict(row)

    def activate_layer(self, layer_id: str | int) -> dict:
        db_id = self._positive_id(layer_id)
        with self.engine.begin() as connection:
            name = connection.execute(text("""
                SELECT layer_name FROM coverage_layers WHERE coverage_layer_id = :layer_id
            """), {"layer_id": db_id}).scalar_one_or_none()
            if name is None:
                raise KeyError(f"Coverage version {db_id} was not found.")
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": "coverage-layer-name:" + str(name).casefold()},
            )
            target = connection.execute(text("""
                SELECT coverage_layer_id, layer_name, version
                FROM coverage_layers WHERE coverage_layer_id = :layer_id
                FOR UPDATE
            """), {"layer_id": db_id}).mappings().first()
            if target is None:
                raise KeyError(f"Coverage version {db_id} was not found.")
            connection.execute(text("""
                UPDATE coverage_layers SET is_active = FALSE
                WHERE LOWER(layer_name) = LOWER(:layer_name)
            """), {"layer_name": target["layer_name"]})
            connection.execute(text("""
                UPDATE coverage_layers SET is_active = TRUE, is_suppressed = FALSE
                WHERE coverage_layer_id = :layer_id
            """), {"layer_id": db_id})
        return dict(target)

    def delete_layer(self, layer_id: str | int) -> dict:
        db_id = self._positive_id(layer_id)
        with self.engine.begin() as connection:
            name = connection.execute(text("""
                SELECT layer_name FROM coverage_layers WHERE coverage_layer_id = :layer_id
            """), {"layer_id": db_id}).scalar_one_or_none()
            if name is None:
                raise KeyError(f"Coverage version {db_id} was not found.")
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": "coverage-layer-name:" + str(name).casefold()},
            )
            row = connection.execute(text("""
                DELETE FROM coverage_layers
                WHERE coverage_layer_id = :layer_id
                RETURNING coverage_layer_id, layer_name, version, feature_count
            """), {"layer_id": db_id}).mappings().first()
            if row is None:
                raise KeyError(f"Coverage version {db_id} was not found.")
        return dict(row)

    def get_layer_bounds(self, layer_id: str | int):
        from pyproj import Transformer

        db_id = self._positive_id(layer_id)
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute("""
                    SELECT ST_XMin(Box3D(extent)) AS xmin,
                           ST_YMin(Box3D(extent)) AS ymin,
                           ST_XMax(Box3D(extent)) AS xmax,
                           ST_YMax(Box3D(extent)) AS ymax
                    FROM coverage_layers WHERE coverage_layer_id = %s
                """, (db_id,))
                row = cur.fetchone()
        if not row or row.get("xmin") is None:
            return None
        west, south, east, north = Transformer.from_crs(25832, 4326, always_xy=True).transform_bounds(
            float(row["xmin"]), float(row["ymin"]), float(row["xmax"]), float(row["ymax"]), densify_pts=21
        )
        return [[south, west], [north, east]]

    @staticmethod
    def _layer_parameter(layer_id) -> dict:
        return {"layer_id": CoverageStore._positive_id(layer_id)}

    def assignment_summary(self, layer_id: str | int) -> dict[str, int]:
        sql = text(_MATCH_CTE + """
            SELECT COUNT(*)::bigint AS total_gcps,
                   COUNT(*) FILTER (WHERE match_count = 1)::bigint AS assigned_unique,
                   COUNT(*) FILTER (WHERE match_count = 0)::bigint AS uncovered,
                   COUNT(*) FILTER (WHERE match_count > 1)::bigint AS multiple_matches
            FROM gcp_matches
        """)
        with self.engine.connect() as connection:
            row = connection.execute(sql, self._layer_parameter(layer_id)).mappings().one()
        return {key: int(row[key]) for key in ("total_gcps", "assigned_unique", "uncovered", "multiple_matches")}

    def feature_statistics(self, layer_id: str | int, *, page: int = 0, page_size: int = 50) -> tuple[list[dict], int]:
        page_size = max(1, min(250, int(page_size)))
        page = max(0, int(page))
        offset = page * page_size
        sql = text(_MATCH_CTE + """
            , assigned_context AS (
                SELECT matched_feature_id AS feature_id,
                       COALESCE(cc.label, 'Unspecified') AS context_label,
                       COUNT(*)::integer AS gcp_count
                FROM gcp_matches gm
                LEFT JOIN gcp_context_categories cc
                    ON cc.context_category_id = gm.context_category_id
                WHERE gm.match_count = 1
                GROUP BY matched_feature_id, COALESCE(cc.label, 'Unspecified')
            ), feature_counts AS (
                SELECT feature_id,
                       SUM(gcp_count)::integer AS assigned_count,
                       jsonb_object_agg(context_label, gcp_count) AS context_breakdown
                FROM assigned_context GROUP BY feature_id
            ), responsible AS (
                SELECT a.coverage_feature_id AS feature_id,
                       jsonb_agg(
                           jsonb_build_object(
                               'student_id', u.user_id,
                               'username', u.username,
                               'is_active', u.is_active
                           ) ORDER BY LOWER(u.username), u.user_id
                       ) AS responsible_students
                FROM coverage_feature_assignments a
                JOIN coverage_features assigned_feature
                  ON assigned_feature.coverage_feature_id = a.coverage_feature_id
                JOIN users u ON u.user_id = a.student_id
                WHERE u.user_role = 'student'
                  AND assigned_feature.coverage_layer_id = :layer_id
                GROUP BY a.coverage_feature_id
            )
            SELECT f.coverage_feature_id, f.source_feature_key, f.feature_label,
                   f.attributes,
                   COALESCE(fc.assigned_count, 0)::integer AS assigned_count,
                   COALESCE(fc.context_breakdown, '{}'::jsonb) AS context_breakdown,
                   COALESCE(r.responsible_students, '[]'::jsonb) AS responsible_students
            FROM coverage_features f
            LEFT JOIN feature_counts fc ON fc.feature_id = f.coverage_feature_id
            LEFT JOIN responsible r ON r.feature_id = f.coverage_feature_id
            WHERE f.coverage_layer_id = :layer_id
            ORDER BY COALESCE(fc.assigned_count, 0) DESC, f.coverage_feature_id ASC
            LIMIT :page_size OFFSET :offset
        """)
        count_sql = text("SELECT COUNT(*) FROM coverage_features WHERE coverage_layer_id = :layer_id")
        params = {**self._layer_parameter(layer_id), "page_size": page_size, "offset": offset}
        with self.engine.connect() as connection:
            rows = connection.execute(sql, params).mappings().all()
            total = int(connection.execute(count_sql, self._layer_parameter(layer_id)).scalar_one())
        result = []
        for row in rows:
            item = dict(row)
            item["coverage_feature_id"] = int(item["coverage_feature_id"])
            item["assigned_count"] = int(item["assigned_count"])
            breakdown = item.get("context_breakdown") or {}
            if isinstance(breakdown, str):
                breakdown = json.loads(breakdown)
            item["context_breakdown"] = breakdown
            responsible = item.get("responsible_students") or []
            if isinstance(responsible, str):
                responsible = json.loads(responsible)
            item["responsible_students"] = responsible if isinstance(responsible, list) else []
            result.append(item)
        return result, total

    def export_feature_statistics(self, layer_id: str | int) -> list[dict]:
        # Reuse the same SQL assignment semantics as the on-screen table.
        sql = text(_MATCH_CTE + """
            , assigned_context AS (
                SELECT matched_feature_id AS feature_id,
                       COALESCE(cc.label, 'Unspecified') AS context_label,
                       COUNT(*)::integer AS gcp_count
                FROM gcp_matches gm
                LEFT JOIN gcp_context_categories cc ON cc.context_category_id = gm.context_category_id
                WHERE gm.match_count = 1
                GROUP BY matched_feature_id, COALESCE(cc.label, 'Unspecified')
            ), feature_counts AS (
                SELECT feature_id, SUM(gcp_count)::integer AS assigned_count,
                       jsonb_object_agg(context_label, gcp_count) AS context_breakdown
                FROM assigned_context GROUP BY feature_id
            ), responsible AS (
                SELECT a.coverage_feature_id AS feature_id,
                       jsonb_agg(
                           jsonb_build_object(
                               'student_id', u.user_id,
                               'username', u.username,
                               'is_active', u.is_active
                           ) ORDER BY LOWER(u.username), u.user_id
                       ) AS responsible_students
                FROM coverage_feature_assignments a
                JOIN coverage_features assigned_feature
                  ON assigned_feature.coverage_feature_id = a.coverage_feature_id
                JOIN users u ON u.user_id = a.student_id
                WHERE u.user_role = 'student'
                  AND assigned_feature.coverage_layer_id = :layer_id
                GROUP BY a.coverage_feature_id
            )
            SELECT f.coverage_feature_id, f.source_feature_key, f.feature_label, f.attributes,
                   COALESCE(fc.assigned_count, 0)::integer AS assigned_count,
                   COALESCE(fc.context_breakdown, '{}'::jsonb) AS context_breakdown,
                   COALESCE(r.responsible_students, '[]'::jsonb) AS responsible_students
            FROM coverage_features f
            LEFT JOIN feature_counts fc ON fc.feature_id = f.coverage_feature_id
            LEFT JOIN responsible r ON r.feature_id = f.coverage_feature_id
            WHERE f.coverage_layer_id = :layer_id
            ORDER BY COALESCE(fc.assigned_count, 0) DESC, f.coverage_feature_id ASC
        """)
        with self.engine.connect() as connection:
            rows = connection.execute(sql, self._layer_parameter(layer_id)).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            for key in ("context_breakdown", "responsible_students"):
                value = item.get(key)
                if isinstance(value, str):
                    value = json.loads(value)
                item[key] = value if isinstance(value, (dict, list)) else ({} if key == "context_breakdown" else [])
            result.append(item)
        return result

    def export_gcp_assignments(self, layer_id: str | int) -> list[dict]:
        sql = text(_MATCH_CTE + """
            SELECT gm.gcp_id,
                   CASE WHEN gm.match_count = 1 THEN 'ASSIGNED_UNIQUE' ELSE 'NOT_UNIQUE' END AS assignment_status,
                   CASE WHEN gm.match_count = 0 THEN 'UNCOVERED'
                        WHEN gm.match_count > 1 THEN 'MULTIPLE_MATCHES'
                        ELSE '' END AS assignment_reason,
                   gm.match_count,
                   CASE WHEN gm.match_count = 1 THEN gm.matched_feature_id END AS coverage_feature_id,
                   cc.code AS context_category_code,
                   cc.label AS context_category_label
            FROM gcp_matches gm
            LEFT JOIN gcp_context_categories cc ON cc.context_category_id = gm.context_category_id
            ORDER BY gm.gcp_id
        """)
        with self.engine.connect() as connection:
            rows = connection.execute(sql, self._layer_parameter(layer_id)).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            item["gcp_id"] = f"GCP-{int(item['gcp_id']):04d}"
            result.append(item)
        return result

    def query_map_geojson(
        self,
        layer_id: str | int,
        bounds: dict[str, float],
        *,
        zoom: float = 10,
        max_features: int = 3000,
        max_points: int = 3000,
    ) -> dict:
        """Load viewport polygons and GCP points; never ship the full layer."""
        layer_id = self._positive_id(layer_id)
        required = ("west", "south", "east", "north")
        values = {key: float(bounds[key]) for key in required}
        if not (-180 <= values["west"] < values["east"] <= 180 and -90 <= values["south"] < values["north"] <= 90):
            raise ValueError("The map viewport bounds are invalid.")
        # Keep display simplification below a scale that could collapse small
        # grid cells. Full-resolution geometries remain untouched for analysis.
        tolerance = max(0.5, 100.0 / (2 ** max(0.0, float(zoom) - 8.0)))
        params = {
            "layer_id": layer_id, **values,
            "tolerance": tolerance,
            "limit_plus_one": int(max_features) + 1,
            "point_limit_plus_one": int(max_points) + 1,
        }
        polygon_sql = text(_MATCH_CTE + """
            , assigned_by_context AS (
                SELECT gm.matched_feature_id AS feature_id,
                       COALESCE(cc.label, 'Unspecified') AS context_label,
                       COUNT(*)::integer AS gcp_count
                FROM gcp_matches gm
                LEFT JOIN gcp_context_categories cc
                    ON cc.context_category_id = gm.context_category_id
                WHERE gm.match_count = 1
                GROUP BY gm.matched_feature_id, COALESCE(cc.label, 'Unspecified')
            ), assigned_counts AS (
                SELECT feature_id, SUM(gcp_count)::integer AS assigned_count,
                       jsonb_object_agg(context_label, gcp_count) AS context_breakdown
                FROM assigned_by_context GROUP BY feature_id
            ), viewport AS (
                SELECT ST_Transform(ST_MakeEnvelope(:west, :south, :east, :north, 4326), 25832) AS geom
            )
            SELECT f.coverage_feature_id, f.source_feature_key, f.feature_label,
                   f.attributes,
                   COALESCE(ac.assigned_count, 0)::integer AS assigned_count,
                   COALESCE(ac.context_breakdown, '{}'::jsonb) AS context_breakdown,
                   ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(f.geom, :tolerance), 4326), 5)::json AS geometry
            FROM coverage_features f
            CROSS JOIN viewport v
            LEFT JOIN assigned_counts ac ON ac.feature_id = f.coverage_feature_id
            WHERE f.coverage_layer_id = :layer_id
              AND f.geom && v.geom AND ST_Intersects(f.geom, v.geom)
            ORDER BY f.coverage_feature_id
            LIMIT :limit_plus_one
        """)
        point_sql = text("""
            WITH viewport AS (
                SELECT ST_Transform(ST_MakeEnvelope(:west, :south, :east, :north, 4326), 25832) AS geom
            ), visible_gcps AS (
                SELECT g.gcp_id, g.context_category_id, g.gcp_status,
                       ST_SetSRID(ST_MakePoint(g.reference_x, g.reference_y), 25832) AS point_geom
                FROM gcps g CROSS JOIN viewport v
                WHERE ST_SetSRID(ST_MakePoint(g.reference_x, g.reference_y), 25832) && v.geom
            ), gcp_matches AS (
                SELECT vg.gcp_id, vg.context_category_id, vg.gcp_status, vg.point_geom,
                       COUNT(m.coverage_feature_id)::integer AS match_count,
                       MIN(m.coverage_feature_id) AS matched_feature_id
                FROM visible_gcps vg
                LEFT JOIN LATERAL (
                    SELECT f.coverage_feature_id
                    FROM coverage_features f
                    WHERE f.coverage_layer_id = :layer_id
                      AND f.geom && vg.point_geom
                      AND ST_Covers(f.geom, vg.point_geom)
                ) m ON TRUE
                GROUP BY vg.gcp_id, vg.context_category_id, vg.gcp_status, vg.point_geom
            )
            SELECT gm.gcp_id, gm.match_count,
                   CASE WHEN gm.match_count = 1 THEN 'ASSIGNED_UNIQUE' ELSE 'NOT_UNIQUE' END AS assignment_status,
                   CASE WHEN gm.match_count = 0 THEN 'UNCOVERED'
                        WHEN gm.match_count > 1 THEN 'MULTIPLE_MATCHES' ELSE '' END AS assignment_reason,
                   CASE WHEN gm.match_count = 1 THEN gm.matched_feature_id END AS coverage_feature_id,
                   COALESCE(cc.label, 'Unspecified') AS context_category,
                   gm.gcp_status,
                   ST_AsGeoJSON(ST_Transform(gm.point_geom, 4326), 6)::json AS geometry
            FROM gcp_matches gm
            LEFT JOIN gcp_context_categories cc ON cc.context_category_id = gm.context_category_id
            ORDER BY gm.gcp_id
            LIMIT :point_limit_plus_one
        """)
        with self.engine.connect() as connection:
            polygon_rows = connection.execute(polygon_sql, params).mappings().all()
            if len(polygon_rows) > max_features:
                return {
                    "polygons": {"type": "FeatureCollection", "features": []},
                    "points": {"type": "FeatureCollection", "features": []},
                    "too_many_features": True,
                    "feature_count_in_view": len(polygon_rows),
                }
            point_rows = connection.execute(point_sql, params).mappings().all()

        polygon_features = []
        for row in polygon_rows:
            polygon_features.append({
                "type": "Feature",
                "id": int(row["coverage_feature_id"]),
                "geometry": row["geometry"] if isinstance(row["geometry"], dict) else json.loads(row["geometry"]),
                "properties": {
                    "coverage_feature_id": int(row["coverage_feature_id"]),
                    "source_feature_key": row["source_feature_key"],
                    "feature_label": row["feature_label"],
                    "attributes": row["attributes"] if isinstance(row["attributes"], dict) else (json.loads(row["attributes"]) if isinstance(row["attributes"], str) else {}),
                    "assigned_count": int(row["assigned_count"]),
                    "context_breakdown": row["context_breakdown"] if isinstance(row["context_breakdown"], dict) else (json.loads(row["context_breakdown"]) if isinstance(row["context_breakdown"], str) else {}),
                },
            })
        point_features = []
        points_limited = len(point_rows) > max_points
        for row in point_rows[:max_points]:
            point_features.append({
                "type": "Feature",
                "id": f"GCP-{int(row['gcp_id']):04d}",
                "geometry": row["geometry"] if isinstance(row["geometry"], dict) else json.loads(row["geometry"]),
                "properties": {
                    "gcp_id": f"GCP-{int(row['gcp_id']):04d}",
                    "match_count": int(row["match_count"]),
                    "assignment_status": row["assignment_status"],
                    "assignment_reason": row["assignment_reason"],
                    "coverage_feature_id": row["coverage_feature_id"],
                    "context_category": row["context_category"],
                    "gcp_status": row["gcp_status"],
                },
            })
        return {
            "polygons": {"type": "FeatureCollection", "features": polygon_features},
            "points": {"type": "FeatureCollection", "features": point_features},
            "too_many_features": False,
            "feature_count_in_view": len(polygon_features),
            "points_limited": points_limited,
        }
