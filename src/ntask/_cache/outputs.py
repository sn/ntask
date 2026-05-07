from __future__ import annotations

import os
import shutil
from pathlib import Path

import pathspec

from .hash import hash_many, hash_many_files


class OutputStore:
    """Content-addressed output blob store.

    Layout: ``<root>/outputs/<outputs-hash>/...`` - preserving relative paths.
    Restore uses hardlinks on POSIX, falls back to copy on Windows or cross-fs.
    """

    def __init__(self, root: Path):
        self.root = root
        self._outputs_dir = root / "outputs"

    def _hash_dir(self, digest: str) -> Path:
        return self._outputs_dir / digest

    def capture(
        self,
        patterns: list[str] | tuple[str, ...],
        *,
        root: Path,
    ) -> str | None:
        """Capture matching files into the content-addressed store, return the hash."""
        if not patterns:
            return None
        spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        matches: list[Path] = []
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if spec.match_file(rel):
                matches.append(p)
        if not matches:
            return None

        file_hashes = hash_many_files(sorted(matches))
        parts: list[bytes] = []
        for fh in file_hashes:
            rel_encoded = fh.path.relative_to(root).as_posix().encode()
            parts.append(rel_encoded)
            parts.append(fh.digest.encode())
        digest = hash_many(parts)

        target = self._hash_dir(digest)
        if target.exists():
            return digest

        target.mkdir(parents=True, exist_ok=True)
        for fh in file_hashes:
            rel_path = fh.path.relative_to(root)
            dest = target / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._link_or_copy(fh.path, dest)
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
            if dest.exists():
                dest.unlink()
            self._link_or_copy(p, dest)

    @staticmethod
    def _link_or_copy(src: Path, dest: Path) -> None:
        try:
            os.link(src, dest)
        except (OSError, NotImplementedError):
            shutil.copy2(src, dest)
