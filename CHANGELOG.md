# Changelog

All notable changes to `ntask` are documented in this file.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses semantic versioning.

## [Unreleased]

### Fixed
- Registering a top-level task whose name collides with a built-in subcommand
  (`clean`, `watch`) now emits a `UserWarning` at registration time. Routing is
  unchanged — the built-in still wins — but the warning makes it obvious that
  the user task body will never execute.

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
