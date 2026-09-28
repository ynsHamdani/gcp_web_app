from __future__ import annotations

"""Persistence abstraction for GCP records.

JSON is the prototype backend. The callback layer depends only on GCPStore,
so a future PostgreSQL implementation can provide the same contract.
"""

from pathlib import Path
from threading import Lock
import json
import os
import tempfile
from typing import Protocol


class GCPStore(Protocol):
    """Persistence contract used by the GCP callbacks."""

    def list(self) -> list[dict]: ...

    def create(self, record: dict) -> dict: ...

    def get(self, gcp_id: str) -> dict | None: ...

    def update(self, gcp_id: str, changes: dict) -> dict: ...

    def delete(self, gcp_id: str) -> None: ...


class JSONGCPStore:
    """Atomic JSON-backed GCP store.

    Legacy ``created_at``/``updated_at`` fields are normalized to the single
    ``recorded_at`` field when records are read.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        if not self.path.exists():
            self._atomic_write([])

    def list(self) -> list[dict]:
        with self._lock:
            records, changed = self._read_with_migration()
            if changed:
                self._atomic_write(records)
            return records

    def get(self, gcp_id: str) -> dict | None:
        with self._lock:
            records, changed = self._read_with_migration()
            if changed:
                self._atomic_write(records)

            return next(
                (
                    record
                    for record in records
                    if record.get("gcp_id") == gcp_id
                ),
                None,
            )

    def create(self, record: dict) -> dict:
        with self._lock:
            records, _ = self._read_with_migration()

            new_record = dict(record)
            new_record["gcp_id"] = self._next_id(records)

            # Do not persist legacy timestamp fields if an older caller passes
            # them accidentally.
            new_record.pop("created_at", None)
            new_record.pop("updated_at", None)
            new_record.setdefault("recorded_at", None)

            records.append(new_record)
            self._atomic_write(records)
            return new_record

    def update(self, gcp_id: str, changes: dict) -> dict:
        with self._lock:
            records, _ = self._read_with_migration()

            for index, record in enumerate(records):
                if record.get("gcp_id") != gcp_id:
                    continue

                updated = {
                    **record,
                    **changes,
                    "gcp_id": gcp_id,
                }
                updated.pop("created_at", None)
                updated.pop("updated_at", None)
                updated.setdefault("recorded_at", record.get("recorded_at"))

                records[index] = updated
                self._atomic_write(records)
                return updated

            raise KeyError(f"Unknown GCP: {gcp_id}")

    def delete(self, gcp_id: str) -> None:
        with self._lock:
            records, _ = self._read_with_migration()

            filtered = [
                record
                for record in records
                if record.get("gcp_id") != gcp_id
            ]

            if len(filtered) == len(records):
                raise KeyError(f"Unknown GCP: {gcp_id}")

            self._atomic_write(filtered)

    def _read_with_migration(self) -> tuple[list[dict], bool]:
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            return [], False

        if not isinstance(data, list):
            raise ValueError(f"Invalid GCP JSON store: {self.path}")

        normalized = []
        changed = False

        for record in data:
            migrated = dict(record)

            if "recorded_at" not in migrated:
                legacy_timestamp = (
                    migrated.get("updated_at")
                    or migrated.get("created_at")
                )
                if legacy_timestamp is not None:
                    migrated["recorded_at"] = legacy_timestamp
                changed = True

            if "created_at" in migrated:
                migrated.pop("created_at", None)
                changed = True

            if "updated_at" in migrated:
                migrated.pop("updated_at", None)
                changed = True

            if (
                "student_id" not in migrated
                and "student" in migrated
            ):
                migrated["student_id"] = migrated.pop("student")
                changed = True

            normalized.append(migrated)

        return normalized, changed

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
