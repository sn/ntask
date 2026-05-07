# ntask examples

Six runnable examples, each self-contained. `cd` into any directory and run
`ntask --list` to see what's available.

| #  | Example                          | Demonstrates                                                         |
|----|----------------------------------|----------------------------------------------------------------------|
| 01 | [hello](01-hello/)               | Minimal `@task` + `@cached` with one input file                      |
| 02 | [python-lib](02-python-lib/)     | Realistic Python project - install / lint / typecheck / test / build |
| 03 | [parallel](03-parallel/)         | `-j N` speedup and the `parallel=False` exclusive barrier            |
| 04 | [watch](04-watch/)               | `ntask watch <task>` for live rerun on file change                   |
| 05 | [remote-cache](05-remote-cache/) | `[tool.ntask.remote_cache]` local-fs backend shared between clones   |
| 06 | [monorepo](06-monorepo/)         | `@group(...)` namespacing and cross-group `deps=`                    |

## Setup

All examples assume `ntask` is installed in the active environment:

```bash
pip install ntask
```

Per-example tools (install on `PATH` or in the example's own venv before
running):

| Example | Needs                                                                                      |
|---------|--------------------------------------------------------------------------------------------|
| 01      | python3 only                                                                               |
| 02      | `pip install -e ".[dev]"` runs from inside the example; provides ruff, mypy, pytest, build |
| 03      | python3 only                                                                               |
| 04      | python3 only                                                                               |
| 05      | python3 only; `/tmp/ntask-team-cache` writable                                             |
| 06      | python3 only                                                                               |
