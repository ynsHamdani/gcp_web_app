from __future__ import annotations

"""One-time migration of the current JSON stores into PostgreSQL.

Usage:
    python scripts/migrate_json_to_postgres.py

The script migrates layer metadata first, then GCPs. The old layer hash IDs
are mapped to the PostgreSQL-generated numeric layer IDs.

GCPs whose historical/reference layer cannot be resolved are reported and
not inserted. This is especially important for legacy records where
reference_layer_id was NULL before basemaps became explicit layer instances.
"""

import json
from pathlib import Path

from config import (
    DEV_USER_ID,
    HISTORICAL_LAYER_JSON_PATH,
    REFERENCE_LAYER_JSON_PATH,
    GCP_JSON_PATH,
)
from database.db import get_db_pool
from models.layer import build_layer_record
from storage.gcp_store import PostgresGCPStore
from storage.layer_store import PostgresLayerStore


def _read_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def _migrate_layers(
    store: PostgresLayerStore,
    path: Path,
    layer_type: str,
) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for old in _read_json(path):
        old_id = old.get("layer_id") or old.get("id") or old.get("sha256")
        if not old_id:
            print(f"SKIP layer without identity: {old}")
            continue

        sha256 = old.get("sha256") or old_id
        extent = old.get("extent")
        if not extent or len(extent) != 4:
            print(f"SKIP layer without valid extent: {old_id}")
            continue

        record = build_layer_record(
            layer_type=layer_type,
            source_type="uploaded",
            filename=old.get("filename") or old.get("name") or str(old_id),
            sha256=sha256,
            crs=old["crs"],
            extent=extent,
            width=old["width"],
            height=old["height"],
        )
        saved = store.upsert(record)
        mapping[str(old_id)] = saved["layer_id"]

    return mapping


def _migrate_gcps(
    gcp_store: PostgresGCPStore,
    layer_map: dict[str, str],
) -> None:
    migrated = 0
    skipped = 0

    for old in _read_json(GCP_JSON_PATH):
        old_reference_id = old.get("reference_layer_id")
        old_historical_id = old.get("historical_layer_id")

        reference_layer_id = layer_map.get(str(old_reference_id)) if old_reference_id else None
        historical_layer_id = layer_map.get(str(old_historical_id)) if old_historical_id else None

        if not reference_layer_id or not historical_layer_id:
            print(
                "SKIP GCP "
                f"{old.get('gcp_id', '?')}: unresolved reference/historical layer."
            )
            skipped += 1
            continue

        reference = old.get("reference", {})
        historical = old.get("historical", {})

        record = {
            "crs": old.get("crs", "EPSG:25832"),
            "reference_layer_id": reference_layer_id,
            "historical_layer_id": historical_layer_id,
            "student_id": old.get("student_id") or DEV_USER_ID,
            "reference": reference,
            "historical": historical,
            "offset_m": float(old.get("offset_m", 0.0)),
            "status": old.get("status", "confirmed"),
            "recorded_at": old.get("recorded_at")
            or old.get("updated_at")
            or old.get("created_at"),
        }

        # PostgreSQL generates the new canonical GCP ID. The old display ID is
        # intentionally not forced into the identity sequence.
        saved = gcp_store.create(record)
        print(f"Migrated {old.get('gcp_id', '?')} -> {saved['gcp_id']}")
        migrated += 1

    print(f"GCP migration complete: {migrated} migrated, {skipped} skipped.")


def main() -> None:
    pool = get_db_pool()
    layer_store = PostgresLayerStore(pool)
    gcp_store = PostgresGCPStore(pool)

    print("Migrating reference layers...")
    layer_map = _migrate_layers(
        layer_store,
        REFERENCE_LAYER_JSON_PATH,
        "reference",
    )

    print("Migrating historical layers...")
    layer_map.update(
        _migrate_layers(
            layer_store,
            HISTORICAL_LAYER_JSON_PATH,
            "historical",
        )
    )

    print("Migrating GCPs...")
    _migrate_gcps(gcp_store, layer_map)

    print("Migration finished.")


if __name__ == "__main__":
    main()
