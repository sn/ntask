from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path

from .._remote.base import RemoteBackend
from .._task import Task
from .body import hash_task_body
from .key import CacheBreakdown, CacheKeyInputs, InputRecord, compute_cache_key
from .manifest import compute_input_manifest
from .outputs import OutputStore
from .store import CacheEntry, CacheStore

# Module-level flag for warn-once pattern.
_remote_warn_fired = False


def _warn_once_remote_failed(e: BaseException) -> None:
    """Print a single warning the first time a remote call fails in this process."""
    global _remote_warn_fired
    if not _remote_warn_fired:
        print(
            f"warning: remote cache unreachable: {type(e).__name__}: {e}. "
            f"Falling back to local.",
            file=sys.stderr,
        )
        _remote_warn_fired = True


def _python_version_str() -> str:
    return ".".join(str(x) for x in sys.version_info[:3])


def _platform_tag_str() -> str:
    return f"{platform.system()}-{platform.machine()}".lower()


class CacheEngine:
    def __init__(self, root: Path, remote: RemoteBackend | None = None):
        self.root = root
        self.store = CacheStore(root=root)
        self.outputs = OutputStore(root=root)
        self._remote = remote

    def compute_key_and_breakdown(
        self,
        t: Task,
        *,
        workspace: Path,
        upstream_keys_by_dep: dict[str, str],
    ) -> tuple[str, CacheBreakdown]:
        cfg = t.cached_config
        assert cfg is not None
        manifest = compute_input_manifest(cfg.inputs, root=workspace)
        body = hash_task_body(t.func)
        env_values = {
            name: os.environ[name] if name in os.environ else "<unset>"
            for name in cfg.env
        }
        py_version = _python_version_str()
        plat_tag = _platform_tag_str()

        # Tuple ordering for cache key matches insertion order of upstream_keys_by_dep.
        upstream_tuple = tuple(upstream_keys_by_dep.values())
        key_inputs = CacheKeyInputs(
            task_fqn=t.fqn,
            task_body_hash=body,
            env={name: ("" if v == "<unset>" else v) for name, v in env_values.items()},
            env_names=cfg.env,
            input_patterns=cfg.inputs,
            input_manifest_digest=manifest.digest,
            root=workspace,
            upstream_keys=upstream_tuple if cfg.propagate else (),
            strict=cfg.strict,
        )
        key = compute_cache_key(key_inputs)

        input_records = tuple(
            InputRecord(
                path=fh.path.relative_to(workspace).as_posix(),
                digest=fh.digest,
                mode=fh.mode,
            )
            for fh in manifest.files
        )
        breakdown = CacheBreakdown(
            input_patterns=cfg.inputs,
            inputs=input_records,
            env_values=env_values,
            task_body_hash=body,
            python_version=py_version,
            platform_tag=plat_tag,
            upstream_keys_by_dep=dict(upstream_keys_by_dep),
        )
        return key, breakdown

    def check(self, t: Task, key: str) -> CacheEntry | None:
        return self.store.get(t.fqn, key)

    def store_entry(
        self,
        t: Task,
        key: str,
        *,
        workspace: Path,
        duration: float,
        breakdown: CacheBreakdown,
        upstream_keys: tuple[str, ...],
    ) -> CacheEntry:
        cfg = t.cached_config
        assert cfg is not None
        outputs_hash = (
            self.outputs.capture(cfg.outputs, root=workspace) if cfg.outputs else None
        )
        entry = CacheEntry(
            key=key,
            outputs_hash=outputs_hash,
            duration=duration,
            completed_at=time.time(),
            upstream_keys=upstream_keys,
            breakdown=breakdown,
        )
        self.store.put(t.fqn, entry)
        return entry

    def restore_outputs(self, entry: CacheEntry, *, workspace: Path) -> None:
        if entry.outputs_hash:
            self.outputs.restore(entry.outputs_hash, root=workspace)

    def check_remote(self, t: Task, key: str) -> CacheEntry | None:
        """Try remote: if hit, download entry + outputs and populate local store."""
        if self._remote is None:
            return None
        try:
            entry_dict = self._remote.get_entry(t.fqn, key)
        except BaseException as e:
            _warn_once_remote_failed(e)
            return None
        if entry_dict is None:
            return None
        try:
            entry = CacheEntry.from_dict(entry_dict)
        except Exception as e:
            _warn_once_remote_failed(e)
            return None
        # Download outputs into the content-addressed store if needed.
        if entry.outputs_hash is not None:
            target_dir = self.outputs._hash_dir(entry.outputs_hash)
            if not target_dir.exists():
                try:
                    self._remote.get_output(entry.outputs_hash, target_dir)
                except BaseException as e:
                    _warn_once_remote_failed(e)
                    return None
        # Mirror the entry into local store so future runs short-circuit.
        self.store.put(t.fqn, entry)
        return entry

    def push_remote(self, t: Task, entry: CacheEntry) -> None:
        """Upload entry + outputs to remote. Non-fatal on error."""
        if self._remote is None:
            return
        try:
            self._remote.put_entry(t.fqn, entry.key, entry.to_dict())
        except BaseException as e:
            _warn_once_remote_failed(e)
            return
        if entry.outputs_hash is not None:
            source = self.outputs._hash_dir(entry.outputs_hash)
            if source.is_dir():
                try:
                    self._remote.put_output(entry.outputs_hash, source)
                except BaseException as e:
                    _warn_once_remote_failed(e)

