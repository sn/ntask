"""Watch loop: rerun a @cached task when its declared inputs change."""
from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pathspec

from ._cache.manifest import _load_gitignore
from ._executor import ExecutionConfig, Executor
from ._registry import default_registry
from ._task import Task

AwatchFactory = Callable[..., AsyncIterator[set[tuple[int, str]]]]

_awatch_factory: AwatchFactory | None
try:
    from watchfiles import awatch as _real_awatch

    _awatch_factory = _real_awatch  # type: ignore[assignment]
except ImportError:
    _awatch_factory = None


def _build_filter(task_obj: Task, workspace: Path) -> Callable[[Path], bool]:
    """Build a predicate: ``is_relevant(Path) -> bool`` for watch events."""
    assert task_obj.cached_config is not None
    patterns = task_obj.cached_config.inputs
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    gitignore = _load_gitignore(workspace)

    def is_relevant(abs_path: Path) -> bool:
        try:
            rel = abs_path.relative_to(workspace).as_posix()
        except ValueError:
            return False
        if gitignore and gitignore.match_file(rel):
            return False
        return spec.match_file(rel)

    return is_relevant


def _clear_screen() -> None:
    """Clear the terminal if stdout is a TTY; otherwise print a separator."""
    if sys.stdout.isatty():
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.flush()
    else:
        sys.stdout.write("\n--- rerun ---\n")
        sys.stdout.flush()


def _print_status_header(task_obj: Task, change_detail: str) -> None:
    """Print the status header before each run."""
    assert task_obj.cached_config is not None
    patterns = ", ".join(task_obj.cached_config.inputs)
    print(f"Watching: {patterns}")
    print(f"Target:   {task_obj.fqn} ({change_detail})")
    print("Press Ctrl-C to exit.")
    print("-" * 42)


def _describe_changes(changes: set[tuple[int, str]], workspace: Path) -> str:
    """Return a human-readable summary of the first changed file."""
    if not changes:
        return "change"
    first = sorted(str(p) for _, p in changes)[0]
    try:
        rel = Path(first).relative_to(workspace).as_posix()
    except ValueError:
        rel = first
    extra = len(changes) - 1
    if extra > 0:
        return f"change: {rel} modified (+{extra} more)"
    return f"change: {rel} modified"


async def _run_once(
    task_obj: Task,
    task_kwargs: dict[str, Any],
    config: ExecutionConfig,
) -> None:
    """Invoke the task via Executor; swallow failures so the loop continues."""
    executor = Executor(default_registry(), config)
    try:
        await executor.run([task_obj.fqn], {task_obj.fqn: task_kwargs})
    except BaseException as e:
        if isinstance(e, KeyboardInterrupt):
            raise
        print(
            f"watch: run failed ({type(e).__name__}). Waiting for changes...",
            file=sys.stderr,
        )


async def watch_loop(
    *,
    task_obj: Task,
    task_kwargs: dict[str, Any],
    workspace: Path,
    config: ExecutionConfig,
    awatch_factory: AwatchFactory | None = None,
) -> int:
    """Run a watch loop: initial run + re-run on input changes. Ctrl-C exits.

    Returns 0 on clean Ctrl-C exit.
    """
    if task_obj.cached_config is None:
        raise ValueError(
            f"Task {task_obj.fqn!r} is not @cached; "
            f"watch requires declared inputs. Add @cached(inputs=[...]) to use it."
        )

    if awatch_factory is None:
        if _awatch_factory is None:
            raise RuntimeError("watchfiles is not installed")
        awatch_factory = _awatch_factory

    is_relevant = _build_filter(task_obj, workspace)

    # Initial run.
    _clear_screen()
    _print_status_header(task_obj, "initial run")
    try:
        await _run_once(task_obj, task_kwargs, config)
    except KeyboardInterrupt:
        return 0

    # Watch loop.
    try:
        async for changes in awatch_factory(workspace):
            relevant = {
                (c_type, p) for c_type, p in changes
                if is_relevant(Path(p))
            }
            if not relevant:
                continue
            _clear_screen()
            _print_status_header(task_obj, _describe_changes(relevant, workspace))
            await _run_once(task_obj, task_kwargs, config)
    except KeyboardInterrupt:
        return 0

    return 0
