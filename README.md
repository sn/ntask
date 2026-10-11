# ntask

[![PyPI](https://img.shields.io/pypi/v/ntask?color=green)](https://pypi.org/project/ntask/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ntask)](https://pypi.org/project/ntask/)
[![PyPI - License](https://img.shields.io/pypi/l/ntask)](https://pypi.org/project/ntask/)
[![Build](https://img.shields.io/github/actions/workflow/status/sn/ntask/test.yml?branch=main)](https://github.com/sn/ntask/actions?query=branch%3Amain)

A Python-native task runner with content-hash caching and DAG execution.

```bash
pip install ntask
```

## Why

Your Makefile runs everything every time. Your Justfile has no dependency graph. Your `tasks.py` for Invoke is five years old, has no types, and you still have to write `ctx.run`. This is what a task runner looks like when you start over with caching, types, and a DAG.

## Quickstart

A complete release pipeline in under 30 lines. Drop this into `tasks.py` at your project root:

```python
from ntask import task, cached, shell

@task
@cached(inputs=["src/**/*.py"])
def lint():
    shell("ruff check src/")

@task
@cached(inputs=["src/**/*.py"])
def typecheck():
    shell("mypy src/")

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test(pattern: str = ""):
    shell(f"pytest -q {'-k ' + pattern if pattern else ''}")

@task
@cached(inputs=["src/**/*.py", "pyproject.toml"], outputs=["dist/"])
def build():
    shell("python -m build")

@task(deps=[lint, typecheck, test, build])
def release(version: str):
    """Run checks, build, tag, and publish to PyPI."""
    shell(f"git tag v{version} && git push --tags && twine upload dist/*")
```

The first time you cut a release, every step runs. `-j` runs independent tasks in parallel:

```
$ ntask release --version=1.0.0 -j
running lint
running typecheck
running test
running build
+ lint       (1.4s)
+ build      (2.3s)
+ typecheck  (3.2s)
+ test       (4.9s)
running release
+ release    (0.9s)
```

The second time, ntask hashes the inputs, sees nothing changed, and skips every cached task. It restores `dist/` from its content-addressed store, so `build` never runs:

```
$ ntask release --version=1.0.1 -j
o lint       cached (3a8f9c2d)
o typecheck  cached (b7c5f1e9)
o test       cached (9f2e8b14)
o build      cached (4dab8273)   <- dist/ restored, build did not run
running release
+ release    (0.9s)
```

Edit one file under `tests/` and only `test` reruns. `lint`, `typecheck` and `build` don't read that file, so they stay cached. `release` isn't cached, so it always runs.

Cache keys also chain: a cached task's key includes the keys of the tasks it depends on, so a change upstream invalidates everything below it, even when the downstream task's own files haven't changed.

A few more commands:

```bash
ntask --list                       # list every task with its docstring
ntask test --pattern=auth          # type hints become CLI flags automatically
ntask --why test                   # explain the last cache hit or miss, item by item
ntask --graph release              # ASCII DAG (mermaid / dot also available)
ntask watch test                   # rerun on every src/ or tests/ change
```

### Mermaid graph for docs

`--graph-format mermaid` prints a Mermaid block you can paste into a
README or design doc. This is `ntask`'s own DAG, straight from
`ntask --graph --graph-format mermaid`:

```mermaid
graph TD
    install
    lint
    typecheck
    test
    check
    build
    release
    lint --> check
    typecheck --> check
    test --> check
    check --> release
    build --> release
```

`--graph-format dot` produces Graphviz output for the same data.

## Team cache

Share cache hits across machines through S3, GCS, HTTP or a shared directory (NFS, a Docker volume):

```toml
# pyproject.toml
[tool.ntask.remote_cache]
type = "s3"
bucket = "my-team-cache"
```

```bash
pip install ntask[s3]
ntask check                        # the first run fills the cache; everyone else gets hits
ntask check --offline              # skip the remote for fast dev loops
```

For S3-compatible stores (MinIO, R2, B2), set `endpoint_url`. GCS and HTTP backends work the same way. The HTTP backend is plain `GET`/`PUT`/`HEAD` over stdlib `urllib`, so any server that accepts `PUT` will do.

## When NOT to use `@cached`

`@cached` suits deterministic work driven by files: `lint`, `typecheck`,
`test`, `build`. It's the wrong fit when the point of the task is its effect
on the world. Skip it (or be deliberate about `inputs=` and `env=`) when the task:

- has external side effects: DB writes, HTTP requests, sending email, queue
  pushes. A cache hit means none of that happened on this run.
- changes shared state that other tasks read: caches, file ownership, the
  contents of `.env`, feature flags.
- depends on the clock or on randomness, so the same inputs can produce
  different output tomorrow.
- *exists to check the world*: smoke tests, integration probes, "is prod
  still healthy" checks. The whole point is to run again.

Use plain `@task` for these. Add `parallel=False` if the task must run alone
(releases, migrations), and `@group(...)` to namespace related tasks.

## Live DAG display

Run `ntask check` in an interactive terminal and a Textual TUI shows the DAG as a live tree, with each task's state and duration. Pipe the output, set `tui = false` in `[tool.ntask]`, or pass `--no-tui` to get plain line-by-line output instead.

## More features

- **Exclusive tasks.** `@task(parallel=False)` waits for every running task to finish, then runs alone. Use it for releases, migrations and anything else that changes shared state.
- **Monorepos.** Put `@group("api")` on a class and its task methods become `api.<name>`. Depend across groups with `@task(deps=[Other.task, ...])` or a string name such as `"web.test"`.
- **Capture output.** `shell("git rev-parse HEAD", capture=True)` returns a `ShellResult` with `.stdout`, `.stderr`, `.returncode`, `.duration`, `.ok`.
- **Force a rerun.** `ntask --force <task>` skips the cache for that one task. `ntask --no-cache` ignores the cache entirely. `ntask clean` deletes the cache entries; `ntask clean --all` deletes the whole `.ntask/` directory.

## Examples

Six runnable, self-contained examples under [`examples/`](examples/):

| Example                                      | Demonstrates                                   |
|----------------------------------------------|------------------------------------------------|
| [01-hello](examples/01-hello/)               | Smallest possible cached task                  |
| [02-python-lib](examples/02-python-lib/)     | install / lint / typecheck / test / build      |
| [03-parallel](examples/03-parallel/)         | `-j N` fan-out and `parallel=False` barrier    |
| [04-watch](examples/04-watch/)               | `ntask watch` rerun-on-change loop             |
| [05-remote-cache](examples/05-remote-cache/) | local-fs remote backend shared between clones  |
| [06-monorepo](examples/06-monorepo/)         | `@group(...)` namespacing and cross-group deps |

`cd` into any of them and run `ntask --list`.

## Features

| feature                          | ntask |  make   |  just   | invoke  |  doit   |   poe   |
|----------------------------------|:-----:|:-------:|:-------:|:-------:|:-------:|:-------:|
| Typed Python tasks               |  yes  |   no    |   no    | partial |   no    | partial |
| Content-hash input caching       |  yes  | partial |   no    |   no    | partial |   no    |
| Transitive cache-key propagation |  yes  |   no    |   no    |   no    | partial |   no    |
| Remote cache (S3/GCS/HTTP)       |  yes  |   no    |   no    |   no    |   no    |   no    |
| DAG dependency resolution        |  yes  |   yes   |   no    | partial |   yes   |   no    |
| Type-hint to CLI args            |  yes  |   no    | partial | partial |   no    |   yes   |
| Parallel DAG execution (`-j`)    |  yes  |   yes   |   no    |   no    |   yes   |   no    |
| Live DAG TUI                     |  yes  |   no    |   no    |   no    |   no    |   no    |
| Windows first-class              |  yes  | partial |   yes   |   yes   |   yes   |   yes   |

When a task misses the cache, ntask names the file or env var that changed. `ntask --why <task>` prints the full breakdown.

## Docs

- [Technical handbook](docs/guide.md): every flag and config key
- [Tutorial: replace your Makefile in 10 minutes](docs/tutorial.md)
- [Caching: the full contract](docs/caching.md)
- [Migrating from Make / just / Invoke / Poe](docs/migration.md)
- [Short API reference](docs/reference.md)

Requirements: Python 3.11.4 or newer.

## License

BSD-3-Clause. Copyright © 2026 Sean Nieuwoudt.
