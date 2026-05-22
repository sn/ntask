"""Textual TUI renderer for live DAG display.

This module is lazy-imported from _cli.py - never imported on non-TUI
invocations, so non-TTY startup cost is unaffected.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.widgets import RichLog, Static, Tree
from textual.widgets.tree import TreeNode

from .._cache.diff import MissReport
from .._dag import Graph, toposort

_LOG_TAIL_POLL_INTERVAL = 0.15
_LOG_TAIL_PLACEHOLDER = "(no task running — output will appear here)"

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_STATE_STYLES: dict[str, tuple[str, str]] = {
    "waiting":        (".", "dim"),
    "running":        ("⠋", "yellow"),       # icon replaced per-frame
    "ok":             ("+", "green"),
    "cached":         ("◦", "dim"),
    "cached-remote":  ("◦", "dim"),
    "failed":         ("x", "red"),
    "skipped":        ("⊘", "dim"),
}


class _DAGApp(App[None]):
    """Full-screen TUI displaying the task DAG as a tree."""

    CSS = """
    Screen { background: $surface; }
    #dag-tree { margin: 1 2 0 2; height: 50%; }
    #task-log {
        margin: 0 2 0 2;
        height: 1fr;
        border-top: solid $accent;
        background: $surface-lighten-1;
    }
    #footer { dock: bottom; height: 1; padding: 0 2; color: $text-muted; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        ("ctrl+c", "quit", "Quit"),
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]
    TITLE = "ntask"

    def __init__(self, logs_dir: Path | None = None) -> None:
        super().__init__()
        self._logs_dir: Path | None = logs_dir
        self._task_nodes: dict[str, TreeNode[Any]] = {}
        self._states: dict[str, str] = {}
        self._durations: dict[str, float] = {}
        self._summary_text: str = "starting..."
        self._spinner_frame = 0
        self._mount_ready = threading.Event()
        # Log-pane tailing state.
        self._tailing_fqn: str | None = None
        self._tail_path: Path | None = None
        self._tail_offset: int = 0

    def compose(self) -> ComposeResult:
        yield Tree("ntask", id="dag-tree")
        yield RichLog(
            id="task-log",
            max_lines=2000,
            highlight=False,
            markup=False,
            wrap=True,
        )
        yield Static(self._summary_text, id="footer")

    def on_mount(self) -> None:
        self.set_interval(0.1, self._advance_spinner)
        self.set_interval(_LOG_TAIL_POLL_INTERVAL, self._tail_current_log)
        # Placeholder so users can see what the pane is for before any task
        # has started writing output.
        self.query_one("#task-log", RichLog).write(_LOG_TAIL_PLACEHOLDER)
        self._mount_ready.set()

    def build_tree(self, graph: Graph) -> None:
        """Populate the Tree from a task Graph."""
        tree = self.query_one("#dag-tree", Tree)
        tree.root.expand()
        for fqn in toposort(graph):
            deps = graph.direct_deps(fqn)
            # Tree visualization of a DAG: each node shown under its first
            # declared dep; additional deps aren't drawn as extra edges.
            parent = (
                self._task_nodes[deps[0]]
                if deps and deps[0] in self._task_nodes
                else tree.root
            )
            node = parent.add(self._label(fqn), expand=True)
            self._task_nodes[fqn] = node

    def update_state(
        self, fqn: str, state: str, duration: float | None = None,
    ) -> None:
        self._states[fqn] = state
        if duration is not None:
            self._durations[fqn] = duration
        node = self._task_nodes.get(fqn)
        if node is not None:
            node.set_label(self._label(fqn))
        # When a task starts running, switch the log pane to tail its file.
        # When it finishes, freeze on the last content — don't blank the
        # pane, since the user may still be reading it.
        if state == "running":
            self._begin_tail(fqn)
        elif fqn == self._tailing_fqn and state in {"ok", "failed", "cached", "cached-remote"}:
            self._end_tail()

    def _begin_tail(self, fqn: str) -> None:
        if self._logs_dir is None:
            return
        self._tailing_fqn = fqn
        self._tail_path = self._logs_dir / f"{fqn}.log"
        self._tail_offset = 0
        log = self.query_one("#task-log", RichLog)
        log.clear()
        log.write(Text(f"── {fqn} ──", style="bold cyan"))

    def _end_tail(self) -> None:
        # Drain any remaining bytes before freezing the pane.
        self._tail_current_log()
        self._tailing_fqn = None

    def _tail_current_log(self) -> None:
        path = self._tail_path
        if path is None or self._tailing_fqn is None:
            return
        try:
            if not path.exists():
                return
            size = path.stat().st_size
            if size <= self._tail_offset:
                return
            with path.open("rb") as f:
                f.seek(self._tail_offset)
                new_bytes = f.read(size - self._tail_offset)
                self._tail_offset = size
        except OSError:
            return
        if not new_bytes:
            return
        text = new_bytes.decode("utf-8", errors="replace")
        log = self.query_one("#task-log", RichLog)
        # RichLog.write splits on newlines for us; trailing newline is
        # ignored so we don't emit a phantom blank line.
        log.write(text.rstrip("\n"))

    def update_summary(self, text: str) -> None:
        self._summary_text = text
        self.query_one("#footer", Static).update(text)

    def _advance_spinner(self) -> None:
        """Rotate spinner for any currently-running nodes."""
        self._spinner_frame = (self._spinner_frame + 1) % len(_SPINNER)
        for fqn, state in self._states.items():
            if state == "running":
                node = self._task_nodes.get(fqn)
                if node is not None:
                    node.set_label(self._label(fqn))

    def _label(self, fqn: str) -> Text:
        state = self._states.get(fqn, "waiting")
        cfg = _STATE_STYLES.get(state, ("·", "dim"))
        icon_char = _SPINNER[self._spinner_frame] if state == "running" else cfg[0]
        icon_style = cfg[1]

        dur = self._durations.get(fqn)
        dur_str = f" ({dur:.2f}s)" if dur is not None else ""
        remote = " [remote]" if state == "cached-remote" else ""

        text = Text()
        text.append(f"{icon_char} ", style=icon_style)
        text.append(fqn)
        text.append(
            f"  {state.replace('-', ' ')}{remote}{dur_str}", style="dim",
        )
        return text


class TUIRenderer:
    """Textual-based live-DAG renderer.

    The executor runs on a background thread; the Textual app runs on the
    main thread. This class holds a reference to a pre-created `_DAGApp`
    and forwards Renderer-protocol events to it via `call_from_thread`.
    """

    def __init__(self, app: _DAGApp) -> None:
        self._app = app
        self._logs_dir: Path | None = None
        self._final_summary: str | None = None

    # Lifecycle hooks (called by the executor from its BG thread) -----------

    def start(self, *, graph: Graph, logs_dir: Path) -> None:
        """Wait for the app to mount, then populate the tree."""
        self._logs_dir = logs_dir
        if not self._app._mount_ready.wait(timeout=5.0):
            raise RuntimeError("TUI app failed to become ready within 5s")
        # The log pane needs to know where to find per-task log files.
        self._app._logs_dir = logs_dir
        self._app.call_from_thread(self._app.build_tree, graph)

    def stop(self) -> None:
        """No-op: the TUI persists until the user dismisses it via q/esc/ctrl+c.

        The CLI is responsible for joining the executor thread and re-raising
        any held exception after ``app.run()`` returns.
        """
        return

    def announce_error(self, message: str) -> None:
        """Show an error message in the footer with the dismiss hint."""
        text = f"error: {message}  ·  press q/esc to quit"
        if self._app.is_running:
            self._app.call_from_thread(self._app.update_summary, text)

    @property
    def final_summary(self) -> str | None:
        """The CLI reads this after `app.run()` returns to print the summary."""
        return self._final_summary

    # Renderer protocol ----------------------------------------------------

    def on_running(self, fqn: str, *, cmd: str | None) -> None:
        if self._app.is_running:
            self._app.call_from_thread(self._app.update_state, fqn, "running")

    def on_ok(self, fqn: str, *, duration: float) -> None:
        if self._app.is_running:
            self._app.call_from_thread(
                self._app.update_state, fqn, "ok", duration,
            )

    def on_cached(self, fqn: str, *, key: str, source: str = "local") -> None:
        state = "cached-remote" if source == "remote" else "cached"
        if self._app.is_running:
            self._app.call_from_thread(self._app.update_state, fqn, state)

    def on_miss_reason(self, fqn: str, *, report: MissReport) -> None:
        # Intentional no-op: miss detail is verbose and already written to
        # the per-task log file by the executor; the TUI shows DAG state only.
        pass

    def on_failed(
        self, fqn: str, *, error: BaseException, tail_lines: list[str],
    ) -> None:
        if self._app.is_running:
            self._app.call_from_thread(self._app.update_state, fqn, "failed")

    def summary(
        self,
        *,
        ran: int,
        cached: int,
        failed: int,
        skipped: int,
        failed_fqns: tuple[str, ...] = (),
    ) -> None:
        text = (
            f"{ran} ran, {cached} cached, {failed} failed, {skipped} skipped"
            f"  ·  logs: {self._logs_dir}"
        )
        if failed_fqns:
            text += f"  ·  failed: {', '.join(failed_fqns)}"
        self._final_summary = text
        footer = f"{text}  ·  press q/esc to quit"
        if self._app.is_running:
            self._app.call_from_thread(self._app.update_summary, footer)
