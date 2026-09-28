# GCP workflow

This update adds a modular Ground Control Point (GCP) workflow while keeping the existing raster, map synchronization, navigation, and opacity code separate.

## Workflow

1. Click the reference map to create a pending GCP.
2. A matching pending marker appears on the historical map.
3. Drag the historical marker to the corresponding historical location.
4. Confirm the GCP to persist it in JSON.
5. Confirmed GCPs appear on both maps and in the table.
6. Selecting a table row highlights the corresponding GCP.

## Coordinate handling

Leaflet interaction uses WGS84 / EPSG:4326 (`lat/lon`). The authoritative GCP coordinates are converted to and stored as ETRS89 / UTM zone 32N (EPSG:25832) (`x/y`, metres).

The coordinate conversion is implemented in `models/gcp.py`; `callbacks/gcp.py` only orchestrates the UI workflow, and `storage/gcp_store.py` provides the persistence interface.

## Structure

```text
models/gcp.py          # GCP domain model + 4326 -> EPSG:25832 conversion
callbacks/gcp.py       # Dash interaction workflow
storage/gcp_store.py   # JSON store + backend interface
maps/gcp.py            # Marker rendering only
assets/gcp.js          # Browser drag-event bridge
config.py              # GCP CRS + JSON path
```

## PostgreSQL later

The callbacks depend on the `GCPStore` protocol rather than the JSON implementation. A future PostgreSQL/PostGIS backend can implement the same interface and replace `JSONGCPStore` in `app1.py` without moving the interaction logic.

## Existing functionality preserved

The package includes the working temporary-raster/content-addressed storage and the corrected raster fit/zoom handling. Existing raster, navigation, opacity, and map synchronization modules are otherwise kept unchanged.
