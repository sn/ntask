# 04 · watch

`ntask watch <task>` runs a `@cached` task on every input change.

## Run

```bash
ntask watch test
```

Leave the watcher running, then in another shell edit `src/test_app.py` -
add a new test, break an assertion, whatever. The watcher will:

1. Clear the screen
2. Print a status header naming the file that changed
3. Re-run `test`
4. Wait for the next change

## What to notice

- Only `@cached` tasks are watchable. `ntask watch` on a non-cached task
  exits with an error - the watcher needs the `inputs` glob to know what
  files to observe.
- File events during a run are **queued**, not dropped - a single rerun is
  scheduled after the current one completes. Successive saves collapse
  into one follow-up run.
- Filtering respects `.gitignore`. Editor-backup files (`.swp`, `~`,
  `.DS_Store`) and build artefacts in ignored paths don't trigger reruns.
- **No TUI while watching.** The watcher uses the Rich renderer even on a
  TTY. Watch + TUI integration is deferred to a future release.
- Ctrl-C exits cleanly. Changes mid-run queue up; one follow-up rerun
  fires after the current run finishes (no cancel-and-restart).
