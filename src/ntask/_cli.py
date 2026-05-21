from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path
from typing import Any

import anyio

from . import __version__
from ._cache.diff import diff_cache_state
from ._cache.key import CacheBreakdown
from ._cli_args import parse_task_args
from ._cli_format import (
    format_graph_ascii,
    format_graph_dot,
    format_graph_mermaid,
    format_list,
)
from ._cli_why import render_why
from ._config import load_project_config
from ._dag import build_graph
from ._discovery import discover
from ._errors import CycleError, DiscoveryError, NtaskError, ShellError
from ._executor import ExecutionConfig, Executor
from ._registry import default_registry
from ._watch import watch_loop


def _build_global_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ntask", add_help=False)
    p.add_argument("-l", "--list", action="store_true")
    p.add_argument("--graph", nargs="?", const="", metavar="TASK")
    p.add_argument("--graph-format", choices=["ascii", "mermaid", "dot"], default="ascii")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--offline", action="store_true",
                   help="Skip remote cache; use local cache only.")
    p.add_argument("--force", action="append", default=[], metavar="TASK")
    p.add_argument("--why", metavar="TASK")
    p.add_argument(
        "-j", "--jobs",
        nargs="?",
        const="auto",
        default=None,
        metavar="N",
        help="Global concurrency cap; bare -j = cpu_count()",
    )
    p.add_argument("--keep-going", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--no-tui", action="store_true",
                   help="Disable the TUI; use the line-based renderer.")
    p.add_argument("--log-dir", metavar="DIR",
                   help="Per-run log directory (default <root>/.ntask/runs).")
    p.add_argument("--max-runs", type=int, default=None, metavar="N",
                   help="Retain only the N most recent run dirs (default 50).")
    p.add_argument("--tb", choices=["short", "long", "line", "none"],
                   default="short",
                   help="Traceback mode for task failures (default short).")
    p.add_argument("--completion", choices=["bash", "zsh", "fish"],
                   metavar="SHELL",
                   help="Emit a shell completion script and exit.")
    p.add_argument("--completion-tasks", action="store_true",
                   help=argparse.SUPPRESS)
    p.add_argument("--completion-flags", metavar="TASK",
                   help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"ntask {__version__}")
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("task", nargs="?")
    p.add_argument("task_args", nargs=argparse.REMAINDER)
    return p


def _print_global_help() -> None:
    print("""usage: ntask [GLOBAL FLAGS] [TASK [TASK_ARGS...]]

Flags:
  -l, --list              List all tasks
  --graph [TASK]          Render task DAG
  --graph-format F        ascii | mermaid | dot
  --dry-run               Plan only
  --no-cache              Ignore and do not write cache
  --offline               Skip remote cache; use local only
  --force TASK            Force-run TASK (repeatable)
  --why TASK              Print last cache key breakdown
  -j, --jobs [N]          Global concurrency cap (bare -j = cpu_count)
  --keep-going            Continue on failure
  -v, --verbose           Stream all output
  -q, --quiet             Suppress cache-hit lines
  --no-color              Disable color
  --no-tui                Disable the TUI; use the line-based renderer
  --log-dir DIR           Per-run log directory (default <root>/.ntask/runs)
  --max-runs N            Retain only the N most recent run dirs (default 50)
  --tb MODE               Traceback for failures: short|long|line|none
  --completion SHELL      Emit a bash/zsh/fish completion script
  --version, -h, --help

Subcommands:
  ntask init [--template=plain|django|fastapi] [--force]
                          Scaffold a minimal tasks.py in the current dir
  ntask clean [--all]     Wipe .ntask/ cache
  ntask watch <task>      Rerun the task when its @cached inputs change
""")


def _discover_quietly() -> bool:
    """Run discovery without raising; returns True on success.

    Used by completion handlers — they must stay silent if discovery fails,
    so the shell doesn't spam errors into the user's prompt.
    """
    default_registry().clear()
    try:
        discover(Path.cwd())
    except Exception:
        return False
    return True


def _handle_completion_tasks() -> int:
    if not _discover_quietly():
        return 0
    for t in sorted(default_registry().all(), key=lambda x: x.fqn):
        print(t.fqn)
    return 0


def _handle_completion_flags(fqn: str) -> int:
    if not _discover_quietly():
        return 0
    t = default_registry().try_get(fqn)
    if t is None:
        return 0
    import inspect
    sig = inspect.signature(t.func)
    for name, param in sig.parameters.items():
        # Required positionals don't get a flag; bool default=True flips to --no-.
        if param.default is inspect.Parameter.empty:
            continue
        if param.annotation is bool and param.default is True:
            print(f"--no-{name}")
        else:
            print(f"--{name}")
    return 0


def _handle_clean(root: Path, clean_all: bool) -> int:
    from ._cache.store import CacheStore
    store = CacheStore(root=root / ".ntask")
    if clean_all:
        store.clear_all()
    else:
        store.clear()
    print("cleaned" + (" (all)" if clean_all else ""))
    return 0


def _handle_why(root: Path, fqn: str) -> int:
    from ._cache import CacheEngine

    reg = default_registry()
    t = reg.try_get(fqn)
    if t is None:
        suggestions = difflib.get_close_matches(fqn, reg.fqns(), n=1, cutoff=0.5)
        hint = f" Did you mean {suggestions[0]!r}?" if suggestions else ""
        print(f"error: no task named {fqn!r}.{hint} (ntask --list)",
              file=sys.stderr)
        return 2

    if t.cached_config is None:
        print(f"error: task {fqn!r} is not a cached task", file=sys.stderr)
        return 1

    engine = CacheEngine(root=root / ".ntask")
    prior = engine.store.latest(fqn)

    if prior is None:
        print(render_why(
            task=t, prior=None,
            report=diff_cache_state(_empty_breakdown_for_why(), None),
            current_key="",
            use_color=sys.stdout.isatty(),
        ), end="")
        return 0

    # Compute current breakdown to diff against the prior. Pass empty upstream
    # dict - --why doesn't simulate the full graph chain; it reports local
    # workspace-vs-last-cache deltas only.
    current_key, current_bd = engine.compute_key_and_breakdown(
        t, workspace=root, upstream_keys_by_dep={},
    )
    report = diff_cache_state(current_bd, prior.breakdown)
    out = render_why(
        task=t, prior=prior, report=report,
        current_key=current_key,
        use_color=sys.stdout.isatty(),
    )
    print(out, end="")
    return 0


def _empty_breakdown_for_why() -> CacheBreakdown:
    """Placeholder CacheBreakdown used when prior is None; render_why short-circuits
    before touching breakdown fields in that case."""
    return CacheBreakdown(
        input_patterns=(), inputs=(), env_values={},
        task_body_hash="", python_version="", platform_tag="",
        upstream_keys_by_dep={},
    )


def _ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 when the runtime picked a codec
    (e.g. Windows cp1252) that can't render the Unicode characters used in
    table borders, graph arrows, and TUI glyphs."""
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None) or ""
        if enc.lower() in ("utf-8", "utf8"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    parser = _build_global_parser()
    ns, _ = parser.parse_known_args(argv)

    # Handle bare -j case: if -j got a non-integer value and task is None,
    # it likely means the value was actually the task name (e.g., -j hi)
    if ns.jobs is not None and ns.task is None:
        try:
            int(ns.jobs)
        except (ValueError, TypeError):
            # ns.jobs is not an integer, so it's probably the task name
            ns.task = ns.jobs
            ns.jobs = "auto"

    if ns.help and not ns.task:
        _print_global_help()
        return 0

    if ns.completion:
        from ._completion import completion_script
        print(completion_script(ns.completion))
        return 0

    if ns.completion_tasks:
        return _handle_completion_tasks()

    if ns.completion_flags:
        return _handle_completion_flags(ns.completion_flags)

    if ns.task == "init":
        from ._init import init_project
        init_parser = argparse.ArgumentParser(prog="ntask init")
        init_parser.add_argument(
            "--template", choices=["plain", "django", "fastapi"], default="plain",
            help="Which scaffold to write (default plain).",
        )
        init_parser.add_argument(
            "--force", action="store_true",
            help="Overwrite an existing tasks.py.",
        )
        init_ns = init_parser.parse_args(ns.task_args)
        code, msg = init_project(
            root=Path.cwd(), template=init_ns.template, force=init_ns.force,
        )
        if code == 0:
            print(msg)
        else:
            print(msg, file=sys.stderr)
        return code

    if ns.task == "clean":
        try:
            root = discover(Path.cwd())
        except DiscoveryError:
            root = Path.cwd()
        clean_parser = argparse.ArgumentParser(prog="ntask clean")
        clean_parser.add_argument("--all", action="store_true", dest="clean_all")
        c_ns = clean_parser.parse_args(ns.task_args)
        return _handle_clean(root, c_ns.clean_all)

    if ns.task == "watch":
        try:
            root = discover(Path.cwd())
        except DiscoveryError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        cfg = load_project_config(root)

        # Parse watch args: first element is the target task name; rest are task args.
        watch_args = ns.task_args
        if not watch_args:
            print(
                "error: ntask watch needs a task name. "
                "Usage: ntask watch <task> [args]",
                file=sys.stderr,
            )
            return 2
        target = watch_args[0]
        rest = watch_args[1:]

        reg = default_registry()
        t = reg.try_get(target)
        if t is None:
            suggestions = difflib.get_close_matches(target, reg.fqns(), n=1, cutoff=0.5)
            hint = f" Did you mean {suggestions[0]!r}?" if suggestions else ""
            print(
                f"error: no task named {target!r}.{hint} (ntask --list)",
                file=sys.stderr,
            )
            return 2

        if t.cached_config is None:
            print(
                f"error: {target!r} is not @cached - watch requires declared "
                f"inputs. Add @cached(inputs=[...]) to your task.",
                file=sys.stderr,
            )
            return 2

        try:
            kwargs = parse_task_args(target, t.func, rest)
        except SystemExit:
            return 2

        concurrency = cfg.default_concurrency
        if ns.jobs is not None:
            if ns.jobs == "auto":
                concurrency = os.cpu_count() or 4
            else:
                try:
                    concurrency = int(ns.jobs)
                except ValueError:
                    print(
                        f"error: --jobs expects an integer or no value, "
                        f"got {ns.jobs!r}",
                        file=sys.stderr,
                    )
                    return 2
                if concurrency < 1:
                    print(
                        f"error: --jobs must be >= 1, got {concurrency}",
                        file=sys.stderr,
                    )
                    return 2

        # Watch mode continues to use the Rich/Log renderer in 0.6.0;
        # TUI + watch integration is deferred.
        from ._render import LogRenderer, RichRenderer
        watch_renderer: Any = None
        if sys.stdout.isatty() and not ns.no_color:
            watch_renderer = RichRenderer(use_color=True, verbose=ns.verbose, quiet=ns.quiet)
        else:
            watch_renderer = LogRenderer(stream=sys.stdout, use_color=False)

        exec_cfg = ExecutionConfig(
            root=root,
            concurrency=concurrency,
            offline=ns.offline,
            renderer=watch_renderer,
            log_dir=Path(ns.log_dir) if ns.log_dir else None,
            max_runs=ns.max_runs if ns.max_runs is not None else 50,
            tb=ns.tb,
        )

        watch_task = t  # narrowed: Task (not None - checked above)

        async def _runner() -> int:
            return await watch_loop(
                task_obj=watch_task,
                task_kwargs=kwargs,
                workspace=root,
                config=exec_cfg,
            )

        try:
            return anyio.run(_runner)
        except KeyboardInterrupt:
            return 0

    try:
        root = discover(Path.cwd())
    except DiscoveryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    cfg = load_project_config(root)
    reg = default_registry()

    if ns.list or (not ns.task and ns.graph is None and not ns.why):
        print(format_list(reg, use_color=not ns.no_color), end="")
        return 0

    if ns.graph is not None:
        g = build_graph(reg)
        target = ns.graph or None
        if ns.graph_format == "ascii":
            print(format_graph_ascii(g, target=target))
        elif ns.graph_format == "mermaid":
            print(format_graph_mermaid(g))
        else:
            print(format_graph_dot(g))
        return 0

    if ns.why:
        return _handle_why(root, ns.why)

    target = ns.task
    t = reg.try_get(target)
    if t is None:
        suggestions = difflib.get_close_matches(target, reg.fqns(), n=1, cutoff=0.5)
        hint = f" Did you mean {suggestions[0]!r}?" if suggestions else ""
        print(f"error: no task named {target!r}.{hint} (ntask --list)", file=sys.stderr)
        return 2

    try:
        kwargs = parse_task_args(target, t.func, ns.task_args)
    except SystemExit:
        return 2

    if ns.jobs is None:
        concurrency = cfg.default_concurrency
    elif ns.jobs == "auto":
        concurrency = os.cpu_count() or 4
    else:
        try:
            concurrency = int(ns.jobs)
        except ValueError:
            print(
                f"error: --jobs expects an integer or no value, got {ns.jobs!r}",
                file=sys.stderr,
            )
            return 2
        if concurrency < 1:
            print(f"error: --jobs must be >= 1, got {concurrency}", file=sys.stderr)
            return 2

    # Renderer construction - TUI is active only when stdout is a TTY, colour
    # is enabled, --no-tui was not passed, and the project config hasn't
    # forced it off.
    renderer: Any = None
    tui_app: Any = None  # set when TUI is active; used by runner below

    tui_wanted = (
        sys.stdout.isatty()
        and not ns.no_color
        and not ns.no_tui
        and cfg.tui is not False
    )
    if tui_wanted:
        try:
            from ._render.tui import TUIRenderer, _DAGApp
            tui_app = _DAGApp()
            renderer = TUIRenderer(app=tui_app)
        except ImportError:
            renderer = None
            tui_app = None

    if renderer is None:
        try:
            from ._render import LogRenderer, RichRenderer
            if sys.stdout.isatty() and not ns.no_color:
                renderer = RichRenderer(use_color=True, verbose=ns.verbose, quiet=ns.quiet)
            else:
                renderer = LogRenderer(stream=sys.stdout, use_color=False)
        except ImportError:
            pass

    exec_cfg = ExecutionConfig(
        root=root,
        concurrency=concurrency,
        force=set(ns.force),
        no_cache=ns.no_cache,
        keep_going=ns.keep_going,
        offline=ns.offline,
        renderer=renderer,
        log_dir=Path(ns.log_dir) if ns.log_dir else None,
        max_runs=ns.max_runs if ns.max_runs is not None else 50,
        tb=ns.tb,
    )
    executor = Executor(reg, exec_cfg)

    if ns.dry_run:
        g = build_graph(reg).reachable_from([target])
        print("would run:")
        for n in g.nodes:
            print(f"  {n}")
        return 0

    if tui_app is not None:
        import threading
        exc_holder: list[BaseException | None] = [None]

        def _run_executor() -> None:
            try:
                result = anyio.run(executor.run, [target], {target: kwargs})
                renderer.summary(
                    ran=len(result.ran), cached=len(result.cached),
                    failed=len(result.failed), skipped=len(result.skipped),
                    failed_fqns=tuple(result.failed),
                )
            except BaseException as exc:
                exc_holder[0] = exc
                renderer.announce_error(f"{type(exc).__name__}: {exc}")

        # The TUI stays mounted after the executor finishes so the user can
        # actually read the final DAG state and summary; q/esc/ctrl+c dismiss.
        bg_thread = threading.Thread(target=_run_executor, daemon=False)
        bg_thread.start()
        tui_app.run()     # blocks until the user dismisses the TUI
        bg_thread.join()
        if renderer.final_summary:
            print(renderer.final_summary)
        if exc_holder[0] is not None:
            raise exc_holder[0]
        return 0
    else:
        try:
            result = anyio.run(executor.run, [target], {target: kwargs})
            if renderer is not None:
                renderer.summary(
                    ran=len(result.ran), cached=len(result.cached),
                    failed=len(result.failed), skipped=len(result.skipped),
                    failed_fqns=tuple(result.failed),
                )
            return 0 if not result.failed else 1
        except CycleError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        except ShellError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except NtaskError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            return 130
        except BaseException as e:
            return _report_unhandled(e)


def _flatten_exceptions(exc: BaseException) -> list[BaseException]:
    """Unwrap a (Base)ExceptionGroup into its leaf exceptions."""
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for sub in exc.exceptions:
            leaves.extend(_flatten_exceptions(sub))
        return leaves
    return [exc]


def _report_unhandled(exc: BaseException) -> int:
    """Print an actionable message and pick a return code, even when the
    failure arrives wrapped in an ExceptionGroup from anyio's task group."""
    leaves = _flatten_exceptions(exc)
    rc = 1
    for leaf in leaves:
        if isinstance(leaf, CycleError):
            rc = max(rc, 2)
            print(f"error: {leaf}", file=sys.stderr)
        elif isinstance(leaf, KeyboardInterrupt):
            rc = max(rc, 130)
        elif isinstance(leaf, NtaskError):
            print(f"error: {leaf}", file=sys.stderr)
        else:
            print(f"error: {type(leaf).__name__}: {leaf}", file=sys.stderr)
    return rc
