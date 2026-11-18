from __future__ import annotations

"""Drop-in PostgreSQL GCP store with mandatory semantic context support.

The geometry, category and remark are inserted by one SQL statement. The
category must be active and cannot be the legacy-only category. The base
PostgresGCPStore is left untouched so the feature can be rolled out as an
isolated adapter in app1.py.
"""

from storage.gcp_store import PostgresGCPStore
from storage.gcp_context_store import GCPContextCategoryStore


class SemanticGCPStore(PostgresGCPStore):
    @classmethod
    def _row_to_record(cls, row: dict) -> dict:
        record = super()._row_to_record(row)
        record.update({
            "context_category_id": str(row["context_category_id"]) if row.get("context_category_id") is not None else None,
            "context_category_code": row.get("context_category_code"),
            "context_category_label": row.get("context_category_label"),
            "context_category_description": row.get("context_category_description"),
            "context_remark": row.get("context_remark"),
        })
        return record

    @staticmethod
    def _select_columns() -> str:
        return PostgresGCPStore._select_columns() + """
            , context_category_id,
              context_remark,
              (SELECT code FROM gcp_context_categories c
               WHERE c.context_category_id = gcps.context_category_id) AS context_category_code,
              (SELECT label FROM gcp_context_categories c
               WHERE c.context_category_id = gcps.context_category_id) AS context_category_label,
              (SELECT description FROM gcp_context_categories c
               WHERE c.context_category_id = gcps.context_category_id) AS context_category_description
        """

    @staticmethod
    def _select_joined_columns() -> str:
        return PostgresGCPStore._select_joined_columns() + """
            , g.context_category_id AS context_category_id,
              cc.code AS context_category_code,
              cc.label AS context_category_label,
              cc.description AS context_category_description,
              g.context_remark AS context_remark
        """

    def _list_joined(self, conditions=None, parameters=()) -> list[dict]:
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT {self._select_joined_columns()}
            FROM gcps g
            LEFT JOIN users u ON u.user_id = g.student_id
            LEFT JOIN layers rl ON rl.layer_id = g.reference_layer_id
            LEFT JOIN layers hl ON hl.layer_id = g.historical_layer_id
            LEFT JOIN gcp_context_categories cc
                ON cc.context_category_id = g.context_category_id
            {where_clause}
            ORDER BY g.historical_layer_id, g.gcp_id
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute(sql, parameters)
                return [self._row_to_record(row) for row in cur.fetchall()]

    def list_for_admin(
        self,
        student_id: int | None = None,
        historical_layer_id: int | None = None,
        context_category_id: int | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        parameters: list[int] = []
        for value, column, label in (
            (student_id, "g.student_id", "student_id"),
            (historical_layer_id, "g.historical_layer_id", "historical_layer_id"),
            (context_category_id, "g.context_category_id", "context_category_id"),
        ):
            if value is None:
                continue
            try:
                numeric = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label} must be a valid database identifier.") from exc
            if numeric <= 0:
                raise ValueError(f"{label} must be a positive database identifier.")
            conditions.append(f"{column} = %s")
            parameters.append(numeric)
        return self._list_joined(conditions, tuple(parameters))

    def create(
        self,
        record: dict,
        *,
        context_category_id: int,
        context_remark: str | None = None,
    ) -> dict:
        """Create the GCP and semantic annotation in one atomic SQL statement."""
        reference = record["reference"]
        historical = record["historical"]
        category_id = int(context_category_id)
        remark = GCPContextCategoryStore.validate_remark(context_remark)
        sql = """
            INSERT INTO gcps (
                student_id, reference_layer_id, historical_layer_id,
                reference_x, reference_y, reference_lon, reference_lat,
                historical_pixel, historical_line, historical_x, historical_y,
                historical_lon, historical_lat, crs, offset_m, gcp_status,
                recorded_at, context_category_id, context_remark
            )
            SELECT
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, c.context_category_id, %s
            FROM gcp_context_categories c
            WHERE c.context_category_id = %s
              AND c.is_active = TRUE
              AND c.code <> 'LEGACY_UNRECORDED'
            RETURNING gcp_id
        """
        params = (
            int(record["student_id"]),
            int(record["reference_layer_id"]),
            int(record["historical_layer_id"]),
            reference["x"], reference["y"], reference["lon"], reference["lat"],
            historical["pixel"], historical["line"], historical["x"], historical["y"],
            historical["lon"], historical["lat"], record["crs"], record["offset_m"],
            record.get("status", "confirmed"), record["recorded_at"], remark, category_id,
        )
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                if row is None:
                    raise ValueError("Choose an active GCP context category before saving the GCP.")
                db_gcp_id = row[0]
        return self.get(db_gcp_id)

    def update_context(self, gcp_id: str | int, category_id: int, remark: str | None = None) -> dict:
        """Administrator-facing context correction; only active categories are accepted."""
        db_id = self._db_id(gcp_id)
        category_id = int(category_id)
        clean_remark = GCPContextCategoryStore.validate_remark(remark)
        sql = """
            UPDATE gcps AS g
            SET context_category_id = c.context_category_id,
                context_remark = %s
            FROM gcp_context_categories AS c
            WHERE g.gcp_id = %s
              AND c.context_category_id = %s
              AND c.is_active = TRUE
              AND c.code <> 'LEGACY_UNRECORDED'
            RETURNING g.gcp_id
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (clean_remark, db_id, category_id))
                if cur.fetchone() is None:
                    raise ValueError("GCP or active context category was not found; no annotation was changed.")
        return self.get(db_id)
