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
            raise ValueError(
                "remote cache type 'local-fs' needs 'path' in [tool.ntask.remote_cache]"
            )
        return LocalFSBackend(root=Path(config.path))
    if config.type == "http":
        if not config.url:
            raise ValueError(
                "remote cache type 'http' needs 'url' in [tool.ntask.remote_cache]"
            )
        return HTTPBackend(base_url=config.url, auth_header=config.auth_header)
    if config.type == "s3":
        if not config.bucket:
            raise ValueError(
                "remote cache type 's3' needs 'bucket' in [tool.ntask.remote_cache]"
            )
        try:
            from .s3 import S3Backend
        except ImportError as e:
            raise RuntimeError(
                "the s3 remote cache needs boto3; install it with: pip install 'ntask[s3]'"
            ) from e
        return S3Backend(
            bucket=config.bucket,
            prefix=config.prefix,
            endpoint_url=config.endpoint_url,
        )
    if config.type == "gcs":
        if not config.bucket:
            raise ValueError(
                "remote cache type 'gcs' needs 'bucket' in [tool.ntask.remote_cache]"
            )
        try:
            from .gcs import GCSBackend
        except ImportError as e:
            raise RuntimeError(
                "the gcs remote cache needs google-cloud-storage; "
                "install it with: pip install 'ntask[gcs]'"
            ) from e
        return GCSBackend(bucket=config.bucket, prefix=config.prefix)
    raise ValueError(f"Unknown remote cache type: {config.type!r}")
