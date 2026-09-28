from __future__ import annotations

"""Persistence abstraction for raster-layer metadata.

The callbacks depend on this small interface rather than on JSON. A future
PostgreSQL implementation can provide the same methods.
"""

from pathlib import Path
from threading import Lock
import json
import os
import tempfile
from typing import Protocol


class LayerStore(Protocol):
    """Persistence contract for one layer type."""

    def list(self) -> list[dict]: ...

    def get(self, layer_id: str) -> dict | None: ...

    def upsert(self, record: dict) -> dict: ...


class JSONLayerStore:
    """Atomic JSON-backed layer metadata store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        if not self.path.exists():
            self._atomic_write([])

    def list(self) -> list[dict]:
        with self._lock:
            return self._read()

    def get(self, layer_id: str) -> dict | None:
        with self._lock:
            return next(
                (
                    record
                    for record in self._read()
                    if record.get("layer_id") == layer_id
                ),
                None,
            )

    def upsert(self, record: dict) -> dict:
        layer_id = record.get("layer_id")
        if not layer_id:
            raise ValueError("Layer record requires layer_id.")

        with self._lock:
            records = self._read()
            new_record = dict(record)

            replaced = False
            for index, existing in enumerate(records):
                if existing.get("layer_id") == layer_id:
                    records[index] = new_record
                    replaced = True
                    break

            if not replaced:
                records.append(new_record)

            self._atomic_write(records)
            return new_record

    def _read(self) -> list[dict]:
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            return []

        if not isinstance(data, list):
            raise ValueError(f"Invalid layer JSON store: {self.path}")

        return data

    def _atomic_write(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.stem}_",
            suffix=".tmp",
            dir=self.path.parent,
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(records, file, indent=2, ensure_ascii=False)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(tmp_name, self.path)

        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
