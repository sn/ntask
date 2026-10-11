"""Normalised tar.gz creation + staged extraction."""
from __future__ import annotations

import io
import tarfile
import uuid
from pathlib import Path


def tar_directory(source_dir: Path) -> bytes:
    """Tar+gzip ``source_dir`` with normalised member metadata.

    Entries sorted alphabetically by relative path; mtime=0; uid=gid=0;
    uname=gname=""; only regular files included (dirs are inferred from paths).
    The gzip header still records the current time, so the compressed bytes
    differ between calls even for identical input.
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
    """Extract a tar.gz into ``dest_dir`` via a temp staging dir.

    Each top-level entry is then renamed into ``dest_dir``, replacing any
    existing entry of the same name. If extraction fails, the staging dir is
    cleaned up and ``dest_dir``'s contents are untouched (it is still created
    if missing); a failure during the renames can leave it partly updated.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    staging = dest_dir.parent / f".{dest_dir.name}.staging.{uuid.uuid4().hex[:8]}"
    try:
        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            # `filter="data"` (PEP 706) rejects entries that would write
            # outside the destination, set unsafe permissions, or include
            # absolute paths. Remote backends fetch attacker-influenceable
            # bytes, so this is load-bearing — not just future-proofing.
            tar.extractall(staging, filter="data")
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
