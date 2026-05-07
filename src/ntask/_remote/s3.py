"""S3 backend using boto3. Supports S3-compatibles via endpoint_url."""
from __future__ import annotations

import json
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "S3 backend requires boto3. Install with: pip install ntask[s3]"
    ) from e

from ._tar import extract_tar, tar_directory


class S3Backend:
    """Remote backend backed by S3.

    Entries at ``<prefix>entries/<fqn>/<key>.json``;
    outputs at ``<prefix>outputs/<hash>.tar.gz``.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.client = boto3.client("s3", endpoint_url=endpoint_url)

    def _key(self, *parts: str) -> str:
        return self.prefix + "/".join(parts)

    def has_entry(self, fqn: str, key: str) -> bool:
        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=self._key("entries", fqn, f"{key}.json"),
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def get_entry(self, fqn: str, key: str) -> dict[str, object] | None:
        try:
            resp = self.client.get_object(
                Bucket=self.bucket,
                Key=self._key("entries", fqn, f"{key}.json"),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(resp["Body"].read())  # type: ignore[no-any-return]

    def put_entry(self, fqn: str, key: str, entry: dict[str, object]) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key("entries", fqn, f"{key}.json"),
            Body=json.dumps(entry, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

    def has_output(self, outputs_hash: str) -> bool:
        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=self._key("outputs", f"{outputs_hash}.tar.gz"),
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def get_output(self, outputs_hash: str, dest_dir: Path) -> None:
        try:
            resp = self.client.get_object(
                Bucket=self.bucket,
                Key=self._key("outputs", f"{outputs_hash}.tar.gz"),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise FileNotFoundError(outputs_hash) from e
            raise
        extract_tar(resp["Body"].read(), dest_dir)

    def put_output(self, outputs_hash: str, source_dir: Path) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key("outputs", f"{outputs_hash}.tar.gz"),
            Body=tar_directory(source_dir),
            ContentType="application/gzip",
        )
