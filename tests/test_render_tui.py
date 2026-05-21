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
