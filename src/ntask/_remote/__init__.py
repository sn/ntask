"""Remote cache backend factory + protocol re-export."""
from __future__ import annotations

from pathlib import Path

from .._config import RemoteCacheConfig
from .base import RemoteBackend
from .http import HTTPBackend
from .local_fs import LocalFSBackend

__all__ = ["RemoteBackend", "make_backend"]


def make_backend(config: RemoteCacheConfig) -> RemoteBackend:
    """Construct a RemoteBackend from a RemoteCacheConfig."""
    if config.type == "local-fs":
        if not config.path:
            raise ValueError("local-fs backend requires 'path' in config")
        return LocalFSBackend(root=Path(config.path))
    if config.type == "http":
        if not config.url:
            raise ValueError("http backend requires 'url' in config")
        return HTTPBackend(base_url=config.url, auth_header=config.auth_header)
    if config.type == "s3":
        if not config.bucket:
            raise ValueError("s3 backend requires 'bucket' in config")
        try:
            from .s3 import S3Backend
        except ImportError as e:
            raise RuntimeError(
                "S3 backend requires: pip install ntask[s3]"
            ) from e
        return S3Backend(
            bucket=config.bucket,
            prefix=config.prefix,
            endpoint_url=config.endpoint_url,
        )
    if config.type == "gcs":
        if not config.bucket:
            raise ValueError("gcs backend requires 'bucket' in config")
        try:
            from .gcs import GCSBackend
        except ImportError as e:
            raise RuntimeError(
                "GCS backend requires: pip install ntask[gcs]"
            ) from e
        return GCSBackend(bucket=config.bucket, prefix=config.prefix)
    raise ValueError(f"Unknown remote cache type: {config.type!r}")
