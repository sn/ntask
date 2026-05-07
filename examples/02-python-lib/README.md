# 02 · python-lib

A realistic `tasks.py` for a small Python library. Mirrors the shape of
ntask' own `tasks.py`.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
ntask install
ntask -j 3 check          # fan-out: lint + typecheck + test in parallel
ntask build
```

Second time:

```bash
ntask check               # all three are cache hits; near-zero time
touch src/mylib/__init__.py
ntask check               # `touch` alone doesn't change content → still a hit
echo "" >> src/mylib/__init__.py
ntask check               # content changed → lint, typecheck, test re-run
```

## What to notice

- `install` is intentionally **not** `@cached`. pip manages its own state;
  caching it would give false hits when deps change on PyPI.
- `check` uses `depends(lint, typecheck, test)` for fan-out. Run with
  `-j 3` to execute all three in parallel (the `-j` flag is global, so it
  goes before the task name).
- `build` declares `outputs=["dist/"]`. On a cache hit, ntask restores
  the `dist/` artefact - no rebuild needed.
- Inputs include `pyproject.toml`. Bumping the package version or changing
  a dep correctly invalidates lint/typecheck/test/build.
