"""Pluggable remote cache backend protocol."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class RemoteBackend(Protocol):
    """Pluggable remote cache backend. All methods are synchronous.

    Implementations raise on network/auth/IO errors. The cache layer catches
    exceptions and falls back to local-only (with one warn-once per process).
    """

    def has_entry(self, fqn: str, key: str) -> bool: ...
    def get_entry(self, fqn: str, key: str) -> dict[str, object] | None: ...
    def put_entry(self, fqn: str, key: str, entry: dict[str, object]) -> None: ...
    def has_output(self, outputs_hash: str) -> bool: ...
    def get_output(self, outputs_hash: str, dest_dir: Path) -> None: ...
    def put_output(self, outputs_hash: str, source_dir: Path) -> None: ...
