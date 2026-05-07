# Migrating to ntask

## From Make

Drop `.PHONY:`. Every task is a Python function.

```makefile
install:
	pip install -e ".[dev]"

test: install
	pytest

lint:
	ruff check src/

check: lint test
```

becomes:

```python
from ntask import task, cached, depends, shell

@task
def install():
    shell('pip install -e ".[dev]"')

@task(deps=[install])
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test():
    shell("pytest")

@task
@cached(inputs=["src/**/*.py"])
def lint():
    shell("ruff check src/")

@task
def check():
    depends(lint, test)
```

What you gain: content-hash caching, real parallelism (`ntask check -j`), typed CLI flags from the function signature, watch mode, and a live TUI display.

What you lose: nothing. Tasks still call shell commands. The function body is the recipe.

Mtime-based "is this newer than that?" checks disappear because ntask doesn't trust mtime. Content-hash decides instead.

## From just

`Justfile`:

```just
test:
    pytest

lint:
    ruff check src/

check: lint test
```

becomes:

```python
from ntask import task, depends, shell, cached

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test():
    shell("pytest")

@task
@cached(inputs=["src/**/*.py"])
def lint():
    shell("ruff check src/")

@task
def check():
    depends(lint, test)
```

just is great for ergonomics; ntask adds caching, a DAG, and parallel execution. If you only need command aliases without a dependency graph, just is the right tool. If you find yourself reaching for `if [ X -nt Y ]` checks, you've outgrown it.

## From Invoke

`tasks.py` (Invoke style):

```python
from invoke import task

@task
def install(ctx):
    ctx.run("pip install -e .")

@task(install)
def test(ctx):
    ctx.run("pytest")
```

becomes:

```python
from ntask import task, shell

@task
def install():
    shell("pip install -e .")

@task(deps=[install])
def test():
    shell("pytest")
```

Differences:
- No `ctx` parameter. `shell()` does what `ctx.run()` did.
- Caching, DAG, parallel execution, and the typed-CLI machinery are built in instead of bolted on.
- Argparse construction is automatic from type hints.

## From Poe (poethepoet)

`pyproject.toml`:

```toml
[tool.poe.tasks]
test = "pytest"
lint = "ruff check src/"
check = ["lint", "test"]
```

becomes:

```python
from ntask import task, depends, shell, cached

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test():
    shell("pytest")

@task
@cached(inputs=["src/**/*.py"])
def lint():
    shell("ruff check src/")

@task
def check():
    depends(lint, test)
```

Poe lives in `pyproject.toml` and is great when you mostly run shell strings. ntask is for when those shell strings have grown into a build pipeline with caching needs.

## From doit

`dodo.py`:

```python
def task_test():
    return {
        "actions": ["pytest"],
        "file_dep": ["src/", "tests/"],
    }
```

becomes:

```python
from ntask import task, cached, shell

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test():
    shell("pytest")
```

doit's task-as-dict format is powerful but verbose. ntask uses Python decorators on plain functions; type hints become CLI flags; `inputs=[...]` does what `file_dep` did with content-hash caching instead of mtime.

## Migration checklist

For any source format:

1. Rename the file to `tasks.py`. Add `from ntask import task, cached, depends, shell`.
2. Rewrite each target as a `@task`-decorated function. Function name = task name.
3. Replace shell-out calls with `shell("...")`.
4. Translate dependencies:
   - For static deps: `@task(deps=[other])`.
   - For runtime deps inside a task body: `depends(other)` (works in the same scope).
5. Add `@cached(inputs=[...])` to anything you don't want to re-run unnecessarily.
6. Run `ntask --list`. Then `ntask --graph <target>`. Then start running tasks.

If a task previously took mode/option flags, add typed parameters:

```python
@task
def serve(port: int = 8000, debug: bool = False):
    shell(f"uvicorn app:main --port={port} {'--reload' if debug else ''}")
```

```bash
ntask serve --port=9000 --debug
```
