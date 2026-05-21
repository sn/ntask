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
