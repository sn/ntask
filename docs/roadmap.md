# Roadmap

Signals of intent, not commitments.

## 1.0 - shipped

The 1.0 release covers the full stable surface:

- **`@task`, `@cached`, `@group`, `depends`, `shell`** - the core decorator + helper API
- **Content-hash caching** with structural body hashing (whitespace and docstring stable)
- **Transitive cache-key propagation** through the DAG
- **Per-input miss diff** via `ntask --why <task>`
- **Output capture** with content-addressed local store; hard-linked or copied restore
- **Parallel DAG execution** with `-j`; `parallel=False` for DAG-wide barriers
- **Watch mode** (`ntask watch <task>`) with OS-level FS events and `.gitignore` filtering
- **Remote cache** backends: `local-fs`, `http`, `s3` (extra), `gcs` (extra)
- **Live Textual TUI** with per-task state + spinner; `--no-tui` and `tui = false` opt-outs
- **Type-hint to CLI** auto-generation (str/int/bool/Path/Literal/Enum/list)
- **Discovery** by walking up from cwd to find `tasks.py` or `tasks/` package

API stability: the symbols listed in [`reference.md`](reference.md) follow semver from 1.0 onward. Breaking changes ship in 2.0.

## Under consideration

These are ideas with active interest, not commitments:

- **Per-task remote disable** - skip the remote cache for specific tasks (e.g., very large outputs that aren't worth shipping over the wire).
- **Background remote uploads** - the producer task returns control to the executor while the upload continues in the background.
- **Log retention policy** - automatic cleanup of `.ntask/logs/<run-id>/` directories beyond a configurable limit.
- **Watch + TUI integration** - the TUI display works during `ntask watch`, replacing the current line-based renderer.
- **Interactive task selection inside the TUI** - keyboard-driven drill-down, "rerun only this", etc.
- **Multi-language input awareness** - hash `package-lock.json` / `Cargo.lock` / etc. transparently for non-Python projects.
- **Editor / LSP integration** - jump-to-definition, "show inputs of this task" overlays.
- **Distributed execution** - hand individual tasks off to remote workers.

## What ntask is not trying to be

- **A build system for compiled languages.** Bazel, Buck, Pants, Please, and Mill cover that ground. ntask is for the layer of orchestration above your compiler / interpreter / packager.
- **A workflow scheduler.** Airflow, Prefect, Dagster handle production data pipelines with retries, backfills, scheduling. ntask runs locally (or in CI) on demand.
- **A package manager.** It calls `pip install` if you tell it to; it doesn't replace `uv` / `pip` / `poetry`.
