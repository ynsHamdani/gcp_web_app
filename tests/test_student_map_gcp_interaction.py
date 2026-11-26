from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_assigned_polygon_click_does_not_open_task_popup_during_gcp_collection():
    source = read("assets/student_coverage_map.js")
    assert 'getElementById("add-gcp-button")' in source
    assert '.includes("stop gcp")' in source
    assert 'if (isGcpCollectionActive()) {\n                    return;' in source
    assert 'L.DomEvent.stopPropagation(event.originalEvent)' in source


def test_collection_mode_returns_before_task_popup_is_created():
    source = read("assets/student_coverage_map.js")
    handler = source.split('layer.on("click", function (event) {', 1)[1]
    collection_check = handler.index("if (isGcpCollectionActive())")
    popup_creation = handler.index('document.createElement("div")')
    assert collection_check < popup_creation


def test_assigned_polygon_clicks_can_reach_map_during_gcp_collection():
    source = read("maps/student_coverage.py")
    assert 'bubblingMouseEvents=True' in source
    js_source = read("assets/student_coverage_map.js")
    assert 'L.DomEvent.stopPropagation(event.originalEvent)' in js_source
    assert 'if (isGcpCollectionActive()) {\n                    return;' in js_source
