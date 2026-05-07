from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("google.cloud.storage")

from google.api_core.exceptions import NotFound


class _FakeBlob:
    def __init__(self, store: dict, key: str):
        self._store = store
        self._key = key

    def exists(self) -> bool:
        return self._key in self._store

    def upload_from_string(self, data, content_type=None):
        self._store[self._key] = data

    def download_as_bytes(self) -> bytes:
        if self._key not in self._store:
            raise NotFound(f"blob {self._key} not found")
        v = self._store[self._key]
        return v if isinstance(v, bytes) else v.encode("utf-8")

    def download_as_text(self) -> str:
        if self._key not in self._store:
            raise NotFound(f"blob {self._key} not found")
        v = self._store[self._key]
        return v if isinstance(v, str) else v.decode("utf-8")


class _FakeBucket:
    def __init__(self, store: dict):
        self._store = store

    def blob(self, key: str) -> _FakeBlob:
        return _FakeBlob(self._store, key)


class _FakeClient:
    def __init__(self):
        self._store: dict[str, bytes | str] = {}

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(self._store)


def _patched_backend(bucket: str = "test", prefix: str = ""):
    """Construct a GCSBackend with its storage.Client replaced by a fake."""
    from ntask._remote.gcs import GCSBackend

    fake = _FakeClient()
    with patch("ntask._remote.gcs.storage.Client", return_value=fake):
        backend = GCSBackend(bucket=bucket, prefix=prefix)
    return backend, fake


def test_gcs_roundtrip_entry():
    backend, _fake = _patched_backend()

    assert backend.has_entry("build", "abc") is False
    assert backend.get_entry("build", "abc") is None

    backend.put_entry("build", "abc", {"v": 1})
    assert backend.has_entry("build", "abc") is True
    assert backend.get_entry("build", "abc") == {"v": 1}


def test_gcs_missing_entry_returns_none():
    backend, _fake = _patched_backend()
    assert backend.get_entry("nothing", "absent") is None


def test_gcs_output_tar_roundtrip(tmp_path: Path):
    backend, _fake = _patched_backend()

    src = tmp_path / "s"
    src.mkdir()
    (src / "f.txt").write_bytes(b"content")

    backend.put_output("h1", src)
    assert backend.has_output("h1") is True

    dest = tmp_path / "d"
    backend.get_output("h1", dest)
    assert (dest / "f.txt").read_bytes() == b"content"
