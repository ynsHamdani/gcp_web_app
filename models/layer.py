from __future__ import annotations

"""Domain model for uploaded raster-layer metadata.

A layer is identified by its content hash and keeps descriptive/structural
metadata that should survive the temporary raster cache. This module does not
know about Dash or JSON/PostgreSQL.
"""


def build_layer_record(
    *,
    layer_id: str,
    filename: str,
    sha256: str,
    crs: str,
    extent: list[float],
    width: int,
    height: int,
) -> dict:
    """Build a database-ready layer metadata record."""

    if len(extent) != 4:
        raise ValueError("extent must contain [xmin, ymin, xmax, ymax].")

    return {
        "layer_id": str(layer_id),
        "filename": str(filename),
        "sha256": str(sha256),
        "crs": str(crs),
        "extent": [float(value) for value in extent],
        "width": int(width),
        "height": int(height),
    }
