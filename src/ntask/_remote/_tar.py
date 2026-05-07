"""Deterministic tar.gz creation + atomic extraction."""
from __future__ import annotations

import io
import tarfile
import uuid
from pathlib import Path


def tar_directory(source_dir: Path) -> bytes:
    """Tar+gzip ``source_dir`` deterministically.

    Entries sorted alphabetically by relative path; mtime=0; uid=gid=0;
    uname=gname=""; only regular files included (dirs are inferred from paths).
    Returns the in-memory tar.gz bytes.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        for p in sorted(source_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(source_dir)
            info = tar.gettarinfo(str(p), arcname=rel.as_posix())
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with p.open("rb") as f:
                tar.addfile(info, f)
    return buf.getvalue()


def extract_tar(data: bytes, dest_dir: Path) -> None:
    """Extract a tar.gz into ``dest_dir`` via a temp staging dir + atomic rename.

    If extraction fails partway, the staging dir is cleaned up and dest_dir
    is not mutated.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    staging = dest_dir.parent / f".{dest_dir.name}.staging.{uuid.uuid4().hex[:8]}"
    try:
        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(staging)  # noqa: S202
        # Move contents of staging into dest_dir
        for p in staging.iterdir():
            target = dest_dir / p.name
            if target.exists():
                if target.is_dir():
                    import shutil

                    shutil.rmtree(target)
                else:
                    target.unlink()
            p.rename(target)
    finally:
        if staging.exists():
            import shutil

            shutil.rmtree(staging, ignore_errors=True)
