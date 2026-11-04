from __future__ import annotations

"""Persistent administrator-controlled runtime settings."""

import json
from typing import Any


DEFAULT_SETTINGS = {
    "raster_ttl_hours": 24,
    "max_upload_size_mb": 256,
}


class PostgresSettingsStore:
    def __init__(self, pool) -> None:
        self.pool = pool

    def get_value(self, key: str, default: Any = None) -> Any:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute("SELECT setting_value FROM app_settings WHERE setting_key = %s", (key,))
                row = cur.fetchone()
        if row is None:
            return DEFAULT_SETTINGS.get(key, default)
        value = row.get("setting_value")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return value
        return value

    def get_settings(self) -> dict:
        result = dict(DEFAULT_SETTINGS)
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=True) as cur:
                cur.execute("SELECT setting_key, setting_value FROM app_settings ORDER BY setting_key")
                rows = cur.fetchall()
        for row in rows:
            value = row.get("setting_value")
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError):
                    pass
            result[str(row["setting_key"])] = value
        return result

    @staticmethod
    def _validate(key: str, value: int) -> None:
        if key not in DEFAULT_SETTINGS:
            raise ValueError(f"Setting is not editable: {key}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Setting value must be an integer.")
        if key == "raster_ttl_hours" and not 1 <= value <= 8760:
            raise ValueError("Raster retention must be between 1 and 8760 hours.")
        if key == "max_upload_size_mb" and not 16 <= value <= 2048:
            raise ValueError("Maximum upload size must be between 16 and 2048 MB.")

    def set_values(self, values: dict[str, int], updated_by: int) -> None:
        """Atomically validate and upsert a group of runtime settings."""
        if not values:
            raise ValueError("At least one setting must be supplied.")
        for key, value in values.items():
            self._validate(key, value)

        ordered = list(values.items())
        placeholders = ", ".join(["(%s, %s::jsonb, %s, CURRENT_TIMESTAMP)"] * len(ordered))
        parameters = []
        for key, value in ordered:
            parameters.extend((key, json.dumps(value), int(updated_by)))

        sql = f"""
            INSERT INTO app_settings (setting_key, setting_value, updated_by, updated_at)
            VALUES {placeholders}
            ON CONFLICT (setting_key) DO UPDATE SET
                setting_value = EXCLUDED.setting_value,
                updated_by = EXCLUDED.updated_by,
                updated_at = CURRENT_TIMESTAMP
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(parameters))

    def set_value(self, key: str, value: int, updated_by: int) -> None:
        self.set_values({key: value}, updated_by)
