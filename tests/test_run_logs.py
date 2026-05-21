"""End-to-end coverage of per-task log capture, `run.json` manifest,
``--log-dir`` override, and retention pruning.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntask import task
from ntask._executor import ExecutionConfig, Executor
from ntask._registry import default_registry


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


async def test_python_print_is_captured_to_per_task_log(tmp_path: Path):
    """Raw print() output from a task body lands in the task's log file."""
    @task
    def hello():
        print("marker line from python")

    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    await Executor(default_registry(), cfg).run(["hello"])

    runs = tmp_path / ".ntask" / "runs"
    run_dir = next(runs.iterdir())
    log = (run_dir / "hello.log").read_text(encoding="utf-8")
    assert "marker line from python" in log


async def test_python_print_log_capture_survives_stdout_redirection(
    tmp_path: Path, capfd
):
    """Even when the surrounding stdout is consumed by pytest's capfd, the
    file is the authoritative record."""
    @task
    def hello():
        print("marker survives")

    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    await Executor(default_registry(), cfg).run(["hello"])

    capfd.readouterr()  # drain the captured stream

    run_dir = next((tmp_path / ".ntask" / "runs").iterdir())
    log = (run_dir / "hello.log").read_text(encoding="utf-8")
    assert "marker survives" in log


async def test_run_manifest_records_counts_and_durations(tmp_path: Path):
    @task
    def alpha():
        pass

    @task(deps=[alpha])
    def beta():
        pass

    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    result = await Executor(default_registry(), cfg).run(["beta"])

    run_dir = next((tmp_path / ".ntask" / "runs").iterdir())
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert manifest["summary"] == {
        "ran": 2, "cached": 0, "failed": 0, "skipped": 0,
    }
    assert manifest["targets"] == ["beta"]
    fqn_to_state = {t["fqn"]: t["state"] for t in manifest["tasks"]}
    assert fqn_to_state == {"alpha": "ran", "beta": "ran"}
    # Per-task durations are populated for tasks that actually ran.
    for entry in manifest["tasks"]:
        assert isinstance(entry["duration"], (int, float))
        assert entry["log"] == f"{entry['fqn']}.log"

    # The RunResult also surfaces the run dir for callers.
    assert result.run_dir == run_dir


async def test_log_dir_override_redirects_runs_dir(tmp_path: Path):
    custom = tmp_path / "custom_logs"

    @task
    def t():
        pass

    cfg = ExecutionConfig(
        root=tmp_path, concurrency=1, log_dir=custom,
    )
    await Executor(default_registry(), cfg).run(["t"])

    # Nothing landed under the default .ntask/runs path...
    assert not (tmp_path / ".ntask" / "runs").exists()
    # ...but the custom dir has exactly one run.
    assert custom.is_dir()
    assert len(list(custom.iterdir())) == 1


async def test_max_runs_prunes_oldest_run_dirs(tmp_path: Path):
    runs_root = tmp_path / ".ntask" / "runs"
    # Seed three "old" run dirs whose names sort before any real run id.
    for stale in ("00000000T000000-001Z", "00000000T000000-002Z", "00000000T000000-003Z"):
        (runs_root / stale).mkdir(parents=True, exist_ok=True)

    @task
    def t():
        pass

    # Retain only 2 (including the current run), so the two oldest seeds
    # should be evicted, leaving the most recent seed plus the new run.
    cfg = ExecutionConfig(root=tmp_path, concurrency=1, max_runs=2)
    await Executor(default_registry(), cfg).run(["t"])

    remaining = sorted(p.name for p in runs_root.iterdir())
    assert len(remaining) == 2
    assert "00000000T000000-003Z" in remaining
    # The new run dir is the lexically-largest entry.
    assert remaining[-1] != "00000000T000000-003Z"


async def test_max_runs_zero_disables_retention(tmp_path: Path):
    runs_root = tmp_path / ".ntask" / "runs"
    (runs_root / "00000000T000000-001Z").mkdir(parents=True)

    @task
    def t():
        pass

    cfg = ExecutionConfig(root=tmp_path, concurrency=1, max_runs=0)
    await Executor(default_registry(), cfg).run(["t"])

    # Seed survived because retention was disabled.
    assert (runs_root / "00000000T000000-001Z").is_dir()


def test_logtee_silent_capture_blocks_underlying_write_keeps_log_file(
    tmp_path: Path,
):
    """Regression: under the TUI the stdout/stderr tee must NOT write to
    the underlying stream — Textual owns stdout but not stderr, so a
    logging-to-stderr handler used to spill JSON over the live DAG view.
    The per-task log file must still receive everything.
    """
    from io import StringIO

    from ntask._logio import _LogTee
    from ntask._shell import _current_log_file, _current_silent_capture

    underlying = StringIO()
    tee = _LogTee(underlying)
    log_path = tmp_path / "task.log"

    log_token = _current_log_file.set(log_path)
    silent_token = _current_silent_capture.set(True)
    try:
        n = tee.write('{"timestamp": "2026-05-21T12:24:06", "level": "info"}\n')
        tee.flush()
    finally:
        _current_silent_capture.reset(silent_token)
        _current_log_file.reset(log_token)

    # Caller still sees a "successful" write.
    assert n > 0
    # The terminal-side stream stayed empty — this is the regression.
    assert underlying.getvalue() == ""
    # The log file got the line.
    assert '"timestamp"' in log_path.read_text(encoding="utf-8")


def test_logtee_non_silent_mode_still_writes_to_underlying(tmp_path: Path):
    """In line-renderer mode (silent=False) the tee must still mirror to
    the underlying stream so terminal output survives, and also to the
    log file."""
    from io import StringIO

    from ntask._logio import _LogTee
    from ntask._shell import _current_log_file

    underlying = StringIO()
    tee = _LogTee(underlying)
    log_path = tmp_path / "task.log"

    token = _current_log_file.set(log_path)
    try:
        tee.write("visible-on-terminal\n")
    finally:
        _current_log_file.reset(token)

    assert "visible-on-terminal" in underlying.getvalue()
    assert "visible-on-terminal" in log_path.read_text(encoding="utf-8")


async def test_executor_silent_capture_under_lifecycle_renderer(tmp_path: Path):
    """End-to-end: when a lifecycle (TUI-style) renderer is active, a
    task that writes to stderr must not reach the captured stderr stream,
    but the per-task log must still contain the line.
    """
    import sys as _sys

    @task
    def emit_log():
        print("structured-log-line", file=_sys.stderr)

    # Minimal stub that looks like the TUI to the executor (has start/stop).
    class _StubLifecycleRenderer:
        def start(self, *, graph, logs_dir): pass
        def stop(self): pass
        def on_running(self, fqn, *, cmd): pass
        def on_ok(self, fqn, *, duration): pass
        def on_cached(self, fqn, *, key, source="local"): pass
        def on_miss_reason(self, fqn, *, report): pass
        def on_failed(self, fqn, *, error, tail_lines): pass
        def summary(self, **kwargs): pass

    # Capture the *underlying* stderr that the executor will save & wrap.
    from io import StringIO
    saved = _sys.stderr
    fake_stderr = StringIO()
    _sys.stderr = fake_stderr
    try:
        cfg = ExecutionConfig(
            root=tmp_path, concurrency=1,
            renderer=_StubLifecycleRenderer(),
        )
        await Executor(default_registry(), cfg).run(["emit_log"])
    finally:
        _sys.stderr = saved

    # The line must NOT have reached the underlying stderr — that's
    # where Textual is rendering and it would corrupt the TUI.
    assert "structured-log-line" not in fake_stderr.getvalue()

    # The log file still has it.
    run_dir = next((tmp_path / ".ntask" / "runs").iterdir())
    log = (run_dir / "emit_log.log").read_text(encoding="utf-8")
    assert "structured-log-line" in log
