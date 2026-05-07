import os
import subprocess
import sys
from pathlib import Path


def _run_ntask(args, cwd):
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ntask", *args],
        cwd=cwd, capture_output=True, text=True,
        env={**os.environ},
    )


def test_end_to_end_caching_flow(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('v1')")
    (tmp_path / "tasks.py").write_text(
        "from ntask import task, cached, shell\n"
        "import sys\n"
        "@task\n"
        "@cached(inputs=['src/**/*.py'])\n"
        "def build():\n"
        "    shell([sys.executable, 'src/app.py'])\n"
    )

    p1 = _run_ntask(["build"], cwd=tmp_path)
    assert p1.returncode == 0, p1.stderr
    assert "v1" in p1.stdout

    p2 = _run_ntask(["build"], cwd=tmp_path)
    assert p2.returncode == 0, p2.stderr
    assert "cached" in (p2.stdout + p2.stderr).lower()

    (tmp_path / "src" / "app.py").write_text("print('v2')")
    p3 = _run_ntask(["build"], cwd=tmp_path)
    assert p3.returncode == 0, p3.stderr
    assert "v2" in p3.stdout


def test_end_to_end_list_and_graph(tmp_path: Path):
    (tmp_path / "tasks.py").write_text(
        "from ntask import task\n"
        "@task\n"
        "def a():\n"
        "    '''Task A.'''\n"
        "@task(deps=[a])\n"
        "def b():\n"
        "    '''Task B.'''\n"
    )
    lst = _run_ntask(["--list"], cwd=tmp_path)
    assert lst.returncode == 0
    assert "Task A" in lst.stdout

    gr = _run_ntask(["--graph", "b"], cwd=tmp_path)
    assert gr.returncode == 0
    assert "a" in gr.stdout and "b" in gr.stdout


def test_end_to_end_shell_failure_exits_1(tmp_path: Path):
    (tmp_path / "tasks.py").write_text(
        "from ntask import task, shell\n"
        "@task\n"
        "def fail():\n"
        "    shell('exit 3')\n"
    )
    p = _run_ntask(["fail"], cwd=tmp_path)
    assert p.returncode == 1


def test_end_to_end_parallel_with_prefixed_output(tmp_path: Path):
    (tmp_path / "tasks.py").write_text(
        "from ntask import task, shell\n"
        "import sys\n"
        "@task\n"
        "def first():\n"
        "    shell([sys.executable, '-c', "
        "         'import time; time.sleep(0.1); print(\"first-done\")'])\n"
        "@task\n"
        "def second():\n"
        "    shell([sys.executable, '-c', "
        "         'import time; time.sleep(0.1); print(\"second-done\")'])\n"
        "@task(deps=[first, second])\n"
        "def both(): pass\n"
    )
    p = _run_ntask(["-j", "2", "both"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "[first]" in p.stdout
    assert "[second]" in p.stdout
    assert "first-done" in p.stdout
    assert "second-done" in p.stdout


def test_end_to_end_no_prefix_when_sequential(tmp_path: Path):
    (tmp_path / "tasks.py").write_text(
        "from ntask import task, shell\n"
        "import sys\n"
        "@task\n"
        "def solo():\n"
        "    shell([sys.executable, '-c', 'print(\"raw-output\")'])\n"
    )
    p = _run_ntask(["solo"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "raw-output" in p.stdout
    # No prefix brackets around our output in default mode.
    # (The renderer may print "running solo" etc. but the shell output line
    # "raw-output" itself should be unprefixed.)
    raw_line_present = any(
        line.strip() == "raw-output" for line in p.stdout.splitlines()
    )
    assert raw_line_present, "expected unprefixed line 'raw-output' in sequential mode"
