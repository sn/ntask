# 03 · parallel

`-j N` fans out independent tasks; `parallel=False` reserves the whole DAG.

Note that `-j` is a **global** flag, so it goes *before* the task name.

## Run

```bash
time ntask -j 1 all_builds     # sequential: ~3 seconds
time ntask -j 3 all_builds     # parallel:   ~1 second
time ntask -j all_builds       # bare -j → uses os.cpu_count()
ntask -j 3 ship                # builds in parallel, then deploy runs solo
```

## What to notice

- The default is `-j 1` (sequential). Opt in to parallelism per invocation;
  there's no "parallel by default" footgun.
- Under `-j > 1`, `shell()` output is auto-prefixed with `[fqn]` so parallel
  logs stay readable. `print()` output isn't prefixed - wrap anything
  interactive in `shell()` or accept the interleave.
- `@task(parallel=False)` is a **DAG-wide barrier**, not a per-task
  serialization knob. When `deploy` is ready to run, the executor first
  waits for every in-flight task across the DAG to finish, then runs
  `deploy` alone.
- `stdin` under `-j > 1` is `/dev/null`. If a task needs a TTY (pdb,
  interactive prompt), stick to `-j 1`.
