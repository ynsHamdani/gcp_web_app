from pathlib import Path
import os


# =========================================================
# PROJECT
# =========================================================

BASE_DIR = Path(__file__).resolve().parent


# =========================================================
# DATA DIRECTORIES
# =========================================================

DATA_DIR = BASE_DIR / "data"

UPLOAD_DIR = DATA_DIR / "uploads"

REFERENCE_UPLOAD_DIR = UPLOAD_DIR / "reference"
HISTORICAL_UPLOAD_DIR = UPLOAD_DIR / "historical"

REFERENCE_ORIGINAL_DIR = REFERENCE_UPLOAD_DIR / "original"
REFERENCE_COG_DIR = REFERENCE_UPLOAD_DIR / "cogs"

HISTORICAL_ORIGINAL_DIR = HISTORICAL_UPLOAD_DIR / "original"
HISTORICAL_COG_DIR = HISTORICAL_UPLOAD_DIR / "cogs"


# Create directories automatically
for directory in [
    REFERENCE_ORIGINAL_DIR,
    REFERENCE_COG_DIR,
    HISTORICAL_ORIGINAL_DIR,
    HISTORICAL_COG_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)



APP_BASE_URL = "http://127.0.0.1:8050"
TITILER_URL = "http://127.0.0.1:8000"
# =========================================================
# TITILER
# =========================================================

TITILER_URL = os.getenv(
    "TITILER_URL",
    "http://127.0.0.1:8000",
).rstrip("/")