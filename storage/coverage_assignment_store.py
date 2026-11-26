from __future__ import annotations

"""Persistence for administrator-to-student polygon work allocation."""

from typing import Any
from sqlalchemy import bindparam, text

_EMPTY_FC = {"type": "FeatureCollection", "features": []}


class CoverageAssignmentStore:
    """Assignments are tied to one exact coverage feature/version, not GCPs."""

    def __init__(self, pool) -> None:
        self.pool = pool
        self.engine = getattr(pool, "engine", None)
        if self.engine is None:
            raise TypeError("CoverageAssignmentStore requires the SQLAlchemy-backed database pool.")

    @staticmethod
    def _positive_id(value: Any, name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a valid database identifier.")
        try:
            text_value = str(value).strip()
            if not text_value or not text_value.isdecimal():
                raise ValueError
            result = int(text_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a valid database identifier.") from exc
        if result <= 0:
            raise ValueError(f"{name} must be a positive database identifier.")
        return result

    @classmethod
    def _student_ids(cls, values) -> list[int]:
        if values in (None, ""):
            return []
        if isinstance(values, (str, int)) and not isinstance(values, bool):
            values = [values]
        return sorted({cls._positive_id(value, "student_id") for value in values})

    def list_students_for_feature(self, feature_id: int, layer_id: int) -> list[int]:
        feature_id = self._positive_id(feature_id, "coverage_feature_id")
        layer_id = self._positive_id(layer_id, "coverage_layer_id")
        sql = text("""
            SELECT a.student_id
            FROM coverage_feature_assignments a
            JOIN coverage_features f ON f.coverage_feature_id = a.coverage_feature_id
            WHERE a.coverage_feature_id = :feature_id
              AND f.coverage_layer_id = :layer_id
            ORDER BY a.student_id
        """)
        with self.engine.connect() as connection:
            rows = connection.execute(sql, {"feature_id": feature_id, "layer_id": layer_id}).scalars().all()
        return [int(value) for value in rows]

    def get_feature_for_assignment(self, feature_id: int, layer_id: int) -> dict | None:
        """Return feature metadata only for an active, unsuppressed version."""
        feature_id = self._positive_id(feature_id, "coverage_feature_id")
        layer_id = self._positive_id(layer_id, "coverage_layer_id")
        sql = text("""
            SELECT f.coverage_feature_id, f.coverage_layer_id,
                   f.source_feature_key, f.feature_label, f.attributes,
                   l.layer_name, l.version,
                   COALESCE(t.objective, '') AS objective,
                   COALESCE(t.instructions, '') AS instructions
            FROM coverage_features f
            JOIN coverage_layers l ON l.coverage_layer_id = f.coverage_layer_id
            LEFT JOIN coverage_feature_tasks t
              ON t.coverage_feature_id = f.coverage_feature_id
            WHERE f.coverage_feature_id = :feature_id
              AND f.coverage_layer_id = :layer_id
              AND l.is_active = TRUE
              AND COALESCE(l.is_suppressed, FALSE) = FALSE
        """)
        with self.engine.connect() as connection:
            row = connection.execute(sql, {"feature_id": feature_id, "layer_id": layer_id}).mappings().first()
        if not row:
            return None
        item = dict(row)
        attrs = item.get("attributes")
        if isinstance(attrs, str):
            import json
            attrs = json.loads(attrs)
        item["attributes"] = attrs if isinstance(attrs, dict) else {}
        item["coverage_feature_id"] = int(item["coverage_feature_id"])
        item["coverage_layer_id"] = int(item["coverage_layer_id"])
        item["version"] = int(item["version"])
        item["assigned_student_ids"] = self.list_students_for_feature(feature_id, layer_id)
        return item

    @staticmethod
    def _task_text(value: Any, name: str, limit: int) -> str:
        normalized = str(value or "").strip()
        if "\x00" in normalized:
            raise ValueError(f"{name} cannot contain null characters.")
        if len(normalized) > limit:
            raise ValueError(f"{name} must not exceed {limit:,} characters.")
        return normalized

    def replace_feature_assignments(
        self, *, feature_id: int, layer_id: int, student_ids, assigned_by: int,
        objective: str | None = None, instructions: str | None = None,
    ) -> list[int]:
        """Atomically replace students and, when supplied, the polygon's shared task.

        Empty student selection removes all assignments. Empty objective and
        instructions remove the optional task row. Omitting both task arguments
        preserves task metadata for backward-compatible callers.
        """
        feature_id = self._positive_id(feature_id, "coverage_feature_id")
        layer_id = self._positive_id(layer_id, "coverage_layer_id")
        assigned_by = self._positive_id(assigned_by, "assigned_by")
        selected_ids = self._student_ids(student_ids)
        task_supplied = objective is not None or instructions is not None
        normalized_objective = self._task_text(objective, "Objective", 240) if objective is not None else None
        normalized_instructions = self._task_text(instructions, "Instructions", 10000) if instructions is not None else None

        with self.engine.begin() as connection:
            feature = connection.execute(text("""
                SELECT f.coverage_feature_id
                FROM coverage_features f
                JOIN coverage_layers l ON l.coverage_layer_id = f.coverage_layer_id
                WHERE f.coverage_feature_id = :feature_id
                  AND f.coverage_layer_id = :layer_id
                  AND l.is_active = TRUE
                  AND COALESCE(l.is_suppressed, FALSE) = FALSE
                FOR UPDATE OF f
            """), {"feature_id": feature_id, "layer_id": layer_id}).first()
            if feature is None:
                raise ValueError("The selected polygon is no longer available in the active coverage version.")

            if selected_ids:
                validate_students = text("""
                    SELECT u.user_id FROM users u
                    WHERE u.user_role = 'student'
                      AND u.user_id IN :student_ids
                      AND (
                          u.is_active = TRUE
                          OR EXISTS (
                              SELECT 1 FROM coverage_feature_assignments existing
                              WHERE existing.coverage_feature_id = :feature_id
                                AND existing.student_id = u.user_id
                          )
                      )
                    ORDER BY u.user_id
                """).bindparams(bindparam("student_ids", expanding=True))
                valid_ids = [int(row[0]) for row in connection.execute(
                    validate_students, {"student_ids": selected_ids, "feature_id": feature_id}
                ).all()]
                if valid_ids != selected_ids:
                    raise ValueError("One or more selected accounts are not student accounts.")

                delete_sql = text("""
                    DELETE FROM coverage_feature_assignments
                    WHERE coverage_feature_id = :feature_id
                      AND student_id NOT IN :student_ids
                """).bindparams(bindparam("student_ids", expanding=True))
                connection.execute(delete_sql, {"feature_id": feature_id, "student_ids": selected_ids})
                insert_sql = text("""
                    INSERT INTO coverage_feature_assignments
                        (coverage_feature_id, student_id, assigned_by, assigned_at)
                    VALUES (:feature_id, :student_id, :assigned_by, CURRENT_TIMESTAMP)
                    ON CONFLICT (coverage_feature_id, student_id)
                    DO UPDATE SET assigned_by = EXCLUDED.assigned_by,
                                  assigned_at = CURRENT_TIMESTAMP
                """)
                connection.execute(insert_sql, [
                    {"feature_id": feature_id, "student_id": student_id, "assigned_by": assigned_by}
                    for student_id in selected_ids
                ])
            else:
                connection.execute(text("""
                    DELETE FROM coverage_feature_assignments
                    WHERE coverage_feature_id = :feature_id
                """), {"feature_id": feature_id})

            if task_supplied:
                # If one field was omitted, preserve its current value rather
                # than silently clearing it. Admin callback supplies both.
                current_task = connection.execute(text("""
                    SELECT objective, instructions
                    FROM coverage_feature_tasks
                    WHERE coverage_feature_id = :feature_id
                    FOR UPDATE
                """), {"feature_id": feature_id}).mappings().first()
                objective_value = (
                    normalized_objective if normalized_objective is not None
                    else str((current_task or {}).get("objective") or "")
                )
                instructions_value = (
                    normalized_instructions if normalized_instructions is not None
                    else str((current_task or {}).get("instructions") or "")
                )
                if objective_value or instructions_value:
                    connection.execute(text("""
                        INSERT INTO coverage_feature_tasks
                            (coverage_feature_id, objective, instructions, updated_by, updated_at)
                        VALUES (:feature_id, :objective, :instructions, :updated_by, CURRENT_TIMESTAMP)
                        ON CONFLICT (coverage_feature_id)
                        DO UPDATE SET objective = EXCLUDED.objective,
                                      instructions = EXCLUDED.instructions,
                                      updated_by = EXCLUDED.updated_by,
                                      updated_at = CURRENT_TIMESTAMP
                    """), {
                        "feature_id": feature_id,
                        "objective": objective_value,
                        "instructions": instructions_value,
                        "updated_by": assigned_by,
                    })
                else:
                    connection.execute(text("""
                        DELETE FROM coverage_feature_tasks
                        WHERE coverage_feature_id = :feature_id
                    """), {"feature_id": feature_id})
        return selected_ids

    def list_student_layers(self, student_id: int) -> list[dict]:
        """List active coverage versions to which this active student is assigned."""
        student_id = self._positive_id(student_id, "student_id")
        sql = text("""
            SELECT l.coverage_layer_id, l.layer_name, l.version,
                   COUNT(DISTINCT a.coverage_feature_id)::BIGINT AS assigned_feature_count
            FROM coverage_feature_assignments a
            JOIN coverage_features f ON f.coverage_feature_id = a.coverage_feature_id
            JOIN coverage_layers l ON l.coverage_layer_id = f.coverage_layer_id
            JOIN users u ON u.user_id = a.student_id
            WHERE a.student_id = :student_id
              AND u.user_role = 'student' AND u.is_active = TRUE
              AND l.is_active = TRUE AND COALESCE(l.is_suppressed, FALSE) = FALSE
            GROUP BY l.coverage_layer_id, l.layer_name, l.version
            HAVING COUNT(DISTINCT a.coverage_feature_id) > 0
            ORDER BY LOWER(l.layer_name), l.version DESC
        """)
        with self.engine.connect() as connection:
            rows = connection.execute(sql, {"student_id": student_id}).mappings().all()
        return [{
            "coverage_layer_id": str(row["coverage_layer_id"]),
            "layer_name": str(row["layer_name"]),
            "version": int(row["version"]),
            "assigned_feature_count": int(row["assigned_feature_count"]),
        } for row in rows]

    def query_student_geojson(self, *, student_id: int, layer_id: int, bounds: dict[str, float], zoom: float = 10, max_features: int = 2500) -> dict:
        """Return the student's assigned polygons visible in one map viewport."""
        student_id = self._positive_id(student_id, "student_id")
        layer_id = self._positive_id(layer_id, "coverage_layer_id")
        values = {key: float(bounds[key]) for key in ("west", "south", "east", "north")}
        if not (-180 <= values["west"] < values["east"] <= 180 and -90 <= values["south"] < values["north"] <= 90):
            raise ValueError("The map viewport bounds are invalid.")
        zoom_value = max(0.0, float(zoom))
        tolerance = 0.0 if zoom_value >= 16 else (0.25 if zoom_value >= 14 else (0.75 if zoom_value >= 11 else 2.0))
        params = {"student_id": student_id, "layer_id": layer_id, **values,
                  "tolerance": tolerance, "limit_plus_one": int(max_features) + 1}
        sql = text("""
            WITH viewport AS (
                SELECT ST_Transform(ST_MakeEnvelope(:west, :south, :east, :north, 4326), 25832) AS geom
            ), visible AS (
                SELECT f.coverage_feature_id, f.source_feature_key, f.feature_label,
                       f.attributes, f.geom,
                       COALESCE(t.objective, '') AS objective,
                       COALESCE(t.instructions, '') AS instructions
                FROM coverage_feature_assignments a
                JOIN coverage_features f ON f.coverage_feature_id = a.coverage_feature_id
                JOIN coverage_layers l ON l.coverage_layer_id = f.coverage_layer_id
                LEFT JOIN coverage_feature_tasks t
                  ON t.coverage_feature_id = f.coverage_feature_id
                JOIN users u ON u.user_id = a.student_id
                CROSS JOIN viewport v
                WHERE a.student_id = :student_id
                  AND f.coverage_layer_id = :layer_id
                  AND u.user_role = 'student' AND u.is_active = TRUE
                  AND l.is_active = TRUE AND COALESCE(l.is_suppressed, FALSE) = FALSE
                  AND f.geom && v.geom AND ST_Intersects(f.geom, v.geom)
                ORDER BY f.coverage_feature_id
                LIMIT :limit_plus_one
            )
            SELECT coverage_feature_id, source_feature_key, feature_label, attributes,
                   objective, instructions,
                   ST_AsGeoJSON(ST_Transform(
                       CASE WHEN :tolerance > 0 THEN ST_SimplifyPreserveTopology(geom, :tolerance) ELSE geom END,
                       4326
                   ), 5)::json AS geometry
            FROM visible ORDER BY coverage_feature_id
        """)
        with self.engine.connect() as connection:
            rows = connection.execute(sql, params).mappings().all()
        if len(rows) > max_features:
            return {"geojson": _EMPTY_FC, "too_many_features": True, "feature_count_in_view": len(rows)}

        import json
        features = []
        for row in rows:
            geometry = row["geometry"]
            if isinstance(geometry, str):
                geometry = json.loads(geometry)
            attrs = row["attributes"]
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            features.append({
                "type": "Feature", "id": int(row["coverage_feature_id"]),
                "geometry": geometry,
                "properties": {
                    "coverage_feature_id": int(row["coverage_feature_id"]),
                    "source_feature_key": row["source_feature_key"],
                    "feature_label": row["feature_label"],
                    "attributes": attrs if isinstance(attrs, dict) else {},
                    "objective": str(row.get("objective") or ""),
                    "instructions": str(row.get("instructions") or ""),
                },
            })
        return {"geojson": {"type": "FeatureCollection", "features": features},
                "too_many_features": False, "feature_count_in_view": len(features)}
