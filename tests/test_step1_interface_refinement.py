from pathlib import Path

import pytest

from maps.student_gcp import build_student_gcp_geojson
from services.gcp_grid_count import format_gcp_grid_count

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_student_gcp_geojson_uses_lon_lat_order_and_only_own_map_positions():
    records = [
        {
            "gcp_id": "GCP-1",
            "reference": {"lat": 56.15, "lon": 10.2},
            "historical": {"lat": 56.16, "lon": 10.21},
        }
    ]

    reference = build_student_gcp_geojson(records, "reference")
    historical = build_student_gcp_geojson(records, "historical")

    assert reference["features"][0]["geometry"]["coordinates"] == [10.2, 56.15]
    assert historical["features"][0]["geometry"]["coordinates"] == [10.21, 56.16]
    assert reference["features"][0]["properties"] == {"gcp_id": "GCP-1"}


def test_student_gcp_geojson_skips_missing_non_finite_and_out_of_range_positions():
    records = [
        {"gcp_id": "valid", "reference": {"lat": 56, "lon": 10}},
        {"gcp_id": "missing", "reference": {"lat": 56}},
        {"gcp_id": "nan", "reference": {"lat": float("nan"), "lon": 10}},
        {"gcp_id": "outside", "reference": {"lat": 100, "lon": 10}},
        {"reference": {"lat": 56, "lon": 10}},
    ]

    collection = build_student_gcp_geojson(records, "reference")
    assert [item["id"] for item in collection["features"]] == ["valid"]


def test_student_gcp_geojson_rejects_invalid_map_kind():
    with pytest.raises(ValueError):
        build_student_gcp_geojson([], "other")


def test_student_confirmed_gcps_are_clustered_and_disabled_during_collection():
    source = read("maps/gcp.py")
    assert "cluster=True" in source
    assert 'superClusterOptions={"radius": 50, "maxZoom": 18, "minPoints": 2}' in source
    assert "zoomToBoundsOnClick=not collection_active" in source
    assert "interactive=not collection_active" in source
    assert "bubblingMouseEvents=True" in source


def test_student_collection_state_rebuild_does_not_rewrite_table_or_move_map():
    source = read("callbacks/gcp.py")
    assert 'Input("gcp-collection-active", "data")' in source
    assert 'collection_active=collection_active' in source
    assert 'ctx.triggered_id == "gcp-collection-active"' in source
    assert "rows = no_update" in source
    assert "setView(" not in source
    assert "flyTo(" not in source
    assert "fitBounds(" not in source


def test_pending_reference_marker_stays_fixed_and_historical_marker_stays_draggable():
    source = read("maps/gcp.py")
    assert 'draggable=(map_kind == "historical")' in source
    assert 'if map_kind == "historical":' in source
    assert '"dragend": _ns("captureHistoricalDrag")' in source
    assert 'id=f"pending-{map_kind}-gcp-marker"' in source


def test_student_cluster_javascript_does_not_change_map_view():
    source = read("assets/student_gcp.js")
    assert "L.circleMarker" in source
    assert "bindTooltip" in source
    for forbidden in ("fitBounds(", "flyTo(", "panTo(", "setView("):
        assert forbidden not in source


def test_grid_count_uses_filtered_rows_and_handles_zero_results():
    rows = [{"gcp_id": "GCP-1"}, {"gcp_id": "GCP-2"}, {"gcp_id": "GCP-3"}]
    visible = [rows[0], rows[2]]
    assert format_gcp_grid_count(visible, rows) == "Showing 2 of 3 loaded GCP(s)."
    assert format_gcp_grid_count([], rows) == "Showing 0 of 3 loaded GCP(s)."
    assert format_gcp_grid_count(None, rows) == "Showing 3 of 3 loaded GCP(s)."


def test_grid_count_ignores_stale_virtual_rows_after_deletion():
    current_rows = [{"gcp_id": "GCP-1"}, {"gcp_id": "GCP-3"}]
    stale_virtual_rows = [
        {"gcp_id": "GCP-1"},
        {"gcp_id": "GCP-2"},
        {"gcp_id": "GCP-3"},
    ]
    assert format_gcp_grid_count(stale_virtual_rows, current_rows) == "Showing 2 of 2 loaded GCP(s)."


def test_admin_count_tracks_ag_grid_virtual_rows_and_current_row_data():
    source = read("admin/gcp_callbacks.py")
    layout = read("ui/admin_layout.py")
    assert 'Input("admin-gcp-table", "virtualRowData")' in source
    assert 'State("admin-gcp-table", "rowData")' in source
    assert 'Output("admin-gcp-count", "children")' in source
    assert 'id="admin-gcp-count"' in layout
    assert "format_gcp_grid_count" in source


def test_super_admin_console_has_its_own_scroll_region_and_fixed_header():
    source = read("ui/super_admin_layout.py")
    assert '"height": "100vh"' in source
    assert '"overflow": "hidden"' in source
    assert '"flex": "0 0 auto"' in source
    assert 'id="super-admin-scroll-container"' in source
    assert '"overflowY": "auto"' in source
    assert '"overflowX": "hidden"' in source
    assert '"minHeight": "0"' in source
