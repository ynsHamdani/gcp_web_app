from __future__ import annotations

import unittest

from admin.collection_callbacks import _selected_entries
from admin.layer_callbacks import _option_exists
from maps.admin_gcp import build_admin_gcp_geojson


class AdminStep2Tests(unittest.TestCase):
    def test_selector_validation_uses_string_safe_ids(self):
        options = [{"label": "Historic map", "value": "17"}]
        self.assertTrue(_option_exists(options, 17))
        self.assertTrue(_option_exists(options, "17"))
        self.assertFalse(_option_exists(options, "18"))
        self.assertFalse(_option_exists(options, None))

    def test_selected_entries_resolve_uploaded_and_basemap_reference(self):
        state = {
            "reference_options": [
                {"label": "OpenStreetMap (basemap)", "value": "4"},
                {"label": "Orthophoto.tif", "value": "8"},
            ],
            "reference_registry": [
                {"id": "ref-sha", "db_layer_id": "8", "name": "Orthophoto.tif"}
            ],
            "historical_registry": [
                {
                    "id": "hist-sha",
                    "db_layer_id": "17",
                    "name": "Historical.tif",
                    "cog_path": "/cache/historical.tif",
                }
            ],
        }

        basemap = _selected_entries(
            state,
            {"reference_db_layer_id": "4", "historical_db_layer_id": "17"},
        )
        self.assertEqual(basemap["reference_ui_id"], "4")
        self.assertEqual(basemap["historical_ui_id"], "hist-sha")

        uploaded = _selected_entries(
            state,
            {"reference_db_layer_id": "8", "historical_db_layer_id": "17"},
        )
        self.assertEqual(uploaded["reference_ui_id"], "ref-sha")
        self.assertEqual(uploaded["reference_db_id"], "8")

    def test_selected_entries_reject_unavailable_historical_layer(self):
        state = {
            "reference_options": [{"label": "OSM", "value": "4"}],
            "reference_registry": [],
            "historical_registry": [],
        }
        with self.assertRaisesRegex(ValueError, "historical raster"):
            _selected_entries(
                state,
                {"reference_db_layer_id": "4", "historical_db_layer_id": "17"},
            )

    def test_admin_geojson_keeps_admin_contributor_metadata(self):
        records = [
            {
                "gcp_id": "GCP-0009",
                "student_id": "12",
                "student_username": "admin-user",
                "contributor_role": "admin",
                "student_email": "admin@example.test",
                "reference": {"lat": 56.1, "lon": 10.2},
                "historical": {"lat": 56.11, "lon": 10.21},
                "historical_layer_name": "Old map",
                "reference_layer_name": "OSM",
                "offset_m": 13.4,
                "status": "confirmed",
                "recorded_at": "2026-11-03T08:00:00+00:00",
            }
        ]
        collection = build_admin_gcp_geojson(records, "reference")
        feature = collection["features"][0]
        self.assertEqual(feature["id"], "GCP-0009")
        self.assertEqual(feature["geometry"]["coordinates"], [10.2, 56.1])
        self.assertEqual(feature["properties"]["contributor_role"], "admin")


if __name__ == "__main__":
    unittest.main()
