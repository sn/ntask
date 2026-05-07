"""End-to-end remote cache integration: two project workspaces sharing a LocalFS remote."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ntask import cached, task
from ntask._executor import ExecutionConfig, Executor
from ntask._registry import default_registry
from ntask._remote.local_fs import LocalFSBackend


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


async def test_remote_cache_hit_on_second_machine_simulation(tmp_path: Path):
    """Machine A populates the remote; machine B gets remote hit with no local cache."""
    import ntask._executor as executor_mod

    (tmp_path / "x.py").write_text("v1")
    remote_dir = tmp_path / "shared-remote"
    remote_dir.mkdir()

    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    # Patch Executor so it uses our remote without needing pyproject config.
    original = executor_mod.Executor.__init__
    def _init(self, registry, config):
        from ntask._cache import CacheEngine
        self.registry = registry
        self.config = config
        remote = None if config.offline else LocalFSBackend(root=remote_dir)
        self.cache = CacheEngine(root=config.root / ".ntask", remote=remote)
    executor_mod.Executor.__init__ = _init
    try:
        # "Machine A" run - first time, miss, populate remote.
        cfg_a = ExecutionConfig(root=tmp_path, concurrency=1)
        await Executor(default_registry(), cfg_a).run(["build"])
        assert runs["build"] == 1

        # Simulate machine B: wipe the local cache.
        shutil.rmtree(tmp_path / ".ntask" / "cache")

        # "Machine B" run - remote hit, no re-execution.
        runs["build"] = 0
        await Executor(default_registry(), cfg_a).run(["build"])
        assert runs["build"] == 0
    finally:
        executor_mod.Executor.__init__ = original


async def test_remote_uploads_outputs(tmp_path: Path):
    """Task with outputs - the tar.gz appears on the remote after run."""
    import ntask._executor as executor_mod

    (tmp_path / "x.py").write_text("v1")
    remote_dir = tmp_path / "shared-remote"
    remote_dir.mkdir()

    @task
    @cached(inputs=["x.py"], outputs=["dist/*"])
    def build():
        dist = tmp_path / "dist"
        dist.mkdir(exist_ok=True)
        (dist / "artifact.txt").write_text("result")

    original = executor_mod.Executor.__init__
    def _init(self, registry, config):
        from ntask._cache import CacheEngine
        self.registry = registry
        self.config = config
        self.cache = CacheEngine(
            root=config.root / ".ntask",
            remote=LocalFSBackend(root=remote_dir),
        )
    executor_mod.Executor.__init__ = _init
    try:
        cfg = ExecutionConfig(root=tmp_path, concurrency=1)
        await Executor(default_registry(), cfg).run(["build"])

        # Remote should now contain at least one output blob.
        outputs_dir = remote_dir / "outputs"
        assert outputs_dir.is_dir()
        tars = list(outputs_dir.glob("*.tar.gz"))
        assert len(tars) >= 1
    finally:
        executor_mod.Executor.__init__ = original


async def test_remote_error_falls_back_with_warning(tmp_path: Path, capsys):
    """Remote that raises on get_entry → one warning → task runs locally."""
    import ntask._cache as cache_mod
    import ntask._executor as executor_mod

    cache_mod._remote_warn_fired = False

    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    broken = MagicMock()
    broken.get_entry.side_effect = RuntimeError("network down")
    broken.has_entry.return_value = False
    broken.put_entry.side_effect = RuntimeError("network down")
    broken.has_output.return_value = False
    broken.get_output.side_effect = RuntimeError("network down")
    broken.put_output.side_effect = RuntimeError("network down")

    original = executor_mod.Executor.__init__
    def _init(self, registry, config):
        from ntask._cache import CacheEngine
        self.registry = registry
        self.config = config
        self.cache = CacheEngine(root=config.root / ".ntask", remote=broken)
    executor_mod.Executor.__init__ = _init
    try:
        cfg = ExecutionConfig(root=tmp_path, concurrency=1)
        await Executor(default_registry(), cfg).run(["build"])
        assert runs["build"] == 1

        err = capsys.readouterr().err.lower()
        assert "remote cache unreachable" in err or "remote cache" in err
    finally:
        executor_mod.Executor.__init__ = original
        cache_mod._remote_warn_fired = False
