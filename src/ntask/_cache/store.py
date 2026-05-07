from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .key import CacheBreakdown, InputRecord


@dataclass(frozen=True, slots=True)
class CacheEntry:
    key: str
    outputs_hash: str | None
    duration: float
    completed_at: float
    upstream_keys: tuple[str, ...] = field(default_factory=tuple)
    breakdown: CacheBreakdown | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "key": self.key,
            "outputs_hash": self.outputs_hash,
            "duration": self.duration,
            "completed_at": self.completed_at,
            "upstream_keys": list(self.upstream_keys),
        }
        if self.breakdown is not None:
            d["breakdown"] = {
                "input_patterns": list(self.breakdown.input_patterns),
                "inputs": [
                    {"path": ir.path, "digest": ir.digest, "mode": ir.mode}
                    for ir in self.breakdown.inputs
                ],
                "env_values": dict(self.breakdown.env_values),
                "task_body_hash": self.breakdown.task_body_hash,
                "python_version": self.breakdown.python_version,
                "platform_tag": self.breakdown.platform_tag,
                "upstream_keys_by_dep": dict(self.breakdown.upstream_keys_by_dep),
            }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CacheEntry:
        bd_raw = data.get("breakdown")
        breakdown: CacheBreakdown | None = None
        if bd_raw is not None:
            bd_raw_dict = bd_raw if isinstance(bd_raw, dict) else {}
            breakdown = CacheBreakdown(
                input_patterns=tuple(bd_raw_dict.get("input_patterns", ())),
                inputs=tuple(
                    InputRecord(path=r["path"], digest=r["digest"], mode=r["mode"])
                    for r in bd_raw_dict.get("inputs", [])
                ),
                env_values=dict(bd_raw_dict.get("env_values", {})),
                task_body_hash=bd_raw_dict.get("task_body_hash", ""),
                python_version=bd_raw_dict.get("python_version", ""),
                platform_tag=bd_raw_dict.get("platform_tag", ""),
                upstream_keys_by_dep=dict(bd_raw_dict.get("upstream_keys_by_dep", {})),
            )
        return cls(
            key=data["key"],  # type: ignore[arg-type]
            outputs_hash=data["outputs_hash"],  # type: ignore[arg-type]
            duration=data["duration"],  # type: ignore[arg-type]
            completed_at=data["completed_at"],  # type: ignore[arg-type]
            upstream_keys=tuple(data.get("upstream_keys", ())),  # type: ignore[arg-type]
            breakdown=breakdown,
        )


class CacheStore:
    """On-disk cache entry store under ``<root>/cache/<fqn>/<key>.json``."""

    def __init__(self, root: Path):
        self.root = root
        self._cache_dir = root / "cache"

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def _path(self, fqn: str, key: str) -> Path:
        return self._cache_dir / fqn / f"{key}.json"

    def put(self, fqn: str, entry: CacheEntry) -> None:
        p = self._path(fqn, entry.key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entry.to_dict(), indent=2))

    def get(self, fqn: str, key: str) -> CacheEntry | None:
        p = self._path(fqn, key)
        if not p.is_file():
            return None
        return CacheEntry.from_dict(json.loads(p.read_text()))

    def has(self, fqn: str, key: str) -> bool:
        return self._path(fqn, key).is_file()

    def latest(self, fqn: str) -> CacheEntry | None:
        """Return the most recently written entry for ``fqn``, or None."""
        d = self._cache_dir / fqn
        if not d.is_dir():
            return None
        entries = list(d.glob("*.json"))
        if not entries:
            return None
        newest = max(entries, key=lambda p: p.stat().st_mtime)
        return CacheEntry.from_dict(json.loads(newest.read_text()))

    def clear(self) -> None:
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)

    def clear_all(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)
