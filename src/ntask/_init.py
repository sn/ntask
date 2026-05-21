"""``ntask init`` scaffolding.

Writes a minimal ``tasks.py`` at the current working directory using one
of a few built-in templates. Refuses to overwrite an existing file unless
``--force`` is passed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

Template = Literal["plain", "django", "fastapi"]

TEMPLATES: dict[Template, str] = {
    "plain": '''\
"""Tasks for this project. Discovered by `ntask` at the repo root."""
from ntask import shell, task


@task
def hello(name: str = "world"):
    """Say hi."""
    shell(f"echo Hello, {name}!")
''',
    "django": '''\
"""Tasks for this Django project.

The bootstrap block below makes `import myapp.models` work from inside a
task body. Replace `myproject.settings` with your settings module and
remove anything you don't need.
"""
import os

# --- ntask <> Django bootstrap ---------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
# A throwaway SECRET_KEY is only safe in a dev/CI context. Remove if your
# settings module already sources one from the environment.
os.environ.setdefault("SECRET_KEY", "ntask-dev-only-replace-me")

import django  # noqa: E402  — must follow the env setup above

django.setup()
# ---------------------------------------------------------------------------

from ntask import shell, task  # noqa: E402


@task
def migrate():
    """Apply database migrations."""
    shell("python manage.py migrate")


@task
def test():
    """Run the Django test suite."""
    shell("python manage.py test")
''',
    "fastapi": '''\
"""Tasks for this FastAPI project."""
import os

# --- ntask <> FastAPI bootstrap --------------------------------------------
# Point this at your FastAPI app's import path so tasks can import the
# application object for in-process work (e.g. running a TestClient).
os.environ.setdefault("APP_MODULE", "myapp.main:app")
# ---------------------------------------------------------------------------

from ntask import shell, task


@task
def dev():
    """Run the dev server with autoreload."""
    shell(f"uvicorn {os.environ['APP_MODULE']} --reload")


@task
def test():
    """Run pytest."""
    shell("pytest -v")
''',
}


def init_project(
    *, root: Path, template: Template, force: bool,
) -> tuple[int, str]:
    """Scaffold ``tasks.py`` under ``root``.

    Returns ``(exit_code, message)``. The CLI prints the message on stderr
    for non-zero exits and on stdout for success.
    """
    target = root / "tasks.py"
    if target.exists() and not force:
        return (
            1,
            f"error: {target} already exists; pass --force to overwrite.",
        )
    body = TEMPLATES[template]
    target.write_text(body, encoding="utf-8")
    return 0, f"wrote {target} ({template} template)"
