"""Coverage for `--completion <shell>` / `--completion-tasks` /
`--completion-flags`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ntask._completion import completion_script


def test_bash_script_includes_function_and_complete_binding() -> None:
    script = completion_script("bash")
    assert "_ntask_complete" in script
    assert "complete -F _ntask_complete ntask" in script
    assert "ntask --completion-tasks" in script
    assert "ntask --completion-flags" in script


def test_zsh_script_has_compdef_header() -> None:
    script = completion_script("zsh")
    assert script.startswith("#compdef ntask")
    assert "ntask --completion-tasks" in script
    assert "ntask --completion-flags" in script


def test_fish_script_uses_complete_directive() -> None:
    script = completion_script("fish")
    assert "complete -c ntask" in script
    assert "__ntask_tasks" in script
    assert "__ntask_flags" in script


def test_unknown_shell_raises() -> None:
    with pytest.raises(ValueError, match="unknown shell"):
        completion_script("powershell")  # type: ignore[arg-type]


def _scaffold(tmp_path: Path, body: str) -> None:
    (tmp_path / "tasks.py").write_text(body, encoding="utf-8")


def test_completion_tasks_lists_user_tasks(tmp_path: Path) -> None:
    _scaffold(
        tmp_path,
        "from ntask import task\n"
        "@task\n"
        "def alpha(): pass\n"
        "@task\n"
        "def beta(): pass\n",
    )
    result = subprocess.run(
        [sys.executable, "-m", "ntask", "--completion-tasks"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    listed = set(result.stdout.split())
    assert {"alpha", "beta"} <= listed


def test_completion_tasks_silent_outside_project(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ntask", "--completion-tasks"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0
    # Whatever happens, no error noise should reach the shell.
    assert result.stderr == ""


def test_completion_flags_lists_task_flags(tmp_path: Path) -> None:
    _scaffold(
        tmp_path,
        "from ntask import task\n"
        "@task\n"
        "def serve(port: int = 8080, verbose: bool = False, safe: bool = True):\n"
        "    pass\n",
    )
    result = subprocess.run(
        [sys.executable, "-m", "ntask", "--completion-flags", "serve"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    flags = set(result.stdout.split())
    assert flags == {"--port", "--verbose", "--no-safe"}


def test_completion_emits_bash_via_cli(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ntask", "--completion", "bash"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "_ntask_complete" in result.stdout
