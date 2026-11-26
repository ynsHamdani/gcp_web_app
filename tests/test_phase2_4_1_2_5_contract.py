from __future__ import annotations

from pathlib import Path

from services.coverage_assignment import classify_match_count
from storage.coverage_assignment_store import CoverageAssignmentStore

ROOT = Path(__file__).resolve().parents[1]


def test_assignment_table_migration_is_additive_and_version_scoped():
    sql = (ROOT / "migrations" / "007_coverage_feature_assignments_up.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS coverage_feature_assignments" in sql
    assert "REFERENCES coverage_features (coverage_feature_id)" in sql
    assert "ON UPDATE CASCADE ON DELETE CASCADE" in sql
    assert "REFERENCES users (user_id)" in sql
    assert "PRIMARY KEY (coverage_feature_id, student_id)" in sql
    assert "idx_coverage_feature_assignments_student_feature" in sql
    assert "007_coverage_feature_assignments" in sql
    assert "ALTER TABLE gcps" not in sql


def test_assignment_store_uses_student_identity_and_viewport_filtering():
    source = (ROOT / "storage" / "coverage_assignment_store.py").read_text(encoding="utf-8")
    assert "WHERE a.student_id = :student_id" in source
    assert "AND l.is_active = TRUE" in source
    assert "COALESCE(l.is_suppressed, FALSE) = FALSE" in source
    assert "f.geom && v.geom AND ST_Intersects(f.geom, v.geom)" in source
    assert "ST_SimplifyPreserveTopology" in source
    assert "max_features: int = 2500" in source


def test_only_exactly_one_matching_feature_is_assigned():
    assert classify_match_count(0) == ("NOT_UNIQUE", "UNCOVERED")
    assert classify_match_count(1) == ("ASSIGNED_UNIQUE", None)
    assert classify_match_count(2) == ("NOT_UNIQUE", "MULTIPLE_MATCHES")


def test_store_validates_and_normalizes_student_ids():
    assert CoverageAssignmentStore._student_ids(["4", 2, 4]) == [2, 4]


def test_student_overlays_allow_collection_clicks_and_reserve_browse_clicks_for_task_popups():
    source = (ROOT / "maps" / "student_coverage.py").read_text(encoding="utf-8")
    handlers = (ROOT / "assets" / "student_coverage_map.js").read_text(encoding="utf-8")
    assert "dl.LayersControl" in source
    assert "dl.Overlay" in source
    # Leaflet bubbling stays enabled so a polygon click can place a GCP
    # while collection is active. The custom handler stops it in browse mode.
    assert "bubblingMouseEvents=True" in source
    assert "interactive=True" in source
    assert "if (isGcpCollectionActive())" in handlers
    assert "L.DomEvent.stopPropagation(event.originalEvent)" in handlers


def test_assignment_callbacks_require_authenticated_admin_and_store_server_ids():
    source = (ROOT / "admin" / "coverage_assignment_callbacks.py").read_text(encoding="utf-8")
    assert 'not is_admin_role(getattr(current_user, "role", None))' in source
    assert "assigned_by=actor_id" in source
    assert "student_values or []" in source


def test_modal_observer_does_not_watch_every_page_style_mutation():
    source = (ROOT / "assets" / "coverage_map.js").read_text(encoding="utf-8")
    assert 'modalObserver.observe(modal, { attributes: true, attributeFilter: ["style"] })' in source
    assert 'mountObserver.observe(document.body, { childList: true, subtree: true })' in source
    assert 'attributes: true, attributeFilter: ["style"]' not in source.split('mountObserver.observe(document.body', 1)[1].split(');', 1)[0]


def test_inactive_student_cannot_receive_new_assignment_but_existing_link_can_be_removed():
    source = (ROOT / "storage" / "coverage_assignment_store.py").read_text(encoding="utf-8")
    assert "u.is_active = TRUE" in source
    assert "existing.coverage_feature_id = :feature_id" in source


def test_modal_scroll_observer_runs_only_on_coverage_page():
    source = (ROOT / "assets" / "coverage_map.js").read_text(encoding="utf-8")
    assert 'startsWith("/admin/coverage/")' in source
