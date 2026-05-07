from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("moto")
pytest.importorskip("boto3")

import boto3
from moto import mock_aws

from ntask._remote.s3 import S3Backend


@mock_aws
def test_s3_roundtrip_entry():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3Backend(bucket="test-bucket")

    assert backend.has_entry("build", "abc") is False
    assert backend.get_entry("build", "abc") is None

    backend.put_entry("build", "abc", {"v": 1})
    assert backend.has_entry("build", "abc") is True
    assert backend.get_entry("build", "abc") == {"v": 1}


@mock_aws
def test_s3_prefix_applied():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3Backend(bucket="test-bucket", prefix="my-project/")
    backend.put_entry("build", "abc", {"v": 1})

    # Verify the object is at the prefixed key by listing.
    resp = boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket="test-bucket")
    keys = [o["Key"] for o in resp["Contents"]]
    assert any(k.startswith("my-project/entries/build/abc.json") for k in keys)


@mock_aws
def test_s3_missing_entry_returns_none():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3Backend(bucket="test-bucket")
    assert backend.get_entry("nothing", "absent") is None


@mock_aws
def test_s3_output_tar_roundtrip(tmp_path: Path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3Backend(bucket="test-bucket")

    src = tmp_path / "s"
    src.mkdir()
    (src / "f.txt").write_bytes(b"content")
    backend.put_output("h1", src)

    assert backend.has_output("h1") is True
    dest = tmp_path / "d"
    backend.get_output("h1", dest)
    assert (dest / "f.txt").read_bytes() == b"content"


def test_s3_endpoint_url_used():
    # Just verify the endpoint_url is passed through to boto3; no real call.
    from ntask._remote.s3 import S3Backend

    backend = S3Backend(
        bucket="test-bucket", endpoint_url="http://minio.local:9000",
    )
    # The client should reflect the custom endpoint
    assert "minio.local" in str(backend.client.meta.endpoint_url)
