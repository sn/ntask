# API reference

All public symbols live at the `ntask` top level:

```python
from ntask import (
    task, cached, group, depends,
    shell, ShellResult,
    NtaskError, CycleError, DiscoveryError, ShellError,
    __version__,
)
```

## `@task`

```python
@task
def fn(): ...

@task(deps=[other], parallel=True)
def fn(): ...
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `deps` | `list[Callable \| str]` | `[]` | Tasks (or fqn strings) that must complete before this one. |
| `parallel` | `bool` | `True` | If `False`, this task runs alone: it waits for in-flight siblings to drain, then holds the DAG exclusively for its runtime. |
| `concurrency` | `int \| None` | `None` | **Deprecated, removed in 1.0.** Has no effect. |

The decorated function keeps its original signature and is callable as a normal Python function from tests or other code.

## `@cached`

```python
@cached(
    inputs=["src/**/*.py"],
    outputs=["dist/"],
    env=["CI"],
    propagate=True,
    strict=True,
)
def fn(): ...
```

Stack with `@task`. Both decorator orderings work.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `inputs` | `list[str]` | `[]` | Gitignore-style globs against the project root. Matched files are content-hashed. |
| `outputs` | `list[str]` | `[]` | Globs captured to a content-addressed store after success; restored on a hit. |
| `env` | `list[str]` | `[]` | Env var names whose values feed the cache key. |
| `propagate` | `bool` | `True` | Include direct dependencies' resolved cache keys in this key. |
| `strict` | `bool` | `True` | Include body hash, Python version, and platform tag in the key. |

See [`caching.md`](caching.md) for the full contract.

## `@group`

```python
@group("api")
class Api:
    @task
    def lint():
        shell("...")

    @task
    @cached(inputs=["api/**/*.py"])
    def test():
        shell("...")
```

Class decorator. Every `@task`-decorated method inside becomes `<group-name>.<method>` in the registry. Methods take no `self`. Group names must be non-empty and must not contain `.`.

Cross-group dependencies via `@task(deps=[Api.lint, ...])` (the class attribute resolves through the underlying `__ntask_task__` marker) or via fqn strings (`@task(deps=["api.lint"])`).

## `depends(*tasks)`

Inside a task body, declares dependencies. Static analysis lifts the call into the DAG at registration time, so deps resolve before execution.

```python
@task
def check():
    depends(lint, test)
```

- Bare-name references (`lint`, `test`) work: they map to registered fqns of the same name.
- Dotted attributes (`Api.lint`) and string fqns are NOT picked up by static analysis. For cross-group references, use `@task(deps=[...])` instead.
- Outside a running task (during import, in tests), `depends()` is a no-op so importing `tasks.py` doesn't execute anything.

## `shell()`

```python
def shell(
    cmd: str | list[str],
    *,
    check: bool = True,
    capture: bool = False,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> ShellResult | None
```

Run a subprocess.

- **String `cmd`**: runs through `/bin/sh -c` (POSIX) or `cmd.exe /c` (Windows). Shell expansion applies.
- **List `cmd`**: direct `execve`, no shell. Safer when args are user-supplied.
- **`check=True`** (default): non-zero exit raises `ShellError`.
- **`capture=True`**: returns a `ShellResult` with stdout/stderr collected.
- **Default**: streams output live and returns `None` on success.

Under parallel execution (`-j > 1`), output is automatically prefixed with `[fqn]` per line so concurrent tasks' lines don't interleave silently. Under the TUI, output is captured to `.ntask/logs/<run-id>/<fqn>.log`. `capture=True` always uses captured mode regardless of context.

## `ShellResult`

```python
@dataclass(frozen=True, slots=True)
class ShellResult:
    returncode: int
    stdout: str
    stderr: str
    duration: float

    @property
    def ok(self) -> bool: ...
```

Returned by `shell(capture=True)` (always populated) or `shell(check=False)` (populated only on non-zero exit). Otherwise `shell()` returns `None`.

## Errors

| Class | Raised when |
|---|---|
| `NtaskError` | Base class. Catch to handle any ntask-raised exception. |
| `DiscoveryError` | `tasks.py` / `tasks/` not found, or import failed. |
| `CycleError` | Circular dependency in the DAG. Has `.cycle: list[str]`. |
| `ShellError` | `shell()` exited non-zero with `check=True`. Has `.returncode: int` and `.cmd: str \| list[str]`. |

## CLI

```
ntask [GLOBAL FLAGS] [TASK [TASK_ARGS...]]
```

| Flag | Description |
|---|---|
| `-l`, `--list` | List all registered tasks with docstrings. |
| `--graph [TASK]` | Render the DAG. With a task, only the reachable subgraph. |
| `--graph-format {ascii,mermaid,dot}` | Output format for `--graph` (default `ascii`). |
| `--dry-run` | Print the task plan without executing. |
| `--no-cache` | Don't read or write the cache. |
| `--offline` | Skip the remote cache; use local only. |
| `--force TASK` | Force-run a task (bypass its cache lookup). Repeatable. |
| `--why TASK` | Explain the last cache decision for TASK. |
| `-j [N]`, `--jobs [N]` | Concurrency cap. Bare `-j` uses `os.cpu_count()`. |
| `--keep-going` | Continue independent tasks after a failure. |
| `-v`, `--verbose` | Stream all output. |
| `-q`, `--quiet` | Suppress cache-hit lines. |
| `--no-color` | Disable ANSI colour. |
| `--no-tui` | Use the line-based renderer instead of the live TUI. |
| `--version` | Print version and exit. |
| `-h`, `--help` | Print help. |

### Subcommands

```
ntask <task> [args...]    # run a task; args populate task parameters
ntask clean [--all]       # wipe .ntask/cache (or the whole .ntask/ tree)
ntask watch <task> [args] # rerun task on input changes; requires @cached
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | All tasks succeeded (cache hits count as success). |
| 1 | At least one task failed. |
| 2 | Usage / discovery error. |
| 130 | Ctrl-C interrupt. |

## Configuration

Read from `[tool.ntask]` in the project's `pyproject.toml`.

| Key | Type | Default | Description |
|---|---|---|---|
| `cache_dir` | string | `".ntask"` | Cache directory, relative to project root. |
| `default_concurrency` | int | `1` | Used when `-j` is not passed. |
| `tui` | bool / null | `null` | `null` = auto-detect; `false` = always line-based; `true` = prefer TUI on TTY. |

Remote-cache config goes under `[tool.ntask.remote_cache]`; see [`guide.md`](guide.md) §9.

## Type-hint to CLI mapping

Function signatures become argparse parsers automatically.

| Hint | CLI form |
|---|---|
| `s: str = ""` | `--s VALUE` (or positional if no default) |
| `n: int = 0` | `--n VALUE` |
| `flag: bool = False` | `--flag` |
| `flag: bool = True` | `--no-flag` |
| `mode: Literal["a", "b"]` | positional choice from `{a,b}` |
| `mode: SomeEnum` | choice from enum values |
| `path: Path` | path coerced via `Path(value).expanduser()` |
| `items: list[str]` | `--items A B C` (zero or more) |

Defaults make the parameter optional with a `--` flag; missing default makes it positional.

## Public marker attributes

ntask attaches a few dunder attributes to your decorated functions so the runtime can resolve cross-group references. These are public but stable:

| Attribute | Type | Meaning |
|---|---|---|
| `<fn>.__ntask_task__` | `str` | The fqn the function is registered under. |
| `<fn>.__ntask_cached_config__` | `CachedConfig` | (only when `@cached` runs before `@task`) |
| `<fn>.__ntask_group__` | `str \| None` | (only inside a `@group(...)` class) |

You can read these for introspection. Don't mutate them.

## Version

```python
ntask.__version__   # "1.0.0"
```
