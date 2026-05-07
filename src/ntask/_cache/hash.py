from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import xxhash


def hash_bytes(data: bytes) -> str:
    return xxhash.xxh3_128(data).hexdigest()


def hash_many(parts: list[bytes]) -> str:
    h = xxhash.xxh3_128()
    for p in parts:
        h.update(len(p).to_bytes(8, "little"))
        h.update(p)
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class FileHash:
    path: Path
    digest: str
    mode: int


def hash_file(path: Path) -> FileHash:
    h = xxhash.xxh3_128()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):  # 1 MiB
            h.update(chunk)
    st = path.stat()
    return FileHash(path=path, digest=h.hexdigest(), mode=st.st_mode & 0o777)


def hash_many_files(paths: list[Path]) -> list[FileHash]:
    if not paths:
        return []
    sorted_paths = sorted(paths)
    with ThreadPoolExecutor() as ex:
        return list(ex.map(hash_file, sorted_paths))
