from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ntask import cached, task
from ntask._executor import ExecutionConfig
from ntask._registry import default_registry
from ntask._watch import watch_loop


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


def _make_awatch_factory(event_batches: list[set[tuple[int, str]]] | None = None,
                         raise_after: int = 0):
    """Return a fake awatch factory that yields ``event_batches`` then raises
    KeyboardInterrupt (or StopAsyncIteration if raise_after is negative).
    """
    batches = event_batches or []

    def factory(path, *args, **kwargs):
        async def _gen() -> AsyncIterator[set[tuple[int, str]]]:
            for b in batches:
                yield b
            if raise_after >= 0:
                raise KeyboardInterrupt()

        return _gen()

    return factory


async def test_watch_requires_cached_task(tmp_path: Path):
    @task
    def bare(): pass

    t = default_registry().get("bare")
    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    with pytest.raises(ValueError, match="not @cached"):
        await watch_loop(
            task_obj=t, task_kwargs={}, workspace=tmp_path, config=cfg,
            awatch_factory=_make_awatch_factory(),
        )


async def test_watch_initial_run_executes_once(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    t = default_registry().get("build")
    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    await watch_loop(
        task_obj=t, task_kwargs={}, workspace=tmp_path, config=cfg,
        awatch_factory=_make_awatch_factory(),
    )
    assert runs["build"] == 1


async def test_watch_reruns_on_relevant_change(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    t = default_registry().get("build")
    cfg = ExecutionConfig(root=tmp_path, concurrency=1)

    # Fake factory that modifies x.py content BEFORE yielding the event - this
    # simulates a real file edit so the rerun's cache-key legitimately misses.
    def factory(path, *args, **kwargs):
        async def _gen():
            (tmp_path / "x.py").write_text("v2")
            yield {(2, str(tmp_path / "x.py"))}
            raise KeyboardInterrupt()
        return _gen()

    await watch_loop(
        task_obj=t, task_kwargs={}, workspace=tmp_path, config=cfg,
        awatch_factory=factory,
    )
    assert runs["build"] == 2  # initial + one rerun (cache-miss driven)


async def test_watch_ignores_irrelevant_change(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    (tmp_path / "README.md").write_text("readme")
    runs = {"build": 0}

    @task
    @cached(inputs=["*.py"])  # README.md doesn't match
    def build(): runs["build"] += 1

    t = default_registry().get("build")
    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    batches = [{(2, str(tmp_path / "README.md"))}]
    await watch_loop(
        task_obj=t, task_kwargs={}, workspace=tmp_path, config=cfg,
        awatch_factory=_make_awatch_factory(batches),
    )
    assert runs["build"] == 1  # only initial


async def test_watch_ignores_gitignored_change(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    (tmp_path / ".gitignore").write_text("build/\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "thing.py").write_text("out")
    runs = {"build_task": 0}

    @task
    @cached(inputs=["**/*.py"])
    def build_task(): runs["build_task"] += 1

    t = default_registry().get("build_task")
    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    batches = [{(2, str(tmp_path / "build" / "thing.py"))}]
    await watch_loop(
        task_obj=t, task_kwargs={}, workspace=tmp_path, config=cfg,
        awatch_factory=_make_awatch_factory(batches),
    )
    assert runs["build_task"] == 1  # gitignored file rejected


async def test_watch_catches_task_failure_and_continues(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    attempts = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build():
        attempts["build"] += 1
        raise RuntimeError("boom")

    t = default_registry().get("build")
    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    batches = [{(2, str(tmp_path / "x.py"))}]
    # Initial run raises; watch must continue to the yielded change.
    await watch_loop(
        task_obj=t, task_kwargs={}, workspace=tmp_path, config=cfg,
        awatch_factory=_make_awatch_factory(batches),
    )
    assert attempts["build"] == 2  # initial (failed) + rerun (also failed)


async def test_watch_rerun_cache_hits_when_content_unchanged(tmp_path: Path):
    """A watch event for a file whose content didn't actually change should
    result in a cache HIT on the rerun, not a forced re-execution. This is
    the documented behavior per spec §6.2."""
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    t = default_registry().get("build")
    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    # Fake factory yields a "change" event but x.py's content is NOT modified.
    batches = [{(2, str(tmp_path / "x.py"))}]
    await watch_loop(
        task_obj=t, task_kwargs={}, workspace=tmp_path, config=cfg,
        awatch_factory=_make_awatch_factory(batches),
    )
    assert runs["build"] == 1, (
        "Expected cache-hit on rerun: runs should stay at 1 because x.py content "
        "was unchanged (same bytes). force=True would incorrectly increment to 2."
    )
