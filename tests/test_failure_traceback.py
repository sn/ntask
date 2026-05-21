"""Traceback formatting on task failure (``--tb`` modes)."""
from __future__ import annotations

from pathlib import Path

import pytest

from ntask import task
from ntask._executor import (
    ExecutionConfig,
    Executor,
    _emit_failure_traceback,
    _format_traceback,
)
from ntask._registry import default_registry


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


def _raise_at_known_location() -> BaseException:
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        return exc


def test_format_traceback_none() -> None:
    assert _format_traceback(_raise_at_known_location(), "none") == ""


def test_format_traceback_line_has_exc_name_and_message() -> None:
    out = _format_traceback(_raise_at_known_location(), "line")
    assert out.rstrip() == "RuntimeError: boom"


def test_format_traceback_short_includes_file_and_line() -> None:
    out = _format_traceback(_raise_at_known_location(), "short")
    # File path + line + exc type + message.
    assert "test_failure_traceback.py" in out
    assert "RuntimeError: boom" in out
    # No frame listing beyond the deepest one.
    assert "Traceback" not in out


def test_format_traceback_long_includes_traceback_header() -> None:
    out = _format_traceback(_raise_at_known_location(), "long")
    assert "Traceback (most recent call last):" in out
    assert "RuntimeError: boom" in out


def test_emit_failure_traceback_writes_full_traceback_to_log_file(
    tmp_path: Path, capsys
) -> None:
    log = tmp_path / "task.log"
    log.write_text("preamble\n", encoding="utf-8")
    _emit_failure_traceback(
        fqn="my_task",
        exc=_raise_at_known_location(),
        mode="none",  # stderr is silent — log file should still get the TB
        log_path=log,
    )
    captured = capsys.readouterr()
    assert captured.err == ""  # `none` suppresses stderr emission
    contents = log.read_text(encoding="utf-8")
    assert "preamble\n" in contents
    assert "--- traceback (my_task) ---" in contents
    assert "RuntimeError: boom" in contents


def test_emit_failure_traceback_writes_short_form_to_stderr(
    tmp_path: Path, capsys
) -> None:
    log = tmp_path / "task.log"
    _emit_failure_traceback(
        fqn="my_task",
        exc=_raise_at_known_location(),
        mode="short",
        log_path=log,
    )
    err = capsys.readouterr().err
    assert "RuntimeError: boom" in err
    assert "test_failure_traceback.py" in err
    # Short form is one-line; no traceback header.
    assert "Traceback" not in err


async def test_executor_streams_traceback_to_stderr_on_failure(
    tmp_path: Path, capfd
) -> None:
    @task
    def boom():
        raise RuntimeError("kaboom")

    cfg = ExecutionConfig(root=tmp_path, concurrency=1, tb="short")
    with pytest.raises(ExceptionGroup):
        await Executor(default_registry(), cfg).run(["boom"])

    err = capfd.readouterr().err
    assert "RuntimeError: kaboom" in err


async def test_executor_writes_full_traceback_to_per_task_log(
    tmp_path: Path
) -> None:
    @task
    def boom():
        raise RuntimeError("kaboom")

    cfg = ExecutionConfig(root=tmp_path, concurrency=1, tb="none")
    with pytest.raises(ExceptionGroup):
        await Executor(default_registry(), cfg).run(["boom"])

    runs = tmp_path / ".ntask" / "runs"
    run_dir = next(runs.iterdir())
    contents = (run_dir / "boom.log").read_text(encoding="utf-8")
    assert "--- traceback (boom) ---" in contents
    assert "RuntimeError: kaboom" in contents
