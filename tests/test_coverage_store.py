from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from storage.coverage_store import CoverageStore


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _Connection:
    def __init__(self, *, fail_on_features=False):
        self.calls = []
        self.fail_on_features = fail_on_features

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "SELECT COALESCE(MAX(version)" in sql:
            return _Result(3)
        if "RETURNING coverage_layer_id" in sql:
            return _Result(77)
        if "INSERT INTO coverage_features" in sql:
            if self.fail_on_features:
                raise RuntimeError("simulated feature insert error")
        return _Result(None)


class _Engine:
    def __init__(self, *, fail_on_features=False):
        self.connection = _Connection(fail_on_features=fail_on_features)
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def begin(self):
        try:
            yield self.connection
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True


class _Pool:
    def __init__(self, engine):
        self.engine = engine


class _Feature:
    source_feature_key = "cell-1"
    feature_label = "Cell 1"
    source_index = 1
    attributes = {"class": "forest"}
    geometry_wkb_hex = "010300000000000000"


def _import_data():
    return SimpleNamespace(
        features=[_Feature()],
        feature_count=1,
        filename="grid.geojson",
        source_format="geojson",
        source_layer_name="grid",
        source_crs="EPSG:4326",
        target_srid=25832,
        geometry_type="MULTIPOLYGON",
        source_sha256="a" * 64,
    )


def test_layer_metadata_validation_trims_and_rejects_invalid_values():
    assert CoverageStore.validate_layer_metadata("  Grid  ", "  notes  ") == ("Grid", "notes")
    with pytest.raises(ValueError, match="Enter a name"):
        CoverageStore.validate_layer_metadata("  ")
    with pytest.raises(ValueError, match="2–160"):
        CoverageStore.validate_layer_metadata("x")
    with pytest.raises(ValueError, match="2,000"):
        CoverageStore.validate_layer_metadata("Grid", "n" * 2001)


def test_publish_writes_layer_and_features_in_one_transaction():
    engine = _Engine()
    store = CoverageStore(_Pool(engine))

    result = store.publish_import(
        layer_name="Danish grid",
        notes="2026 release",
        import_data=_import_data(),
        imported_by=9,
    )

    assert result == {
        "coverage_layer_id": "77",
        "layer_name": "Danish grid",
        "version": 3,
        "feature_count": 1,
        "is_active": True,
    }
    assert engine.committed is True
    assert engine.rolled_back is False
    sql_statements = [sql for sql, _params in engine.connection.calls]
    assert any("UPDATE coverage_layers" in sql for sql in sql_statements)
    assert any("INSERT INTO coverage_layers" in sql for sql in sql_statements)
    assert any("INSERT INTO coverage_features" in sql for sql in sql_statements)


def test_feature_insert_failure_rolls_back_registry_and_feature_writes():
    engine = _Engine(fail_on_features=True)
    store = CoverageStore(_Pool(engine))

    with pytest.raises(RuntimeError, match="simulated feature insert error"):
        store.publish_import(
            layer_name="Danish grid",
            notes="",
            import_data=_import_data(),
            imported_by=9,
        )

    assert engine.rolled_back is True
    assert engine.committed is False
