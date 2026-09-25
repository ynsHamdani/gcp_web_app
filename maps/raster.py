from __future__ import annotations

import base64
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import rasterio
import requests
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

@dataclass
class RasterAsset:
    name: str
    original_path: Path
    cog_path: Path
    tile_url: str
    bounds: list[float]
    minzoom: int
    maxzoom: int

    @property
    def center(self) -> list[float]:
        west, south, east, north = self.bounds

        return [
            (south + north) / 2,
            (west + east) / 2,
        ]

    @property
    def initial_zoom(self) -> int:
        """
        Estimate a useful initial Leaflet zoom level from
        the raster extent. This avoids opening the sheet
        at a very broad Denmark-wide zoom.
        """
        west, south, east, north = self.bounds

        lon_span = max(abs(east - west), 1e-9)
        lat_span = max(abs(north - south), 1e-9)

        # Approximate zoom for a ~700 px wide map.
        zoom_lon = math.log2(
            700 * 360 / (256 * lon_span)
        )

        zoom_lat = math.log2(
            500 * 180 / (256 * lat_span)
        )

        zoom = int(
            max(
                1,
                min(
                    zoom_lon,
                    zoom_lat,
                ),
            )
        )

        return max(
            1,
            min(zoom, self.maxzoom),
        )


def save_uploaded_tiff(
    contents: str,
    filename: str,
    original_dir: Path,
) -> Path:

    if not filename:
        raise ValueError(
            "No filename supplied."
        )

    if Path(filename).suffix.lower() not in {
        ".tif",
        ".tiff",
    }:
        raise ValueError(
            "Only TIFF files are supported."
        )

    safe_name = Path(filename).name
    stem = Path(safe_name).stem
    unique_id = uuid.uuid4().hex[:8]

    output_path = (
        original_dir
        / f"{stem}_{unique_id}.tif"
    )

    try:
        _, encoded = contents.split(",", 1)
        data = base64.b64decode(encoded)
    except Exception as exc:
        raise ValueError(
            "Could not decode uploaded TIFF."
        ) from exc

    output_path.write_bytes(data)

    return output_path


def validate_geotiff(path: Path) -> None:

    try:
        with rasterio.open(path) as src:

            if src.crs is None:
                raise ValueError(
                    "The TIFF is not georeferenced."
                )

            if src.count < 1:
                raise ValueError(
                    "The TIFF contains no raster bands."
                )

            if src.width <= 0 or src.height <= 0:
                raise ValueError(
                    "Invalid raster dimensions."
                )

    except rasterio.errors.RasterioIOError as exc:
        raise ValueError(
            "The uploaded file is not a valid GeoTIFF."
        ) from exc


def convert_to_cog(
    input_path: Path,
    output_path: Path,
) -> None:

    profile = dict(
        cog_profiles.get("deflate")
    )

    profile.update(
        {
            "BIGTIFF": "IF_SAFER",
        }
    )

    config = {
        "GDAL_NUM_THREADS": "ALL_CPUS",
        "GDAL_TIFF_INTERNAL_MASK": True,
        "GDAL_TIFF_OVR_BLOCKSIZE": "128",
    }

    cog_translate(
        str(input_path),
        str(output_path),
        profile,
        config=config,
        in_memory=False,
        quiet=True,
    )


def get_titiler_asset(
    raster_url: str,
    titiler_url: str,
    cog_path: Path,
) -> tuple[str, list[float], int, int]:

    # -----------------------------------------------------
    # Get raster metadata from TiTiler
    # -----------------------------------------------------

    info_endpoint = (
        f"{titiler_url.rstrip('/')}"
        "/cog/info"
    )

    response = requests.get(
        info_endpoint,
        params={
            "url": raster_url,
        },
        timeout=60,
    )

    response.raise_for_status()

    info = response.json()

    # -----------------------------------------------------
    # Get exact geographic bounds from the COG
    # -----------------------------------------------------

    with rasterio.open(cog_path) as src:

        if src.crs is None:
            raise RuntimeError(
                "COG has no CRS."
            )

        bounds = transform_bounds(
            src.crs,
            "EPSG:4326",
            *src.bounds,
        )

        # Estimate native maximum zoom from pixel size.
        center_lat = (
            bounds[1] + bounds[3]
        ) / 2

        pixel_size = max(
            abs(src.transform.a),
            abs(src.transform.e),
        )

    # -----------------------------------------------------
    # Estimate maximum useful zoom
    # -----------------------------------------------------

    # Approximate Web Mercator resolution at equator.
    world_resolution = (
        156543.03392804097
        * math.cos(math.radians(center_lat))
    )

    if pixel_size > 0:
        estimated_maxzoom = int(
            math.floor(
                math.log2(
                    world_resolution
                    / pixel_size
                )
            )
        )
    else:
        estimated_maxzoom = 18

    maxzoom = max(
        1,
        min(
            estimated_maxzoom,
            24,
        ),
    )

    minzoom = 0

    # -----------------------------------------------------
    # Build the tile URL explicitly
    # -----------------------------------------------------
    #
    # Important:
    # - 256x256 tiles
    # - band 1
    # - PNG
    # - explicit 0-255 rescaling
    # - no alpha mask hiding the image
    #

    encoded_url = quote(
        raster_url,
        safe="",
    )

    tile_url = (
        f"{titiler_url.rstrip('/')}"
        "/cog/tiles/WebMercatorQuad/"
        "{z}/{x}/{y}.png"
        f"?url={encoded_url}"
        f"&tilesize=256"
        f"&bidx=1"
        f"&rescale=0,255"
        f"&return_mask=true"
    )

    return (
        tile_url,
        [
            float(bounds[0]),
            float(bounds[1]),
            float(bounds[2]),
            float(bounds[3]),
        ],
        minzoom,
        maxzoom,
    )

def calculate_fit_zoom(
    bounds: list[float],
    map_width: int = 800,
    map_height: int = 500,
    padding: float = 0.90,
    max_zoom: int = 24,
) -> int:
    """
    Calculate a practical Leaflet zoom level that fits
    the complete raster extent inside the map.
    
    bounds = [west, south, east, north]
    """

    west, south, east, north = bounds

    # Normalize longitude.
    x1 = (west + 180.0) / 360.0
    x2 = (east + 180.0) / 360.0

    # Web Mercator normalized Y.
    def mercator_y(lat):
        lat = max(-85.05112878, min(85.05112878, lat))
        lat_rad = math.radians(lat)

        return (
            1.0
            - math.log(
                math.tan(lat_rad)
                + 1.0 / math.cos(lat_rad)
            ) / math.pi
        ) / 2.0

    y1 = mercator_y(north)
    y2 = mercator_y(south)

    span_x = max(abs(x2 - x1), 1e-12)
    span_y = max(abs(y2 - y1), 1e-12)

    usable_width = map_width * padding
    usable_height = map_height * padding

    zoom_x = math.log2(
        usable_width / (256.0 * span_x)
    )

    zoom_y = math.log2(
        usable_height / (256.0 * span_y)
    )

    zoom = math.floor(
        min(zoom_x, zoom_y)
    )

    return max(
        1,
        min(zoom, max_zoom),
    )