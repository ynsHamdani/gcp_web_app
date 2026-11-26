from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_assignment_selection_uses_persistent_store_not_geojson_hideout():
    source = (ROOT / "admin" / "coverage_assignment_callbacks.py").read_text(encoding="utf-8")
    assert 'Input("coverage-selected-feature", "data")' in source
    assert 'Output("coverage-polygons", "hideout")' not in source
    assert 'Input("coverage-polygons", "clickData")' not in source
    assert 'Input("coverage-assignment-students", "value")' not in source
    assert 'Output("coverage-assignment-save", "disabled")' in source


def test_polygon_click_updates_stable_dash_store_and_keeps_popup():
    source = (ROOT / "assets" / "coverage_map.js").read_text(encoding="utf-8")
    assert 'set_props("coverage-selected-feature"' in source
    assert 'layer.bindPopup(root).openPopup()' in source
    assert 'Uniquely assigned GCPs' in source
    assert 'context.setProps({clickData:' not in source
    assert 'window.coverageMap.clearSelectedPolygon' in source


def test_map_payload_contains_coverage_version_for_assignment_selection():
    source = (ROOT / "admin" / "coverage_callbacks.py").read_text(encoding="utf-8")
    assert 'properties["coverage_layer_id"] = int(layer_id)' in source


def test_student_viewport_and_visual_only_overlays_remain_in_place():
    student_callback = (ROOT / "callbacks" / "student_coverage.py").read_text(encoding="utf-8")
    map_source = (ROOT / "maps" / "student_coverage.py").read_text(encoding="utf-8")
    assert "query_student_geojson" in student_callback
    assert 'student_id = _require_student_id()' in student_callback
    assert "dl.LayersControl" in map_source
    # Feature clicks can reach dl.Map while collecting a GCP; in browse mode
    # the student handler stops propagation before opening the task popup.
    assert "bubblingMouseEvents=True" in map_source
    student_js = (ROOT / "assets" / "student_coverage_map.js").read_text(encoding="utf-8")
    assert "isGcpCollectionActive()" in student_js
    assert "L.DomEvent.stopPropagation(event.originalEvent)" in student_js
