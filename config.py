from __future__ import annotations

"""Central application configuration.

Student uploads are stored in a temporary, content-addressed raster cache.
Layer metadata and GCP records are stored separately in JSON files so the
persistence layer can later be replaced by PostgreSQL without changing the
Dash interaction logic.
"""

import os
from pathlib import Path


# =========================================================
# PROJECT PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"


# =========================================================
# EXISTING UPLOAD PATHS
# =========================================================
# Kept for compatibility. New student uploads use TEMP_RASTER_DIR.
# =========================================================

REFERENCE_ORIGINAL_DIR = UPLOAD_DIR / "reference" / "original"
REFERENCE_COG_DIR = UPLOAD_DIR / "reference" / "cogs"

HISTORICAL_ORIGINAL_DIR = UPLOAD_DIR / "historical" / "original"
HISTORICAL_COG_DIR = UPLOAD_DIR / "historical" / "cogs"


# =========================================================
# TEMPORARY STUDENT-RASTER STORAGE
# =========================================================

TEMP_RASTER_DIR = DATA_DIR / "temp_rasters"
TEMP_RASTER_STAGING_DIR = TEMP_RASTER_DIR / "staging"

TEMP_RASTER_TTL_HOURS = float(
    os.getenv("TEMP_RASTER_TTL_HOURS", "24")
)


# =========================================================
# GCP + LAYER METADATA STORAGE
# =========================================================

# Leaflet interaction remains WGS84 (EPSG:4326), while authoritative GCP
# ground coordinates are stored in this projected CRS.
GCP_CRS = "EPSG:25832"

GCP_DATA_DIR = DATA_DIR / "gcps"
GCP_JSON_PATH = GCP_DATA_DIR / "gcps.json"

LAYER_DATA_DIR = DATA_DIR / "layers"
REFERENCE_LAYER_JSON_PATH = LAYER_DATA_DIR / "reference_layers.json"
HISTORICAL_LAYER_JSON_PATH = LAYER_DATA_DIR / "historical_layers.json"

GCP_STUDENT_ID = os.getenv("GCP_STUDENT_ID", "")


# =========================================================
# WEB SERVICES
# =========================================================

APP_BASE_URL = os.getenv(
    "APP_BASE_URL",
    "http://127.0.0.1:8050",
).rstrip("/")

TITILER_URL = os.getenv(
    "TITILER_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


# =========================================================
# CREATE REQUIRED DIRECTORIES
# =========================================================

for directory in (
    REFERENCE_ORIGINAL_DIR,
    REFERENCE_COG_DIR,
    HISTORICAL_ORIGINAL_DIR,
    HISTORICAL_COG_DIR,
    TEMP_RASTER_DIR,
    TEMP_RASTER_STAGING_DIR,
    GCP_DATA_DIR,
    LAYER_DATA_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)
