# ntask Technical Handbook

> Version 1.0.0 - Python 3.11+ - BSD-3-Clause

---

## Contents

1. [Introduction](#1-introduction)
2. [Installation](#2-installation)
3. [Quickstart](#3-quickstart)
4. [Core concepts](#4-core-concepts)
5. [CLI reference](#5-cli-reference)
6. [Caching](#6-caching)
7. [Parallel execution](#7-parallel-execution)
8. [Watch mode](#8-watch-mode)
9. [Remote cache](#9-remote-cache)
10. [TUI](#10-tui)
11. [Configuration](#11-configuration)
12. [Architecture](#12-architecture)
13. [Recipes and patterns](#13-recipes-and-patterns)
14. [FAQ and troubleshooting](#14-faq-and-troubleshooting)
15. [Appendix A: public API](#appendix-a-public-api)
16. [Appendix B: glossary](#appendix-b-glossary)

---

## 1. Introduction

ntask is a Python-native task runner built around four properties:

- **Python-native.** Tasks are plain Python functions. No DSL, no YAML, no shell-string-with-substitution. Type annotations drive CLI argument parsing automatically.
- **Explicit.** Every dependency is declared. Nothing runs unless the DAG asks it to.
- **File-based.** Configuration lives in `tasks.py` and `pyproject.toml`. There's no server, no daemon.
- **Cache-correct.** Caching is content-addressed, not timestamp-based. A file checked out, restored, or rebuilt with identical content always hashes the same.

### The problem it solves

Make re-runs everything unless you carefully maintain `.PHONY` targets and mtime stamps. just has no dependency graph. Invoke (Fabric's task runner) works for simple tasks but has no DAG and no caching. doit has caching but uses a verbose dict-based task format. Bazel is hermetic and expensive to set up.

ntask occupies the space between those tools: smarter than Make for the cases that matter (lint, typecheck, test, build) without Bazel's setup cost.

### Killer feature: transitive cache-key propagation

A `@cached` task's key includes the resolved keys of all its upstream dependencies. If task A depends on task B, and B's inputs change, B gets a new key, which feeds into A's key. A then misses even when its own inputs are unchanged.

You get this for free. Declare your deps; propagation is automatic.

### Comparison

| Feature | ntask | make | just | invoke | doit | poe |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Typed Python tasks | yes | no | no | partial | no | partial |
| Content-hash caching | yes | partial | no | no | partial | no |
| Transitive cache-key propagation | yes | no | no | no | partial | no |
| Remote cache (S3/GCS/HTTP) | yes | no | no | no | no | no |
| DAG dependency resolution | yes | yes | no | partial | yes | no |
| Type-hint to CLI args | yes | no | partial | partial | no | yes |
| Parallel DAG execution | yes | yes | no | no | yes | no |
| Live DAG TUI | yes | no | no | no | no | no |
| Zero daemon | yes | yes | yes | yes | yes | yes |

---

## 2. Installation

```bash
pip install ntask
```

Installs the `ntask` console script and the `ntask` Python package.

**Requirements:** Python 3.11 or newer. Tested on 3.11, 3.12, and 3.13.

### Optional extras

```bash
pip install ntask[s3]     # boto3 for S3 remote cache
pip install ntask[gcs]    # google-cloud-storage for GCS remote cache
pip install ntask[all]    # both
```

The `local-fs` and `http` remote backends use only the standard library and need no extra.

### Core dependencies

| Package | Minimum | Role |
|---|---|---|
| `rich` | 13.7 | Terminal rendering |
| `xxhash` | 3.4 | Content hashing (xxh3_128) |
| `pathspec` | 0.12 | Gitignore-style globs |
| `anyio` | 4.3 | Structured async concurrency |
| `watchfiles` | 0.22 | OS-level FS events for watch mode |
| `textual` | 0.80 | TUI framework |

### Verify

```bash
ntask --version
# ntask 1.0.0
```

---

## 3. Quickstart

`tasks.py`:

```python
from ntask import task, cached, depends, shell

@task
def install():
    """Install dev dependencies."""
    shell('pip install -e ".[dev]"')

@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test():
    """Run the test suite."""
    shell("pytest -q")

@task
@cached(inputs=["src/**/*.py"])
def lint():
    """Lint with ruff."""
    shell("ruff check src/")

@task
def check():
    """All quality checks."""
    depends(lint, test)
```

```bash
ntask --list
ntask test
ntask check                 # lint + test
ntask check -j              # all CPU cores
ntask watch test            # rerun on input change
```

The first run executes everything. The second `ntask check` finds matching cache entries for `lint` and `test` and skips both:

```
o lint cached (3a8f9c2d)
o test cached (4b7e1a82)
+ check (0.00s)
```

Edit a source file and run again - only the affected tasks rerun. Run `ntask --why test` to see exactly what changed.

---

## 4. Core concepts

### 4.1 `@task`

Registers a function in the global task registry. Usable bare or as a factory:

```python
from ntask import task

@task
def build():
    ...

@task(deps=[build], parallel=True)
def publish():
    ...
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `deps` | `list[Callable \| str]` | `[]` | Tasks (or fqn strings) that must complete first. |
| `parallel` | `bool` | `True` | If `False`, this task runs alone (see §7.3). |
| `concurrency` | `int \| None` | `None` | **Removed in 1.0.** Has no effect. |

Decorated functions keep their original signature and remain callable from tests or other code.

**Discovery** walks upward from the current working directory looking for `tasks.py` or a `tasks/` package (with `__init__.py`). The first match wins. Importing the module executes top-level decorators which populate the registry.

**FQN.** A bare task `build` has fqn `"build"`. A method inside a `@group` has fqn `"<group>.<method>"`.

**Type hints become CLI args.** ntask inspects the function signature and builds an argparse subparser for the task automatically:

```python
@task
def test(pattern: str = "", verbose: bool = False):
    flags = "-v" if verbose else ""
    k = f"-k {pattern}" if pattern else ""
    shell(f"pytest {flags} {k}")
```

```bash
ntask test --pattern=auth --verbose
```

| Hint | CLI |
|---|---|
| `s: str = ""` | `--s VALUE` |
| `n: int = 0` | `--n VALUE` |
| `flag: bool = False` | `--flag` |
| `flag: bool = True` | `--no-flag` |
| `m: Literal["a","b"]` | choice from `{a,b}` |
| `m: SomeEnum` | choice from enum values |
| `p: Path` | coerced via `Path.expanduser` |
| `xs: list[str]` | `--xs A B C` (zero or more) |

Missing default makes the parameter positional.

### 4.2 `@cached`

Opts a task into content-hash caching. Stack with `@task`; either order works.

```python
@task
@cached(inputs=["src/**/*.py"], env=["CI"], outputs=["dist/"])
def build():
    shell("python -m build")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `inputs` | `list[str]` | `[]` | Gitignore-style globs; matched files are content-hashed. |
| `env` | `list[str]` | `[]` | Env var names included in the key. |
| `outputs` | `list[str]` | `[]` | Globs captured to the local store after success; restored on hit. |
| `propagate` | `bool` | `True` | Include upstream cache keys in this key. |
| `strict` | `bool` | `True` | Include Python version, platform tag, and body hash. |

See §6 for the full cache contract.

### 4.3 `@group`

Class decorator that namespaces methods under a common prefix:

```python
from ntask import task, group, shell

@group("docs")
class Docs:
    @task
    def build():
        shell("mkdocs build")

    @task
    def serve():
        shell("mkdocs serve")
```

Registers `docs.build` and `docs.serve`. Methods take no `self`. Group names must be non-empty and must not contain `.`. Nesting groups isn't supported.

Cross-group dependencies work via `@task(deps=[Other.method, ...])` - the class attribute resolves through the underlying `__ntask_task__` marker - or via fqn strings.

### 4.4 `depends(*tasks)`

Declares dependencies inside a task body.

```python
@task
def check():
    depends(lint, test)
```

Two roles:

1. **Static (import time):** an AST visitor reads `depends(name)` calls and adds DAG edges before any task runs. Bare names that match registered fqns are picked up; dotted attributes and string fqns are not.
2. **Runtime:** when execution reaches the call, `depends()` is a no-op (the static analysis already wired things up).

For cross-group references, prefer `@task(deps=[Api.lint, "web.test"])` over `depends()`.

### 4.5 `shell()`

Subprocess helper.

```python
from ntask import shell, ShellResult

# String - runs through /bin/sh -c (POSIX) or cmd.exe /c (Windows)
shell("ruff check src/")

# List - direct exec, no shell interpolation
shell(["pytest", "-v", "-k", pattern])

# Capture
result: ShellResult = shell("git rev-parse HEAD", capture=True)
print(result.stdout.strip())

# Tolerate failure
result = shell("optional-tool", check=False)
if not result.ok:
    print("skipping")

# Override cwd / env
shell("make", cwd="/path/to/sub", env={"CC": "gcc"})
```

```python
def shell(
    cmd: str | list[str],
    *,
    check: bool = True,
    capture: bool = False,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> ShellResult | None: ...
```

`ShellResult` fields: `returncode: int`, `stdout: str`, `stderr: str`, `duration: float`, plus `ok: bool` (property).

**Execution modes** chosen automatically:

1. **Capture** (`capture=True`) - `subprocess.run` with `capture_output=True`. No streaming, no prefix.
2. **Log-file** (TUI active) - stdout+stderr piped to `.ntask/logs/<run-id>/<fqn>.log`. Nothing on screen.
3. **Prefixed streaming** (parallel, no TUI) - lines piped through threads that prefix `[fqn] ` before flushing.
4. **Default streaming** - `subprocess.run` inheriting stdout/stderr.

`check=True` (default) raises `ShellError` on non-zero exit.

### 4.6 Errors

```
NtaskError
+- DiscoveryError       tasks.py / tasks/ not found or import failed
+- CycleError           circular dependency in the DAG
+- ShellError           shell() exited non-zero
```

```python
from ntask import NtaskError, CycleError, DiscoveryError, ShellError
```

`CycleError` has `.cycle: list[str]` and renders as `cycle in task graph: a -> b -> a`.

`ShellError` has `.returncode: int` and `.cmd: str | list[str]`.

---

## 5. CLI reference

All interactions go through the `ntask` console script.

### Global flags

| Flag | Description |
|---|---|
| `-l`, `--list` | List all registered tasks with docstring summaries. |
| `--graph [TASK]` | Render the DAG. With a task, only the reachable subgraph. |
| `--graph-format {ascii,mermaid,dot}` | Output format for `--graph`. |
| `--dry-run` | Print the task plan without running. |
| `--no-cache` | Don't read or write the cache. |
| `--offline` | Skip the remote cache; use local only. |
| `--force TASK` | Force-run TASK (bypass its cache). Repeatable. |
| `--why TASK` | Explain the last cache decision for TASK. |
| `-j [N]`, `--jobs [N]` | Concurrency cap. Bare `-j` uses `os.cpu_count()`. |
| `--keep-going` | Continue independent tasks after a failure. |
| `-v`, `--verbose` | Stream all output. |
| `-q`, `--quiet` | Suppress cache-hit lines. |
| `--no-color` | Disable ANSI colour. |
| `--no-tui` | Use the line-based renderer. |
| `--version` | Print version and exit. |
| `-h`, `--help` | Print help. |

### Subcommands

#### `ntask <task> [args...]`

Run a task and its dependencies. Args are parsed from the function signature.

```bash
ntask test --pattern=auth --verbose
ntask release --version=1.2.0
```

#### `ntask --list`

Lists all tasks with their docstring summaries and a `*` mark on cached tasks. Tasks inside a `@group` appear under a sub-table.

```
                        Tasks
+---------+---+----------------------------------------+
| build   | * | Build the wheel.                       |
| check   |   | All quality checks.                    |
| install |   | Install dev dependencies.              |
| lint    | * | Lint with ruff.                        |
| test    | * | Run the test suite.                    |
+---------+---+----------------------------------------+
```

Use `--graph` for dependency arrows.

#### `ntask --graph [TASK]`

Renders the dependency tree.

```bash
ntask --graph check
ntask --graph --graph-format mermaid > docs/dag.md
ntask --graph --graph-format dot | dot -Tsvg > dag.svg
```

#### `ntask --dry-run <task>`

```
$ ntask --dry-run check
would run:
  lint
  test
  check
```

#### `ntask --why <task>`

Computes the current cache key, loads the prior entry, and diffs them.

```
$ ntask --why test
Task: test
Last cached: 2026-04-22 10:43:12 (2h 15m ago)
Cache key: 3a8f9c2d...
Duration: 4.21s

If you ran `test` now:
  x MISS - 2 changes since last cache

Changes:
  - src/auth.py                modified
  - BUILD_ENV                  changed

Inputs:
  Declared globs: src/**/*.py, tests/**/*.py
  Files matched: 87 (1 changed)

Environment:
  BUILD_ENV = 'prod' (changed)
```

`--why` reports local workspace deltas against the named task's prior breakdown. It doesn't simulate the full transitive graph.

#### `ntask --force <task>`

Bypass the cache for a specific task. The task still runs and writes a new cache entry.

```bash
ntask --force test check    # force test; lint cached as usual
```

#### `ntask clean [--all]`

```bash
ntask clean         # remove .ntask/cache/ (output blobs survive)
ntask clean --all   # remove the entire .ntask/ directory
```

#### `ntask watch <task> [args...]`

See §8.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | All tasks succeeded. |
| 1 | At least one task failed. |
| 2 | Usage / discovery error. |
| 130 | Interrupted (Ctrl-C). |

---

## 6. Caching

The full contract is in [`caching.md`](caching.md). This section gives the working summary.

### 6.1 Why xxh3_128

xxh3_128 is a non-cryptographic 128-bit hash. About 10x faster than SHA-256 on modern hardware, with collision probability negligible at the file counts a build pipeline produces. ntask's threat model is accidental collision, not adversarial.

### 6.2 The cache key

Every `@cached` task's key is xxh3_128 over a length-prefixed concatenation:

1. Format version (`ntask/v1`)
2. Task fqn
3. Body hash (if `strict=True`)
4. Python version (if `strict=True`)
5. Platform tag (if `strict=True`)
6. Env values - `NAME=value` per declared env name, sorted; unset is `<unset>`
7. Input patterns - sorted globs
8. Input manifest digest - hash of `(path, content-digest, mode)` triples
9. Upstream keys - resolved keys of direct deps in declaration order (skipped if `propagate=False`)

### 6.3 Body hash: structural, not lexical

```
inspect.getsource -> ast.parse(dedent) -> strip docstrings ->
ast.dump(annotate_fields=False, include_attributes=False) -> xxh3_128
```

Consequences:
- Reformatting (ruff format / black) doesn't invalidate.
- Adding or editing docstrings doesn't invalidate.
- Comment changes don't invalidate.
- Real logic changes do invalidate.

### 6.4 Transitive propagation

If B depends on A, A's resolved key is part of B's key. A's miss propagates to B. This composes through the entire DAG.

`@cached(propagate=False)` opts out for tasks whose output is genuinely independent of upstream output.

### 6.5 Strict mode

`strict=True` (default) ties the key to body, Python version, and platform tag.

`strict=False` replaces those three with placeholders so cache entries persist across refactors, Python upgrades, and OS/arch changes. Use only for pure data transformations where you actively want cross-platform sharing.

### 6.6 Input glob matching

`pathspec` `gitwildmatch` mode:

- `src/**/*.py` - all `.py` recursively under `src/`
- `*.toml` - any `.toml` at the root
- `!src/generated/**/*.py` - re-modify a previously-included match (same as `.gitignore`). Order matters: include first, then negate.

`.gitignore` is loaded from the project root and applied automatically. Files are sorted before hashing - filesystem ordering is irrelevant.

### 6.7 Output capture and restore

After success, declared `outputs` are captured into `.ntask/outputs/<outputs-hash>/`. The outputs-hash is itself a hash over `(path, content-digest)` pairs.

On a hit, files are hard-linked (POSIX) or copied (Windows / cross-fs) back to the workspace.

Two implications:
- Hard-linked files share inode and mtime with the captured copy. Tools that compare mtimes may behave differently than after a fresh run.
- Output tarballs for remote upload are constructed in memory. Outputs in the gigabyte+ range may pressure RAM during push.

### 6.8 The `.ntask/` layout

```
.ntask/
+-- cache/
|   +-- <fqn>/
|       +-- <key>.json     CacheEntry with breakdown
+-- outputs/
|   +-- <outputs-hash>/    content-addressed output tree
+-- logs/
    +-- <run-id>/          per-run TUI log dir
        +-- lint.log
        +-- test.log
```

`ntask clean` removes `cache/` only. `ntask clean --all` removes the whole `.ntask/`. Log directories accumulate; clean manually with `rm -rf .ntask/logs/`.

### 6.9 Miss reporting

Every miss produces a `MissReport` of `MissItem(kind, detail)` entries.

| `kind` | Meaning |
|---|---|
| `first-run` | No prior entry. |
| `input-modified` | A matched file's content or mode changed. |
| `input-added` | A new file appeared in the matched set. |
| `input-removed` | A previously-matched file was deleted. |
| `env-changed` | An env var's value changed. |
| `env-added` | An env var appeared. |
| `env-removed` | An env var disappeared. |
| `body-changed` | The structural AST changed. |
| `upstream-invalidated` | An upstream dep's key changed. |
| `python-changed` | Python version differs. |
| `platform-changed` | Platform tag differs. |

Order: `input-*` first (alphabetical by path, kinds interleaved), then `env-*` (alphabetical), then `body-changed`, then `upstream-invalidated`, then `python-changed`/`platform-changed`. `first-run` is always alone.

Inline rendering shows the first item:
```
x test: cache miss (input-modified: src/auth.py (+2 more))
```

`--why` shows the full report plus the prior breakdown.

### 6.10 Safety valves

| Command | Effect |
|---|---|
| `ntask --no-cache` | Disable all cache reads/writes for this invocation. |
| `ntask --force lint` | Bypass `lint`'s cache lookup; still write after. |
| `ntask clean` | Wipe cache entries (outputs survive). |
| `ntask clean --all` | Wipe the entire `.ntask/`. |

---

## 7. Parallel execution

Sequential by default. Opt in per invocation.

### 7.1 Enabling

```bash
ntask check -j        # concurrency = os.cpu_count()
ntask check -j 4      # cap at 4
ntask check --jobs 2  # same as -j 2
```

`-j` is a global cap implemented as an `anyio.CapacityLimiter`. DAG ordering is preserved: a task waits for its dependencies; the limiter adds a "slot must be free" condition on top.

### 7.2 Prefixed output

When concurrency is greater than 1, `shell()` reads the per-task `_current_line_prefix` context var (set by the executor) and routes process output through threaded pumps that prefix `[fqn] ` per line:

```
[lint] checking src/
[test] pytest starting
[lint] src/auth.py: ok
[test] collected 87 items
[lint] All checks passed.
```

Lines from the same task are atomic; lines from different tasks may interleave. With concurrency 1 (default) or `shell(capture=True)`, no prefix is added.

### 7.3 `@task(parallel=False)` - DAG-wide barrier

For a release step, a database migration, anything that mutates shared state:

```python
@task(parallel=False)
def migrate():
    shell("alembic upgrade head")
```

Two invariants:
1. Before an exclusive task starts, all running normal tasks drain to zero.
2. While an exclusive task runs, no other task starts.

Implemented via an internal `_ParallelCoordinator` with anyio events. `parallel=False` is a DAG-wide property; even under `-j 16`, the exclusive task runs alone.

### 7.4 Stdin under parallel

Under `-j > 1`, `shell()` sets `stdin=DEVNULL`. Tasks that prompt for input will receive EOF. If a task genuinely needs a TTY (pdb, interactive prompt), run sequentially (`-j 1`).

---

## 8. Watch mode

```bash
ntask watch test
ntask watch test --pattern=auth
ntask watch lint -j 4
```

Reruns a `@cached` task whenever any of its declared input files changes on disk.

### 8.1 Behaviour

- The target must be `@cached(inputs=[...])`. Watch uses the inputs glob as the watch set. Non-cached targets exit with code 2.
- On startup, watch runs the task once even if the cache would have been a hit (gives you fresh output).
- After the initial run, the watch loop awaits OS-level FS events from `watchfiles`. Each batch is filtered through `inputs` globs and `.gitignore`.
- Relevant change: clear screen, print status header (`Watching: <patterns>` / `Target: <fqn> (<change-detail>)`), rerun.
- Changes during a run are coalesced into one queued rerun; no cancel-and-restart.

### 8.2 Limitations

- One target per `ntask watch` invocation.
- Editing `tasks.py` doesn't reload. Ctrl-C and restart to pick up new task definitions.
- The TUI doesn't activate during watch (line-based renderer is used).
- A delete-and-replace where the new file has the same content hash isn't detected as a change (rare edge case).

Ctrl-C exits cleanly with code 0.

---

## 9. Remote cache

Share cache hits across machines.

### 9.1 Configuration

```toml
# pyproject.toml
[tool.ntask.remote_cache]
type = "s3"
bucket = "my-team-cache"
prefix = "myproject/"
```

No code changes needed. Remote is transparent: local first, then remote, then execute.

### 9.2 Read-through / write-through

For each `@cached` task:

1. Compute the key.
2. Check local (`.ntask/cache/<fqn>/<key>.json`). Hit -> restore outputs, skip.
3. Check remote (unless `--offline`). Hit -> download entry + outputs, mirror to local, restore.
4. Execute.
5. Write local entry.
6. Push entry + output tarball to remote (unless `--offline`).

### 9.3 Backends

**Local filesystem** (shared NFS, Docker volume, single-host multi-user):

```toml
[tool.ntask.remote_cache]
type = "local-fs"
path = "/mnt/shared/cache"
```

**HTTP** (any server with PUT enabled - plain `GET` / `PUT` / `HEAD` over stdlib `urllib`):

```toml
[tool.ntask.remote_cache]
type = "http"
url = "https://cache.example.com/ntask"
auth_header = "Bearer $CACHE_TOKEN"   # $VAR expanded at load time
```

`$VAR` references in any string field are expanded via `os.path.expandvars` at config load time. No WebDAV verbs are used; nginx with `ngx_http_dav_module`, Caddy, S3 presigned-URL fronts, or any plain HTTP PUT-capable server work.

**S3** (`pip install ntask[s3]`):

```toml
[tool.ntask.remote_cache]
type = "s3"
bucket = "my-team-cache"
prefix = "ntask/"
```

Credentials follow boto3's standard chain (env vars, `~/.aws/credentials`, IAM, SSO).

S3-compatibles (MinIO, R2, B2):

```toml
[tool.ntask.remote_cache]
type = "s3"
bucket = "builds"
endpoint_url = "https://s3.example.r2.cloudflarestorage.com"
```

**GCS** (`pip install ntask[gcs]`):

```toml
[tool.ntask.remote_cache]
type = "gcs"
bucket = "my-team-cache"
prefix = "ntask/"
```

Credentials: `gcloud auth application-default login` or `GOOGLE_APPLICATION_CREDENTIALS`.

### 9.4 Object layout

| Key pattern | Content |
|---|---|
| `<prefix>entries/<fqn>/<key>.json` | JSON-serialised `CacheEntry`. |
| `<prefix>outputs/<outputs-hash>.tar.gz` | Deterministic tar.gz of output files. |

The tarball is created with sorted entries, `mtime=0`, `uid=gid=0`, empty uname/gname. Identical output trees produce byte-identical tarballs regardless of when or where they were captured.

### 9.5 Error handling

If the remote is unreachable (network, auth, misconfig):

1. ntask prints one warning to stderr: `warning: remote cache unreachable: <type>: <message>. Falling back to local.`
2. Subsequent remote operations are silently skipped for the rest of the process.

Builds never fail because the remote is down. `--offline` is a faster opt-out when you know the remote is unavailable.

### 9.6 Trust model

The remote operates on trust-your-team. A team member with write access can publish a cache entry with corrupt outputs. Same model as shared CI artefact storage. Use per-team buckets with appropriate IAM. Don't expose to untrusted parties.

### 9.7 Performance notes

- Uploads are synchronous; a task with large outputs blocks completion until upload finishes.
- Output tarballs are constructed in memory; avoid declaring outputs that are gigabytes in size.
- No per-task remote disable; use bucket-level IAM if you need exclusion.

---

## 10. TUI

When stdout is a TTY and the TUI is enabled (default), `ntask` displays a live full-screen interface using [Textual](https://textual.textualize.io/).

### 10.1 What you see

```
+-- ntask -----------------------------------------------------+
| > ntask                                                       |
|   +- > check        waiting                                   |
|       +- o lint       cached                                  |
|       +- o typecheck  cached                                  |
|       +- > test       running (8.3s)                          |
|                                                               |
| starting...                                                   |
+---------------------------------------------------------------+
```

| Icon | State |
|---|---|
| `.` | waiting |
| spinner | running |
| `+` | ok |
| `o` | cached (local) |
| `o [remote]` | cached (remote) |
| `x` | failed |
| `~` | skipped (upstream failed; `--keep-going` was set) |

The spinner rotates at 10 Hz via a Textual interval timer.

The footer shows `starting...` for the duration of the run. After the executor finishes, the TUI exits and the CLI prints the final summary line:

```
3 ran, 2 cached, 0 failed, 0 skipped  -  logs: .ntask/logs/20260422-103045-731
```

### 10.2 Log capture

When the TUI is active, `shell()` output is redirected to per-task files at `.ntask/logs/<run-id>/<fqn>.log`. The run-id is `YYYYMMDD-HHMMSS-mmm`.

```bash
cat .ntask/logs/20260422-103045-731/test.log
```

Log directories accumulate; clean manually with `rm -rf .ntask/logs/`.

### 10.3 Disabling

In order of precedence:

```bash
ntask check --no-tui                       # one-off
```

```toml
[tool.ntask]
tui = false                                 # always off for this project
```

```bash
ntask check | tee build.log                # non-TTY: TUI auto-disables
```

The TUI also auto-disables in CI environments where stdout isn't a TTY. Setting `tui = true` in pyproject.toml prevents auto-disable by config but doesn't override the TTY check.

### 10.4 Architecture

Textual's `App.run()` must own the main thread (signal handlers). The executor is an anyio coroutine running multiple tasks concurrently. ntask resolves this by inverting:

```
Main thread             Background thread
---------------------   ----------------------------------
tui_app.run()           anyio.run(executor.run, ...)
  blocks on app exit      runs the DAG
  receives events via     calls app.call_from_thread(...)
    call_from_thread        to push state updates
```

`call_from_thread` is Textual's thread-safe widget update mechanism. The executor uses it for every state event (`on_running`, `on_ok`, `on_cached`, `on_failed`).

The `TUIRenderer.start()` lifecycle hook waits on a `threading.Event` set when the app's `on_mount` fires. This avoids racing widget mutation against widget construction.

When the executor completes, `TUIRenderer.stop()` posts `app.exit()` via `call_from_thread`. The main thread's `app.run()` then returns and the CLI joins the bg thread.

---

## 11. Configuration

`[tool.ntask]` in `pyproject.toml`. No `pyproject.toml` -> all defaults apply.

### 11.1 `[tool.ntask]`

| Key | Type | Default | Description |
|---|---|---|---|
| `cache_dir` | string | `".ntask"` | Cache directory, relative to project root. |
| `default_concurrency` | int | `1` | Used when `-j` isn't passed. |
| `tui` | bool / null | `null` | `null` auto-detect; `false` always off; `true` prefer TUI on TTY. |

### 11.2 `[tool.ntask.remote_cache]`

| Field | Applies to | Required |
|---|---|---|
| `type` | all | yes |
| `path` | `local-fs` | yes |
| `url` | `http` | yes |
| `auth_header` | `http` | no |
| `bucket` | `s3`, `gcs` | yes |
| `prefix` | `s3`, `gcs` | no |
| `endpoint_url` | `s3` | no |

All string values support `$VAR` expansion at load time.

### 11.3 Full example

```toml
[tool.ntask]
cache_dir = ".ntask"
default_concurrency = 4
tui = false

[tool.ntask.remote_cache]
type = "s3"
bucket = "my-company-build-cache"
prefix = "myproject/"
endpoint_url = "https://s3.us-east-1.amazonaws.com"
```

### 11.4 Environment variables

ntask doesn't read env for its own configuration (uses pyproject.toml). However:

- AWS_*, GOOGLE_APPLICATION_CREDENTIALS, etc. are honoured by the underlying SDKs.
- `$VAR` references inside pyproject.toml string values expand from the environment at load time.
- Tasks declare which env affects their cache key via `@cached(env=["NAME"])`.

---

## 12. Architecture

For contributors and embedders.

### 12.1 Module layout

```
src/ntask/
+-- __init__.py          public re-exports
+-- __main__.py          python -m ntask entry
+-- _cli.py              argparse, renderer selection, main()
+-- _cli_args.py         signature -> argparse converter
+-- _cli_docstring.py    docstring summary extraction
+-- _cli_format.py       --list and --graph rendering
+-- _cli_why.py          --why renderer
+-- _config.py           ProjectConfig, RemoteCacheConfig, loader
+-- _coordinator.py      _ParallelCoordinator (parallel=False barriers)
+-- _dag.py              Graph, toposort (Kahn), build_graph
+-- _depends.py          depends() + _DependsVisitor (AST)
+-- _discovery.py        find_project_root, discover
+-- _errors.py           NtaskError, CycleError, DiscoveryError, ShellError
+-- _executor.py         Executor, ExecutionConfig, RunResult
+-- _registry.py         Registry, default_registry()
+-- _shell.py            shell(), ShellResult, ContextVars for prefix/log-file
+-- _task.py             task(), cached(), group(), Task, CachedConfig
+-- _watch.py            watch_loop(), filter builder
+-- _cache/
|   +-- __init__.py      CacheEngine
|   +-- body.py          structural body hash
|   +-- diff.py          MissReport, MissItem, diff_cache_state
|   +-- hash.py          xxh3_128 helpers
|   +-- key.py           CacheKeyInputs, CacheBreakdown, compute_cache_key
|   +-- manifest.py      compute_input_manifest
|   +-- outputs.py       OutputStore (capture + restore)
|   +-- store.py         CacheStore, CacheEntry
+-- _remote/
|   +-- __init__.py      make_backend factory
|   +-- base.py          RemoteBackend protocol
|   +-- local_fs.py      LocalFSBackend
|   +-- http.py          HTTPBackend (urllib)
|   +-- s3.py            S3Backend (boto3, optional extra)
|   +-- gcs.py           GCSBackend (google-cloud-storage, optional extra)
|   +-- _tar.py          deterministic tar.gz helpers
+-- _render/
    +-- __init__.py      re-exports
    +-- base.py          Renderer protocol
    +-- log.py           LogRenderer (plain text)
    +-- rich.py          RichRenderer (TTY, colour)
    +-- tui.py           TUIRenderer + _DAGApp (Textual)
```

### 12.2 Discovery and registry

`discover(start)` walks from `start` (typically `Path.cwd()`) up through parents looking for `tasks.py` or `tasks/__init__.py`. The first match is imported with a synthetic module name. Top-level decorators run during import and populate `default_registry()`.

The registry is a module-level dict from fqn to `Task`. Registering the same fqn twice raises. Registry is built once per process; hot-reload isn't supported.

### 12.3 DAG construction and topological sort

`build_graph(reg)` collects two kinds of edges:

1. **Declared deps** (`@task(deps=[a, b])`): `_resolve_ref` follows function-object identity, the `__ntask_task__` marker, or string fqns.
2. **Static `depends()` calls**: `scan_static_depends(func)` parses the function source, walks the body (stopping at nested function/class scopes), and collects bare `Name` arguments. Dotted attributes are recorded as dotted strings; string literals are flagged dynamic and contribute nothing.

`toposort(g)` runs Kahn's algorithm (BFS from zero-indegree). If the result is shorter than the node count, a cycle exists; `_find_cycle` runs DFS over the remaining nodes and reports it via `CycleError`.

`reachable_from([target])` prunes the graph before execution.

### 12.4 Executor

```
Executor(registry, config).run(targets, task_kwargs) -> RunResult
```

For each task in topological order:

1. Await all dependency completion events.
2. If any dep failed: mark this task skipped, set its event, return.
3. If `@cached` and not `--no-cache`: compute key + breakdown.
4. Check local cache. Hit -> restore outputs, signal done, return.
5. Check remote cache (if not `--offline`). Hit -> mirror to local, restore, signal done, return.
6. Emit `on_miss_reason`.
7. Enter `_ParallelCoordinator` (respecting `parallel=False`).
8. Acquire the `CapacityLimiter`.
9. Set per-task ContextVars (`_current_log_file` for TUI, `_current_line_prefix` for parallel non-TUI).
10. Invoke the task. Sync functions go through `anyio.to_thread.run_sync`; async functions are awaited directly.
11. Store cache entry, push to remote. Emit `on_ok`.
12. On failure: emit `on_failed`, record in failures dict, re-raise (or suppress with `--keep-going`).
13. Signal done.

### 12.5 Cache engine

`CacheEngine` interface:

- `compute_key_and_breakdown(t, workspace, upstream_keys_by_dep)` - returns `(key, CacheBreakdown)`. One call avoids redundant work; the breakdown is used for both lookup and miss reporting.
- `check(t, key)` - local lookup.
- `check_remote(t, key)` - remote lookup; mirrors entry+outputs to local on hit. Non-fatal on error.
- `store_entry(t, key, ...)` - capture outputs, write JSON entry.
- `restore_outputs(entry, workspace)` - hard-link or copy.
- `push_remote(t, entry)` - upload entry + output tarball.

`CacheStore` serialises `CacheEntry` to JSON at `.ntask/cache/<fqn>/<key>.json`. The breakdown is included so `--why` can diff against it.

File hashing uses a `ThreadPoolExecutor` for parallel reads when many inputs are present.

### 12.6 Renderer protocol

```python
class Renderer(Protocol):
    def on_running(self, fqn: str, *, cmd: str | None) -> None: ...
    def on_ok(self, fqn: str, *, duration: float) -> None: ...
    def on_cached(self, fqn: str, *, key: str, source: str = "local") -> None: ...
    def on_miss_reason(self, fqn: str, *, report: MissReport) -> None: ...
    def on_failed(self, fqn: str, *, error: BaseException, tail_lines: list[str]) -> None: ...
    def summary(self, *, ran: int, cached: int, failed: int, skipped: int) -> None: ...
```

Optional lifecycle methods `start(graph, logs_dir)` and `stop()` are detected via `hasattr` - present on `TUIRenderer`, absent on `LogRenderer` and `RichRenderer`.

| Class | Used when |
|---|---|
| `LogRenderer` | Non-TTY (pipe / CI) or `--no-color`. |
| `RichRenderer` | TTY with `--no-tui`, or watch mode. |
| `TUIRenderer` | TTY, colour enabled, `--no-tui` not set, Textual importable. |

Selection lives in `_cli.py`.

### 12.7 ContextVars as wiring

Two ContextVars thread information from the executor into `shell()` without argument plumbing:

- `_current_line_prefix: ContextVar[str | None]` - set to the task fqn when `-j > 1` and TUI inactive.
- `_current_log_file: ContextVar[Path | None]` - set to the per-task log path when TUI is active.

ContextVars are copy-on-write within anyio tasks, so values don't leak across coroutines. The executor resets the token after each task call.

### 12.8 `depends()` dual role

`depends(*tasks)`:

1. **Static (registration time):** an AST visitor reads `depends(name)` calls in the function source and adds DAG edges before any task runs. Bare-name references are resolved against the registry at graph-build time.
2. **Runtime:** the body-level call is a no-op. The static analysis already wired everything into the DAG; no runtime dispatch is needed.

For dynamic dependencies that can't be statically determined, use `@task(deps=[...])` - that resolution path accepts function objects and string fqns at registration time.

---

## 13. Recipes and patterns

### 13.1 Cross-group dependency

```python
from ntask import task, group, cached, shell

@group("build")
class Build:
    @task
    @cached(inputs=["src/**/*.py"], outputs=["dist/"])
    def wheel():
        shell("python -m build")

@group("publish")
class Publish:
    @task(deps=[Build.wheel])
    def pypi():
        shell("twine upload dist/*.whl")
```

`ntask publish.pypi` runs `build.wheel` first.

### 13.2 Generated files in inputs

```python
@task
@cached(
    inputs=["src/**/*.proto"],
    outputs=["src/generated/**/*.py"],
)
def codegen():
    shell("protoc --python_out=src/generated src/**/*.proto")

@task(deps=[codegen])
@cached(inputs=["src/**/*.py"])
def test():
    shell("pytest")
```

`propagate=True` (default) means a `codegen` miss invalidates `test` automatically. The generated files are also picked up by `test`'s own `inputs=` glob, so their content is tracked twice for safety.

### 13.3 Env-sensitive caching

```python
@task
@cached(
    inputs=["src/**/*.py", "tests/**/*.py"],
    env=["CI", "TEST_DATABASE_URL"],
)
def test(pattern: str = ""):
    k = f"-k {pattern}" if pattern else ""
    shell(f"pytest -v {k}")
```

A run with `CI=true TEST_DATABASE_URL=postgres://...` has a different key than one with those unset, so CI test results don't get served as hits during local development.

### 13.4 Exclusive task

```python
@task(parallel=False, deps=[check, build])
def release(version: str):
    """Cut a release. Never overlaps with anything else."""
    shell(f"git tag v{version}")
    shell("git push --tags")
    shell("twine upload dist/*.whl")
```

`ntask release --version=1.2.0 -j 16` still runs `release` alone after the in-flight DAG drains.

### 13.5 Branch on captured output

```python
@task
@cached(inputs=["pyproject.toml"])
def maybe_publish():
    version = shell("python -m build --version", capture=True).stdout.strip()
    existing = shell(f"pip show mypackage", capture=True, check=False)
    if version in existing.stdout:
        print(f"version {version} already published, skipping")
        return
    shell("twine upload dist/*.whl")
```

`capture=True` always uses captured mode (no streaming, no prefix). The returned `ShellResult` is never `None` in capture mode.

### 13.6 Team S3 cache

**One-time setup:**

1. Create a bucket (`my-team-ntask-cache`).
2. IAM policy granting `s3:GetObject`, `s3:PutObject`, `s3:HeadObject` to team members / CI roles.

**Project (committed):**

```toml
[tool.ntask.remote_cache]
type = "s3"
bucket = "my-team-ntask-cache"
prefix = "myproject/"
```

**Developer:**

```bash
pip install ntask[s3]
ntask check            # first run populates remote
ntask check --offline  # fast dev loop
```

**CI:**

```yaml
- name: Run checks
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
  run: ntask check
```

---

## 14. FAQ and troubleshooting

### My task didn't re-run after I changed the code

**Cause:** the body hash treats formatting-only changes (whitespace, comments, docstrings) as no-ops. If you only reformatted, the key is identical.

**Verify:** `ntask --why <task>`. If it says `HIT - no changes` and you expected a miss, the actual logic didn't change.

**Force:** `ntask --force <task>`.

**Reset:** `ntask clean`.

### Watch mode doesn't detect a file change

**Check 1:** Is the file matched by the `inputs` glob? Run `ntask --why <task>` and look at "Files matched". If it's zero or the file isn't listed, the glob doesn't match.

**Check 2:** Is the file gitignored? Watch applies the same rules as the cache. Ignored files don't trigger reruns.

**Check 3:** Did you edit `tasks.py`? It's not in the watch set. Ctrl-C and restart.

**Check 4:** Is the file outside the project root? Watch uses the project root as the base directory.

### TUI renders garbled

Try `ntask check --no-tui`. The TUI requires a terminal that handles modern ANSI sequences. Some multiplexers (`tmux`, `screen`) without `TERM=xterm-256color` and `COLORTERM=truecolor` may misrender.

Permanent fix: `tui = false` in `[tool.ntask]`.

### Remote cache S3 keeps failing

**Symptom:** `warning: remote cache unreachable: ClientError: ... Falling back to local.`

**Check credentials:** `aws s3 ls s3://your-bucket/` from the same shell. boto3 uses the same chain.

**Check bucket / prefix:** match what's in `pyproject.toml`.

**Offline fallback:** `ntask check --offline` skips remote entirely.

**Retry behaviour:** none. ntask warns once and uses the local cache for the rest of the process. If the remote is genuinely flaky, fix it at the infrastructure level (transfer acceleration, VPC endpoint).

### Parallel logs are jumbled

Under `-j > 1`, every line through `shell()` is prefixed `[fqn]` so lines don't interleave in confusing ways. `print()` in your task body is NOT prefixed - those writes go raw to stdout.

To label your own non-shell output:

```python
@task
def my_task():
    fqn = "my_task"
    for item in items:
        print(f"[{fqn}] processing {item}")
```

Or run sequentially (`-j 1`).

### Circular dependency

```
error: cycle in task graph: build -> publish -> build
```

The cycle is the shortest one DFS found in the unresolved nodes. Review `@task(deps=[...])` and `depends(...)` calls and break the cycle.

Cycles are detected at graph-build time; no partial execution occurs.

---

## Appendix A: public API

All of the following are imported from `ntask`:

```python
from ntask import (
    task, cached, group, depends,
    shell, ShellResult,
    NtaskError, CycleError, DiscoveryError, ShellError,
    __version__,
)
```

### `task`

```python
@task
def fn() -> None: ...

@task(deps: list[Callable | str] = [], parallel: bool = True)
def fn() -> None: ...
```

Registers the function. `concurrency` keyword was deprecated in 0.3 and is removed in 1.0.

### `cached`

```python
@cached(
    inputs: list[str] = [],
    outputs: list[str] = [],
    env: list[str] = [],
    propagate: bool = True,
    strict: bool = True,
)
def fn() -> None: ...
```

Stack with `@task` (either order).

### `group`

```python
@group(name: str)
class Tasks:
    @task
    def method() -> None: ...
```

Methods take no `self`. Group names must be non-empty and must not contain `.`.

### `depends`

```python
depends(*tasks: Callable | str) -> None
```

Runtime no-op; static AST analysis lifts bare-name references into the DAG at registration time.

### `shell`

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

### `ShellResult`

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

### Errors

`NtaskError` (base), `DiscoveryError`, `CycleError` (with `.cycle: list[str]`), `ShellError` (with `.returncode: int` and `.cmd`).

### `__version__`

```python
__version__: str  # "1.0.0"
```

### Marker attributes

ntask attaches three dunder attributes to decorated functions for runtime introspection:

- `<fn>.__ntask_task__: str` - registered fqn
- `<fn>.__ntask_cached_config__: CachedConfig` - present when `@cached` wrapped before `@task` ran
- `<fn>.__ntask_group__: str | None` - present when wrapped inside `@group(...)`

Read these for diagnostics; don't mutate them.

---

## Appendix B: glossary

**body hash.** Structural AST hash of a task function, computed after stripping docstrings. Stable under whitespace, comment, and formatting changes; sensitive to logic changes.

**cache hit.** The computed cache key matches an entry in the local or remote store. The task is skipped; outputs are restored from the captured blob.

**cache key.** A 128-bit xxh3 hash uniquely identifying a particular combination of task identity, inputs, environment, body, and upstream state.

**CacheBreakdown.** The structured record stored alongside each cache entry containing per-file input digests, env values, body hash, Python version, platform tag, and upstream keys. Used by `--why` to compute diffs.

**CacheEntry.** The JSON record at `.ntask/cache/<fqn>/<key>.json`.

**CapacityLimiter.** anyio primitive; semaphore that caps concurrent task count to the value given by `-j`.

**content-addressed.** Storage scheme where data is located by its hash rather than its name.

**DAG.** Directed Acyclic Graph. Used for execution order and reachability.

**fqn.** Fully Qualified Name. `build` for a bare task; `ci.build` for a method inside `@group("ci")`.

**gitignore-style glob.** Pattern following `.gitignore` rules: `**` matches any path component, `!` negates, directory prefixes match recursively. Implemented by `pathspec` in `gitwildmatch` mode.

**input manifest.** Ordered list of `(path, content-digest, mode)` triples for every file matched by `inputs=`. Its aggregate hash feeds the cache key.

**MissItem.** A single record in a `MissReport` describing one cache-miss reason.

**MissReport.** A tuple of `MissItem` values describing all reasons a lookup didn't hit. `is_hit` is `True` when the tuple is empty.

**outputs hash.** xxh3_128 of `(path, content-digest)` pairs for every file matched by `outputs=`. Used as the directory name in the local store and as the filename stem in the remote store.

**parallel=False.** Task attribute making the task a DAG-wide barrier: it waits for everything in flight to drain, then holds the DAG exclusively.

**propagate.** `@cached(propagate=True)` causes upstream cache keys to be included. Default `True`. Setting `False` makes this task's key independent of upstream changes.

**remote cache.** Shared cache backend (S3, GCS, HTTP, local-fs) from which teams and CI can read and write. Transparent to the task author.

**run-id.** Timestamp string `YYYYMMDD-HHMMSS-mmm` used as the directory name for per-run TUI logs.

**strict mode.** When `strict=True` (default), the cache key includes body hash, Python version, and platform tag. When `False`, those three are replaced with placeholders to allow cross-platform / cross-version cache sharing.

**transitive key propagation.** A downstream task's key includes its upstream dependencies' keys, so any upstream change invalidates the downstream automatically.

**toposort.** Topological sort of the DAG (Kahn's algorithm). Produces a stable order where each task appears after all its dependencies.

**xxh3_128.** 128-bit variant of the xxHash non-cryptographic hash. About 10x faster than SHA-256; sufficient collision resistance for build tooling.
