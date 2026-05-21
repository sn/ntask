# Open issues / follow-ups

Tracks issues discovered while working through other punch-list items
that weren't bundled into those PRs.

## `--graph <TARGET>` ignores the target for mermaid / dot output

`format_graph_mermaid` and `format_graph_dot` in `src/ntask/_cli_format.py`
emit the full graph regardless of whether a target was passed. Only
`format_graph_ascii` honours `target=` via `g.reachable_from([target])`.

Repro:

```bash
ntask --graph build --graph-format mermaid
# returns the full DAG, not the subgraph reachable from `build`
```

Fix: route the target through `g.reachable_from([target])` in both
functions, mirroring `format_graph_ascii`. Add coverage for all three
formatters with a target argument.

Discovered while verifying item 11 of the punch-list (Mermaid output
for embedding in markdown docs).

## `shell()` in the default sequential line renderer doesn't tee to the per-task log file

`subprocess.run(text=True)` (used in the default path) inherits the
real stdout fd, so the Python-level `_LogTee` we installed at
`sys.stdout` never sees the output. The TUI silent-log path and the
parallel-prefix path both capture correctly via Python pumps; closing
this gap would mean switching the default path to a PIPE-and-pump
implementation that writes to both `sys.stdout` and the per-task log.

Discovered while implementing item 2.
