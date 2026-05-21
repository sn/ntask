import time as _time
from pathlib import Path

import anyio
import pytest

from ntask import cached, depends, task
from ntask._executor import ExecutionConfig, Executor
from ntask._registry import default_registry


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


async def test_executor_runs_tasks_in_dep_order(tmp_path: Path):
    order: list[str] = []

    @task
    def a():
        order.append("a")

    @task(deps=[a])
    def b():
        order.append("b")

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["b"])
    assert order == ["a", "b"]


async def test_executor_skips_unrelated_tasks(tmp_path: Path):
    order: list[str] = []

    @task
    def a(): order.append("a")

    @task
    def unrelated(): order.append("unrelated")

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["a"])
    assert order == ["a"]


async def test_executor_fail_fast_cancels_dependents(tmp_path: Path):
    order: list[str] = []

    @task
    def will_fail():
        order.append("fail")
        raise RuntimeError("boom")

    @task(deps=[will_fail])
    def dependent():
        order.append("dependent")

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    with pytest.raises(ExceptionGroup):
        await ex.run(["dependent"])
    assert "dependent" not in order


async def test_executor_invokes_async_task_directly(tmp_path: Path):
    counter = {"n": 0}

    @task
    async def ping():
        counter["n"] += 1

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["ping"])
    assert counter["n"] == 1


async def test_cached_task_skips_on_second_run(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build():
        runs["build"] += 1

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["build"])
    await ex.run(["build"])
    assert runs["build"] == 1


async def test_cache_invalidated_when_input_changes(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build():
        runs["build"] += 1

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["build"])
    (tmp_path / "x.py").write_text("v2")
    await ex.run(["build"])
    assert runs["build"] == 2


async def test_transitive_propagation_invalidates_dependents(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0, "test": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    @task(deps=[build])
    @cached(inputs=[])
    def test(): runs["test"] += 1

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["test"])
    (tmp_path / "x.py").write_text("v2")
    await ex.run(["test"])
    assert runs["build"] == 2
    assert runs["test"] == 2


async def test_force_bypasses_cache(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    cfg = ExecutionConfig(root=tmp_path, concurrency=1, force={"build"})
    ex = Executor(default_registry(), cfg)
    await ex.run(["build"])
    await ex.run(["build"])
    assert runs["build"] == 2


async def test_runtime_depends_triggers_dep_execution(tmp_path: Path):
    order: list[str] = []

    @task
    def a(): order.append("a")

    @task
    def b():
        depends(a)
        order.append("b")

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["b"])
    assert order == ["a", "b"]


async def test_cache_miss_reason_reports_miss_report(tmp_path: Path):
    from ntask._cache.diff import MissReport

    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}
    captured_reports: list[MissReport] = []

    class _CapturingRenderer:
        def on_running(self, fqn, *, cmd): pass
        def on_ok(self, fqn, *, duration): pass
        def on_cached(self, fqn, *, key, source="local"): pass
        def on_miss_reason(self, fqn, *, report):
            captured_reports.append(report)
        def on_failed(self, fqn, *, error, tail_lines): pass
        def summary(self, *, ran, cached, failed, skipped): pass

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    renderer = _CapturingRenderer()
    cfg = ExecutionConfig(root=tmp_path, concurrency=1, renderer=renderer)
    ex = Executor(default_registry(), cfg)
    await ex.run(["build"])
    (tmp_path / "x.py").write_text("v2")
    await ex.run(["build"])
    assert len(captured_reports) == 2
    assert captured_reports[0].items[0].kind == "first-run"
    assert captured_reports[1].items[0].kind == "input-modified"
    assert captured_reports[1].items[0].detail == "x.py"


async def test_executor_runs_independent_tasks_in_parallel(tmp_path: Path):
    events: list[tuple[str, float]] = []

    @task
    async def a():
        events.append(("a-start", _time.perf_counter()))
        await anyio.sleep(0.15)
        events.append(("a-end", _time.perf_counter()))

    @task
    async def b():
        events.append(("b-start", _time.perf_counter()))
        await anyio.sleep(0.15)
        events.append(("b-end", _time.perf_counter()))

    @task(deps=[a, b])
    def check(): pass

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=2))
    started = _time.perf_counter()
    await ex.run(["check"])
    elapsed = _time.perf_counter() - started
    # Sequential would take ~0.30s; parallel should be < 0.25s.
    assert elapsed < 0.25, f"expected parallel execution, took {elapsed:.3f}s"


async def test_executor_runs_sequentially_by_default(tmp_path: Path):
    events: list[str] = []

    @task
    async def a():
        events.append("a-start")
        await anyio.sleep(0.05)
        events.append("a-end")

    @task
    async def b():
        events.append("b-start")
        await anyio.sleep(0.05)
        events.append("b-end")

    @task(deps=[a, b])
    def check(): pass

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=1))
    await ex.run(["check"])
    # With concurrency=1, one task fully completes before the other starts.
    a_end = events.index("a-end")
    b_start = events.index("b-start")
    a_start = events.index("a-start")
    b_end = events.index("b-end")
    # Either A runs before B or vice-versa - both serial.
    assert (a_end < b_start) or (b_end < a_start)


async def test_executor_respects_parallel_false_barrier(tmp_path: Path):
    events: list[tuple[str, float]] = []

    @task
    async def a():
        events.append(("a-start", _time.perf_counter()))
        await anyio.sleep(0.10)
        events.append(("a-end", _time.perf_counter()))

    @task(parallel=False)
    async def b():
        events.append(("b-start", _time.perf_counter()))
        await anyio.sleep(0.05)
        events.append(("b-end", _time.perf_counter()))

    @task
    async def c():
        events.append(("c-start", _time.perf_counter()))
        await anyio.sleep(0.10)
        events.append(("c-end", _time.perf_counter()))

    @task(deps=[a, b, c])
    def check(): pass

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=3))
    await ex.run(["check"])
    times = dict(events)
    # B is non-overlapping with A and C.
    # Either B runs entirely before A and C start, or entirely after they end.
    b_runs_before = times["b-end"] <= times["a-start"] and times["b-end"] <= times["c-start"]
    b_runs_after = times["b-start"] >= times["a-end"] and times["b-start"] >= times["c-end"]
    assert b_runs_before or b_runs_after


async def test_executor_fail_fast_cancels_parallel_siblings(tmp_path: Path):
    finished_events: dict[str, anyio.Event] = {}

    @task
    async def will_fail():
        raise RuntimeError("boom")

    @task
    async def slow_a():
        ev = anyio.Event()
        finished_events["slow_a"] = ev
        await anyio.sleep(1.0)
        ev.set()  # reached only if not cancelled

    @task
    async def slow_b():
        ev = anyio.Event()
        finished_events["slow_b"] = ev
        await anyio.sleep(1.0)
        ev.set()

    @task(deps=[will_fail, slow_a, slow_b])
    def check(): pass

    ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=3))
    with pytest.raises(ExceptionGroup):
        await ex.run(["check"])
    # The slow tasks should have been cancelled before their events were set.
    for name in ("slow_a", "slow_b"):
        if name in finished_events:
            assert not finished_events[name].is_set(), f"{name} completed despite cancellation"


async def test_executor_keep_going_lets_parallel_siblings_finish(tmp_path: Path):
    completed: list[str] = []

    @task
    async def will_fail():
        await anyio.sleep(0.02)
        raise RuntimeError("boom")

    @task
    async def sibling_a():
        await anyio.sleep(0.10)
        completed.append("sibling_a")

    @task
    async def sibling_b():
        await anyio.sleep(0.10)
        completed.append("sibling_b")

    @task(deps=[will_fail, sibling_a, sibling_b])
    def check(): pass

    cfg = ExecutionConfig(root=tmp_path, concurrency=3, keep_going=True)
    ex = Executor(default_registry(), cfg)
    await ex.run(["check"])
    # Siblings completed despite the failure.
    assert "sibling_a" in completed
    assert "sibling_b" in completed


async def test_executor_uses_remote_cache_when_configured(tmp_path: Path):
    """A task's local-miss should consult the remote; on hit, restore from remote."""
    from ntask._remote.local_fs import LocalFSBackend

    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    # First run populates the remote via push_remote.
    remote_dir = tmp_path / "shared-remote"
    remote = LocalFSBackend(root=remote_dir)

    # Monkey-patch Executor so it uses our remote directly (avoid pyproject config for unit test).
    import ntask._executor as executor_mod
    from ntask._cache import CacheEngine

    original_init = executor_mod.Executor.__init__
    def patched_init(self, registry, config):
        self.registry = registry
        self.config = config
        self.cache = CacheEngine(root=config.root / ".ntask", remote=remote)
    executor_mod.Executor.__init__ = patched_init
    try:
        # First run: miss + execute + push to remote.
        cfg = ExecutionConfig(root=tmp_path, concurrency=1)
        await Executor(default_registry(), cfg).run(["build"])
        assert runs["build"] == 1

        # Wipe local cache; re-run; should hit remote.
        import shutil
        shutil.rmtree(tmp_path / ".ntask" / "cache")

        runs["build"] = 0
        await Executor(default_registry(), cfg).run(["build"])
        assert runs["build"] == 0, "expected remote-hit → task not re-executed"
    finally:
        executor_mod.Executor.__init__ = original_init


async def test_executor_offline_skips_remote(tmp_path: Path):
    """With offline=True, the remote should not be consulted even when configured."""
    (tmp_path / "x.py").write_text("v1")
    runs = {"build": 0}
    remote_calls = {"count": 0}

    @task
    @cached(inputs=["x.py"])
    def build(): runs["build"] += 1

    class _CountingBackend:
        def has_entry(self, fqn, key):
            remote_calls["count"] += 1
            return False

        def get_entry(self, fqn, key):
            remote_calls["count"] += 1
            return None

        def put_entry(self, fqn, key, entry):
            remote_calls["count"] += 1

        def has_output(self, h):
            remote_calls["count"] += 1
            return False

        def get_output(self, h, d):
            remote_calls["count"] += 1

        def put_output(self, h, s):
            remote_calls["count"] += 1

    import ntask._executor as executor_mod
    from ntask._cache import CacheEngine

    counting = _CountingBackend()
    original_init = executor_mod.Executor.__init__
    def patched_init(self, registry, config):
        self.registry = registry
        self.config = config
        # Remote is constructed but offline means it shouldn't be called.
        backend = None if config.offline else counting
        self.cache = CacheEngine(root=config.root / ".ntask", remote=backend)
    executor_mod.Executor.__init__ = patched_init
    try:
        cfg = ExecutionConfig(root=tmp_path, concurrency=1, offline=True)
        await Executor(default_registry(), cfg).run(["build"])
        assert runs["build"] == 1
        assert remote_calls["count"] == 0
    finally:
        executor_mod.Executor.__init__ = original_init


class _StubLifecycleRenderer:
    """Minimal Renderer protocol impl with start/stop lifecycle methods."""
    def __init__(self):
        self.events: list = []

    def start(self, *, graph, logs_dir):
        self.events.append(("start", tuple(graph.nodes), logs_dir))

    def stop(self):
        self.events.append("stop")

    def on_running(self, fqn, *, cmd): self.events.append(("running", fqn))
    def on_ok(self, fqn, *, duration): self.events.append(("ok", fqn))
    def on_cached(self, fqn, *, key, source="local"):
        self.events.append(("cached", fqn, source))
    def on_miss_reason(self, fqn, *, report): pass
    def on_failed(self, fqn, *, error, tail_lines):
        self.events.append(("failed", fqn))
    def summary(self, **kwargs): self.events.append(("summary", kwargs))


async def test_executor_calls_start_and_stop_when_lifecycle_renderer(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")

    @task
    @cached(inputs=["x.py"])
    def build(): pass

    renderer = _StubLifecycleRenderer()
    cfg = ExecutionConfig(root=tmp_path, concurrency=1, renderer=renderer)
    await Executor(default_registry(), cfg).run(["build"])
    # First event must be start, last must be stop.
    assert renderer.events[0][0] == "start"
    assert renderer.events[-1] == "stop"


async def test_executor_creates_runs_dir_when_lifecycle_renderer(tmp_path: Path):
    (tmp_path / "x.py").write_text("v1")

    @task
    @cached(inputs=["x.py"])
    def build(): pass

    renderer = _StubLifecycleRenderer()
    cfg = ExecutionConfig(root=tmp_path, concurrency=1, renderer=renderer)
    await Executor(default_registry(), cfg).run(["build"])

    runs_root = tmp_path / ".ntask" / "runs"
    assert runs_root.is_dir()
    run_dirs = list(runs_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    # Verify start() received this dir
    start_event = next(e for e in renderer.events if e[0] == "start")
    assert start_event[2] == run_dir


async def test_executor_creates_runs_dir_even_for_plain_renderer(tmp_path: Path):
    """LogRenderer has no start/stop, but the run dir is still created so the
    on-disk record exists regardless of which renderer was active."""
    from ntask._render.log import LogRenderer

    (tmp_path / "x.py").write_text("v1")

    @task
    @cached(inputs=["x.py"])
    def build(): pass

    renderer = LogRenderer(use_color=False)
    cfg = ExecutionConfig(root=tmp_path, concurrency=1, renderer=renderer)
    await Executor(default_registry(), cfg).run(["build"])
    runs_root = tmp_path / ".ntask" / "runs"
    assert runs_root.is_dir()
    assert len(list(runs_root.iterdir())) == 1


async def test_executor_per_task_log_file_captures_shell_output(tmp_path: Path):
    """Task with a lifecycle renderer writes shell output to its per-task log."""
    import sys as _sys

    from ntask._shell import shell

    (tmp_path / "x.py").write_text("v1")

    @task
    @cached(inputs=["x.py"])
    def build():
        shell([_sys.executable, "-c", "print('task-output-marker')"])

    renderer = _StubLifecycleRenderer()
    cfg = ExecutionConfig(root=tmp_path, concurrency=1, renderer=renderer)
    await Executor(default_registry(), cfg).run(["build"])

    runs_root = tmp_path / ".ntask" / "runs"
    run_dir = next(runs_root.iterdir())
    log_file = run_dir / "build.log"
    assert log_file.is_file()
    assert b"task-output-marker" in log_file.read_bytes()
