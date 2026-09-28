from  __future__ import annotations

"""Persistence abstraction for GCP records.

The store deliberately does not perform coordinate conversion.  The domain
model creates records containing authoritative X/Y coordinates and the CRS;
this module simply persists those records.

The callbacks depend on ``GCPStore`` only.  ``JSONGCPStore`` is the prototype
backend.  A future ``PostgresGCPStore`` can implement the same methods without
changing the Dash interaction workflow.
"""

from pathlib import Path
from threading import Lock
import json
import os
import tempfile
from typing import Protocol


class GCPStore(Protocol):
    """Small persistence contract used by the GCP callbacks."""

    def list(self) -> list[dict]: ...

    def create(self, record: dict) -> dict: ...

    def get(self, gcp_id: str) -> dict | None: ...

    def update(self, gcp_id: str, changes: dict) -> dict: ...

    def delete(self, gcp_id: str) -> None: ...


class JSONGCPStore:
    """File-backed implementation of the GCPStore contract.

    GCP records are stored exactly as produced by the domain model, including
    reference/historical X/Y coordinates and the CRS identifier.

    The file is rewritten atomically.  The in-process lock is sufficient for
    the current single-process prototype; PostgreSQL should be used later when
    multiple app workers write concurrently.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        if not self.path.exists():
            self._atomic_write([])

    def list(self) -> list[dict]:
        with self._lock:
            return self._read()

    def get(self, gcp_id: str) -> dict | None:
        with self._lock:
            return next(
                (record for record in self._read() if record.get("gcp_id") == gcp_id),
                None,
            )

    def create(self, record: dict) -> dict:
        with self._lock:
            records = self._read()
            new_record = dict(record)
            new_record["gcp_id"] = self._next_id(records)
            records.append(new_record)
            self._atomic_write(records)
            return new_record

    def update(self, gcp_id: str, changes: dict) -> dict:
        with self._lock:
            records = self._read()

            for index, record in enumerate(records):
                if record.get("gcp_id") != gcp_id:
                    continue

                updated = {**record, **changes, "gcp_id": gcp_id}
                records[index] = updated
                self._atomic_write(records)
                return updated

            raise KeyError(f"Unknown GCP: {gcp_id}")

    def delete(self, gcp_id: str) -> None:
        with self._lock:
            records = self._read()
            filtered = [
                record
                for record in records
                if record.get("gcp_id") != gcp_id
            ]

            if len(filtered) == len(records):
                raise KeyError(f"Unknown GCP: {gcp_id}")

            self._atomic_write(filtered)

    def _read(self) -> list[dict]:
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            return []

        if not isinstance(data, list):
            raise ValueError(f"Invalid GCP JSON store: {self.path}")

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

    @staticmethod
    def _next_id(records: list[dict]) -> str:
        highest = 0

        for record in records:
            value = str(record.get("gcp_id", ""))
            if not value.startswith("GCP-"):
                continue

            try:
                highest = max(highest, int(value[4:]))
            except ValueError:
                continue

        return f"GCP-{highest + 1:04d}"
