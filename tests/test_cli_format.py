import pytest

from ntask import cached, group, task
from ntask._cli_format import format_graph_ascii, format_graph_mermaid, format_list
from ntask._dag import Graph
from ntask._registry import default_registry


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


def test_list_shows_task_summaries():
    @task
    def hello():
        """Say hi."""

    @task
    @cached(inputs=["x.py"])
    def build(): pass

    out = format_list(default_registry(), use_color=False)
    assert "hello" in out
    assert "Say hi." in out
    assert "build" in out
    build_line = next(line for line in out.splitlines() if "build" in line)
    assert "*" in build_line or "*" in build_line


def test_list_groups_namespaces_separately():
    @group("docker")
    class Docker:
        @task
        def build(): pass

    out = format_list(default_registry(), use_color=False)
    assert "docker" in out
    assert "docker.build" in out


def test_graph_ascii_linear():
    g = Graph(nodes=["a", "b", "c"], edges=[("a", "b"), ("b", "c")])
    s = format_graph_ascii(g, target="c")
    assert "a" in s and "b" in s and "c" in s


def test_graph_mermaid_emits_valid_header():
    g = Graph(nodes=["a", "b"], edges=[("a", "b")])
    s = format_graph_mermaid(g)
    assert s.startswith("graph TD")
    assert "a --> b" in s
