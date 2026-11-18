
from __future__ import annotations

import pytest

from maps.admin_gcp import build_admin_gcp_geojson, build_admin_gcp_row
from admin.gcp_callbacks import _optional_id


def _sample_record():
    return {
        "gcp_id": "GCP-0007",
        "student_id": "3",
        "student_username": "student_a",
        "student_email": "student_a@example.org",
        "reference_layer_id": "11",
        "reference_layer_name": "Orthophoto",
        "historical_layer_id": "21",
        "historical_layer_name": "Historic map 1890",
        "reference": {
            "lat": 56.15, "lon": 10.20,
            "x": 575000.0, "y": 6225000.0
        },
        "historical": {
            "lat": 56.151, "lon": 10.201,
            "x": 575060.0, "y": 6225110.0,
            "pixel": 100.5, "line": 200.5
        },
        "offset_m": 125.3,
        "status": "confirmed",
        "reference_raster_available": True,
        "historical_raster_available": False,
        "recorded_at": "2026-10-13T10:00:00+00:00",
    }


def test_geojson_builder_returns_point_features():
    result = build_admin_gcp_geojson([_sample_record()], "reference")

    assert len(result["features"]) == 1
    feature = result["features"][0]

    assert feature["id"] == "GCP-0007"
    assert feature["geometry"]["coordinates"] == [10.20, 56.15]
    assert feature["properties"]["contributor"] == "student_a"
    assert feature["properties"]["historical_layer"] == "Historic map 1890"


def test_geojson_builder_skips_invalid_coordinates():
    records = [
        _sample_record(),
        {"gcp_id": "GCP-0008", "reference": {"lat": None, "lon": 0}},
    ]

    result = build_admin_gcp_geojson(records, "reference")
    assert len(result["features"]) == 1

    with pytest.raises(ValueError):
        build_admin_gcp_geojson(records, "other")


def test_admin_table_contains_owner_and_layer_names():
    row = build_admin_gcp_row(_sample_record())

    assert row["student_username"] == "student_a"
    assert row["reference_layer_name"] == "Orthophoto"
    assert row["historical_layer_name"] == "Historic map 1890"
    assert row["reference_raster_available"] == "yes"
    assert row["historical_raster_available"] == "no"


def test_filter_id_parsing_is_strict_and_supports_all():
    assert _optional_id("all", "student") is None
    assert _optional_id(None, "layer") is None
    assert _optional_id("21", "layer") == 21

    with pytest.raises(ValueError):
        _optional_id("abc", "layer")

    with pytest.raises(ValueError):
        _optional_id("0", "layer")
