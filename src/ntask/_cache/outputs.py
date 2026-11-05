from __future__ import annotations

import shutil
import uuid
from collections.abc import Collection
from pathlib import Path

from .hash import hash_many, hash_many_files
from .manifest import iter_matching_files


class OutputStore:
    """Content-addressed output blob store.

    Layout: ``<root>/outputs/<outputs-hash>/...``, preserving relative paths.

    Files are always *copied* in and out, never hardlinked: most tools
    rewrite their outputs in place, and a shared inode would let that
    rewrite silently change the stored blob (and anything later pushed to
    a remote cache) without changing its hash.
    """

    def __init__(self, root: Path):
        self.root = root
        self._outputs_dir = root / "outputs"

    @property
    def outputs_dir(self) -> Path:
        return self._outputs_dir

    def _hash_dir(self, digest: str) -> Path:
        return self._outputs_dir / digest

    def staging_dir(self, digest: str) -> Path:
        """A unique sibling of the blob dir to fill before renaming it into place."""
        return self._outputs_dir / f".{digest}.staging.{uuid.uuid4().hex[:8]}"

    def commit_staged(self, staging: Path, digest: str) -> None:
        """Atomically move a fully-written ``staging`` dir to the blob path.

        If another writer got there first, its (identical) blob wins and
        ``staging`` is discarded.
        """
        target = self._hash_dir(digest)
        try:
            staging.rename(target)
        except OSError:
            if not target.is_dir():
                raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def capture(
        self,
        patterns: list[str] | tuple[str, ...],
        *,
        root: Path,
        exclude: Collection[Path] = (),
    ) -> str | None:
        """Capture matching files into the content-addressed store, return the hash."""
        if not patterns:
            return None
        matches = list(iter_matching_files(
            patterns, root=root, exclude=(self.root, *exclude),
        ))
        if not matches:
            return None

        file_hashes = hash_many_files(sorted(matches))
        parts: list[bytes] = []
        for fh in file_hashes:
            rel_encoded = fh.path.relative_to(root).as_posix().encode()
            parts.append(rel_encoded)
            parts.append(fh.digest.encode())
        digest = hash_many(parts)

        if self._hash_dir(digest).is_dir():
            return digest

        self._outputs_dir.mkdir(parents=True, exist_ok=True)
        staging = self.staging_dir(digest)
        try:
            for fh in file_hashes:
                dest = staging / fh.path.relative_to(root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fh.path, dest)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self.commit_staged(staging, digest)
        return digest

    def restore(self, digest: str, *, root: Path) -> None:
        """Restore a previously captured output tree into ``root``."""
        src = self._hash_dir(digest)
        if not src.is_dir():
            raise FileNotFoundError(f"no output blob for hash {digest}")
        for p in src.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(src)
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Unlink first: the workspace file may still be a hardlink into
            # the store from an older ntask, and copying over it in place
            # would write straight through into the blob.
            if dest.is_file() or dest.is_symlink():
                dest.unlink()
            shutil.copy2(p, dest)

    def clear(self) -> None:
        if self._outputs_dir.exists():
            shutil.rmtree(self._outputs_dir)
