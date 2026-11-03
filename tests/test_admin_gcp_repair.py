from __future__ import annotations

import pytest

from maps.admin_gcp import build_admin_gcp_markers, build_admin_gcp_row
from admin.gcp_callbacks import _extract_drag_position, _extract_map_position, _optional_filter_id


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
        "reference": {"lat": 56.15, "lon": 10.20, "x": 575000.0, "y": 6225000.0},
        "historical": {"lat": 56.151, "lon": 10.201, "x": 575060.0, "y": 6225110.0, "pixel": 100.5, "line": 200.5},
        "offset_m": 125.3,
        "status": "confirmed",
        "reference_raster_available": True,
        "historical_raster_available": False,
        "recorded_at": "2026-10-13T10:00:00+00:00",
    }


def test_marker_builder_returns_flat_markers_for_cluster_group():
    record = _sample_record()
    markers = build_admin_gcp_markers([record], "reference")

    assert len(markers) == 1
    assert list(markers[0].position) == [56.15, 10.2]
    assert markers[0].id["gcp_id"] == "GCP-0007"
    assert "student_a" in markers[0].title
    assert "Historic map 1890" in markers[0].title


def test_marker_builder_skips_invalid_coordinates():
    records = [_sample_record(), {"gcp_id": "GCP-0008", "reference": {"lat": None, "lon": 0}}]
    assert len(build_admin_gcp_markers(records, "reference")) == 1
    with pytest.raises(ValueError):
        build_admin_gcp_markers(records, "other")


def test_admin_table_row_contains_owner_and_both_layer_names():
    row = build_admin_gcp_row(_sample_record())
    assert row["student_username"] == "student_a"
    assert row["reference_layer_name"] == "Orthophoto"
    assert row["historical_layer_name"] == "Historic map 1890"
    assert row["historical_raster_available"] == "no"


def test_filter_id_parsing_is_strict_and_supports_all():
    assert _optional_filter_id("all", "student") is None
    assert _optional_filter_id(None, "layer") is None
    assert _optional_filter_id("21", "layer") == 21
    with pytest.raises(ValueError):
        _optional_filter_id("abc", "layer")
    with pytest.raises(ValueError):
        _optional_filter_id("0", "layer")


def test_map_and_drag_coordinates_accept_leaflet_payloads():
    assert _extract_map_position({"latlng": {"lat": 56.1, "lng": 10.2}}) == {"lat": 56.1, "lon": 10.2}
    assert _extract_drag_position({"position": [56.3, 10.4], "timestamp": 10}) == {"lat": 56.3, "lon": 10.4}
    assert _extract_map_position(None) is None
    assert _extract_drag_position({"position": None}) is None
