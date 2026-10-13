from __future__ import annotations

import csv
from io import StringIO

from services.gcp_export import CSV_COLUMNS, build_gcp_csv


def test_csv_has_gcp_attributes_and_joined_layer_names(monkeypatch):
    # Avoid depending on local COG files; availability flags are provided by
    # the service under test below.
    from services import gcp_export

    monkeypatch.setattr(
        gcp_export,
        "annotate_gcp_raster_availability",
        lambda records: [
            {
                **dict(records[0]),
                "reference_raster_available": True,
                "historical_raster_available": False,
                "rasters_available": False,
            }
        ],
    )
    record = {
        "gcp_id": "GCP-0007",
        "student_id": "3",
        "student_username": "dev_student",
        "student_email": "dev_student@gcp.local",
        "reference_layer_id": "2",
        "reference_layer_name": "Orthophoto 2024",
        "reference_layer_source_type": "uploaded",
        "reference": {"x": 500000.0, "y": 6200000.0, "lon": 10.2, "lat": 56.1},
        "historical_layer_id": "8",
        "historical_layer_name": "Historical map 1890",
        "historical_layer_source_type": "uploaded",
        "historical": {"pixel": 123.5, "line": 456.5, "x": 500002.0, "y": 6200001.0, "lon": 10.2001, "lat": 56.1001},
        "crs": "EPSG:25832",
        "offset_m": 2.24,
        "status": "confirmed",
        "recorded_at": "2026-10-13T10:00:00+00:00",
    }

    raw = build_gcp_csv([record])
    assert raw.startswith(b"\xef\xbb\xbf")
    decoded = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(StringIO(decoded)))

    assert len(rows) == 1
    row = rows[0]
    assert tuple(row.keys()) == CSV_COLUMNS
    assert row["student_username"] == "dev_student"
    assert row["reference_layer_name"] == "Orthophoto 2024"
    assert row["historical_layer_name"] == "Historical map 1890"
    assert row["historical_pixel"] == "123.5"
    assert row["reference_raster_available"] == "True"
    assert row["historical_raster_available"] == "False"


def test_empty_export_still_has_headers():
    raw = build_gcp_csv([])
    decoded = raw.decode("utf-8-sig")
    rows = list(csv.reader(StringIO(decoded)))
    assert rows == [list(CSV_COLUMNS)]
