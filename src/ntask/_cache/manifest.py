from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pathspec
from pathspec.pattern import Pattern

from .hash import FileHash, hash_many, hash_many_files


@dataclass(frozen=True, slots=True)
class InputManifest:
    files: list[FileHash]
    digest: str


def _load_gitignore(root: Path) -> pathspec.PathSpec[Pattern] | None:
    gi = root / ".gitignore"
    if not gi.is_file():
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text().splitlines())


def compute_input_manifest(
    patterns: list[str] | tuple[str, ...],
    *,
    root: Path,
    respect_gitignore: bool = True,
) -> InputManifest:
    if not patterns:
        return InputManifest(files=[], digest=hash_many([b"<empty-manifest>"]))

    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    candidates: set[Path] = set()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if spec.match_file(rel):
            candidates.add(p)

    if respect_gitignore:
        ig = _load_gitignore(root)
        if ig is not None:
            candidates = {
                p for p in candidates if not ig.match_file(p.relative_to(root).as_posix())
            }

    file_hashes = hash_many_files(sorted(candidates))
    parts: list[bytes] = []
    for fh in file_hashes:
        rel_str: str = fh.path.relative_to(root).as_posix()
        parts.append(rel_str.encode())
        parts.append(fh.digest.encode())
        parts.append(str(fh.mode).encode())
    digest = hash_many(parts) if parts else hash_many([b"<empty-manifest>"])
    return InputManifest(files=file_hashes, digest=digest)
