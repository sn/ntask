# Changelog

All notable changes to `ntask` are documented in this file.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses semantic versioning.

## [Unreleased]

### Added
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
