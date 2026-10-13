from __future__ import annotations

import pytest

from maps.admin_gcp import build_admin_gcp_row, build_admin_gcp_markers


def _record():
    return {
        "gcp_id": "GCP-0012",
        "student_id": "3",
        "student_username": "student_a",
        "student_email": "student_a@example.org",
        "historical_layer_id": "21",
        "historical_layer_name": "historical_1920.tif",
        "reference_layer_id": "18",
        "reference_layer_name": "orthophoto.tif",
        "reference": {"x": 500000.0, "y": 6200000.0, "lon": 10.2, "lat": 56.1},
        "historical": {"pixel": 123.5, "line": 88.0, "x": 500010.0, "y": 6200005.0, "lon": 10.2002, "lat": 56.1001},
        "offset_m": 11.18,
        "status": "confirmed",
        "recorded_at": "2026-10-13T08:00:00+00:00",
        "reference_raster_available": True,
        "historical_raster_available": False,
    }


def test_admin_row_contains_owner_layer_names_and_raster_flags():
    row = build_admin_gcp_row(_record())
    assert row["student_username"] == "student_a"
    assert row["historical_layer_name"] == "historical_1920.tif"
    assert row["reference_layer_name"] == "orthophoto.tif"
    assert row["reference_raster_available"] == "yes"
    assert row["historical_raster_available"] == "no"
    assert row["historical_pixel"] == 123.5


def test_invalid_map_kind_is_rejected():
    with pytest.raises(ValueError):
        build_admin_gcp_markers([_record()], "unknown")


def test_markers_are_clustered_and_missing_positions_are_skipped():
    records = [_record(), {"gcp_id": "GCP-bad", "reference": {}, "historical": {}}]
    groups = build_admin_gcp_markers(records, "reference")
    assert len(groups) == 1
    assert len(groups[0].children) == 1
