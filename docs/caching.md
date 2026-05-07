# Caching: the full contract

Caching is what makes ntask faster than re-running everything. This document specifies precisely what gets hashed, what counts as a hit, and why.

## What `@cached` does

```python
@task
@cached(
    inputs=["src/**/*.py"],
    outputs=["dist/"],
    env=["CI", "BUILD_TARGET"],
    propagate=True,
    strict=True,
)
def build():
    shell("python -m build")
```

When ntask is asked to run `build`:

1. Compute a content-addressed cache key (see below).
2. Look it up in `.ntask/cache/build/<key>.json`.
3. **Hit** → restore the captured `outputs=` files into the workspace, skip execution, mark the task done.
4. **Miss** → run the body. After success, capture `outputs=` to a content-addressed blob, write the cache entry.

## What the cache key includes

The key is a single xxh3_128 hash over a length-prefixed concatenation, in this order:

| # | Component | Notes |
|---|---|---|
| 1 | Format version (`ntask/v1`) | Constant; isolates entries across major schema changes. |
| 2 | Task fqn | `lint`, `api.test`, etc. |
| 3 | Body hash | Structural AST hash of the task function (see below). Skipped when `strict=False`. |
| 4 | Python version | `sys.version_info[:3]`, e.g. `3.12.3`. Skipped when `strict=False`. |
| 5 | Platform tag | `<system>-<machine>` lowercased, e.g. `linux-x86_64`. Skipped when `strict=False`. |
| 6 | Env values | One `NAME=value` line per `env=` entry, sorted by name. Unset vars contribute `<unset>`. |
| 7 | Input patterns | The `inputs=` glob strings, sorted. |
| 8 | Input manifest | Hash over `(path, content-digest, mode)` triples for every matched file. |
| 9 | Upstream keys | The resolved keys of direct dependencies, in declaration order. Skipped when `propagate=False`. |

Each field is fed in with an 8-byte length prefix, preventing one field from spilling into the next.

## The body hash

ntask hashes the function's structural AST, not its source text. Steps:

1. `inspect.getsource(func)` to read the function source.
2. `ast.parse(textwrap.dedent(source))` to build an AST.
3. Strip leading docstring nodes from every function/class/module body.
4. `ast.dump(tree, annotate_fields=False, include_attributes=False)`.
5. xxh3_128 of the dumped string.

This means:
- `ruff format` / `black` don't invalidate caches: whitespace and style produce identical AST.
- Comments don't invalidate.
- Docstring edits don't invalidate.
- Adding or removing a line, calling a different function, renaming a variable does invalidate.

If you can't get source for a task (lambda, dynamically generated function), the body hash falls back to a stable identifier so the task still caches. Don't rely on that path for production tasks; use named functions.

## Transitive key propagation

When task `B` depends on task `A` (via `@task(deps=[A])` or a static `depends(A)` call), `A`'s resolved key is included as an upstream-key in `B`'s key computation.

The effect: if `A` is invalidated for any reason - inputs changed, body changed, upstream of `A` changed - `B` automatically misses too, even when `B`'s own inputs and env are unchanged. Build correctness is structural.

This propagates the full depth of the DAG. A change at the leaves invalidates everything that transitively depends on those leaves.

**Opt-out:** `@cached(propagate=False)` excludes upstream keys from this task's key. Use only when the task's outputs are genuinely independent of upstream output (e.g., a task that prints help text).

## `strict=True` (default)

Includes the body hash, Python version, and platform tag. Cache entries are tied to the exact code, interpreter, and OS arch.

## `strict=False`

Replaces those three components with fixed placeholders (`<body-unstrict>`, `<py-unstrict>`, `<plat-unstrict>`), so cache entries persist across:
- Refactors that change AST (without changing inputs)
- Python version upgrades
- macOS/Linux machines

Don't use `strict=False` for code-execution tasks where the binary you produce depends on the interpreter or platform. The main use case is pure data transformations.

## Inputs

`inputs=[...]` is a list of gitignore-style glob patterns. Behavior:

- Matched against every file under the project root using `pathspec` in `gitwildmatch` mode.
- `.gitignore` is consulted if present; ignored files are removed from the matched set.
- Files are content-hashed with xxh3_128. Mtime is irrelevant: a file checked out from git, restored from a backup, or re-saved with the same content all hash identically.
- File mode is included in the manifest, so `chmod +x` invalidates.
- Sorted before hashing - filesystem ordering doesn't affect the result.

### Negation

`!pattern` re-modifies a previously-included match (same as `.gitignore`). Put the broader include first, then the negation:

```python
@cached(inputs=["src/**/*.py", "!src/generated/**/*.py"])
```

A `!` line on its own with nothing to negate has no effect.

## Outputs

`outputs=[...]` is a list of glob patterns matched the same way as inputs. After a successful run, ntask:

1. Hashes every matched file (path + content) into an `outputs-hash`.
2. Stores the files in `.ntask/outputs/<outputs-hash>/`.
3. On a future cache hit, hard-links the files (POSIX) or copies them (Windows / cross-filesystem) back to the workspace.

Effects:
- Downstream tasks consuming these files via their own `inputs=` glob will see them on a cache hit, even when the producer didn't run.
- Hard-linked files share inode and mtime with the captured copy. Tools that compare mtimes may behave differently than after a fresh run.

## Env

`env=["NAME1", "NAME2"]` includes the named environment variables' values in the cache key. Unset variables contribute the string `<unset>`. Use this when a task's behavior actually depends on env (CI flag, target arch, build env).

Don't include every env var "to be safe": most env churn is irrelevant noise that just disables your cache.

## Miss reporting

Every cache decision produces a `MissReport` - a tuple of `MissItem(kind, detail)` describing exactly why the lookup didn't hit.

| `kind` | When |
|---|---|
| `first-run` | No prior entry exists for this fqn. |
| `input-modified` | A matched file's content or mode changed. |
| `input-added` | A new file appeared in the matched set. |
| `input-removed` | A previously-matched file was deleted. |
| `env-changed` | An env var's value changed. |
| `env-added` | An env var appeared (was previously unset). |
| `env-removed` | An env var disappeared. |
| `body-changed` | The structural AST of the task function changed. |
| `upstream-invalidated` | An upstream dependency's key changed. |
| `python-changed` | Python version differs from the cached run. |
| `platform-changed` | Platform tag differs. |

Order in the report: `input-*` first (alphabetical by path, kinds interleaved per file), then `env-*` (alphabetical), then `body-changed`, then `upstream-invalidated` (alphabetical by dep), then `python-changed` and `platform-changed`. The `first-run` kind always appears alone.

The line-renderer prints the first item inline (`x test: cache miss (input-modified: src/auth.py (+2 more))`).

`ntask --why <task>` prints the full report plus the prior cache entry's breakdown so you can see exactly what state the prior key was computed against.

## Cache layout

```
.ntask/
|-- cache/
|   |-- <fqn>/
|   |   |-- <key-a>.json
|   |   |-- <key-b>.json
|-- outputs/
|   |-- <outputs-hash>/
|   |   |-- dist/
|   |       |-- mypackage-1.0.whl
|-- logs/
    |-- <run-id>/
        |-- lint.log
        |-- test.log
```

- `cache/<fqn>/<key>.json` is the cache entry (key, outputs-hash, duration, completed_at, breakdown). One file per (task, key) pair.
- `outputs/<outputs-hash>/` is the captured output blob, content-addressed. Two tasks with identical output trees share storage.
- `logs/<run-id>/<fqn>.log` captures stdout+stderr per task during TUI runs (timestamp run-id; multiple runs accumulate).

## Safety valves

| Command | Effect |
|---|---|
| `ntask --no-cache` | Don't read or write the cache for this invocation. |
| `ntask --force <task>` | Bypass the cache for that task's lookup; still write a new entry on success. |
| `ntask clean` | Delete `.ntask/cache/`. Output blobs survive. |
| `ntask clean --all` | Delete the entire `.ntask/` directory. |

`--no-cache` is the right choice when you suspect a cache-correctness bug and want a clean slate. `--force` is the right choice when you know one task's environment changed in a way you didn't declare in `env=` (e.g., a tool you call out to was upgraded).

## What's NOT in the key

Things ntask deliberately ignores:

- **File mtime** - timestamps are unreliable across checkouts and restores. Content is what matters.
- **Comments and docstrings** - they're stripped before hashing.
- **Whitespace, line endings, and formatting** - structural AST hash is stable under these.
- **Sibling tasks** - only direct dependencies (and their transitive keys) feed into this task's key.
- **Repository state** (commit SHA, branch) - if your tool actually consumes git state, declare relevant files as inputs (e.g., `.git/HEAD`) or env vars.

## Performance notes

- xxh3_128 is roughly 10x faster than SHA-256 on modern hardware. Hashing isn't typically the bottleneck.
- File hashing is parallelized via a `ThreadPoolExecutor` when many inputs are present.
- For large outputs (gigabyte+), capture is a content-addressed copy on disk; remote upload constructs the tarball in memory and may pressure RAM. The remote tarball is deterministic (sorted entries, mtime=0), so identical outputs share storage on the remote too.
