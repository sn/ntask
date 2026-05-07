# Tutorial: replace your Makefile in 10 minutes

This tutorial converts a typical Python project Makefile into a `tasks.py` and shows you how to use ntask's caching, parallelism, and watch mode.

## Before: a typical Makefile

```makefile
.PHONY: install test lint typecheck build check

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

build:
	python -m build

check: lint typecheck test
```

Drawbacks:
- `make test` runs the full suite every time, even when no source changed.
- Adding a new file to `src/` doesn't automatically invalidate dependent targets.
- There's no concurrency. `make -j` exists but doesn't compose well with Python tooling.

## After: `tasks.py`

```python
from ntask import task, cached, depends, shell

@task
def install():
    """Install dev dependencies."""
    shell('pip install -e ".[dev]"')

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py", "pyproject.toml"])
def test():
    """Run the test suite."""
    shell("pytest -q")

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py", "pyproject.toml"])
def lint():
    """Lint with ruff."""
    shell("ruff check src tests")

@task
@cached(inputs=["src/**/*.py", "pyproject.toml"])
def typecheck():
    """Static-type-check with mypy."""
    shell("mypy src")

@task
@cached(
    inputs=["src/**/*.py", "pyproject.toml", "README.md"],
    outputs=["dist/"],
)
def build():
    """Build the wheel."""
    shell("python -m build")

@task
def check():
    """All quality checks."""
    depends(lint, typecheck, test)
```

Save it as `tasks.py` at your project root. No other configuration needed.

## Run it

```bash
ntask --list                        # show every task with its docstring
ntask check                         # runs lint, typecheck, test in order
ntask check                         # second time: all three are cache hits
ntask check -j                      # run them in parallel across all cores
ntask test                          # run just the test task
ntask --why test                    # explain the last cache decision for test
ntask --graph check                 # draw the DAG as ASCII
```

The first run executes everything. The second `ntask check` looks at the inputs glob, hashes every matching file with xxh3_128, compares to the prior cache key, and short-circuits each task that hasn't changed.

Edit one file under `src/`, run `ntask check` again, and watch only the tasks whose inputs (or transitive upstream inputs) changed actually rerun.

## Add watch mode

```bash
ntask watch test
```

ntask reads the `inputs=[...]` globs of `test`, registers a filesystem watcher, and reruns the task whenever any matching file changes on disk. Save a file, see test output, repeat.

Watch mode requires the target to be `@cached` because the inputs glob is what defines "changed."

## Bonus: type hints become CLI flags

Add a parameter to a task and ntask wires it up automatically:

```python
@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test(pattern: str = "", verbose: bool = False):
    """Run a subset of the test suite."""
    flags = "-v" if verbose else "-q"
    k = f"-k {pattern}" if pattern else ""
    shell(f"pytest {flags} {k}")
```

```bash
ntask test --pattern=auth --verbose
```

Booleans become `--flag`/`--no-flag`. Strings become `--name VALUE`. `Literal[...]` and `Enum` become `--name {choice1,choice2}`. `Path` arguments coerce automatically.

## What you got

- Same five-line invocation surface as Make.
- Skip work the cache says is unchanged: instant `lint`/`typecheck`/`test` when nothing relevant changed.
- Real parallelism with `-j`.
- A live rerun loop with `watch`.
- A diagnostic flag (`--why`) that names the specific file or env var that invalidated the cache.

Read [`caching.md`](caching.md) next for the full cache contract, or jump to [`guide.md`](guide.md) for the comprehensive reference.
