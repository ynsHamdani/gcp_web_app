from __future__ import annotations

"""Reusable CSV export for GCP records returned by the data store."""

import csv
from collections.abc import Iterable, Mapping
from io import StringIO
from typing import Any

from services.layer_availability import annotate_gcp_raster_availability

CSV_COLUMNS = (
    "gcp_id",
    "student_id",
    "student_username",
    "student_email",
    "reference_layer_id",
    "reference_layer_name",
    "reference_layer_source_type",
    "reference_x",
    "reference_y",
    "reference_lon",
    "reference_lat",
    "reference_raster_available",
    "historical_layer_id",
    "historical_layer_name",
    "historical_layer_source_type",
    "historical_pixel",
    "historical_line",
    "historical_x",
    "historical_y",
    "historical_lon",
    "historical_lat",
    "historical_raster_available",
    "rasters_available",
    "crs",
    "offset_m",
    "status",
    "recorded_at",
)


def _number(value: Any) -> Any:
    """Keep numeric values intact and convert missing nested attributes to blank."""
    return "" if value is None else value


def _flatten(record: Mapping[str, Any]) -> dict[str, Any]:
    reference = record.get("reference") or {}
    historical = record.get("historical") or {}
    return {
        "gcp_id": record.get("gcp_id", ""),
        "student_id": record.get("student_id", ""),
        "student_username": record.get("student_username", ""),
        "student_email": record.get("student_email", ""),
        "reference_layer_id": record.get("reference_layer_id", ""),
        "reference_layer_name": record.get("reference_layer_name", ""),
        "reference_layer_source_type": record.get("reference_layer_source_type", ""),
        "reference_x": _number(reference.get("x")),
        "reference_y": _number(reference.get("y")),
        "reference_lon": _number(reference.get("lon")),
        "reference_lat": _number(reference.get("lat")),
        "reference_raster_available": record.get("reference_raster_available", False),
        "historical_layer_id": record.get("historical_layer_id", ""),
        "historical_layer_name": record.get("historical_layer_name", ""),
        "historical_layer_source_type": record.get("historical_layer_source_type", ""),
        "historical_pixel": _number(historical.get("pixel")),
        "historical_line": _number(historical.get("line")),
        "historical_x": _number(historical.get("x")),
        "historical_y": _number(historical.get("y")),
        "historical_lon": _number(historical.get("lon")),
        "historical_lat": _number(historical.get("lat")),
        "historical_raster_available": record.get("historical_raster_available", False),
        "rasters_available": record.get("rasters_available", False),
        "crs": record.get("crs", ""),
        "offset_m": _number(record.get("offset_m")),
        "status": record.get("status", ""),
        "recorded_at": record.get("recorded_at", ""),
    }


def build_gcp_csv(records: Iterable[Mapping[str, Any]]) -> bytes:
    """Return a UTF-8-with-BOM CSV containing GCP and layer metadata.

    Records should be fetched with ``list_for_student`` or
    ``list_for_admin`` so student and layer names are provided by PostgreSQL
    joins. This function does not authorize requests; callers must choose the
    appropriately scoped query before exporting.
    """

    annotated = annotate_gcp_raster_availability(records)
    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=CSV_COLUMNS,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for record in annotated:
        writer.writerow(_flatten(record))
    # Excel on Windows reliably recognizes UTF-8 CSVs with this BOM.
    return stream.getvalue().encode("utf-8-sig")
