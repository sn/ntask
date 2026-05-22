from __future__ import annotations

import threading
from pathlib import Path

import pytest

pytest.importorskip("textual")

from ntask._dag import Graph
from ntask._render.tui import _DAGApp


def _collect_labels(tree_node) -> list[str]:
    """Depth-first walk of a TreeNode; return plain string labels."""
    labels = []
    for child in tree_node.children:
        labels.append(str(child.label))
        labels.extend(_collect_labels(child))
    return labels


async def test_tui_app_builds_tree_from_graph(tmp_path: Path):
    g = Graph(nodes=["a", "b", "c"], edges=[("a", "b"), ("a", "c")])
    app = _DAGApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        await pilot.pause()
        tree = app.query_one("#dag-tree")
        labels = _collect_labels(tree.root)
        assert any("a" in label for label in labels)
        assert any("b" in label for label in labels)
        assert any("c" in label for label in labels)


async def test_tui_app_update_state_changes_label(tmp_path: Path):
    g = Graph(nodes=["build"], edges=[])
    app = _DAGApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        app.update_state("build", "running")
        await pilot.pause()
        tree = app.query_one("#dag-tree")
        labels = _collect_labels(tree.root)
        assert any("running" in label for label in labels)


async def test_tui_app_update_duration_in_label(tmp_path: Path):
    g = Graph(nodes=["build"], edges=[])
    app = _DAGApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        app.update_state("build", "ok", duration=1.23)
        await pilot.pause()
        tree = app.query_one("#dag-tree")
        labels = _collect_labels(tree.root)
        assert any("1.23s" in label for label in labels)


async def test_tui_app_remote_cached_suffix(tmp_path: Path):
    g = Graph(nodes=["build"], edges=[])
    app = _DAGApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        app.update_state("build", "cached-remote")
        await pilot.pause()
        tree = app.query_one("#dag-tree")
        labels = _collect_labels(tree.root)
        assert any("[remote]" in label for label in labels)


async def test_tui_app_summary_updates_footer(tmp_path: Path):
    app = _DAGApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.update_summary("3 ran, 2 cached")
        await pilot.pause()
        footer = app.query_one("#footer")
        assert "3 ran" in str(footer.content)


async def test_tui_app_failed_state_in_label(tmp_path: Path):
    g = Graph(nodes=["build"], edges=[])
    app = _DAGApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        app.update_state("build", "failed")
        await pilot.pause()
        tree = app.query_one("#dag-tree")
        labels = _collect_labels(tree.root)
        assert any("failed" in label for label in labels)


def _spawn_app(app: _DAGApp) -> threading.Thread:
    """Start the app on a BG thread for test harness.

    In production, the CLI runs the app on the main thread and the executor
    on a BG thread. Tests flip this (tests on main, app on BG) so the test
    coroutine can drive renderer methods from the main thread; headless=True
    is fine since we only assert state.
    """
    t = threading.Thread(target=lambda: app.run(headless=True), daemon=True)
    t.start()
    if not app._mount_ready.wait(timeout=5.0):
        raise RuntimeError("Test app failed to mount within 5s")
    return t


def _teardown_app(app: _DAGApp, t: threading.Thread) -> None:
    if app.is_running:
        app.call_from_thread(app.exit)
    t.join(timeout=2.0)


def test_tui_renderer_start_builds_tree_and_stores_logs_dir(tmp_path: Path):
    from ntask._render.tui import TUIRenderer, _DAGApp
    app = _DAGApp(logs_dir=tmp_path)
    r = TUIRenderer(app=app)
    t = _spawn_app(app)
    try:
        g = Graph(nodes=["a", "b"], edges=[("a", "b")])
        r.start(graph=g, logs_dir=tmp_path)
        import time
        time.sleep(0.2)
        # Tree was built on the app's thread via call_from_thread.
        assert "a" in app._task_nodes
        assert "b" in app._task_nodes
        # logs_dir was captured for later summary formatting.
        assert r._logs_dir == tmp_path
    finally:
        r.stop()
        _teardown_app(app, t)


def test_tui_renderer_forwards_events_to_app(tmp_path: Path):
    from ntask._render.tui import TUIRenderer, _DAGApp
    app = _DAGApp(logs_dir=tmp_path)
    r = TUIRenderer(app=app)
    t = _spawn_app(app)
    try:
        g = Graph(nodes=["build"], edges=[])
        r.start(graph=g, logs_dir=tmp_path)
        r.on_running("build", cmd=None)
        import time
        time.sleep(0.2)
        assert app._states.get("build") == "running"
        r.on_ok("build", duration=0.5)
        time.sleep(0.2)
        assert app._states["build"] == "ok"
        assert app._durations["build"] == 0.5
    finally:
        r.stop()
        _teardown_app(app, t)


def test_tui_renderer_on_cached_routes_remote_source(tmp_path: Path):
    from ntask._render.tui import TUIRenderer, _DAGApp
    app = _DAGApp(logs_dir=tmp_path)
    r = TUIRenderer(app=app)
    t = _spawn_app(app)
    try:
        g = Graph(nodes=["build"], edges=[])
        r.start(graph=g, logs_dir=tmp_path)
        r.on_cached("build", key="abc", source="remote")
        import time
        time.sleep(0.2)
        assert app._states["build"] == "cached-remote"
        r.on_cached("build", key="def", source="local")
        time.sleep(0.2)
        assert app._states["build"] == "cached"
    finally:
        r.stop()
        _teardown_app(app, t)


def test_tui_renderer_summary_stored_for_caller(tmp_path: Path):
    """Summary text is stored so the CLI can print it after app.run() returns."""
    from ntask._render.tui import TUIRenderer, _DAGApp
    app = _DAGApp(logs_dir=tmp_path)
    r = TUIRenderer(app=app)
    t = _spawn_app(app)
    try:
        g = Graph(nodes=["build"], edges=[])
        r.start(graph=g, logs_dir=tmp_path)
        r.summary(ran=2, cached=1, failed=0, skipped=0)
    finally:
        r.stop()
        _teardown_app(app, t)
    assert r.final_summary is not None
    assert "2 ran" in r.final_summary
    assert "1 cached" in r.final_summary


def test_tui_renderer_summary_shows_quit_hint_in_footer(tmp_path: Path):
    """The footer is sticky on completion — user must press q/esc to dismiss."""
    from ntask._render.tui import TUIRenderer, _DAGApp
    app = _DAGApp(logs_dir=tmp_path)
    r = TUIRenderer(app=app)
    t = _spawn_app(app)
    try:
        g = Graph(nodes=["build"], edges=[])
        r.start(graph=g, logs_dir=tmp_path)
        r.summary(ran=1, cached=0, failed=0, skipped=0)
        import time
        time.sleep(0.2)
        footer = app.query_one("#footer")
        assert "press q/esc to quit" in str(footer.content)
    finally:
        _teardown_app(app, t)


def test_tui_renderer_stop_is_noop(tmp_path: Path):
    """stop() must not close the app — the CLI relies on the user dismissing."""
    from ntask._render.tui import TUIRenderer, _DAGApp
    app = _DAGApp(logs_dir=tmp_path)
    r = TUIRenderer(app=app)
    t = _spawn_app(app)
    try:
        r.stop()
        import time
        time.sleep(0.2)
        assert app.is_running, "stop() must not exit the app"
    finally:
        _teardown_app(app, t)


def test_tui_renderer_announce_error_updates_footer(tmp_path: Path):
    from ntask._render.tui import TUIRenderer, _DAGApp
    app = _DAGApp(logs_dir=tmp_path)
    r = TUIRenderer(app=app)
    t = _spawn_app(app)
    try:
        g = Graph(nodes=["build"], edges=[])
        r.start(graph=g, logs_dir=tmp_path)
        r.announce_error("RuntimeError: boom")
        import time
        time.sleep(0.2)
        footer = app.query_one("#footer")
        text = str(footer.content)
        assert "RuntimeError: boom" in text
        assert "press q/esc to quit" in text
    finally:
        _teardown_app(app, t)


def test_tui_app_quit_bindings_include_q_and_escape():
    """q and escape must trigger the quit action so users can dismiss the TUI."""
    from ntask._render.tui import _DAGApp
    # BINDINGS entries are (key, action, description) tuples.
    keys = {b[0] for b in _DAGApp.BINDINGS}
    assert "q" in keys
    assert "escape" in keys
    assert "ctrl+c" in keys


async def test_tui_log_pane_tails_running_task_log_file(tmp_path: Path):
    """When a task transitions to 'running' the log pane should switch
    to tailing that task's log file, and surface bytes appended after
    the transition."""
    from textual.widgets import RichLog

    from ntask._dag import Graph
    from ntask._render.tui import _DAGApp

    g = Graph(nodes=["scenario_a"], edges=[])
    app = _DAGApp(logs_dir=tmp_path)
    log_file = tmp_path / "scenario_a.log"
    log_file.write_text("", encoding="utf-8")

    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        # Begin running — pane should switch to this task.
        app.update_state("scenario_a", "running")
        await pilot.pause()
        # Append a fake log line, as the executor would.
        with log_file.open("a", encoding="utf-8") as f:
            f.write('{"service": "tender-api", "event": "kickoff"}\n')
        # Give the polling interval a couple of ticks to pick it up.
        await pilot.pause(0.4)
        rendered = "\n".join(
            seg.text for line in app.query_one("#task-log", RichLog).lines
            for seg in line._segments
        )
        assert "tender-api" in rendered
        assert "── scenario_a ──" in rendered


async def test_tui_log_pane_freezes_when_task_completes(tmp_path: Path):
    """After ok/cached/failed the pane should hold the final content,
    not blank out — the user may still be reading it."""
    from textual.widgets import RichLog

    from ntask._dag import Graph
    from ntask._render.tui import _DAGApp

    g = Graph(nodes=["scenario_a"], edges=[])
    app = _DAGApp(logs_dir=tmp_path)
    log_file = tmp_path / "scenario_a.log"
    log_file.write_text("first-line\n", encoding="utf-8")

    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        app.update_state("scenario_a", "running")
        await pilot.pause(0.4)
        app.update_state("scenario_a", "ok", duration=0.2)
        await pilot.pause(0.4)
        rendered = "\n".join(
            seg.text for line in app.query_one("#task-log", RichLog).lines
            for seg in line._segments
        )
        # Content remains visible after completion.
        assert "first-line" in rendered
        # And the tail state was released.
        assert app._tailing_fqn is None


async def test_tui_log_pane_switches_between_tasks(tmp_path: Path):
    """When a second task starts running, the pane should clear and
    rebind to its log file."""
    from textual.widgets import RichLog

    from ntask._dag import Graph
    from ntask._render.tui import _DAGApp

    g = Graph(nodes=["a", "b"], edges=[])
    app = _DAGApp(logs_dir=tmp_path)
    (tmp_path / "a.log").write_text("output-from-a\n", encoding="utf-8")
    (tmp_path / "b.log").write_text("output-from-b\n", encoding="utf-8")

    async with app.run_test() as pilot:
        await pilot.pause()
        app.build_tree(g)
        app.update_state("a", "running")
        await pilot.pause(0.4)
        app.update_state("a", "ok", duration=0.1)
        await pilot.pause(0.2)
        app.update_state("b", "running")
        await pilot.pause(0.4)
        rendered = "\n".join(
            seg.text for line in app.query_one("#task-log", RichLog).lines
            for seg in line._segments
        )
        # The pane now belongs to b; a's content was cleared.
        assert "output-from-b" in rendered
        assert "── b ──" in rendered
        assert "output-from-a" not in rendered
