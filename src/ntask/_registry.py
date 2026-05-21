from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

from ._task import CachedConfig, Task

# Top-level CLI subcommands that shadow same-named user tasks. Routing
# isn't changed (people rely on `ntask clean` wiping `.ntask/`); the
# registry warns so users notice their task body never ran.
RESERVED_SUBCOMMANDS: frozenset[str] = frozenset({"clean", "init", "watch"})


class Registry:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def register(
        self,
        fqn: str,
        func: Callable[..., Any],
        *,
        deps: tuple[Any, ...],
        concurrency: int | None,
        parallel: bool,
        cached_config: CachedConfig | None,
        group: str | None,
    ) -> Task:
        if fqn in self._tasks:
            raise ValueError(f"task {fqn!r} already registered")
        if fqn in RESERVED_SUBCOMMANDS:
            warnings.warn(
                f"user task {fqn!r} is shadowed by the built-in subcommand "
                f"{fqn!r}; the built-in will be invoked when you run "
                f"'ntask {fqn}'. Rename the task (e.g. to '{fqn}_task') or "
                f"place it under a group.",
                UserWarning,
                stacklevel=3,
            )
        task = Task(
            fqn=fqn,
            func=func,
            deps=deps,
            concurrency=concurrency,
            parallel=parallel,
            cached_config=cached_config,
            group=group,
        )
        self._tasks[fqn] = task
        return task

    def get(self, fqn: str) -> Task:
        return self._tasks[fqn]

    def try_get(self, fqn: str) -> Task | None:
        return self._tasks.get(fqn)

    def fqns(self) -> tuple[str, ...]:
        return tuple(self._tasks)

    def all(self) -> tuple[Task, ...]:
        return tuple(self._tasks.values())

    def unregister(self, fqn: str) -> None:
        """Remove a task from the registry. Raises KeyError if not present."""
        del self._tasks[fqn]

    def clear(self) -> None:
        self._tasks.clear()


_default = Registry()


def default_registry() -> Registry:
    return _default
