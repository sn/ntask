"""Coverage for `ntask init` scaffolding."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ntask._init import init_project


def test_init_writes_plain_template(tmp_path: Path) -> None:
    code, msg = init_project(root=tmp_path, template="plain", force=False)
    assert code == 0, msg
    target = tmp_path / "tasks.py"
    assert target.is_file()
    body = target.read_text(encoding="utf-8")
    assert "from ntask import" in body
    assert "@task" in body


def test_init_writes_django_template_with_bootstrap(tmp_path: Path) -> None:
    code, _ = init_project(root=tmp_path, template="django", force=False)
    assert code == 0
    body = (tmp_path / "tasks.py").read_text(encoding="utf-8")
    assert "DJANGO_SETTINGS_MODULE" in body
    assert "django.setup()" in body


def test_init_writes_fastapi_template(tmp_path: Path) -> None:
    code, _ = init_project(root=tmp_path, template="fastapi", force=False)
    assert code == 0
    body = (tmp_path / "tasks.py").read_text(encoding="utf-8")
    assert "APP_MODULE" in body
    assert "uvicorn" in body


def test_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / "tasks.py").write_text("# pre-existing\n", encoding="utf-8")
    code, msg = init_project(root=tmp_path, template="plain", force=False)
    assert code != 0
    assert "already exists" in msg
    assert (tmp_path / "tasks.py").read_text() == "# pre-existing\n"


def test_init_overwrites_with_force(tmp_path: Path) -> None:
    (tmp_path / "tasks.py").write_text("# old\n", encoding="utf-8")
    code, _ = init_project(root=tmp_path, template="plain", force=True)
    assert code == 0
    body = (tmp_path / "tasks.py").read_text(encoding="utf-8")
    assert "# old" not in body
    assert "@task" in body


def test_init_end_to_end_via_cli(tmp_path: Path) -> None:
    """Scaffold and then run `ntask --list` to prove the scaffold is valid."""
    init = subprocess.run(
        [sys.executable, "-m", "ntask", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stderr

    listing = subprocess.run(
        [sys.executable, "-m", "ntask", "--list"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert listing.returncode == 0, listing.stderr
    assert "hello" in listing.stdout


def test_init_refuses_overwrite_via_cli(tmp_path: Path) -> None:
    (tmp_path / "tasks.py").write_text("# pre-existing\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "ntask", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "already exists" in result.stderr
    # File unchanged.
    assert (tmp_path / "tasks.py").read_text() == "# pre-existing\n"


def test_init_name_is_reserved() -> None:
    """Registering a top-level task named `init` should warn (shadowing the
    subcommand)."""
    from ntask._registry import RESERVED_SUBCOMMANDS, Registry
    assert "init" in RESERVED_SUBCOMMANDS

    reg = Registry()
    def f() -> None: pass
    with pytest.warns(UserWarning, match="shadowed by the built-in subcommand 'init'"):
        reg.register("init", f, deps=(), concurrency=None, parallel=True,
                     cached_config=None, group=None)
