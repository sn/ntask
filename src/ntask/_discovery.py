from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from ._errors import DiscoveryError


def find_project_root(start: Path) -> Path | None:
    """Walk upward from ``start`` looking for tasks.py or tasks/ package.

    Returns the directory containing the match, or None.
    """
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / "tasks").is_dir() and (d / "tasks" / "__init__.py").is_file():
            return d
        if (d / "tasks.py").is_file():
            return d
    return None


def discover(start: Path) -> Path:
    """Find and import the tasks module, registering all tasks as a side effect.

    Returns the project root directory.
    """
    root = find_project_root(start)
    if root is None:
        raise DiscoveryError(
            f"no tasks.py or tasks/ package found from {start} upward"
        )

    if (root / "tasks").is_dir():
        target = root / "tasks" / "__init__.py"
        module_name = "_ntask_user_tasks_pkg"
    else:
        target = root / "tasks.py"
        module_name = "_ntask_user_tasks"

    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        raise DiscoveryError(f"could not build import spec for {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    sys.path.insert(0, str(root))
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise DiscoveryError(f"failed to import {target}: {e}") from e
    return root
