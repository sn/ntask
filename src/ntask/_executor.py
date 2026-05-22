from __future__ import annotations

import inspect
import json
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import anyio

from ._cache import CacheEngine
from ._cache.diff import MissReport, diff_cache_state
from ._config import load_project_config
from ._coordinator import _ParallelCoordinator
from ._dag import build_graph, toposort
from ._logio import _LogTee, hijack_logging_streams, restore_logging_streams
from ._registry import Registry
from ._remote import RemoteBackend, make_backend
from ._shell import _current_line_prefix, _current_log_file, _current_silent_capture
from ._task import Task

TbMode = Literal["short", "long", "line", "none"]

DEFAULT_MAX_RUNS = 50


@dataclass(slots=True)
class ExecutionConfig:
    root: Path
    concurrency: int = 1
    force: set[str] = field(default_factory=set)
    no_cache: bool = False
    keep_going: bool = False
    offline: bool = False
    renderer: Any = None
    # Per-run log directory; if None, defaults to <root>/.ntask/runs/<run-id>.
    log_dir: Path | None = None
    # Number of recent run directories to retain; older ones are pruned at
    # run start. Set to 0 to disable retention.
    max_runs: int = DEFAULT_MAX_RUNS
    # Traceback formatting mode for failures. ``none`` mirrors the pre-1.2
    # behaviour (renderer's one-line summary only).
    tb: TbMode = "short"


@dataclass(slots=True)
class RunResult:
    ran: list[str] = field(default_factory=list)
    cached: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    # Per-task wall-clock seconds; only populated for tasks that ran (not
    # cached/skipped).
    durations: dict[str, float] = field(default_factory=dict)
    # Per-task captured-log path, relative to the run dir; absent for tasks
    # that produced no output.
    log_paths: dict[str, str] = field(default_factory=dict)
    # The directory holding per-task logs + run.json for this invocation.
    run_dir: Path | None = None


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

        # Per-run log directory + stdout/stderr capture is always set up,
        # regardless of which renderer is active. This is the authoritative
        # record of what each task produced; the TUI and line renderers are
        # both live views on top of it.
        run_id = _utc_run_id()
        runs_root = self.config.log_dir or (self.config.root / ".ntask" / "runs")
        logs_dir = runs_root / run_id
        logs_dir.mkdir(parents=True, exist_ok=True)
        result.run_dir = logs_dir
        _prune_old_runs(runs_root, keep=self.config.max_runs, current=logs_dir)
        started_at_utc = datetime.now(UTC)

        # Lifecycle-aware renderer setup (TUI is currently the only consumer).
        needs_lifecycle = (
            self.config.renderer is not None
            and hasattr(self.config.renderer, "start")
            and hasattr(self.config.renderer, "stop")
        )
        if needs_lifecycle:
            self.config.renderer.start(graph=sub, logs_dir=logs_dir)
        # Line renderers expose `set_total(n)` so they can emit a
        # [k/n done; next: <fqn>] progress prefix on each on_running.
        if self.config.renderer is not None and hasattr(
            self.config.renderer, "set_total",
        ):
            self.config.renderer.set_total(len(order))

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

            # Pre-compute the per-task log path so the except handler below
            # can append a traceback to it even if the failure happens
            # before _invoke().
            log_path = logs_dir / f"{fqn}.log"
            result.log_paths[fqn] = log_path.name

            exclusive = not t.parallel
            await coordinator.enter(exclusive=exclusive)
            try:
                async with limiter:
                    if self.config.renderer:
                        self.config.renderer.on_running(fqn, cmd=None)
                    kwargs = task_kwargs.get(fqn, {})
                    started = time.perf_counter()

                    # Set the per-task log file. The stdout/stderr tee
                    # installed for the run appends print() output to this
                    # file; under the TUI, shell() also routes there
                    # directly so it doesn't fight Textual for the screen.
                    log_token = _current_log_file.set(log_path)
                    silent_token = _current_silent_capture.set(needs_lifecycle)

                    # Prefix only when TUI is NOT active (TUI owns the screen).
                    prefix_token = (
                        _current_line_prefix.set(fqn)
                        if prefix_enabled and not needs_lifecycle
                        else None
                    )
                    try:
                        await self._invoke(t, kwargs)
                    finally:
                        if prefix_token is not None:
                            _current_line_prefix.reset(prefix_token)
                        _current_silent_capture.reset(silent_token)
                        _current_log_file.reset(log_token)

                    elapsed = time.perf_counter() - started
                    result.durations[fqn] = elapsed
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
                _emit_failure_traceback(
                    fqn=fqn, exc=e, mode=self.config.tb, log_path=log_path,
                )
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

        # Tee sys.stdout/sys.stderr so raw print() from Python task bodies
        # is appended to the per-task log file (resolved via context var).
        # Capture AFTER renderer.start() — if Textual replaced stdout there,
        # we wrap its replacement rather than the original tty.
        saved_stdout, saved_stderr = sys.stdout, sys.stderr
        sys.stdout = _LogTee(saved_stdout)
        sys.stderr = _LogTee(saved_stderr)
        # Rebind any logging.StreamHandler that captured the immutable
        # original sys.__stdout__/__stderr__ onto our tees. This is what
        # catches structured loggers (stdlib logging / structlog with the
        # stdlib handler) that would otherwise bypass the tee and fight
        # Textual for the screen.
        hijacked_handlers = hijack_logging_streams(
            tee_stdout=sys.stdout, tee_stderr=sys.stderr,
        )
        try:
            async with anyio.create_task_group() as tg:
                for n in order:
                    tg.start_soon(run_one, n)
        finally:
            restore_logging_streams(hijacked_handlers)
            sys.stdout, sys.stderr = saved_stdout, saved_stderr
            if needs_lifecycle:
                self.config.renderer.stop()
            _write_run_manifest(
                logs_dir,
                run_id=run_id,
                started_at_utc=started_at_utc,
                finished_at_utc=datetime.now(UTC),
                targets=tuple(targets),
                concurrency=self.config.concurrency,
                result=result,
            )
        return result

    @staticmethod
    async def _invoke(t: Task, kwargs: dict[str, Any]) -> None:
        underlying = getattr(t.func, "__wrapped__", t.func)
        if inspect.iscoroutinefunction(underlying):
            await underlying(**kwargs)
        else:
            await anyio.to_thread.run_sync(lambda: t.func(**kwargs))


def _format_traceback(exc: BaseException, mode: TbMode) -> str:
    """Render an exception per ``--tb`` mode.

    - ``none``: empty string (renderer's one-liner remains the only output).
    - ``line``: ``ExcType: message`` only.
    - ``short``: ``file:line: ExcType: message`` using the deepest frame.
    - ``long``: full traceback.
    """
    if mode == "none":
        return ""
    if mode == "line":
        return f"{type(exc).__name__}: {exc}\n"
    if mode == "long":
        return "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
    # short: deepest frame location + one-liner.
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        last = frames[-1]
        return f"{last.filename}:{last.lineno}: {type(exc).__name__}: {exc}\n"
    return f"{type(exc).__name__}: {exc}\n"


def _emit_failure_traceback(
    *, fqn: str, exc: BaseException, mode: TbMode, log_path: Path,
) -> None:
    """Stream a per-mode traceback to stderr and persist the full traceback
    to the per-task log file. Best-effort — never raises."""
    formatted = _format_traceback(exc, mode)
    if formatted:
        try:
            sys.stderr.write(formatted)
            sys.stderr.flush()
        except Exception:  # noqa: S110 — emission must never break a run
            pass
    # The log file always gets the full traceback regardless of stderr mode,
    # so a `--tb=none` run still produces a post-mortem record on disk.
    full = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n--- traceback ({fqn}) ---\n{full}")
    except OSError:
        pass


def _utc_run_id() -> str:
    """Filesystem-safe UTC run identifier — sortable lexically."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S-%f")[:-3] + "Z"


def _prune_old_runs(runs_root: Path, *, keep: int, current: Path) -> None:
    """Retain the ``keep`` most recent run directories under ``runs_root``."""
    if keep <= 0 or not runs_root.exists():
        return
    try:
        entries = [p for p in runs_root.iterdir() if p.is_dir() and p != current]
    except OSError:
        return
    # Directory names sort chronologically because the run-id format is
    # `YYYYMMDDTHHMMSS-fff Z`. Newest last.
    entries.sort(key=lambda p: p.name)
    # `keep` is the budget *including* the current run, so we drop everything
    # but the (keep - 1) newest historical runs.
    drop_count = max(0, len(entries) - (keep - 1))
    for old in entries[:drop_count]:
        shutil.rmtree(old, ignore_errors=True)


def _write_run_manifest(
    run_dir: Path,
    *,
    run_id: str,
    started_at_utc: datetime,
    finished_at_utc: datetime,
    targets: tuple[str, ...],
    concurrency: int,
    result: RunResult,
) -> None:
    """Emit ``run.json`` summarising the run.

    Errors during manifest write are swallowed — the manifest is observability,
    never on the critical path.
    """
    state_by_fqn: dict[str, str] = {}
    for fqn in result.ran:
        state_by_fqn[fqn] = "ran"
    for fqn in result.cached:
        state_by_fqn[fqn] = "cached"
    for fqn in result.failed:
        state_by_fqn[fqn] = "failed"
    for fqn in result.skipped:
        state_by_fqn[fqn] = "skipped"

    tasks: list[dict[str, Any]] = []
    for fqn, state in state_by_fqn.items():
        tasks.append({
            "fqn": fqn,
            "state": state,
            "duration": result.durations.get(fqn),
            "log": result.log_paths.get(fqn),
        })

    manifest = {
        "run_id": run_id,
        "started_at_utc": started_at_utc.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": finished_at_utc.isoformat().replace("+00:00", "Z"),
        "targets": list(targets),
        "concurrency": concurrency,
        "tasks": tasks,
        "summary": {
            "ran":     len(result.ran),
            "cached":  len(result.cached),
            "failed":  len(result.failed),
            "skipped": len(result.skipped),
        },
    }
    try:
        (run_dir / "run.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
