from __future__ import annotations

"""Runtime setting access shared by uploads and opportunistic cache cleanup."""

import math


def _settings_store():
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            store = current_app.extensions.get("gcp_settings_store")
            if store is not None:
                return store
    except Exception:
        pass
    try:
        from database.db import get_db_pool
        from storage.settings_store import PostgresSettingsStore
        return PostgresSettingsStore(get_db_pool())
    except Exception:
        return None


def get_runtime_setting(key: str, default):
    store = _settings_store()
    if store is None:
        return default
    try:
        return store.get_value(key, default)
    except Exception:
        return default


def raster_ttl_hours(default: int = 24) -> float:
    try:
        value = float(get_runtime_setting("raster_ttl_hours", default))
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if not math.isfinite(value) or value <= 0:
        return float(default)
    return value


def max_upload_size_mb(default: int = 256) -> int:
    try:
        raw = get_runtime_setting("max_upload_size_mb", default)
        if isinstance(raw, bool) or int(raw) != float(raw):
            return int(default)
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        return int(default)
    return max(16, min(2048, value))


def max_upload_size_bytes(default: int = 256) -> int:
    return max_upload_size_mb(default) * 1024 * 1024


def dash_request_max_content_length(default: int = 256) -> int:
    """Allow base64/JSON expansion while enforcing decoded TIFF size separately."""
    raw = max_upload_size_mb(default) * 1024 * 1024
    return int(math.ceil(raw * 1.42 + 2 * 1024 * 1024))


def validate_dash_upload_size(contents: str, filename: str = "upload") -> int:
    """Estimate decoded file size from a Dash data URL without allocating another copy."""
    if not contents or "," not in contents:
        raise ValueError("Choose a valid upload file first.")
    encoded = contents.split(",", 1)[1].strip()
    if not encoded:
        raise ValueError("The selected file is empty.")
    padding = len(encoded) - len(encoded.rstrip("="))
    size = max(0, (len(encoded) * 3 // 4) - padding)
    limit = max_upload_size_bytes()
    if size > limit:
        limit_mb = limit // (1024 * 1024)
        raise ValueError(f"{filename} exceeds the configured {limit_mb} MB upload limit.")
    return size
