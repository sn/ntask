# 01 · hello

The smallest possible cached task. Observe a miss, a hit, and an
invalidation.

## Run

```bash
ntask hello            # first run: cache miss - prints "Hello, world!"
ntask hello            # second run: cache hit - nothing happens
echo "team" > greeting.txt
ntask hello            # cache miss - input changed - prints "Hello, team!"
ntask --why hello      # breakdown of why the last run missed
```

## What to notice

- No `pyproject.toml` needed. `tasks.py` + the `ntask` CLI is enough.
- The `inputs=["greeting.txt"]` glob feeds the content hash. Changing the
  file's contents invalidates the cache; re-saving with identical content
  does not.
- `ntask --why hello` shows the cached key that matched, or a `MissReport`
  naming the specific file/env/upstream that changed.
