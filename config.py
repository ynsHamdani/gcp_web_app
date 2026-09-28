from __future__ import annotations

"""Central application configuration.

Paths intentionally remain compatible with the existing project structure.
Student uploads are now stored only in a temporary content-addressed cache.
Reference/historical "original" and "COG" directories are retained as
configuration names for backward compatibility, but the new upload callbacks
do not use them for student uploads.
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
# Kept for compatibility with the rest of the project.  New student uploads
# should NOT be written here.
# =========================================================

REFERENCE_ORIGINAL_DIR = UPLOAD_DIR / "reference" / "original"
REFERENCE_COG_DIR = UPLOAD_DIR / "reference" / "cogs"

HISTORICAL_ORIGINAL_DIR = UPLOAD_DIR / "historical" / "original"
HISTORICAL_COG_DIR = UPLOAD_DIR / "historical" / "cogs"


# =========================================================
# TEMPORARY STUDENT-RASTER STORAGE
# =========================================================
#
# Layout:
#
# data/
#   temp_rasters/
#       staging/                <- raw upload, very short-lived
#       reference/
#           <sha256>/
#               <sha256>.tif   <- one temporary COG
#       historical/
#           <sha256>/
#               <sha256>.tif
#
# The SHA-256 directory means identical uploads share the same COG.
# =========================================================

TEMP_RASTER_DIR = DATA_DIR / "temp_rasters"
TEMP_RASTER_STAGING_DIR = TEMP_RASTER_DIR / "staging"

# =========================================================
# GCP STORAGE
# =========================================================

# Authoritative coordinate reference system for registered GCPs.
# Leaflet still uses WGS84 (EPSG:4326) for map interaction; only the stored
# GCP coordinates use this projected CRS.
GCP_CRS = "EPSG:25832"

GCP_DATA_DIR = DATA_DIR / "gcps"
GCP_JSON_PATH = GCP_DATA_DIR / "gcps.json"
GCP_STUDENT_ID = os.getenv("GCP_STUDENT_ID", "")


# Remove temporary raster entries after this period of inactivity.
TEMP_RASTER_TTL_HOURS = float(
    os.getenv("TEMP_RASTER_TTL_HOURS", "1")
)


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
):
    directory.mkdir(parents=True, exist_ok=True)
