# Changelog

All notable changes to `ntask` are documented in this file.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses semantic versioning.

## [Unreleased]

### Fixed
- `_LogTee` (the `sys.stdout` / `sys.stderr` proxy installed by the executor
  to capture per-task output) was writing to the underlying stream even
  under the TUI. Textual owns stdout but not stderr, so library code that
  used `logging` to stderr (very common — structured JSON loggers, etc.)
  bled raw lines straight onto the live DAG view. The tee now consults
  `_current_silent_capture` and suppresses the underlying write while the
  TUI is active. The per-task log file still receives every line, so
  nothing is dropped — only the terminal stream is quiet.

### Documentation
- `docs/design/pre-post-hooks.md` captures the deferred design for
  per-task before/after hooks: why composition (`@with_reset`) is the
  recommended pattern today, and the constraints we'd commit to if we
  ever do build module-level hooks.
- README now includes a worked `--graph --graph-format mermaid` example
  embedded as a real Mermaid block (the project's own DAG) so users can
  see what to paste into their own design docs. See `ISSUES.md` for the
  target-scoping bug found while verifying this.
- New README section "When NOT to use `@cached`" documenting the categories
  of task — side effects, mutating shared state, time- or randomness-
  dependent, world-probing — where caching is the wrong default.

### Added
- The line-based renderers (`LogRenderer`, `RichRenderer`) now prefix each
  `running <fqn>` line with `[k/n done; next: <fqn>]` so multi-task runs
  no longer feel positionally opaque. Silent for single-task runs. The
  TUI already provided this implicitly via the live tree.
- The end-of-run summary now lists the failed tasks by name on a second
  line — useful for `--keep-going` runs where there was no fail-fast and
  the user would otherwise have to scroll back through the log.
- Shell completion: `ntask --completion bash|zsh|fish` prints a completion
  script. The script calls back into `ntask --completion-tasks` and
  `ntask --completion-flags <task>`, so task and per-task flag suggestions
  stay in sync with the project's actual `tasks.py`.
- `ntask init` scaffolds a minimal `tasks.py` in the current directory.
  `--template plain|django|fastapi` chooses the boilerplate (django/fastapi
  templates ship the framework bootstrap block users had to hand-roll).
  Refuses to overwrite an existing `tasks.py` without `--force`. `init` is
  also reserved, so naming a task `init` now emits the same shadowing
  warning as `clean` / `watch`.
- `ntask --list` now renders each task's CLI signature next to its name —
  `<required: type>`, `[--name=default]`, `[--flag]` for bool default-False,
  `[--no-flag]` for default-True. Long signatures are truncated at 40 chars
  so the table stays readable.
- `@task(deps=...)` now accepts a zero-arg callable returning an iterable of
  task refs — e.g. `@task(deps=lambda: [a, b])` — so dependent tasks can sit
  above their deps in the source file without the linter complaining. The
  resolver is invoked once at graph-build time and memoised.
- Task failures now stream a traceback to stderr by default and append the
  full traceback to the per-task log file. New `--tb` global flag accepts
  `short` (default), `long`, `line`, or `none` — the renderer's one-line
  `x <fqn> FAILED: ...` summary on stdout is unchanged.
- Per-task log files are now written for every run, regardless of which
  renderer is active. The on-disk layout is
  `.ntask/runs/<UTC-run-id>/<task-fqn>.log` plus a `run.json` manifest with
  counts, per-task durations, and log paths. Override the location with the
  global `--log-dir DIR` flag.
- Raw `print()` output from inside a task body is captured to the per-task
  log file via a context-aware `sys.stdout` / `sys.stderr` tee. Previously
  the TUI absorbed those writes and they could not be recovered after the
  run.
- Retention: only the `--max-runs` most recent run directories are kept;
  default is 50. `--max-runs 0` disables retention.

### Fixed
- Registering a top-level task whose name collides with a built-in subcommand
  (`clean`, `watch`) now emits a `UserWarning` at registration time. Routing is
  unchanged — the built-in still wins — but the warning makes it obvious that
  the user task body will never execute.

### Notes
- `shell()` subprocess output in the default sequential line renderer is
  not yet pumped through the Python-level tee, so it appears on the
  terminal but is not appended to the per-task log file in that mode. The
  TUI silent-log path and the parallel-prefix path both already capture
  it correctly; closing the gap in the default path is tracked separately.

## [1.1.0]

### Changed
- The TUI no longer auto-closes when the run finishes. It stays mounted with
  the final DAG state and a summary footer until you press `q`, `Esc`, or
  `Ctrl+C`. Non-interactive runs (CI, piped output) are unaffected — the TUI
  is still gated on `sys.stdout.isatty()`.
- The TUI footer now includes the run summary (counts + log path) plus a
  `press q/esc to quit` hint while the app is showing it. This was previously
  rendered only by the line-based renderers.

## [1.0.0]

Initial public release.
