"""Forward-reference / lazy `deps=lambda: [...]` form of @task."""
from __future__ import annotations

from pathlib import Path

import pytest

from ntask import task
from ntask._dag import build_graph, toposort
from ntask._executor import ExecutionConfig, Executor
from ntask._registry import default_registry
from ntask._task import _LazyDeps


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


def test_lazy_deps_resolves_forward_reference() -> None:
    """The dependent is defined *before* the deps it references."""
    @task(deps=lambda: [a, b])
    def all_task():
        pass

    @task
    def a():
        pass

    @task
    def b():
        pass

    g = build_graph(default_registry())
    order = toposort(g)
    assert order.index("a") < order.index("all_task")
    assert order.index("b") < order.index("all_task")


def test_lazy_deps_accepts_fqn_string_refs() -> None:
    @task(deps=lambda: ["alpha"])
    def beta():
        pass

    @task
    def alpha():
        pass

    g = build_graph(default_registry())
    assert ("alpha", "beta") in g.edges


async def test_lazy_deps_executed_in_order(tmp_path: Path) -> None:
    order: list[str] = []

    @task(deps=lambda: [first, second])
    def both():
        order.append("both")

    @task
    def first():
        order.append("first")

    @task
    def second():
        order.append("second")

    cfg = ExecutionConfig(root=tmp_path, concurrency=1)
    await Executor(default_registry(), cfg).run(["both"])

    assert order.index("first") < order.index("both")
    assert order.index("second") < order.index("both")


def test_lazy_deps_resolver_invoked_at_most_once() -> None:
    calls = {"n": 0}

    @task
    def upstream():
        pass

    def lazy_deps():
        calls["n"] += 1
        return [upstream]

    @task(deps=lazy_deps)
    def downstream():
        pass

    # Two graph builds in a row — the resolver should fire once.
    build_graph(default_registry())
    build_graph(default_registry())
    assert calls["n"] == 1


def test_lazy_deps_resolver_returning_non_iterable_raises() -> None:
    @task(deps=lambda: 42)  # type: ignore[arg-type,return-value]
    def t():
        pass

    with pytest.raises(TypeError, match="must return an iterable"):
        build_graph(default_registry())


def test_lazy_deps_marker_stored_on_task() -> None:
    @task(deps=lambda: [])
    def t():
        pass

    [stored] = default_registry().get("t").deps
    assert isinstance(stored, _LazyDeps)
