from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio

from ._cache import CacheEngine
from ._cache.diff import MissReport, diff_cache_state
from ._config import load_project_config
from ._coordinator import _ParallelCoordinator
from ._dag import build_graph, toposort
from ._registry import Registry
from ._remote import RemoteBackend, make_backend
from ._shell import _current_line_prefix, _current_log_file
from ._task import Task


@dataclass(slots=True)
class ExecutionConfig:
    root: Path
    concurrency: int = 1
    force: set[str] = field(default_factory=set)
    no_cache: bool = False
    keep_going: bool = False
    offline: bool = False
    renderer: Any = None


@dataclass(slots=True)
class RunResult:
    ran: list[str] = field(default_factory=list)
    cached: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _resolve_remote(config: ExecutionConfig) -> RemoteBackend | None:
    """Construct a RemoteBackend from pyproject config, or None. Catches errors."""
    if config.offline:
        return None
    try:
        project_cfg = load_project_config(config.root)
    except Exception:
        return None
    if project_cfg.remote_cache is None:
        return None
    try:
        return make_backend(project_cfg.remote_cache)
    except Exception as e:
        from ._cache import _warn_once_remote_failed
        _warn_once_remote_failed(e)
        return None


class Executor:
    def __init__(self, registry: Registry, config: ExecutionConfig):
        self.registry = registry
        self.config = config
        self.cache = CacheEngine(
            root=config.root / ".ntask",
            remote=_resolve_remote(config),
        )

    async def run(
        self,
        targets: list[str],
        task_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> RunResult:
        task_kwargs = task_kwargs or {}
        full_graph = build_graph(self.registry)
        sub = full_graph.reachable_from(targets)
        order = toposort(sub)
        result = RunResult()
        done: dict[str, anyio.Event] = {n: anyio.Event() for n in order}
        resolved_keys: dict[str, str] = {}
        failures: dict[str, BaseException] = {}

        limiter = anyio.CapacityLimiter(self.config.concurrency)
        coordinator = _ParallelCoordinator()
        prefix_enabled = self.config.concurrency > 1

        # Lifecycle-aware renderer setup (TUI + log capture).
        needs_lifecycle = (
            self.config.renderer is not None
            and hasattr(self.config.renderer, "start")
            and hasattr(self.config.renderer, "stop")
        )
        logs_dir: Path | None = None
        if needs_lifecycle:
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
            logs_dir = self.config.root / ".ntask" / "logs" / run_id
            logs_dir.mkdir(parents=True, exist_ok=True)
            self.config.renderer.start(graph=sub, logs_dir=logs_dir)

        async def run_one(fqn: str) -> None:
            for dep in sub.direct_deps(fqn):
                await done[dep].wait()
                if dep in failures:
                    result.skipped.append(fqn)
                    done[fqn].set()
                    return
            t = self.registry.get(fqn)
            upstream_by_dep = {
                d: resolved_keys.get(d, "") for d in sub.direct_deps(fqn)
            }
            upstream_tuple = tuple(upstream_by_dep.values())

            key: str | None = None
            breakdown = None
            if t.cached_config is not None and not self.config.no_cache:
                key, breakdown = self.cache.compute_key_and_breakdown(
                    t, workspace=self.config.root,
                    upstream_keys_by_dep=upstream_by_dep,
                )
                resolved_keys[fqn] = key
                if fqn not in self.config.force:
                    entry = self.cache.check(t, key)
                    if entry is not None:
                        self.cache.restore_outputs(entry, workspace=self.config.root)
                        result.cached.append(fqn)
                        if self.config.renderer:
                            self.config.renderer.on_cached(fqn, key=key, source="local")
                        done[fqn].set()
                        return

                    # Try remote before falling through to execute.
                    if not self.config.offline:
                        entry = self.cache.check_remote(t, key)
                        if entry is not None:
                            self.cache.restore_outputs(entry, workspace=self.config.root)
                            result.cached.append(fqn)
                            if self.config.renderer:
                                self.config.renderer.on_cached(fqn, key=key, source="remote")
                            done[fqn].set()
                            return

                if self.config.renderer:
                    prior = self.cache.store.latest(fqn)
                    prior_bd = prior.breakdown if prior is not None else None
                    report: MissReport = diff_cache_state(breakdown, prior_bd)
                    self.config.renderer.on_miss_reason(fqn, report=report)

            exclusive = not t.parallel
            await coordinator.enter(exclusive=exclusive)
            try:
                async with limiter:
                    if self.config.renderer:
                        self.config.renderer.on_running(fqn, cmd=None)
                    kwargs = task_kwargs.get(fqn, {})
                    started = time.perf_counter()

                    # Set the per-task log file (TUI / lifecycle renderer path).
                    log_token = None
                    if logs_dir is not None:
                        log_path = logs_dir / f"{fqn}.log"
                        log_token = _current_log_file.set(log_path)

                    # Prefix only when TUI is NOT active (TUI owns the screen).
                    prefix_token = (
                        _current_line_prefix.set(fqn)
                        if prefix_enabled and logs_dir is None
                        else None
                    )
                    try:
                        await self._invoke(t, kwargs)
                    finally:
                        if prefix_token is not None:
                            _current_line_prefix.reset(prefix_token)
                        if log_token is not None:
                            _current_log_file.reset(log_token)

                    elapsed = time.perf_counter() - started
                    stored_entry = None
                    if key is not None and breakdown is not None:
                        stored_entry = self.cache.store_entry(
                            t, key,
                            workspace=self.config.root,
                            duration=elapsed,
                            breakdown=breakdown,
                            upstream_keys=upstream_tuple,
                        )
                        if not self.config.offline and stored_entry is not None:
                            self.cache.push_remote(t, stored_entry)
                    if self.config.renderer:
                        self.config.renderer.on_ok(fqn, duration=elapsed)
                    result.ran.append(fqn)
            except BaseException as e:
                failures[fqn] = e
                result.failed.append(fqn)
                if self.config.renderer:
                    self.config.renderer.on_failed(fqn, error=e, tail_lines=[])
                done[fqn].set()
                await coordinator.exit(exclusive=exclusive)
                if not self.config.keep_going:
                    raise
                return
            else:
                done[fqn].set()
                await coordinator.exit(exclusive=exclusive)

        try:
            async with anyio.create_task_group() as tg:
                for n in order:
                    tg.start_soon(run_one, n)
        finally:
            if needs_lifecycle:
                self.config.renderer.stop()
        return result

    @staticmethod
    async def _invoke(t: Task, kwargs: dict[str, Any]) -> None:
        underlying = getattr(t.func, "__wrapped__", t.func)
        if inspect.iscoroutinefunction(underlying):
            await underlying(**kwargs)
        else:
            await anyio.to_thread.run_sync(lambda: t.func(**kwargs))
