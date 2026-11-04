from __future__ import annotations

import base64
import unittest

from services.admin_gcp_requirements import (
    can_collect_gcp, is_historical_available, is_reference_available,
)
from services.admin_user_management import (
    generate_temporary_password, parse_student_roster,
)
from services import runtime_settings
from storage.settings_store import PostgresSettingsStore
from unittest.mock import patch
from pathlib import Path


class AdminProductionMilestoneTests(unittest.TestCase):
    def setUp(self):
        self.layers = {
            "basemap_reference_layer_id": "3",
            "reference_options": [
                {"label": "OpenStreetMap (basemap)", "value": "3"},
                {"label": "ortho.tif", "value": "12"},
            ],
            "available_historical_options": [
                {"label": "historic.tif", "value": "22"},
            ],
        }

    def test_openstreetmap_is_valid_reference_without_upload(self):
        self.assertTrue(is_reference_available(self.layers, "3"))
        self.assertFalse(is_reference_available(self.layers, None))

    def test_uploaded_reference_requires_available_option(self):
        self.assertTrue(is_reference_available(self.layers, "12"))
        self.assertFalse(is_reference_available(self.layers, "99"))

    def test_collection_requires_reference_and_available_historical(self):
        self.assertTrue(is_historical_available(self.layers, "22"))
        self.assertFalse(is_historical_available(self.layers, "23"))
        self.assertTrue(can_collect_gcp(self.layers, {
            "reference_db_layer_id": "3",
            "historical_db_layer_id": "22",
        }))
        self.assertFalse(can_collect_gcp(self.layers, {
            "reference_db_layer_id": "3",
            "historical_db_layer_id": None,
        }))

    def test_temporary_password_contains_all_character_classes(self):
        password = generate_temporary_password()
        self.assertGreaterEqual(len(password), 16)
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))
        self.assertTrue(any(c in "!@#$%*-_" for c in password))

    def test_roster_csv_accepts_utf8_bom_and_case_insensitive_headers(self):
        raw = "\ufeffUsername,EMAIL\nstudent_01,one@example.org\nstudent_02,two@example.org\n".encode("utf-8")
        contents = "data:text/csv;base64," + base64.b64encode(raw).decode("ascii")
        rows = parse_student_roster(contents)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["username"], "student_01")
        self.assertEqual(rows[1]["email"], "two@example.org")

    def test_roster_limits_rows_and_file_size(self):
        raw = b"username,email\na,a@example.org\nb,b@example.org\n"
        contents = "data:text/csv;base64," + base64.b64encode(raw).decode("ascii")
        with self.assertRaises(ValueError):
            parse_student_roster(contents, max_rows=1)
        with self.assertRaises(ValueError):
            parse_student_roster(contents, max_bytes=2)

    def test_runtime_setting_validation(self):
        PostgresSettingsStore._validate("raster_ttl_hours", 24)
        PostgresSettingsStore._validate("max_upload_size_mb", 256)
        for key, value in (("raster_ttl_hours", 0), ("raster_ttl_hours", 8761), ("max_upload_size_mb", 8), ("unknown", 12)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                PostgresSettingsStore._validate(key, value)

    def test_runtime_settings_fail_safely_on_corrupt_values(self):
        with patch.object(runtime_settings, "get_runtime_setting", return_value="not-a-number"):
            self.assertEqual(runtime_settings.raster_ttl_hours(24), 24.0)
            self.assertEqual(runtime_settings.max_upload_size_mb(256), 256)
        with patch.object(runtime_settings, "get_runtime_setting", return_value=True):
            self.assertEqual(runtime_settings.max_upload_size_mb(256), 256)

    def test_migration_is_additive_and_down_migration_has_guard(self):
        root = Path(__file__).resolve().parents[1]
        up = (root / "migrations" / "003_admin_production_up.sql").read_text(encoding="utf-8")
        down = (root / "migrations" / "003_admin_production_down.sql").read_text(encoding="utf-8")
        self.assertIn("must_change_password", up)
        self.assertIn("CREATE TABLE IF NOT EXISTS auth_sessions", up)
        self.assertIn("CREATE TABLE IF NOT EXISTS admin_audit_log", up)
        self.assertNotIn("DROP TABLE gcps", up.upper())
        self.assertIn("WHERE must_change_password = TRUE", down)
        self.assertIn("DROP TABLE IF EXISTS auth_sessions", down)



if __name__ == "__main__":
    unittest.main()
