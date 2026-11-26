from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_task_migration_is_additive_and_does_not_change_gcp_schema():
    sql = read("migrations/008_coverage_feature_tasks_up.sql")
    assert "CREATE TABLE IF NOT EXISTS coverage_feature_tasks" in sql
    assert "REFERENCES coverage_features (coverage_feature_id)" in sql
    assert "ON UPDATE CASCADE ON DELETE CASCADE" in sql
    assert "objective VARCHAR(240)" in sql
    assert "instructions TEXT" in sql
    assert "008_coverage_feature_tasks" in sql
    assert "ALTER TABLE gcps" not in sql
    assert "CREATE TABLE IF NOT EXISTS coverage_feature_assignments" not in sql
    assert "ALTER TABLE coverage_feature_assignments" not in sql


def test_assignment_and_task_metadata_are_saved_in_one_transaction():
    source = read("storage/coverage_assignment_store.py")
    assert "def replace_feature_assignments(" in source
    assert "objective: str | None = None" in source
    assert "instructions: str | None = None" in source
    assert "with self.engine.begin() as connection" in source
    assert "INSERT INTO coverage_feature_tasks" in source
    assert "DELETE FROM coverage_feature_tasks" in source
    assert "coverage_layer_id = :layer_id" in source
    assert "COALESCE(t.instructions, '') AS instructions" in source


def test_students_only_receive_task_text_for_features_they_are_assigned():
    source = read("storage/coverage_assignment_store.py")
    query = source.split("def query_student_geojson", 1)[1]
    assert "FROM coverage_feature_assignments a" in query
    assert "WHERE a.student_id = :student_id" in query
    assert "f.coverage_layer_id = :layer_id" in query
    assert "LEFT JOIN coverage_feature_tasks" in query
    assert '"objective": str(row.get("objective") or "")' in query
    assert '"instructions": str(row.get("instructions") or "")' in query


def test_save_button_is_scoped_to_the_currently_selected_coverage_layer():
    source = read("admin/coverage_assignment_callbacks.py")
    block = source.split("def set_assignment_save_enabled", 1)[1].split("@app.callback", 1)[0]
    assert 'Input("coverage-analysis-layer", "value")' in source
    assert 'def clear_selection_on_layer_change(_layer_id):' in source
    assert "return None" in source.split("def clear_selection_on_layer_change", 1)[1].split("@app.callback", 1)[0]
    assert 'str(selection.get("coverage_layer_id")) == str(active_layer_id)' in block
    assert "objective=objective or \"\"" in source
    assert "instructions=instructions or \"\"" in source


def test_student_assigned_polygons_are_outlines_and_click_only():
    source = read("assets/student_coverage_map.js")
    assert "fill: true" in source  # transparent fill preserves clickability inside the polygon
    assert "fillOpacity: 0" in source
    assert 'layer.on("click"' in source
    assert "bindTooltip" not in source
    assert "Read full instructions" in source
    assert "textContent = instructions" in source


def test_admin_polygon_information_is_click_only():
    source = read("assets/coverage_map.js")
    assert "Polygon information is intentionally click-only" in source
    assert "bindTooltip" not in source
    assert 'layer.on("click"' in source


def test_feature_statistics_sort_by_unique_gcp_count_and_include_student_json():
    source = read("storage/coverage_store.py")
    assert source.count("ORDER BY COALESCE(fc.assigned_count, 0) DESC, f.coverage_feature_id ASC") == 2
    assert source.count("AS responsible_students") >= 2
    assert "'student_id', u.user_id" in source
    assert "'username', u.username" in source
    assert "COALESCE(r.responsible_students, '[]'::jsonb)" in source


def test_feature_statistics_csv_serializes_responsible_students_as_json():
    source = read("admin/coverage_callbacks.py")
    assert '"responsible_students"' in source
    assert '"responsible_students", "context_breakdown"' in source
    assert "colSpan=6" in source  # initial table placeholder matches the six-column table


def test_admin_form_has_short_objective_and_long_instructions_fields():
    source = read("ui/admin_coverage_layout.py")
    assert 'id="coverage-assignment-objective"' in source
    assert 'maxLength=240' in source
    assert 'id="coverage-assignment-instructions"' in source
    assert 'maxLength=10000' in source
    assert 'id="coverage-assignment-students"' in source


def test_student_overlay_controls_remain_independent_per_map():
    source = read("maps/student_coverage.py")
    assert "dl.LayersControl" in source
    assert "dl.Overlay" in source
    assert "checked=True" in source
    assert 'map_kind not in {"reference", "historical"}' in source


def test_student_workspace_keeps_existing_gcp_ids_and_compacts_actions():
    layout = read("ui/layout.py")
    css = read("assets/student_workspace.css")
    assert "student-table-actions" in layout
    assert 'id="student-export-gcps"' in layout
    assert 'id="refresh-gcp-button"' in layout
    assert layout.count('id="student-export-gcps"') == 1
    assert layout.count('id="student-gcp-download"') == 1
    assert layout.count('id="refresh-gcp-button"') == 1
    assert "table-toolbar" not in layout
    assert ".maps-area" in css
    assert "@media (max-width: 700px)" in css
    assert "#student-reference-coverage-status" in css
    assert "#student-historical-coverage-status" in css
    assert "#gcp-table" not in css  # existing table component is not replaced


def test_down_migration_preserves_assignment_links_and_gcp_records():
    sql = read("migrations/008_coverage_feature_tasks_down.sql")
    assert "DROP TABLE IF EXISTS coverage_feature_tasks" in sql
    assert "DROP TABLE IF EXISTS coverage_feature_assignments" not in sql
    assert "DROP TABLE IF EXISTS gcps" not in sql


def test_student_layout_patch_moves_existing_actions_without_dropping_ids():
    """Verify the installed layout contains one compact action group.

    These post-install tests must not depend on the release installer being
    present beside the project directory; it is distributed in the ZIP only.
    """
    source = read("ui/layout.py")
    start = source.index('className="student-table-actions"')
    download = 'dcc.Download(id="student-gcp-download")'
    group_end = source.index(download, start)
    action_group = source[start:group_end + len(download)]
    assert 'id="student-export-gcps"' in action_group
    assert 'id="refresh-gcp-button"' in action_group
    assert 'id="student-gcp-download"' in action_group
    assert source.count('id="student-export-gcps"') == 1
    assert source.count('id="student-gcp-download"') == 1
    assert source.count('id="refresh-gcp-button"') == 1
    assert "table-toolbar" not in source
