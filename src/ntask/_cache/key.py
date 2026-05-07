from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from .hash import hash_many

FORMAT_VERSION = b"ntask/v1"


@dataclass(frozen=True, slots=True)
class CacheKeyInputs:
    task_fqn: str
    task_body_hash: str
    env: dict[str, str]
    env_names: tuple[str, ...]
    input_patterns: tuple[str, ...]
    input_manifest_digest: str
    root: Path
    upstream_keys: tuple[str, ...]
    strict: bool = True


def _python_version_tuple() -> bytes:
    return ".".join(str(x) for x in sys.version_info[:3]).encode()


def _platform_tag() -> bytes:
    return f"{platform.system()}-{platform.machine()}".lower().encode()


def compute_cache_key(inp: CacheKeyInputs) -> str:
    parts: list[bytes] = [
        FORMAT_VERSION,
        inp.task_fqn.encode(),
        inp.task_body_hash.encode() if inp.strict else b"<body-unstrict>",
        _python_version_tuple() if inp.strict else b"<py-unstrict>",
        _platform_tag() if inp.strict else b"<plat-unstrict>",
    ]
    env_parts: list[str] = []
    for name in sorted(inp.env_names):
        val = inp.env.get(name)
        env_parts.append(f"{name}={'<unset>' if val is None else val}")
    parts.append("\n".join(env_parts).encode())
    parts.extend(p.encode() for p in sorted(inp.input_patterns))
    parts.append(inp.input_manifest_digest.encode())
    parts.extend(k.encode() for k in inp.upstream_keys)
    return hash_many(parts)


@dataclass(frozen=True, slots=True)
class InputRecord:
    path: str
    digest: str
    mode: int


@dataclass(frozen=True, slots=True)
class CacheBreakdown:
    input_patterns: tuple[str, ...]
    inputs: tuple[InputRecord, ...]
    env_values: dict[str, str]
    task_body_hash: str
    python_version: str
    platform_tag: str
    upstream_keys_by_dep: dict[str, str]
