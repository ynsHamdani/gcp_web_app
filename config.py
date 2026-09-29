from __future__ import annotations

"""Application configuration.

Database credentials/settings are loaded from a local, git-ignored
config.yaml file.

Expected config.yaml:

database:
  host: ep-xxxxxxxx-pooler.c-6.eu-central-1.aws.neon.tech
  port: 5432
  name: gcp_web_app
  user: neondb_owner
  password: "YOUR_NEON_PASSWORD"
  sslmode: require
  channel_binding: require
  min_pool_size: 1
  max_pool_size: 5
  pool_timeout_seconds: 10
  connect_timeout_seconds: 10
"""

import os
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

REFERENCE_ORIGINAL_DIR = UPLOAD_DIR / "reference" / "original"
REFERENCE_COG_DIR = UPLOAD_DIR / "reference" / "cogs"

HISTORICAL_ORIGINAL_DIR = UPLOAD_DIR / "historical" / "original"
HISTORICAL_COG_DIR = UPLOAD_DIR / "historical" / "cogs"

TEMP_RASTER_DIR = DATA_DIR / "temp_rasters"
TEMP_RASTER_STAGING_DIR = TEMP_RASTER_DIR / "staging"

GCP_DATA_DIR = DATA_DIR / "gcps"
LAYER_DATA_DIR = DATA_DIR / "layers"


# ---------------------------------------------------------------------------
# Application settings
# ---------------------------------------------------------------------------

APP_BASE_URL = os.getenv(
    "APP_BASE_URL",
    "http://127.0.0.1:8050",
).rstrip("/")

TITILER_URL = os.getenv(
    "TITILER_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

GCP_CRS = "EPSG:25832"

# Temporary development identity until authentication is implemented.
GCP_STUDENT_ID = os.getenv("GCP_STUDENT_ID", "")

TEMP_RASTER_TTL_HOURS = float(
    os.getenv("TEMP_RASTER_TTL_HOURS", "24")
)


# ---------------------------------------------------------------------------
# Local YAML configuration
# ---------------------------------------------------------------------------

CONFIG_YAML_PATH = Path(
    os.getenv(
        "GCP_CONFIG_FILE",
        str(BASE_DIR / "config.yaml"),
    )
)


def load_yaml_config() -> dict[str, Any]:
    """Load the local YAML configuration file."""

    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_YAML_PATH}\n"
            "Create config.yaml from config.example.yaml."
        )

    with CONFIG_YAML_PATH.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    if not isinstance(config, dict):
        raise ValueError(
            "The root of config.yaml must be a mapping."
        )

    return config


def get_database_config() -> dict[str, Any]:
    """Return and validate the PostgreSQL configuration."""

    config = load_yaml_config()
    database = config.get("database")

    if not isinstance(database, dict):
        raise ValueError(
            "config.yaml must contain a 'database' section."
        )

    required = (
        "host",
        "port",
        "name",
        "user",
        "password",
    )

    missing = [
        key
        for key in required
        if database.get(key) in (None, "")
    ]

    if missing:
        raise ValueError(
            "Missing database configuration value(s): "
            + ", ".join(missing)
        )

    return database



DEV_USER_ID = load_yaml_config()["development"]["user_id"]

def get_development_user_id() -> int:
    config = load_yaml_config()
    development = config.get("development", {})

    if "user_id" not in development:
        raise ValueError("config.yaml must contain development.user_id")

    return int(development["user_id"])


DEV_USER_ID = get_development_user_id()

# Backward-compatible name used by callbacks/gcp.py
GCP_STUDENT_ID = str(DEV_USER_ID)
# ---------------------------------------------------------------------------
# Required directories
# ---------------------------------------------------------------------------

for directory in (
    DATA_DIR,
    UPLOAD_DIR,
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
