from __future__ import annotations

"""Resolve whether the raster assets referenced by GCP records still exist."""

from collections.abc import Iterable, Mapping
from typing import Any

from maps.raster import get_cached_raster_path


def is_layer_raster_available(
    *,
    layer_type: str,
    source_type: str | None,
    sha256: str | None,
) -> bool:
    """Return whether a layer's display source is currently available.

    Basemaps (currently OpenStreetMap) are remote services and do not need a
    local COG. Uploaded layers are available only while their cached COG file
    exists. This checks availability; it never removes database records.
    """

    if source_type == "basemap":
        return True
    if source_type != "uploaded":
        return False
    return get_cached_raster_path(layer_type, sha256) is not None


def annotate_gcp_raster_availability(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Copy GCP records and add reference/historical raster status flags.

    Expected metadata comes from ``PostgresGCPStore.list_for_student`` or
    ``list_for_admin``. The input records are not mutated.
    """

    annotated: list[dict[str, Any]] = []
    for original in records:
        record = dict(original)
        reference_available = is_layer_raster_available(
            layer_type="reference",
            source_type=record.get("reference_layer_source_type"),
            sha256=record.get("reference_layer_sha256"),
        )
        historical_available = is_layer_raster_available(
            layer_type="historical",
            source_type=record.get("historical_layer_source_type"),
            sha256=record.get("historical_layer_sha256"),
        )
        record["reference_raster_available"] = reference_available
        record["historical_raster_available"] = historical_available
        record["rasters_available"] = (
            reference_available and historical_available
        )
        annotated.append(record)
    return annotated
