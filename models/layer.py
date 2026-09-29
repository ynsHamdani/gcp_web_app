from __future__ import annotations

"""Domain model for durable raster-layer metadata."""


def build_layer_record(
    *,
    layer_type: str,
    source_type: str,
    filename: str,
    sha256: str,
    crs: str,
    extent: list[float],
    width: int,
    height: int,
) -> dict:
    """Build a PostgreSQL-ready layer metadata record.

    ``layer_id`` is deliberately not supplied here. PostgreSQL owns the
    relational layer identity; SHA-256 remains the content identity.
    """

    if layer_type not in {"reference", "historical"}:
        raise ValueError("layer_type must be 'reference' or 'historical'.")

    if source_type not in {"uploaded", "basemap"}:
        raise ValueError("source_type must be 'uploaded' or 'basemap'.")

    if len(extent) != 4:
        raise ValueError("extent must contain [xmin, ymin, xmax, ymax].")

    return {
        "layer_id": None,
        "layer_type": layer_type,
        "source_type": source_type,
        "filename": str(filename),
        "sha256": str(sha256),
        "crs": str(crs),
        "extent": [float(value) for value in extent],
        "width": int(width),
        "height": int(height),
    }
