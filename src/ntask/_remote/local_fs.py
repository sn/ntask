"""Filesystem-backed remote cache (shared NFS, Docker volumes, tests)."""
from __future__ import annotations

import json
from pathlib import Path

from ._tar import extract_tar, tar_directory


class LocalFSBackend:
    """Store entries as JSON and outputs as tar.gz under a directory tree."""

    def __init__(self, *, root: Path):
        self.root = Path(root)

    def _entry_path(self, fqn: str, key: str) -> Path:
        return self.root / "entries" / fqn / f"{key}.json"

    def _output_path(self, outputs_hash: str) -> Path:
        return self.root / "outputs" / f"{outputs_hash}.tar.gz"

    def has_entry(self, fqn: str, key: str) -> bool:
        return self._entry_path(fqn, key).is_file()

    def get_entry(self, fqn: str, key: str) -> dict[str, object] | None:
        p = self._entry_path(fqn, key)
        if not p.is_file():
            return None
        return json.loads(p.read_text())  # type: ignore[no-any-return]

    def put_entry(self, fqn: str, key: str, entry: dict[str, object]) -> None:
        p = self._entry_path(fqn, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entry, indent=2))

    def has_output(self, outputs_hash: str) -> bool:
        return self._output_path(outputs_hash).is_file()

    def get_output(self, outputs_hash: str, dest_dir: Path) -> None:
        p = self._output_path(outputs_hash)
        if not p.is_file():
            raise FileNotFoundError(f"no output blob for hash {outputs_hash}")
        extract_tar(p.read_bytes(), dest_dir)

    def put_output(self, outputs_hash: str, source_dir: Path) -> None:
        p = self._output_path(outputs_hash)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(tar_directory(source_dir))
