"""End-to-end watch test using real filesystem events via watchfiles."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def test_watch_reruns_on_file_edit_end_to_end(tmp_path: Path):
    """A real file edit during watch triggers a rerun within a few seconds."""
    tasks_py = (
        "from ntask import task, cached\n"
        "from pathlib import Path\n"
        "@task\n"
        "@cached(inputs=['x.py'])\n"
        "def build():\n"
        "    c = Path('counter.txt')\n"
        "    current = int(c.read_text()) if c.exists() else 0\n"
        "    c.write_text(str(current + 1))\n"
    )
    (tmp_path / "tasks.py").write_text(tasks_py)
    (tmp_path / "x.py").write_text("v1")

    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        interrupt_signal = signal.CTRL_BREAK_EVENT
    else:
        creationflags = 0
        interrupt_signal = signal.SIGINT

    proc = subprocess.Popen(
        [sys.executable, "-m", "ntask", "watch", "build"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ},
        creationflags=creationflags,
    )
    counter = tmp_path / "counter.txt"

    try:
        # Wait up to 5s for the initial run to increment to "1".
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if counter.exists() and counter.read_text() == "1":
                break
            time.sleep(0.05)
        assert counter.read_text() == "1", "initial run did not produce counter=1"

        # Trigger a rerun by editing x.py.
        (tmp_path / "x.py").write_text("v2")

        # Wait up to 5s for the rerun to increment to "2".
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if counter.read_text() == "2":
                break
            time.sleep(0.05)
        assert counter.read_text() == "2", \
            f"rerun did not increment counter; got {counter.read_text()!r}"
    finally:
        proc.send_signal(interrupt_signal)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    # Clean exit on SIGINT.
    assert proc.returncode in (0, 130), f"unexpected exit {proc.returncode}"
