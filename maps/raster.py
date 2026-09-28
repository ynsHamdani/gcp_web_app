from __future__ import annotations

"""Raster utilities used by the GCP web application.

The module keeps the existing TIFF -> COG -> TiTiler workflow, but changes
student uploads to a temporary, content-addressed cache:

    upload -> SHA-256 -> temporary cache -> COG -> TiTiler

Only one COG is kept for identical files, regardless of how many students
upload the same raster.  Temporary files are removed automatically according
to TEMP_RASTER_TTL_HOURS (cleanup is performed opportunistically whenever the
application touches the temporary-raster subsystem).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import base64
import hashlib
import math
import os
import re
import shutil
import time
import uuid
from urllib.parse import quote

import requests
import rasterio
from pyproj import Transformer
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from config import (
    APP_BASE_URL,
    TITILER_URL,
    TEMP_RASTER_DIR,
    TEMP_RASTER_STAGING_DIR,
    TEMP_RASTER_TTL_HOURS,
)


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class RasterAsset:
    """Description of a raster that can be displayed by TiTiler."""

    name: str
    original_path: Path
    cog_path: Path
    tile_url: str
    bounds: list[list[float]]
    minzoom: int
    maxzoom: int

    @property
    def center(self) -> list[float]:
        """Return the center of the raster bounds as [lat, lon]."""

        # TiTiler/GeoJSON-style bounds are expected as:
        # [[south, west], [north, east]]
        south, west = self.bounds[0]
        north, east = self.bounds[1]
        return [
            (south + north) / 2.0,
            (west + east) / 2.0,
        ]


# =========================================================
# GENERAL HELPERS
# =========================================================

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(filename: str) -> str:
    """Create a filesystem-safe filename while preserving its extension."""

    name = Path(filename).name
    name = _SAFE_FILENAME.sub("_", name).strip("._")

    if not name:
        name = "upload.tif"

    suffix = Path(name).suffix.lower()
    if suffix not in {".tif", ".tiff"}:
        name += ".tif"

    return name


def _decode_upload(contents: str) -> bytes:
    """Decode Dash dcc.Upload contents into raw file bytes."""

    if not contents or "," not in contents:
        raise ValueError("Invalid upload data.")

    _, encoded = contents.split(",", 1)

    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("The uploaded file could not be decoded.") from exc


def _hash_bytes(data: bytes) -> str:
    """Return the SHA-256 digest of uploaded bytes."""

    return hashlib.sha256(data).hexdigest()


def _cache_root(raster_kind: str) -> Path:
    """Return the temporary cache root for reference or historical rasters."""

    if raster_kind not in {"reference", "historical"}:
        raise ValueError("raster_kind must be 'reference' or 'historical'.")

    root = TEMP_RASTER_DIR / raster_kind
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_dir(raster_kind: str, sha256: str) -> Path:
    """Return the content-addressed cache directory for one raster."""

    return _cache_root(raster_kind) / sha256


def _cog_path(raster_kind: str, sha256: str) -> Path:
    """Return the deterministic COG path for one uploaded raster."""

    return _cache_dir(raster_kind, sha256) / f"{sha256}.tif"


def _touch_path(path: Path) -> None:
    """Update a file/directory access timestamp for TTL-based cleanup."""

    try:
        now = time.time()
        os.utime(path, (now, now))
    except FileNotFoundError:
        pass


def _safe_remove(path: Path) -> None:
    """Remove a file or directory without raising if it disappeared already."""

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except FileNotFoundError:
        pass


# =========================================================
# TEMPORARY STORAGE / CLEANUP
# =========================================================


def cleanup_expired_temp_rasters(
    ttl_hours: float | None = None,
) -> int:
    """Delete temporary raster cache entries older than the configured TTL.

    Cleanup is intentionally filesystem-based and does not require a daemon,
    scheduler, Redis, or another service.  It is called opportunistically when
    the raster subsystem is used.

    Returns
    -------
    int
        Number of expired cache directories removed.
    """

    ttl = (
        TEMP_RASTER_TTL_HOURS
        if ttl_hours is None
        else float(ttl_hours)
    )

    if ttl <= 0:
        raise ValueError("Temporary raster TTL must be greater than zero.")

    if not TEMP_RASTER_DIR.exists():
        return 0

    cutoff = time.time() - (ttl * 3600.0)
    removed = 0

    # The staging directory contains short-lived raw upload files.
    if TEMP_RASTER_STAGING_DIR.exists():
        for item in TEMP_RASTER_STAGING_DIR.iterdir():
            try:
                if item.stat().st_mtime < cutoff:
                    _safe_remove(item)
                    removed += 1
            except FileNotFoundError:
                continue

    # Cache layout:
    # temp_rasters/
    #   reference/<sha256>/<sha256>.tif
    #   historical/<sha256>/<sha256>.tif
    for kind in ("reference", "historical"):
        root = TEMP_RASTER_DIR / kind
        if not root.exists():
            continue

        for cache_dir in root.iterdir():
            if not cache_dir.is_dir():
                continue

            try:
                if cache_dir.stat().st_mtime < cutoff:
                    _safe_remove(cache_dir)
                    removed += 1
            except FileNotFoundError:
                continue

    return removed


def _write_staging_file(data: bytes, filename: str) -> Path:
    """Write raw uploaded bytes to a short-lived staging file."""

    TEMP_RASTER_STAGING_DIR.mkdir(parents=True, exist_ok=True)

    staging_name = (
        f"{uuid.uuid4().hex}_{_safe_filename(filename)}"
    )
    staging_path = TEMP_RASTER_STAGING_DIR / staging_name

    staging_path.write_bytes(data)
    return staging_path


# =========================================================
# LEGACY-COMPATIBLE UPLOAD HELPER
# =========================================================


def save_uploaded_tiff(
    contents: str,
    filename: str,
    output_dir: Path,
) -> Path:
    """Save an uploaded TIFF to a supplied directory.

    This function is retained for compatibility with older code.  The new
    student-upload path uses ``prepare_uploaded_raster`` instead, so raw
    uploads are only staged temporarily and are never kept permanently.
    """

    if not contents or not filename:
        raise ValueError("No raster file was provided.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = _decode_upload(contents)
    output_path = output_dir / (
        f"{uuid.uuid4().hex}_{_safe_filename(filename)}"
    )
    output_path.write_bytes(data)
    return output_path


# =========================================================
# GEO-TIFF VALIDATION
# =========================================================


def validate_geotiff(path: Path) -> None:
    """Validate that a file is a readable georeferenced raster."""

    path = Path(path)

    if not path.exists():
        raise ValueError(f"Raster file does not exist: {path}")

    try:
        with rasterio.open(path) as src:
            if src.width <= 0 or src.height <= 0:
                raise ValueError("Raster has invalid dimensions.")

            if src.count < 1:
                raise ValueError("Raster contains no bands.")

            if src.crs is None:
                raise ValueError(
                    "GeoTIFF has no CRS. Please upload a georeferenced raster."
                )

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"The uploaded file is not a valid readable GeoTIFF: {exc}"
        ) from exc


# =========================================================
# HISTORICAL RASTER: GEOGRAPHIC POSITION -> PIXEL/LINE
# =========================================================


def geographic_to_pixel_line(
    cog_path: str | Path,
    lon: float,
    lat: float,
) -> dict[str, float]:
    """Convert WGS84 longitude/latitude to continuous raster pixel/line.

    The historical raster's own CRS and affine transform are used.  Fractional
    pixel/line values are preserved because GDAL GCPs support continuous
    raster coordinates.  A ValueError is raised when the position is outside
    the raster footprint.
    """

    cog_path = Path(cog_path)

    if not cog_path.exists() or not cog_path.is_file():
        raise ValueError(
            "The selected historical raster is no longer available."
        )

    with rasterio.open(cog_path) as src:
        if src.crs is None:
            raise ValueError("The historical raster has no CRS.")

        to_raster = Transformer.from_crs(
            "EPSG:4326",
            src.crs,
            always_xy=True,
        )
        raster_x, raster_y = to_raster.transform(
            float(lon),
            float(lat),
        )

        # Invert the affine transform to obtain continuous (column, row)
        # coordinates in the historical image.
        pixel, line = (~src.transform) * (raster_x, raster_y)

        if not (
            0.0 <= float(pixel) < float(src.width)
            and 0.0 <= float(line) < float(src.height)
        ):
            raise ValueError(
                "The historical point is outside the uploaded historical raster."
            )

    return {
        "pixel": float(pixel),
        "line": float(line),
    }


# =========================================================
# COG CONVERSION
# =========================================================


def convert_to_cog(
    input_path: Path,
    output_path: Path,
) -> Path:
    """Convert a GeoTIFF into a Cloud Optimized GeoTIFF."""

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        output_path.unlink()

    # DEFATE keeps the raster compact and works well for the mostly
    # discrete/uint8 historical-map data used by this application.
    profile = cog_profiles.get("deflate")

    cog_translate(
        str(input_path),
        str(output_path),
        profile,
        in_memory=False,
        quiet=True,
    )

    return output_path


# =========================================================
# TITILER
# =========================================================


def get_titiler_asset(
    raster_url: str,
    titiler_url: str,
    cog_path: Path | None = None,
) -> tuple[str, list[list[float]], int, int]:
    """Request TiTiler metadata and build a usable tile URL.

    The local COG path is used to derive reliable WGS84 bounds for Leaflet.
    TiTiler itself receives the HTTP raster URL for tile metadata and tiles.
    """

    base_url = titiler_url.rstrip("/")

    # -----------------------------------------------------
    # 1. Fetch COG metadata from TiTiler.
    # -----------------------------------------------------

    info_url = f"{base_url}/cog/info"
    response = requests.get(
        info_url,
        params={"url": raster_url},
        timeout=30,
    )
    response.raise_for_status()
    info = response.json()

    # TiTiler's /cog/info endpoint returns bounds in the dataset CRS.
    # Those coordinates are NOT necessarily longitude/latitude (for example,
    # EPSG:25832 uses metres).  Leaflet, however, needs WGS84 coordinates for
    # the map center, and calculate_fit_zoom() expects degrees.
    #
    # Therefore, derive the geographic bounds directly from the COG and only
    # use TiTiler for the service metadata needed by the tile layer.
    if cog_path is not None:
        with rasterio.open(cog_path) as src:
            if src.crs is None:
                raise ValueError(
                    "The raster has no CRS; geographic bounds cannot be calculated."
                )

            west, south, east, north = transform_bounds(
                src.crs,
                "EPSG:4326",
                *src.bounds,
                densify_pts=21,
            )
    else:
        # Compatibility fallback for callers that do not provide cog_path.
        bounds_raw = info.get("bounds")
        if not bounds_raw or len(bounds_raw) != 4:
            raise ValueError("TiTiler did not return valid raster bounds.")

        info_crs = str(info.get("crs", "")).upper()
        if "4326" not in info_crs and "CRS84" not in info_crs:
            raise ValueError(
                "Geographic bounds require the COG path or a WGS84 TiTiler response."
            )

        west, south, east, north = map(float, bounds_raw)

    bounds = [
        [float(south), float(west)],
        [float(north), float(east)],
    ]

    # -----------------------------------------------------
    # 2. Determine zoom limits.
    # -----------------------------------------------------

    minzoom = int(info.get("minzoom", 0))
    maxzoom = int(info.get("maxzoom", 24))

    # -----------------------------------------------------
    # 3. TileJSON endpoint.
    # -----------------------------------------------------
    # The map already uses the TiTiler COG tile endpoint.  Keeping the URL
    # construction here avoids hard-coding a generated tile URL into the UI.
    # -----------------------------------------------------

    tile_url = (
        f"{base_url}/cog/tiles/WebMercatorQuad/"
        f"{{z}}/{{x}}/{{y}}.png"
        f"?url={quote(raster_url, safe='')}"
        f"&return_mask=true"
    )

    return tile_url, bounds, minzoom, maxzoom


# =========================================================
# MAP ZOOM CALCULATION
# =========================================================


def calculate_fit_zoom(
    bounds: list[list[float]],
    map_width_px: int = 800,
    map_height_px: int = 500,
) -> int:
    """Estimate a useful Leaflet zoom level for a raster extent."""

    if not bounds or len(bounds) != 2:
        return 7

    south, west = bounds[0]
    north, east = bounds[1]

    lat_span = max(abs(float(north) - float(south)), 1e-9)
    lon_span = max(abs(float(east) - float(west)), 1e-9)

    # Web-Mercator approximation: world width at zoom z is 256 * 2**z.
    lon_zoom = math.log2((360.0 * map_width_px) / (256.0 * lon_span))
    lat_zoom = math.log2((170.1023 * map_height_px) / (256.0 * lat_span))

    zoom = int(math.floor(min(lon_zoom, lat_zoom)))
    return max(0, min(24, zoom))


# =========================================================
# NEW DEDUPLICATED UPLOAD PIPELINE
# =========================================================


def prepare_uploaded_raster(
    contents: str,
    filename: str,
    raster_kind: str,
) -> RasterAsset:
    """Prepare an uploaded raster using temporary storage and SHA-256 dedup.

    Workflow
    --------
    1. Decode the Dash upload.
    2. Compute SHA-256 from the exact uploaded bytes.
    3. Check the temporary cache for that hash.
    4. On a cache hit, reuse the existing COG.
    5. On a cache miss, stage the raw TIFF briefly, validate it, convert it
       to one hash-named COG, then remove the raw staged TIFF.
    6. Build the TiTiler tile URL and return the RasterAsset.

    The raw student upload is therefore never retained as a permanent copy.
    Identical files uploaded by different students share one temporary COG.
    """

    if not contents or not filename:
        raise ValueError("No raster file was provided.")

    if raster_kind not in {"reference", "historical"}:
        raise ValueError(
            "raster_kind must be 'reference' or 'historical'."
        )

    # Cleanup old temporary data before doing new work.
    cleanup_expired_temp_rasters()

    data = _decode_upload(contents)
    if not data:
        raise ValueError("The uploaded file is empty.")

    sha256 = _hash_bytes(data)
    cache_dir = _cache_dir(raster_kind, sha256)
    cog_path = _cog_path(raster_kind, sha256)

    # -----------------------------------------------------
    # CACHE HIT
    # -----------------------------------------------------

    if cog_path.exists():
        # Touch the cache entry so an actively reused raster survives TTL
        # cleanup.  No new TIFF is written and no COG conversion is repeated.
        _touch_path(cache_dir)
    else:
        # -------------------------------------------------
        # CACHE MISS
        # -------------------------------------------------

        staging_path = _write_staging_file(data, filename)
        temp_build_dir = cache_dir.with_name(
            f".{sha256}.building"
        )

        try:
            validate_geotiff(staging_path)

            # Try to claim the build directory atomically.  This prevents two
            # concurrent students uploading the same file from converting the
            # same COG simultaneously.
            try:
                temp_build_dir.mkdir(
                    parents=True,
                    exist_ok=False,
                )
                is_builder = True
            except FileExistsError:
                is_builder = False

            if is_builder:
                try:
                    build_cog = temp_build_dir / f"{sha256}.tif"
                    convert_to_cog(
                        staging_path,
                        build_cog,
                    )

                    # Publish only after conversion completed successfully.
                    cache_dir.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    try:
                        temp_build_dir.rename(cache_dir)
                    except FileExistsError:
                        # Another process may have published the cache while
                        # this process was converting.  The published copy is
                        # the one we keep.
                        _safe_remove(temp_build_dir)

                except Exception:
                    _safe_remove(temp_build_dir)
                    raise

            else:
                # Another worker is building the exact same content.  Wait a
                # short, bounded period for the published COG to appear.
                deadline = time.time() + 120.0
                while time.time() < deadline:
                    if cog_path.exists():
                        break
                    if not temp_build_dir.exists():
                        # Builder exited without publishing.  Take over.
                        temp_build_dir.mkdir(
                            parents=True,
                            exist_ok=False,
                        )
                        build_cog = temp_build_dir / f"{sha256}.tif"
                        convert_to_cog(
                            staging_path,
                            build_cog,
                        )
                        temp_build_dir.rename(cache_dir)
                        break
                    time.sleep(0.25)

                if not cog_path.exists():
                    raise RuntimeError(
                        "Timed out while waiting for another upload to finish "
                        "building the shared raster cache."
                    )

        finally:
            # Raw input is always temporary.  It is deleted even when COG
            # conversion or validation fails.
            _safe_remove(staging_path)

    # -----------------------------------------------------
    # BUILD TI TILER ASSET
    # -----------------------------------------------------

    relative_cog = cog_path.relative_to(TEMP_RASTER_DIR).as_posix()
    raster_url = (
        f"{APP_BASE_URL.rstrip('/')}/raster/{quote(relative_cog, safe='/')}"
    )

    tile_url, bounds, minzoom, maxzoom = get_titiler_asset(
        raster_url,
        TITILER_URL,
        cog_path,
    )

    _touch_path(cache_dir)

    # ``original_path`` is intentionally empty: the raw source TIFF is not
    # retained after COG creation.  The COG is the temporary canonical copy.
    return RasterAsset(
        name=filename,
        original_path=Path(""),
        cog_path=cog_path,
        tile_url=tile_url,
        bounds=bounds,
        minzoom=minzoom,
        maxzoom=maxzoom,
    )


# =========================================================
# ROUTE HELPER
# =========================================================


def touch_cached_raster_from_relative_path(relative_path: str) -> None:
    """Touch a cached COG when it is requested by the Flask route."""

    path = (TEMP_RASTER_DIR / relative_path).resolve()
    root = TEMP_RASTER_DIR.resolve()

    # Prevent path traversal outside the temporary-raster root.
    if root not in path.parents and path != root:
        raise ValueError("Invalid temporary raster path.")

    if path.exists():
        _touch_path(path.parent)


def get_temp_raster_path(relative_path: str) -> Path:
    """Resolve a relative temporary raster path safely."""

    path = (TEMP_RASTER_DIR / relative_path).resolve()
    root = TEMP_RASTER_DIR.resolve()

    if root not in path.parents and path != root:
        raise ValueError("Invalid temporary raster path.")

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(relative_path)

    return path
