from __future__ import annotations

from pathlib import Path

import pytest

from ntask._config import RemoteCacheConfig
from ntask._remote import make_backend
from ntask._remote.http import HTTPBackend
from ntask._remote.local_fs import LocalFSBackend


def test_make_backend_local_fs(tmp_path: Path):
    cfg = RemoteCacheConfig(type="local-fs", path=str(tmp_path / "remote"))
    backend = make_backend(cfg)
    assert isinstance(backend, LocalFSBackend)


def test_make_backend_http():
    cfg = RemoteCacheConfig(type="http", url="https://cache.example.com")
    backend = make_backend(cfg)
    assert isinstance(backend, HTTPBackend)


def test_make_backend_unknown_type_raises():
    cfg = RemoteCacheConfig(type="nonsense")
    with pytest.raises(ValueError, match="Unknown remote cache type"):
        make_backend(cfg)


def test_make_backend_s3_when_boto3_installed():
    pytest.importorskip("boto3")
    from ntask._remote.s3 import S3Backend

    cfg = RemoteCacheConfig(type="s3", bucket="test")
    backend = make_backend(cfg)
    assert isinstance(backend, S3Backend)


def test_make_backend_gcs_when_gcs_installed():
    pytest.importorskip("google.cloud.storage")
    from ntask._remote.gcs import GCSBackend

    cfg = RemoteCacheConfig(type="gcs", bucket="test")
    backend = make_backend(cfg)
    assert isinstance(backend, GCSBackend)
