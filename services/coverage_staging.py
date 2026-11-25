from __future__ import annotations

"""Short-lived, server-side staging for already validated coverage imports.

Prepared geometry WKB and attributes are stored as gzip-compressed JSON Lines,
not pickle and not browser dcc.Store data. Publication can stream features in
batches without decoding/reprojecting the original vector file a second time.
"""

import gzip
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from services.coverage_import import CoverageFeature


@dataclass(frozen=True)
class StagedCoverageImport:
    token: str
    path: Path
    metadata: dict

    def __getattr__(self, name: str):
        # Keep the same metadata-shaped interface used by CoverageStore.
        if name in self.metadata:
            return self.metadata[name]
        raise AttributeError(name)

    def iter_feature_batches(self, batch_size: int = 500) -> Iterator[list[CoverageFeature]]:
        if batch_size < 1 or batch_size > 5000:
            raise ValueError("Staged import batch size must be between 1 and 5,000.")
        batch: list[CoverageFeature] = []
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as stream:
                header = json.loads(stream.readline())
                if header.get("_record_type") != "metadata" or header.get("source_sha256") != self.metadata.get("source_sha256"):
                    raise ValueError("The staged coverage import metadata is corrupt.")
                for line_number, line in enumerate(stream, start=2):
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    batch.append(CoverageFeature(**item))
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
        except (OSError, EOFError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"The prepared coverage import cannot be read: {exc}") from exc
        if batch:
            yield batch


class CoverageStagingStore:
    """Manage TTL-bound prepared imports under a private server data directory."""

    def __init__(self, root: str | Path, ttl_seconds: int = 4 * 60 * 60) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = max(300, int(ttl_seconds))

    @staticmethod
    def _token(value: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("The validation token is invalid. Validate the source file again.") from exc

    def cleanup_expired(self) -> int:
        import time

        cutoff = time.time() - self.ttl_seconds
        removed = 0
        for path in self.root.glob("*.jsonl.gz"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
        for path in self.root.glob("*.part"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
        return removed

    def stage(self, import_data) -> tuple[str, dict]:
        self.cleanup_expired()
        token = str(uuid.uuid4())
        target = self.root / f"{token}.jsonl.gz"
        temporary = self.root / f"{token}.part"
        metadata = {
            "filename": import_data.filename,
            "source_format": import_data.source_format,
            "source_layer_name": import_data.source_layer_name,
            "source_crs": import_data.source_crs,
            "target_srid": int(import_data.target_srid),
            "geometry_type": import_data.geometry_type,
            "feature_count": int(import_data.feature_count),
            "source_sha256": import_data.source_sha256,
            "warnings": list(import_data.warnings),
        }
        try:
            with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=5) as stream:
                stream.write(json.dumps({"_record_type": "metadata", **metadata}, ensure_ascii=False) + "\n")
                for feature in import_data.features:
                    record = {
                        "source_feature_key": feature.source_feature_key,
                        "feature_label": feature.feature_label,
                        "source_index": int(feature.source_index),
                        "attributes": feature.attributes,
                        "geometry_wkb_hex": feature.geometry_wkb_hex,
                    }
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise
        return token, metadata

    def open(self, token: str) -> StagedCoverageImport:
        safe_token = self._token(token)
        path = self.root / f"{safe_token}.jsonl.gz"
        if not path.is_file():
            raise ValueError("The prepared import has expired or is unavailable. Validate the file again.")
        import time
        if time.time() - path.stat().st_mtime > self.ttl_seconds:
            path.unlink(missing_ok=True)
            raise ValueError("The prepared import has expired. Validate the file again.")
        try:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                header = json.loads(stream.readline())
            if header.pop("_record_type", None) != "metadata":
                raise ValueError("The prepared import header is invalid.")
            return StagedCoverageImport(token=safe_token, path=path, metadata=header)
        except (OSError, EOFError, json.JSONDecodeError) as exc:
            raise ValueError(f"The prepared import is corrupt: {exc}") from exc

    def delete(self, token: str) -> None:
        safe_token = self._token(token)
        (self.root / f"{safe_token}.jsonl.gz").unlink(missing_ok=True)
