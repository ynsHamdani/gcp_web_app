from __future__ import annotations

from pathlib import Path

from services import layer_availability


def test_basemap_does_not_require_a_local_file(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Basemaps should not be resolved as local COGs")

    monkeypatch.setattr(layer_availability, "get_cached_raster_path", fail_if_called)
    assert layer_availability.is_layer_raster_available(
        layer_type="reference",
        source_type="basemap",
        sha256=None,
    ) is True


def test_uploaded_layer_is_available_only_if_cog_exists(monkeypatch, tmp_path):
    existing = tmp_path / "raster.tif"
    existing.write_bytes(b"test")
    monkeypatch.setattr(
        layer_availability,
        "get_cached_raster_path",
        lambda layer_type, sha256: existing if sha256 == "a" * 64 else None,
    )

    assert layer_availability.is_layer_raster_available(
        layer_type="historical",
        source_type="uploaded",
        sha256="a" * 64,
    ) is True
    assert layer_availability.is_layer_raster_available(
        layer_type="historical",
        source_type="uploaded",
        sha256="b" * 64,
    ) is False


def test_annotate_does_not_mutate_records(monkeypatch):
    monkeypatch.setattr(
        layer_availability,
        "get_cached_raster_path",
        lambda layer_type, sha256: Path("/fake/raster.tif") if sha256 == "h" else None,
    )
    records = [{
        "gcp_id": "GCP-0001",
        "reference_layer_source_type": "uploaded",
        "reference_layer_sha256": "r",
        "historical_layer_source_type": "uploaded",
        "historical_layer_sha256": "h",
    }]

    updated = layer_availability.annotate_gcp_raster_availability(records)

    assert updated[0]["reference_raster_available"] is False
    assert updated[0]["historical_raster_available"] is True
    assert updated[0]["rasters_available"] is False
    assert "rasters_available" not in records[0]
