import pytest

from ntask._dag import Graph, build_graph, toposort
from ntask._errors import CycleError
from ntask._registry import Registry
from ntask._task import Task


def test_toposort_linear():
    g = Graph(nodes=["a", "b", "c"], edges=[("a", "b"), ("b", "c")])
    assert toposort(g) == ["a", "b", "c"]


def test_toposort_diamond():
    g = Graph(nodes=["a", "b", "c", "d"],
              edges=[("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    order = toposort(g)
    assert order.index("a") < order.index("b") < order.index("d")
    assert order.index("a") < order.index("c") < order.index("d")


def test_toposort_detects_cycle():
    g = Graph(nodes=["a", "b"], edges=[("a", "b"), ("b", "a")])
    with pytest.raises(CycleError) as exc:
        toposort(g)
    assert set(exc.value.cycle) >= {"a", "b"}


def test_subgraph_reachable_from_targets():
    g = Graph(
        nodes=["a", "b", "c", "d", "unrelated"],
        edges=[("a", "b"), ("b", "c"), ("d", "c")],
    )
    sub = g.reachable_from(["c"])
    assert set(sub.nodes) == {"a", "b", "c", "d"}
    assert "unrelated" not in sub.nodes


def test_graph_direct_deps():
    g = Graph(nodes=["a", "b", "c"], edges=[("a", "c"), ("b", "c")])
    assert set(g.direct_deps("c")) == {"a", "b"}
    assert g.direct_deps("a") == []


def _make_task(fqn, func=None, deps=()):
    if func is None:
        def func(): pass
    return Task(fqn=fqn, func=func, deps=deps, concurrency=None,
                parallel=True, cached_config=None, group=None)


def test_build_graph_from_decorator_deps():
    reg = Registry()
    def a_fn(): pass
    def b_fn(): pass
    reg._tasks["a"] = _make_task("a", func=a_fn)
    reg._tasks["b"] = _make_task("b", func=b_fn, deps=(a_fn,))
    g = build_graph(reg)
    assert set(g.nodes) == {"a", "b"}
    assert ("a", "b") in g.edges


def test_build_graph_handles_wrapper_refs_via_attr():
    reg = Registry()
    def a_fn(): pass
    def wrapper_b(): pass
    wrapper_b.__ntask_task__ = "a"  # type: ignore
    reg._tasks["a"] = _make_task("a", func=a_fn)
    reg._tasks["x"] = _make_task("x", func=lambda: None, deps=(wrapper_b,))
    g = build_graph(reg)
    assert ("a", "x") in g.edges
