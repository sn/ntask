from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ntask._cache import CacheEngine
from ntask._cache.key import CacheBreakdown
from ntask._cache.store import CacheEntry
from ntask._remote.local_fs import LocalFSBackend
from ntask._task import CachedConfig, Task


def _sample_task(fqn: str = "build") -> Task:
    def fn(): pass
    return Task(
        fqn=fqn, func=fn, deps=(), concurrency=None, parallel=True,
        cached_config=CachedConfig(inputs=(), outputs=(), env=(), propagate=True, strict=True),
        group=None,
    )


def _sample_entry(key: str = "k1") -> CacheEntry:
    bd = CacheBreakdown(
        input_patterns=(), inputs=(), env_values={},
        task_body_hash="body", python_version="3.12.3",
        platform_tag="linux-x86_64", upstream_keys_by_dep={},
    )
    return CacheEntry(
        key=key, outputs_hash=None, duration=0.1,
        completed_at=100.0, upstream_keys=(), breakdown=bd,
    )


def test_check_remote_returns_none_when_no_remote(tmp_path: Path):
    engine = CacheEngine(root=tmp_path / ".ntask")
    assert engine.check_remote(_sample_task(), "k1") is None


def test_check_remote_hit_populates_local_cache(tmp_path: Path):
    remote = LocalFSBackend(root=tmp_path / "remote")
    # Pre-populate remote with an entry.
    entry = _sample_entry()
    remote.put_entry("build", "k1", entry.to_dict())

    engine = CacheEngine(root=tmp_path / ".ntask", remote=remote)
    result = engine.check_remote(_sample_task(), "k1")
    assert result is not None
    assert result.key == "k1"
    # And the local store should now have it too.
    assert engine.store.has("build", "k1")


def test_check_remote_miss_returns_none(tmp_path: Path):
    remote = LocalFSBackend(root=tmp_path / "remote")
    engine = CacheEngine(root=tmp_path / ".ntask", remote=remote)
    assert engine.check_remote(_sample_task(), "absent") is None


def test_push_remote_uploads_entry(tmp_path: Path):
    remote = LocalFSBackend(root=tmp_path / "remote")
    engine = CacheEngine(root=tmp_path / ".ntask", remote=remote)
    entry = _sample_entry()
    engine.push_remote(_sample_task(), entry)
    assert remote.has_entry("build", "k1")


def test_push_remote_with_outputs_uploads_tar(tmp_path: Path):
    remote = LocalFSBackend(root=tmp_path / "remote")
    engine = CacheEngine(root=tmp_path / ".ntask", remote=remote)

    # Create a local output blob.
    outputs_hash = "output_h1"
    local_output_dir = engine.outputs._hash_dir(outputs_hash)
    local_output_dir.mkdir(parents=True, exist_ok=True)
    (local_output_dir / "f.txt").write_bytes(b"contents")

    bd = CacheBreakdown(
        input_patterns=(), inputs=(), env_values={},
        task_body_hash="body", python_version="3.12.3",
        platform_tag="linux-x86_64", upstream_keys_by_dep={},
    )
    entry = CacheEntry(
        key="k1", outputs_hash=outputs_hash, duration=0.1,
        completed_at=100.0, upstream_keys=(), breakdown=bd,
    )
    engine.push_remote(_sample_task(), entry)
    assert remote.has_output(outputs_hash)


def test_remote_error_warns_once_and_falls_back(tmp_path: Path, capsys):
    import ntask._cache as cache_mod

    # Reset the module-level warn flag
    cache_mod._remote_warn_fired = False

    broken = MagicMock()
    broken.get_entry.side_effect = RuntimeError("network down")

    engine = CacheEngine(root=tmp_path / ".ntask", remote=broken)
    # First failure: warning printed.
    assert engine.check_remote(_sample_task(), "k1") is None
    out = capsys.readouterr()
    assert "remote cache unreachable" in out.err.lower() or "remote cache" in out.err.lower()

    # Second failure: no additional warning.
    assert engine.check_remote(_sample_task(), "k2") is None
    out2 = capsys.readouterr()
    assert out2.err == ""
