from __future__ import annotations

"""Safe polygon-vector inspection and normalization for coverage imports.

The importer deliberately does not repair geometries. It reports invalid input
and requires the source to be corrected before publication.
"""

import base64
import hashlib
import json
import math
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import MultiPolygon
from shapely.validation import explain_validity

from config import GCP_CRS
from services.runtime_settings import validate_dash_upload_size

TARGET_CRS = GCP_CRS
TARGET_SRID = int(str(GCP_CRS).split(":")[-1])
MAX_FEATURES = 250_000
MAX_ZIP_UNCOMPRESSED_BYTES = 1_000_000_000
MAX_DIAGNOSTIC_ITEMS = 12
ID_FIELD_CANDIDATES = (
    "feature_id", "objectid", "ogc_fid", "fid", "gml_id", "uuid", "gid", "id"
)
LABEL_FIELD_CANDIDATES = ("name", "label", "title", "display_name", "code")


class CoverageImportError(ValueError):
    """A user-correctable import or validation error."""


@dataclass(frozen=True)
class CoverageFeature:
    source_feature_key: str
    feature_label: str
    source_index: int
    attributes: dict[str, Any]
    geometry_wkb_hex: str


@dataclass(frozen=True)
class CoverageImportData:
    filename: str
    source_format: str
    source_layer_name: str
    source_crs: str
    target_srid: int
    geometry_type: str
    feature_count: int
    source_sha256: str
    warnings: tuple[str, ...]
    features: tuple[CoverageFeature, ...]

    def validation_state(self) -> dict[str, Any]:
        return {
            "valid": True,
            "filename": self.filename,
            "source_sha256": self.source_sha256,
            "source_format": self.source_format,
            "source_layer_name": self.source_layer_name,
            "source_crs": self.source_crs,
            "target_srid": self.target_srid,
            "feature_count": self.feature_count,
            "geometry_type": self.geometry_type,
            "warnings": list(self.warnings),
        }


def _safe_filename(filename: str) -> str:
    name = Path(str(filename or "").replace("\\", "/")).name.strip()
    if not name or name in {".", ".."} or "\x00" in name:
        raise CoverageImportError("The uploaded file has no valid filename.")
    if len(name) > 255:
        raise CoverageImportError("The filename is longer than 255 characters.")
    return name


def _decode_upload(contents: str, filename: str) -> bytes:
    if not contents or "," not in contents:
        raise CoverageImportError("Choose a valid file before validating the import.")
    # Enforce the application's configured upload limit before decoding.
    try:
        validate_dash_upload_size(contents, filename)
    except ValueError as exc:
        raise CoverageImportError(str(exc)) from exc
    encoded = contents.split(",", 1)[1].strip()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise CoverageImportError("The uploaded file payload is not valid base64 data.") from exc
    if not raw:
        raise CoverageImportError("The uploaded file is empty.")
    return raw


def _extract_shapefile_zip(raw: bytes, destination: Path) -> Path:
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise CoverageImportError("The uploaded .zip file is not a valid ZIP archive.") from exc

    with archive:
        entries = [item for item in archive.infolist() if not item.is_dir()]
        if not entries:
            raise CoverageImportError("The ZIP archive is empty.")
        total_uncompressed = sum(item.file_size for item in entries)
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise CoverageImportError("The ZIP archive expands beyond the 1 GB safety limit.")

        # Reject absolute paths and traversal entries, even though extraction is
        # restricted to the single selected shapefile's sidecar files.
        for item in entries:
            normalized = item.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
                raise CoverageImportError("The ZIP archive contains an unsafe file path.")

        shp_entries = [item for item in entries if Path(item.filename).suffix.lower() == ".shp"]
        if len(shp_entries) != 1:
            raise CoverageImportError(
                "A zipped Shapefile must contain exactly one .shp file. "
                "Create one ZIP per Shapefile."
            )

        shp_info = shp_entries[0]
        shp_path = PurePosixPath(shp_info.filename.replace("\\", "/"))
        stem = shp_path.stem.casefold()
        parent = tuple(part.casefold() for part in shp_path.parent.parts)
        related: dict[str, zipfile.ZipInfo] = {}
        for item in entries:
            item_path = PurePosixPath(item.filename.replace("\\", "/"))
            if tuple(part.casefold() for part in item_path.parent.parts) != parent:
                continue
            if item_path.stem.casefold() == stem:
                related[item_path.suffix.lower()] = item

        required = {".shp", ".shx", ".dbf", ".prj"}
        missing = sorted(required - set(related))
        if missing:
            raise CoverageImportError(
                "The zipped Shapefile is missing required component(s): " + ", ".join(missing)
                + ". A .prj file is required; the importer will not guess the CRS."
            )

        for suffix, item in related.items():
            if suffix not in required | {".cpg", ".qix", ".sbn", ".sbx"}:
                continue
            target = destination / f"{shp_path.stem}{suffix}"
            # Stream ZIP members to disk; do not allocate a second full copy
            # of a potentially large Shapefile component in memory.
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
        return destination / f"{shp_path.stem}.shp"


def _read_vector_file(path: Path, source_format: str) -> tuple[gpd.GeoDataFrame, str, str | None]:
    if source_format == "gpkg":
        try:
            available = pyogrio.list_layers(path)
        except Exception as exc:
            raise CoverageImportError(f"Could not inspect GeoPackage layers: {exc}") from exc
        if len(available) == 0:
            raise CoverageImportError("The GeoPackage contains no vector layers.")
        # Select the first polygon or multipolygon layer, not an unrelated
        # point/line layer that may happen to be stored first.
        polygon_candidates = []
        for layer_name, geometry_type in available:
            gtype = str(geometry_type or "").casefold()
            if "polygon" in gtype:
                polygon_candidates.append(str(layer_name))
        if not polygon_candidates:
            layer_summary = ", ".join(f"{name} ({kind})" for name, kind in available[:8])
            raise CoverageImportError(
                "The GeoPackage has no Polygon or MultiPolygon layer. Available: " + layer_summary
            )
        selected = polygon_candidates[0]
        try:
            frame = gpd.read_file(path, layer=selected, engine="pyogrio")
        except Exception as exc:
            raise CoverageImportError(f"Could not read GeoPackage layer '{selected}': {exc}") from exc
        warning = None
        if len(available) > 1:
            warning = (
                f"GeoPackage layer '{selected}' was selected. Other layers "
                "were not imported; import each desired polygon layer separately."
            )
        return frame, selected, warning

    if source_format == "shapefile_zip":
        try:
            return gpd.read_file(path, engine="pyogrio"), path.stem, None
        except Exception as exc:
            raise CoverageImportError(f"Could not read the zipped Shapefile: {exc}") from exc

    try:
        return gpd.read_file(path, engine="pyogrio"), path.stem, None
    except Exception as exc:
        raise CoverageImportError(f"Could not read the GeoJSON file: {exc}") from exc


def _first_field(columns, candidates) -> str | None:
    by_folded_name = {str(column).casefold(): str(column) for column in columns}
    for candidate in candidates:
        if candidate in by_folded_name:
            return by_folded_name[candidate]
    return None


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        missing = pd.isna(value)
        # pandas/numpy scalar booleans do not always share Python's bool type.
        if not hasattr(missing, "__len__") and bool(missing):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    if isinstance(value, (list, tuple)):
        return [_json_scalar(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_scalar(item) for key, item in value.items()}
    return str(value)


def inspect_coverage_upload(contents: str, filename: str) -> CoverageImportData:
    """Decode, inspect, validate and normalize one supported polygon dataset.

    Supported inputs: GeoPackage (.gpkg), GeoJSON (.geojson/.json), or one
    Shapefile packaged as .zip. Geometries are normalized to the application's
    EPSG:25832 working CRS. No geometry repair or feature dropping is performed.
    """
    safe_name = _safe_filename(filename)
    suffix = Path(safe_name).suffix.casefold()
    formats = {
        ".gpkg": "gpkg",
        ".geojson": "geojson",
        ".json": "geojson",
        ".zip": "shapefile_zip",
    }
    if suffix not in formats:
        raise CoverageImportError(
            "Unsupported format. Upload a GeoPackage (.gpkg), GeoJSON (.geojson/.json), "
            "or a zipped Shapefile (.zip)."
        )
    source_format = formats[suffix]
    raw = _decode_upload(contents, safe_name)
    digest = hashlib.sha256(raw).hexdigest()

    with tempfile.TemporaryDirectory(prefix="gcp_coverage_import_") as tmp:
        root = Path(tmp)
        if source_format == "shapefile_zip":
            vector_path = _extract_shapefile_zip(raw, root)
        else:
            vector_path = root / safe_name
            vector_path.write_bytes(raw)

        frame, source_layer_name, read_warning = _read_vector_file(vector_path, source_format)

    if frame is None or frame.empty:
        raise CoverageImportError("The selected vector layer contains no features.")
    if len(frame) > MAX_FEATURES:
        raise CoverageImportError(
            f"The selected layer has {len(frame):,} features; the current import limit is {MAX_FEATURES:,}."
        )
    if frame.crs is None and source_format == "geojson":
        # RFC 7946 GeoJSON coordinates use the WGS84 longitude/latitude
        # convention; this is a format-defined CRS, not a coordinate guess.
        frame = frame.set_crs("EPSG:4326", allow_override=True)
    if frame.crs is None:
        raise CoverageImportError(
            "The source layer has no CRS metadata. Add a correct CRS to the source file and retry; "
            "the importer will not infer one from projected coordinates."
        )

    source_crs = frame.crs.to_string()
    if not source_crs:
        raise CoverageImportError("The source CRS could not be identified.")
    if not source_layer_name or len(source_layer_name) > 255 or "\x00" in source_layer_name:
        raise CoverageImportError("The selected source layer name is empty, too long, or invalid.")

    geometry_name = frame.geometry.name
    invalid_messages: list[str] = []
    for index, geometry in enumerate(frame.geometry, start=1):
        if geometry is None:
            invalid_messages.append(f"Feature row {index}: missing geometry")
        elif geometry.is_empty:
            invalid_messages.append(f"Feature row {index}: empty geometry")
        elif geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            invalid_messages.append(f"Feature row {index}: {geometry.geom_type} is not Polygon/MultiPolygon")
        elif getattr(geometry, "has_z", False) or getattr(geometry, "has_m", False):
            invalid_messages.append(f"Feature row {index}: 3D/measured coordinates are not supported; export 2D polygons")
        elif not geometry.is_valid:
            invalid_messages.append(f"Feature row {index}: {explain_validity(geometry)}")
        if len(invalid_messages) >= MAX_DIAGNOSTIC_ITEMS:
            break
    if invalid_messages:
        raise CoverageImportError(
            "The layer failed polygon validation. No geometries were repaired or discarded. "
            + "; ".join(invalid_messages)
        )

    id_field = _first_field(frame.columns, ID_FIELD_CANDIDATES)
    warnings: list[str] = [read_warning] if read_warning else []
    use_source_id = False
    if id_field:
        ids = [_json_scalar(value) for value in frame[id_field].tolist()]
        id_strings = [
            None if value is None or (isinstance(value, str) and not value.strip()) else str(value)
            for value in ids
        ]
        if all(value is not None for value in id_strings) and len(set(id_strings)) == len(id_strings):
            if all(len(value) <= 500 for value in id_strings):
                use_source_id = True
            else:
                warnings.append(
                    f"'{id_field}' contains values longer than 500 characters; "
                    "unique row-based feature keys were generated instead."
                )
        else:
            warnings.append(
                f"'{id_field}' is not a unique, non-null identifier. It is preserved as an attribute; "
                "the importer generated unique row-based feature keys instead."
            )

    label_field = _first_field(frame.columns, LABEL_FIELD_CANDIDATES)
    try:
        normalized = frame.to_crs(TARGET_CRS)
    except Exception as exc:
        raise CoverageImportError(
            f"Could not transform source CRS {source_crs} to {TARGET_CRS}: {exc}"
        ) from exc

    features: list[CoverageFeature] = []
    attribute_columns = [str(column) for column in normalized.columns if column != geometry_name]
    for row_number, (_, row) in enumerate(normalized.iterrows(), start=1):
        geometry = row[geometry_name]
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            reason = "missing/empty geometry" if geometry is None or geometry.is_empty else explain_validity(geometry)
            raise CoverageImportError(f"Feature row {row_number} became invalid after CRS transformation: {reason}")
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise CoverageImportError(
                f"Feature row {row_number} changed to unsupported geometry type {geometry.geom_type} after transformation."
            )
        if getattr(geometry, "has_z", False) or getattr(geometry, "has_m", False):
            raise CoverageImportError(f"Feature row {row_number} contains 3D/measured coordinates; export 2D polygons.")
        bounds = geometry.bounds
        if not all(math.isfinite(float(value)) for value in bounds):
            raise CoverageImportError(f"Feature row {row_number} has non-finite transformed coordinates.")

        source_key = (
            str(_json_scalar(row[id_field]))
            if use_source_id and id_field
            else f"row:{row_number}"
        )
        if "\x00" in source_key:
            source_key = f"row:{row_number}"
            if not any("null byte" in warning for warning in warnings):
                warnings.append("A source identifier contained a null byte; row-based feature keys were generated.")
        label_value = _json_scalar(row[label_field]) if label_field else None
        label = str(label_value).strip() if label_value not in (None, "") else source_key
        if "\x00" in label:
            raise CoverageImportError(f"Feature row {row_number} has a label containing a null byte.")
        attributes = {
            column: _json_scalar(row[column])
            for column in attribute_columns
        }
        if any("\x00" in str(key) or (isinstance(value, str) and "\x00" in value) for key, value in attributes.items()):
            raise CoverageImportError(f"Feature row {row_number} contains an attribute with a null byte.")
        # Ensure attributes are JSON-compatible before anything reaches the DB.
        try:
            json.dumps(attributes, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise CoverageImportError(f"Feature row {row_number} contains an unsupported attribute value: {exc}") from exc
        features.append(CoverageFeature(
            source_feature_key=source_key,
            feature_label=label[:500],
            source_index=row_number,
            attributes=attributes,
            geometry_wkb_hex=geometry.wkb_hex,
        ))

    return CoverageImportData(
        filename=safe_name,
        source_format=source_format,
        source_layer_name=source_layer_name,
        source_crs=source_crs,
        target_srid=TARGET_SRID,
        geometry_type="MULTIPOLYGON",
        feature_count=len(features),
        source_sha256=digest,
        warnings=tuple(warnings),
        features=tuple(features),
    )
