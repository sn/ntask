"""GCS backend using google-cloud-storage."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from google.api_core.exceptions import NotFound
    from google.cloud import storage
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "GCS backend requires google-cloud-storage. "
        "Install with: pip install ntask[gcs]"
    ) from e

from ._tar import extract_tar, tar_directory


class GCSBackend:
    """Entries + tar.gz outputs under a GCS bucket, optionally prefixed."""

    def __init__(self, *, bucket: str, prefix: str = ""):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket)
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""

    def _blob(self, *parts: str) -> Any:
        return self.bucket.blob(self.prefix + "/".join(parts))

    def has_entry(self, fqn: str, key: str) -> bool:
        return bool(self._blob("entries", fqn, f"{key}.json").exists())

    def get_entry(self, fqn: str, key: str) -> dict[str, object] | None:
        blob = self._blob("entries", fqn, f"{key}.json")
        try:
            data: str = blob.download_as_text()
        except NotFound:
            return None
        result: dict[str, object] = json.loads(data)
        return result

    def put_entry(self, fqn: str, key: str, entry: dict[str, object]) -> None:
        self._blob("entries", fqn, f"{key}.json").upload_from_string(
            json.dumps(entry, indent=2),
            content_type="application/json",
        )

    def has_output(self, outputs_hash: str) -> bool:
        return bool(self._blob("outputs", f"{outputs_hash}.tar.gz").exists())

    def get_output(self, outputs_hash: str, dest_dir: Path) -> None:
        blob = self._blob("outputs", f"{outputs_hash}.tar.gz")
        try:
            data: bytes = blob.download_as_bytes()
        except NotFound as e:
            raise FileNotFoundError(outputs_hash) from e
        extract_tar(data, dest_dir)

    def put_output(self, outputs_hash: str, source_dir: Path) -> None:
        self._blob("outputs", f"{outputs_hash}.tar.gz").upload_from_string(
            tar_directory(source_dir),
            content_type="application/gzip",
        )
