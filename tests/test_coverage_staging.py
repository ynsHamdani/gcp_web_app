from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.coverage_staging import CoverageStagingStore


class _Feature:
    source_feature_key = "grid-1"
    feature_label = "Grid 1"
    source_index = 1
    attributes = {"class": "forest", "name": "Area 1"}
    geometry_wkb_hex = "010300000000000000"


def _import_data():
    return SimpleNamespace(
        filename="grid.geojson", source_format="geojson", source_layer_name="grid",
        source_crs="EPSG:4326", target_srid=25832, geometry_type="MULTIPOLYGON",
        feature_count=1, source_sha256="a" * 64, warnings=("test warning",),
        features=(_Feature(),),
    )


def test_staging_round_trip_streams_prepared_features(tmp_path):
    store = CoverageStagingStore(tmp_path)
    token, metadata = store.stage(_import_data())
    staged = store.open(token)
    assert metadata["feature_count"] == 1
    assert staged.source_sha256 == "a" * 64
    batches = list(staged.iter_feature_batches(batch_size=1))
    assert len(batches) == 1
    assert batches[0][0].source_feature_key == "grid-1"
    assert batches[0][0].attributes["class"] == "forest"
    store.delete(token)
    with pytest.raises(ValueError, match="expired or is unavailable"):
        store.open(token)


def test_staging_token_cannot_escape_root(tmp_path):
    store = CoverageStagingStore(tmp_path)
    with pytest.raises(ValueError, match="token is invalid"):
        store.open("../../outside")
