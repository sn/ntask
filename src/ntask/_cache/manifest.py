from __future__ import annotations

import os
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path

import pathspec
from pathspec.pattern import Pattern

from .hash import FileHash, hash_many, hash_many_files

_GLOB_CHARS = frozenset("*?[\\")

# Directories that never hold task inputs or outputs.
_ALWAYS_SKIP = frozenset({".git"})


@dataclass(frozen=True, slots=True)
class InputManifest:
    files: list[FileHash]
    digest: str


def _load_gitignore(root: Path) -> pathspec.PathSpec[Pattern] | None:
    gi = root / ".gitignore"
    if not gi.is_file():
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text().splitlines())


def _walk_prefixes(patterns: Collection[str]) -> list[str]:
    """Return the relative directories a walk must cover to see every match.

    A pattern anchored to a literal directory (``src/**/*.py``, ``/docs/x``)
    can only match under that directory, so the walk can start there. A
    pattern with no directory part (``*.py``, ``dist/``) matches at any depth,
    which forces a walk of the whole tree (returned as ``""``).
    """
    prefixes: set[str] = set()
    for raw in patterns:
        pat = raw.strip()
        if not pat or pat.startswith(("#", "!")):
            continue  # comments and negations never add matches
        pat = pat.lstrip("/")
        parts = pat.rstrip("/").split("/")
        if "/" not in raw.strip().rstrip("/"):
            return [""]  # unanchored: may match anywhere
        literal: list[str] = []
        for part in parts[:-1]:
            if any(c in _GLOB_CHARS for c in part):
                break
            literal.append(part)
        if not literal:
            return [""]
        prefixes.add("/".join(literal))
    # Drop prefixes nested under another prefix so nothing is walked twice.
    ordered = sorted(prefixes)
    kept: list[str] = []
    for p in ordered:
        if not any(p == k or p.startswith(k + "/") for k in kept):
            kept.append(p)
    return kept


def iter_matching_files(
    patterns: Collection[str],
    *,
    root: Path,
    ignore: pathspec.PathSpec[Pattern] | None = None,
    exclude: Collection[Path] = (),
) -> Iterator[Path]:
    """Yield files under ``root`` whose relative path matches ``patterns``.

    Directories matched by ``ignore`` (a gitignore spec), ``.git``, and any
    directory in ``exclude`` are pruned during the walk instead of being
    filtered after it, so large ignored trees (``venv/``, ``node_modules/``)
    cost nothing.
    """
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    excluded = {os.path.normpath(p.resolve()) for p in exclude}
    for prefix in _walk_prefixes(patterns):
        top = root / prefix if prefix else root
        if not top.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            here = Path(dirpath)
            rel_dir = here.relative_to(root).as_posix()
            rel_dir = "" if rel_dir == "." else rel_dir
            keep: list[str] = []
            for d in dirnames:
                if d in _ALWAYS_SKIP:
                    continue
                rel = f"{rel_dir}/{d}" if rel_dir else d
                if ignore is not None and ignore.match_file(rel + "/"):
                    continue
                if excluded and os.path.normpath((here / d).resolve()) in excluded:
                    continue
                keep.append(d)
            dirnames[:] = keep
            for name in filenames:
                rel = f"{rel_dir}/{name}" if rel_dir else name
                if not spec.match_file(rel):
                    continue
                if ignore is not None and ignore.match_file(rel):
                    continue
                p = here / name
                if p.is_file():
                    yield p


def compute_input_manifest(
    patterns: list[str] | tuple[str, ...],
    *,
    root: Path,
    respect_gitignore: bool = True,
    exclude: Collection[Path] = (),
) -> InputManifest:
    if not patterns:
        return InputManifest(files=[], digest=hash_many([b"<empty-manifest>"]))

    ignore = _load_gitignore(root) if respect_gitignore else None
    candidates = set(
        iter_matching_files(patterns, root=root, ignore=ignore, exclude=exclude),
    )

    file_hashes = hash_many_files(sorted(candidates))
    parts: list[bytes] = []
    for fh in file_hashes:
        rel_str: str = fh.path.relative_to(root).as_posix()
        parts.append(rel_str.encode())
        parts.append(fh.digest.encode())
        parts.append(str(fh.mode).encode())
    digest = hash_many(parts) if parts else hash_many([b"<empty-manifest>"])
    return InputManifest(files=file_hashes, digest=digest)
