from __future__ import annotations

import unittest

from services.admin_layer_summary import summarize_unavailable_layers


class AdminWorkspaceRefinementTests(unittest.TestCase):
    def test_unavailable_summary_groups_rasters_and_keeps_names(self):
        summary = summarize_unavailable_layers(
            [
                "Reference: orthophoto.tif (raster unavailable)",
                "Historical: old_map.tif (raster unavailable)",
                "Historical: damaged_map.tif (map service unavailable)",
            ]
        )
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["reference"], 1)
        self.assertEqual(summary["historical"], 2)
        self.assertEqual(len(summary["groups"]["reference"]), 1)
        self.assertIn("old_map.tif", summary["groups"]["historical"][0])

    def test_empty_unavailable_summary_is_clean(self):
        summary = summarize_unavailable_layers([])
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["reference"], 0)
        self.assertEqual(summary["historical"], 0)

    def test_unclassified_messages_are_retained(self):
        summary = summarize_unavailable_layers(["Unexpected raster metadata warning"])
        self.assertEqual(summary["total"], 1)
        self.assertEqual(
            summary["groups"]["other"],
            ["Unexpected raster metadata warning"],
        )


if __name__ == "__main__":
    unittest.main()
