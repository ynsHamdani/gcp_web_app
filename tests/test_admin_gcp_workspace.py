from __future__ import annotations

import unittest

from maps.admin_gcp import build_admin_gcp_geojson, build_admin_gcp_row


class AdminGcpWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "gcp_id": "GCP-0042",
            "student_id": "7",
            "student_username": "map_admin",
            "student_email": "map_admin@example.org",
            "contributor_role": "admin",
            "reference_layer_id": "11",
            "reference_layer_name": "Orthophoto 2024",
            "historical_layer_id": "22",
            "historical_layer_name": "Historical map 1890",
            "reference": {"lat": 56.15, "lon": 10.20, "x": 570000.0, "y": 6220000.0},
            "historical": {"lat": 56.151, "lon": 10.201, "pixel": 120.5, "line": 88.25, "x": 570050.0, "y": 6220050.0},
            "offset_m": 75.2,
            "status": "confirmed",
            "recorded_at": "2026-11-03T08:00:00+00:00",
            "reference_raster_available": True,
            "historical_raster_available": False,
        }

    def test_geojson_uses_longitude_latitude_and_keeps_metadata(self):
        collection = build_admin_gcp_geojson([self.record], "reference")
        self.assertEqual(collection["type"], "FeatureCollection")
        self.assertEqual(len(collection["features"]), 1)
        feature = collection["features"][0]
        self.assertEqual(feature["geometry"]["coordinates"], [10.20, 56.15])
        self.assertEqual(feature["properties"]["gcp_id"], "GCP-0042")
        self.assertEqual(feature["properties"]["contributor_role"], "admin")
        self.assertEqual(feature["properties"]["historical_layer"], "Historical map 1890")

    def test_geojson_skips_records_without_map_coordinates(self):
        invalid = dict(self.record)
        invalid["historical"] = {"pixel": 5, "line": 6}
        collection = build_admin_gcp_geojson([invalid], "historical")
        self.assertEqual(collection["features"], [])

    def test_table_row_exposes_contributor_role_and_raster_availability(self):
        row = build_admin_gcp_row(self.record)
        self.assertEqual(row["student_username"], "map_admin")
        self.assertEqual(row["contributor_role"], "admin")
        self.assertEqual(row["reference_raster_available"], "yes")
        self.assertEqual(row["historical_raster_available"], "no")

    def test_invalid_map_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            build_admin_gcp_geojson([self.record], "wrong")


if __name__ == "__main__":
    unittest.main()
