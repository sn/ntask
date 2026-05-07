import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _write_tasks_py(tmp_dir: Path, body: str) -> None:
    (tmp_dir / "tasks.py").write_text(body)


def _run_ntask(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ntask", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ},
    )


def test_cli_list_shows_tasks(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hello():\n"
        "    '''Say hi.'''\n"
        "    print('hello')\n"
    ))
    p = _run_ntask(["--list"], cwd=tmp_path)
    assert p.returncode == 0
    assert "hello" in p.stdout
    assert "Say hi" in p.stdout


def test_cli_runs_task(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi():\n"
        "    print('from-task')\n"
    ))
    p = _run_ntask(["hi"], cwd=tmp_path)
    assert p.returncode == 0
    assert "from-task" in p.stdout


def test_cli_unknown_task_suggests(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def testing(): pass\n"
    ))
    p = _run_ntask(["tseting"], cwd=tmp_path)
    assert p.returncode in (1, 2)
    assert "did you mean" in p.stderr.lower()


def test_cli_discovery_error_exits_2(tmp_path: Path):
    p = _run_ntask(["--list"], cwd=tmp_path)
    assert p.returncode == 2


def test_cli_passes_task_args(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def greet(name: str):\n"
        "    print(f'hi {name}')\n"
    ))
    p = _run_ntask(["greet", "world"], cwd=tmp_path)
    assert p.returncode == 0
    assert "hi world" in p.stdout


def test_cli_dry_run_does_not_execute(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def write_file():\n"
        "    from pathlib import Path\n"
        "    Path('sentinel.txt').write_text('ran')\n"
    ))
    p = _run_ntask(["--dry-run", "write_file"], cwd=tmp_path)
    assert p.returncode == 0
    assert not (tmp_path / "sentinel.txt").exists()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT semantics differ on Windows")
def test_cli_ctrl_c_exits_130(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task, shell\n"
        "import sys\n"
        "@task\n"
        "def slow():\n"
        "    shell([sys.executable, '-c', 'import time; time.sleep(10)'])\n"
    ))
    p = subprocess.Popen(
        [sys.executable, "-m", "ntask", "slow"],
        cwd=tmp_path,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(0.8)
    p.send_signal(signal.SIGINT)
    p.wait(timeout=10)
    assert p.returncode == 130


def test_cli_why_no_cache_entries(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task, cached\n"
        "@task\n"
        "@cached(inputs=['x.py'])\n"
        "def build(): pass\n"
    ))
    (tmp_path / "x.py").write_text("v1")
    p = _run_ntask(["--why", "build"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "no cached entries" in p.stdout.lower()


def test_cli_why_hit_after_run(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task, cached\n"
        "@task\n"
        "@cached(inputs=['x.py'])\n"
        "def build(): pass\n"
    ))
    (tmp_path / "x.py").write_text("v1")
    # Prime the cache
    assert _run_ntask(["build"], cwd=tmp_path).returncode == 0
    # --why should report HIT
    p = _run_ntask(["--why", "build"], cwd=tmp_path)
    assert p.returncode == 0
    assert "HIT" in p.stdout


def test_cli_why_miss_after_edit(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task, cached\n"
        "@task\n"
        "@cached(inputs=['x.py'])\n"
        "def build(): pass\n"
    ))
    (tmp_path / "x.py").write_text("v1")
    assert _run_ntask(["build"], cwd=tmp_path).returncode == 0
    (tmp_path / "x.py").write_text("v2")
    p = _run_ntask(["--why", "build"], cwd=tmp_path)
    assert p.returncode == 0
    assert "MISS" in p.stdout
    assert "x.py" in p.stdout


def test_cli_why_unknown_task_exits_2(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def build(): pass\n"
    ))
    p = _run_ntask(["--why", "bild"], cwd=tmp_path)
    assert p.returncode == 2
    assert "did you mean" in p.stderr.lower()


def test_cli_why_uncached_task_exits_1(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def build(): pass\n"
    ))
    p = _run_ntask(["--why", "build"], cwd=tmp_path)
    assert p.returncode == 1
    assert "not a cached task" in p.stderr.lower() or "not cached" in p.stderr.lower()


def test_cli_j_with_value(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi():\n"
        "    print('from-task')\n"
    ))
    p = _run_ntask(["-j", "2", "hi"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "from-task" in p.stdout


def test_cli_j_bare_uses_cpu_count(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi():\n"
        "    print('bare-j')\n"
    ))
    p = _run_ntask(["-j", "hi"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "bare-j" in p.stdout


def test_cli_j_zero_exits_2(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi(): pass\n"
    ))
    p = _run_ntask(["-j", "0", "hi"], cwd=tmp_path)
    assert p.returncode == 2
    assert "must be" in p.stderr.lower() or ">=" in p.stderr


def test_cli_j_non_integer_exits_2(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi(): pass\n"
    ))
    p = _run_ntask(["-j", "abc", "hi"], cwd=tmp_path)
    assert p.returncode == 2
    assert "integer" in p.stderr.lower()


def test_cli_watch_requires_cached_task(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi(): pass\n"
    ))
    p = _run_ntask(["watch", "hi"], cwd=tmp_path)
    assert p.returncode == 2
    combined = (p.stderr + p.stdout).lower()
    assert "not @cached" in combined or "requires declared inputs" in combined


def test_cli_watch_unknown_task_exits_2(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def testing(): pass\n"
    ))
    p = _run_ntask(["watch", "tseting"], cwd=tmp_path)
    assert p.returncode == 2
    assert "did you mean" in p.stderr.lower()


def test_cli_watch_no_task_exits_2(tmp_path: Path):
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi(): pass\n"
    ))
    p = _run_ntask(["watch"], cwd=tmp_path)
    assert p.returncode == 2
    combined = (p.stderr + p.stdout).lower()
    assert "needs a task name" in combined or "task name" in combined


def test_cli_watch_initial_run_and_exit_on_sigint(tmp_path: Path):
    import signal
    import time

    _write_tasks_py(tmp_path, (
        "from ntask import task, cached\n"
        "from pathlib import Path\n"
        "@task\n"
        "@cached(inputs=['x.py'])\n"
        "def build():\n"
        "    Path('sentinel.txt').write_text('ran')\n"
    ))
    (tmp_path / "x.py").write_text("v1")

    # Windows can't deliver SIGINT to a child via Popen.send_signal; the
    # cross-platform recipe is to spawn the child in its own process group
    # and send CTRL_BREAK_EVENT, which Python's default handler converts to
    # KeyboardInterrupt the same way SIGINT does on POSIX.
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        interrupt_signal = signal.CTRL_BREAK_EVENT
    else:
        creationflags = 0
        interrupt_signal = signal.SIGINT

    proc = subprocess.Popen(
        [sys.executable, "-m", "ntask", "watch", "build"],
        cwd=tmp_path,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=creationflags,
    )

    # Wait up to 3s for the initial run to complete.
    deadline = time.time() + 3.0
    sentinel = tmp_path / "sentinel.txt"
    while time.time() < deadline:
        if sentinel.exists() and sentinel.read_text() == "ran":
            break
        time.sleep(0.05)
    assert sentinel.exists(), "initial run did not produce sentinel.txt"

    proc.send_signal(interrupt_signal)
    proc.wait(timeout=10)
    # Exit 0 on clean watch exit; POSIX may report 130 for SIGINT;
    # Windows reports 0xC000013A (STATUS_CONTROL_C_EXIT) when the runtime
    # propagates SIGBREAK out of the process without a clean handler.
    assert proc.returncode in (0, 130, 0xC000013A), \
        f"unexpected exit {proc.returncode}"


def test_cli_offline_flag_skips_remote(tmp_path: Path):
    """Config has a remote pointing at a bogus path; --offline succeeds anyway."""
    _write_tasks_py(tmp_path, (
        "from ntask import task, cached\n"
        "@task\n"
        "@cached(inputs=['x.py'])\n"
        "def build():\n"
        "    print('ran')\n"
    ))
    (tmp_path / "x.py").write_text("v1")
    # pyproject with a bogus S3 config - would fail if consulted, but --offline skips
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ntask.remote_cache]\n"
        "type = \"s3\"\n"
        "bucket = \"this-bucket-does-not-exist-ever\"\n"
    )
    p = _run_ntask(["--offline", "build"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "ran" in p.stdout


def test_cli_no_tui_flag_accepted(tmp_path: Path):
    """--no-tui should be an accepted flag; runs routed to non-TUI renderer."""
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi():\n"
        "    print('no-tui-ok')\n"
    ))
    p = _run_ntask(["--no-tui", "hi"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "no-tui-ok" in p.stdout


def test_cli_tui_config_false_routes_to_non_tui(tmp_path: Path):
    """pyproject.toml [tool.ntask] tui = false disables TUI even on TTY."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ntask]\n"
        "tui = false\n"
    )
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi():\n"
        "    print('config-disabled-tui')\n"
    ))
    p = _run_ntask(["hi"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "config-disabled-tui" in p.stdout


def test_cli_piped_output_does_not_activate_tui(tmp_path: Path):
    """When stdout is piped (not TTY), the TUI must not activate - we get plain line output."""
    _write_tasks_py(tmp_path, (
        "from ntask import task\n"
        "@task\n"
        "def hi():\n"
        "    print('piped-output-marker')\n"
    ))
    p = _run_ntask(["hi"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "piped-output-marker" in p.stdout


def test_cli_remote_config_via_pyproject_shares_cache(tmp_path: Path):
    """Two separate 'project' dirs with a shared LocalFS remote hit each other's cache."""
    shared_remote = tmp_path / "shared-remote"
    shared_remote.mkdir()

    def _init_project(dir_name: str) -> Path:
        project = tmp_path / dir_name
        project.mkdir()
        (project / "x.py").write_text("v1")
        (project / "tasks.py").write_text(
            "from ntask import task, cached\n"
            "from pathlib import Path\n"
            "@task\n"
            "@cached(inputs=['x.py'])\n"
            "def build():\n"
            "    Path('ran-marker.txt').write_text('executed')\n"
        )
        # TOML literal string ('...') so Windows backslashes in the path
        # aren't interpreted as escape sequences.
        (project / "pyproject.toml").write_text(
            "[tool.ntask.remote_cache]\n"
            "type = \"local-fs\"\n"
            f"path = '{shared_remote}'\n"
        )
        return project

    project_a = _init_project("project_a")
    project_b = _init_project("project_b")

    # Run in A - populates remote.
    pa = _run_ntask(["build"], cwd=project_a)
    assert pa.returncode == 0, pa.stderr
    assert (project_a / "ran-marker.txt").exists()

    # Run in B - should hit remote (marker file should NOT exist because B did not
    # run the task body; outputs list is empty so restoration doesn't populate it
    # either). Confirm the renderer emitted a [remote] marker.
    pb = _run_ntask(["build"], cwd=project_b)
    assert pb.returncode == 0, pb.stderr
    # Task body didn't run in B → no ran-marker.txt.
    assert not (project_b / "ran-marker.txt").exists()
    # Output should mention [remote] marker.
    combined = pb.stdout + pb.stderr
    assert "[remote]" in combined
