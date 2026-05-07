# ntask

A Python-native task runner with content-hash caching and DAG execution.

```bash
pip install ntask
```

## Why

Your Makefile runs everything every time. Your Justfile has no dependency graph. Your `tasks.py` for Invoke is five years old, has no types, and you still have to write `ctx.run`. This is what a task runner looks like when you start over with caching, types, and a DAG.

## Quickstart

Create a `tasks.py`:

```python
from ntask import task, cached, depends, shell

@task
def install():
    shell("pip install -e .")

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test(pattern: str = "", verbose: bool = False):
    """Run the test suite."""
    flags = "-v" if verbose else ""
    k = f"-k {pattern}" if pattern else ""
    shell(f"pytest {flags} {k}")

@task
@cached(inputs=["src/**/*.py"])
def lint():
    shell("ruff check src/")

@task
def check():
    """All quality checks."""
    depends(lint, test)
```

Run:

```bash
ntask --list                       # show every registered task
ntask test --pattern=auth --verbose
ntask check                        # lint + test in order; both cache
ntask check -j                     # all CPU cores; bare -j picks the count
ntask watch test                   # rerun on every src/ or tests/ change
ntask --why test                   # explain why the last cache lookup missed
ntask --graph check                # ASCII DAG (mermaid / dot also available)
```

The second time you run `ntask check`, both `lint` and `test` are content-hash cache hits and finish in milliseconds. Change one file in `src/` and only the affected tasks rerun, transitively.

## Team cache

Share cache hits across machines via S3 (or GCS, HTTP, NFS):

```toml
# pyproject.toml
[tool.ntask.remote_cache]
type = "s3"
bucket = "my-team-cache"
```

```bash
pip install ntask[s3]
ntask check                        # first person populates, the rest hit instantly
ntask check --offline              # skip the remote for fast dev loops
```

S3-compatibles (MinIO, R2, B2) take an `endpoint_url`. GCS and HTTP backends work the same way; the HTTP backend is plain `GET`/`PUT`/`HEAD` over stdlib `urllib`, so any object store with PUT enabled is fair game.

## Live DAG display

Run `ntask check` from an interactive terminal and a Textual TUI shows a live tree of the DAG with per-task state icons and durations. Pipe the output, set `tui = false` in `[tool.ntask]`, or pass `--no-tui` to fall back to the line-based renderer.

## Other things you'll reach for

- **Exclusive tasks.** `@task(parallel=False)` makes a task a DAG-wide barrier: it waits for everything in flight to drain, then runs alone. Use it for releases, migrations, anything that mutates shared state.
- **Monorepos.** `@group("api")` over a class namespaces every task method as `api.<name>`. Cross-group dependencies via `@task(deps=[Other.task, ...])` or string fqns.
- **Capture output.** `shell("git rev-parse HEAD", capture=True)` returns a `ShellResult` with `.stdout`, `.stderr`, `.returncode`, `.duration`, `.ok`.
- **Force a rerun.** `ntask --force <task>` bypasses the cache for that one task. `ntask --no-cache` ignores the cache entirely. `ntask clean` wipes entry manifests; `ntask clean --all` wipes the whole `.ntask/` directory.

## Examples

Six runnable, self-contained examples under [`examples/`](examples/):

| #                                            | Demonstrates                                   |
|----------------------------------------------|------------------------------------------------|
| [01-hello](examples/01-hello/)               | Smallest possible cached task                  |
| [02-python-lib](examples/02-python-lib/)     | install / lint / typecheck / test / build      |
| [03-parallel](examples/03-parallel/)         | `-j N` fan-out and `parallel=False` barrier    |
| [04-watch](examples/04-watch/)               | `ntask watch` rerun-on-change loop             |
| [05-remote-cache](examples/05-remote-cache/) | local-fs remote backend shared between clones  |
| [06-monorepo](examples/06-monorepo/)         | `@group(...)` namespacing and cross-group deps |

`cd` into any directory and run `ntask --list`.

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

Cache miss messages name the specific file or env change that caused the invalidation. `ntask --why <task>` prints the full breakdown.

## Docs

- [Technical handbook](docs/guide.md) - the comprehensive reference, every flag and config key
- [Tutorial: replace your Makefile in 10 minutes](docs/tutorial.md)
- [Caching: the full contract](docs/caching.md)
- [Migrating from Make / just / Invoke / Poe](docs/migration.md)
- [Short API reference](docs/reference.md)
- [Roadmap](docs/roadmap.md)

Requirements: Python 3.11 or newer. BSD-3-Clause.

## License

BSD-3-Clause. Copyright © 2026 Sean Nieuwoudt.
