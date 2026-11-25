from pathlib import Path


def _migration(name: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "migrations" / name).read_text(encoding="utf-8")


def test_migration_006_adds_only_coverage_metadata_and_indexes():
    sql = _migration("006_coverage_management_assignment_up.sql").lower()
    assert "alter table coverage_layers" in sql
    assert "is_suppressed boolean" in sql
    assert "publish_token uuid" in sql
    assert "extent geometry(polygon, 25832)" in sql
    assert "uq_coverage_layers_publish_token" in sql
    assert "idx_coverage_features_layer_feature" in sql
    assert "alter table gcps" not in sql
    assert "create table" not in sql or "coverage_features" not in sql
    assert "partition by" not in sql


def test_down_migration_preserves_coverage_layers_and_features():
    sql = _migration("006_coverage_management_assignment_down.sql").lower()
    assert "drop table coverage_features" not in sql
    assert "drop table coverage_layers" not in sql
    assert "drop column if exists publish_token" in sql
    assert "drop column if exists is_suppressed" in sql
    assert "drop column if exists extent" in sql


def test_assignment_policy_uses_one_spatial_predicate_and_two_main_outcomes():
    from storage.coverage_store import _MATCH_CTE
    from services.coverage_assignment import classify_match_count

    assert "st_covers(f.geom, p.point_geom)" in _MATCH_CTE.lower()
    assert classify_match_count(1) == ("ASSIGNED_UNIQUE", None)
    assert classify_match_count(0) == ("NOT_UNIQUE", "UNCOVERED")
    assert classify_match_count(2) == ("NOT_UNIQUE", "MULTIPLE_MATCHES")
