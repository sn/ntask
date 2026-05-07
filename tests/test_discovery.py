from pathlib import Path

import pytest

from ntask._discovery import DiscoveryError, discover
from ntask._registry import default_registry


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


def test_discovers_tasks_py_at_root(tmp_path: Path):
    (tmp_path / "tasks.py").write_text(
        "from ntask import task\n"
        "@task\n"
        "def hello(): pass\n"
    )
    root = discover(tmp_path)
    assert root == tmp_path
    assert "hello" in default_registry().fqns()


def test_discovers_tasks_py_from_subdirectory(tmp_path: Path):
    (tmp_path / "tasks.py").write_text(
        "from ntask import task\n"
        "@task\n"
        "def hello(): pass\n"
    )
    sub = tmp_path / "deep" / "nested"
    sub.mkdir(parents=True)
    root = discover(sub)
    assert root == tmp_path


def test_discovers_tasks_package(tmp_path: Path):
    pkg = tmp_path / "tasks"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from ntask import task\n"
        "@task\n"
        "def a(): pass\n"
    )
    root = discover(tmp_path)
    assert root == tmp_path
    assert "a" in default_registry().fqns()


def test_missing_tasks_raises(tmp_path: Path):
    with pytest.raises(DiscoveryError, match=r"no tasks\.py"):
        discover(tmp_path)


def test_import_error_in_tasks_py_raises_discovery_error(tmp_path: Path):
    (tmp_path / "tasks.py").write_text("import nonexistent_module_xyz\n")
    with pytest.raises(DiscoveryError, match=r"failed to import"):
        discover(tmp_path)
