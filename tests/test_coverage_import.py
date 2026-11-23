from __future__ import annotations

import base64
import json

import pytest
from shapely import wkb

import services.coverage_import as coverage_import
from services.coverage_import import CoverageImportError, inspect_coverage_upload


def _geojson(features, crs=None):
    result = {"type": "FeatureCollection", "features": features}
    if crs:
        result["crs"] = crs
    return json.dumps(result).encode("utf-8")


def _payload(raw: bytes) -> str:
    return "data:application/geo+json;base64," + base64.b64encode(raw).decode("ascii")


def _feature(coords, properties=None, geometry_type="Polygon"):
    return {
        "type": "Feature",
        "properties": properties or {},
        "geometry": {"type": geometry_type, "coordinates": coords},
    }


@pytest.fixture(autouse=True)
def _disable_runtime_size_lookup(monkeypatch):
    monkeypatch.setattr(coverage_import, "validate_dash_upload_size", lambda *_args, **_kwargs: None)


def test_valid_geojson_is_normalized_and_feature_attributes_are_preserved():
    raw = _geojson([
        _feature([[[10.0, 56.0], [10.01, 56.0], [10.01, 56.01], [10.0, 56.01], [10.0, 56.0]]], {"id": "cell-1", "name": "Cell 1", "class": "forest"}),
        _feature([[[10.02, 56.0], [10.03, 56.0], [10.03, 56.01], [10.02, 56.01], [10.02, 56.0]]], {"id": "cell-2", "name": "Cell 2", "class": "water"}),
    ])

    result = inspect_coverage_upload(_payload(raw), "coverage.geojson")

    assert result.source_format == "geojson"
    assert result.feature_count == 2
    assert result.source_crs
    assert result.target_srid == 25832
    assert len(result.source_sha256) == 64
    assert result.features[0].source_feature_key == "cell-1"
    assert result.features[1].attributes["class"] == "water"
    geom = wkb.loads(bytes.fromhex(result.features[0].geometry_wkb_hex))
    assert geom.geom_type == "Polygon"
    assert 400_000 < geom.centroid.x < 700_000


def test_invalid_self_intersecting_polygon_is_rejected_without_repair():
    raw = _geojson([
        _feature([[[10.0, 56.0], [10.02, 56.02], [10.0, 56.02], [10.02, 56.0], [10.0, 56.0]]])
    ])

    with pytest.raises(CoverageImportError, match="failed polygon validation"):
        inspect_coverage_upload(_payload(raw), "invalid.geojson")


def test_non_polygon_features_are_rejected():
    raw = _geojson([
        _feature([10.0, 56.0], {"name": "point"}, geometry_type="Point")
    ])

    with pytest.raises(CoverageImportError, match="not Polygon/MultiPolygon"):
        inspect_coverage_upload(_payload(raw), "points.geojson")


def test_duplicate_candidate_ids_generate_explicit_row_keys_and_warning():
    ring = [[[10.0, 56.0], [10.01, 56.0], [10.01, 56.01], [10.0, 56.01], [10.0, 56.0]]]
    raw = _geojson([
        _feature(ring, {"id": "duplicate"}),
        _feature(ring, {"id": "duplicate"}),
    ])

    result = inspect_coverage_upload(_payload(raw), "duplicate-ids.geojson")

    assert result.features[0].source_feature_key == "row:1"
    assert result.features[1].source_feature_key == "row:2"
    assert any("not a unique" in warning for warning in result.warnings)


def test_unsupported_file_extension_is_rejected():
    with pytest.raises(CoverageImportError, match="Unsupported format"):
        inspect_coverage_upload("data:application/octet-stream;base64,AA==", "coverage.csv")


def test_zip_shapefile_path_traversal_is_rejected(monkeypatch):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.shp", b"fake")
    with pytest.raises(CoverageImportError, match="unsafe file path"):
        inspect_coverage_upload(_payload(buffer.getvalue()), "coverage.zip")


def test_geopackage_import_uses_first_polygon_layer_and_reports_other_polygon_layers(tmp_path):
    import geopandas as gpd
    from shapely.geometry import box

    gpkg = tmp_path / "areas.gpkg"
    first = gpd.GeoDataFrame({"name": ["first"]}, geometry=[box(10.0, 56.0, 10.01, 56.01)], crs="EPSG:4326")
    second = gpd.GeoDataFrame({"name": ["second"]}, geometry=[box(10.02, 56.0, 10.03, 56.01)], crs="EPSG:4326")
    first.to_file(gpkg, layer="first_areas", driver="GPKG", engine="pyogrio")
    second.to_file(gpkg, layer="second_areas", driver="GPKG", engine="pyogrio")

    result = inspect_coverage_upload(_payload(gpkg.read_bytes()), "areas.gpkg")

    assert result.source_layer_name == "first_areas"
    assert result.feature_count == 1
    assert any("Other layers were not imported" in warning for warning in result.warnings)


def test_zipped_shapefile_import_requires_and_reads_sidecar_files(tmp_path):
    import zipfile
    import geopandas as gpd
    from shapely.geometry import box

    shp = tmp_path / "regions.shp"
    frame = gpd.GeoDataFrame({"region": ["north"]}, geometry=[box(10.0, 56.0, 10.01, 56.01)], crs="EPSG:4326")
    frame.to_file(shp, driver="ESRI Shapefile", engine="pyogrio")
    archive_path = tmp_path / "regions.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for sidecar in tmp_path.glob("regions.*"):
            if sidecar.suffix.lower() in {".shp", ".shx", ".dbf", ".prj", ".cpg"}:
                archive.write(sidecar, arcname=sidecar.name)

    result = inspect_coverage_upload(_payload(archive_path.read_bytes()), "regions.zip")

    assert result.source_format == "shapefile_zip"
    assert result.feature_count == 1
    assert result.source_layer_name == "regions"


def test_multipolygon_features_are_supported():
    # Two disjoint polygon parts inside one MultiPolygon feature.
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[10.0, 56.0], [10.01, 56.0], [10.01, 56.01], [10.0, 56.01], [10.0, 56.0]]],
            [[[10.02, 56.0], [10.03, 56.0], [10.03, 56.01], [10.02, 56.01], [10.02, 56.0]]],
        ],
    }
    raw = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "islands"}, "geometry": geometry}]}).encode("utf-8")

    result = inspect_coverage_upload(_payload(raw), "islands.geojson")

    assert result.feature_count == 1
    imported_geometry = wkb.loads(bytes.fromhex(result.features[0].geometry_wkb_hex))
    assert imported_geometry.geom_type == "MultiPolygon"
    assert len(imported_geometry.geoms) == 2


def test_shapefile_zip_without_prj_is_rejected(tmp_path):
    import zipfile
    import geopandas as gpd
    from shapely.geometry import box

    shp = tmp_path / "missing_prj.shp"
    frame = gpd.GeoDataFrame({"region": ["north"]}, geometry=[box(10.0, 56.0, 10.01, 56.01)], crs="EPSG:4326")
    frame.to_file(shp, driver="ESRI Shapefile", engine="pyogrio")
    archive_path = tmp_path / "missing_prj.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for sidecar in tmp_path.glob("missing_prj.*"):
            if sidecar.suffix.lower() in {".shp", ".shx", ".dbf"}:
                archive.write(sidecar, arcname=sidecar.name)

    with pytest.raises(CoverageImportError, match=".prj file is required"):
        inspect_coverage_upload(_payload(archive_path.read_bytes()), "missing_prj.zip")
