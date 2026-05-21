import pytest

from ntask import cached, group, task
from ntask._cli_format import (
    format_graph_ascii,
    format_graph_mermaid,
    format_list,
    format_task_signature,
)
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


def test_signature_required_param_uses_angle_brackets():
    def fn(name: str): ...
    assert format_task_signature(fn) == "<name: str>"


def test_signature_optional_param_uses_default_value():
    def fn(attempts: int = 10): ...
    assert format_task_signature(fn) == "[--attempts=10]"


def test_signature_bool_default_false_renders_as_flag():
    def fn(verbose: bool = False): ...
    assert format_task_signature(fn) == "[--verbose]"


def test_signature_bool_default_true_renders_as_no_flag():
    def fn(safe: bool = True): ...
    assert format_task_signature(fn) == "[--no-safe]"


def test_signature_mixed_params_are_space_separated():
    def fn(target: str, attempts: int = 5, verbose: bool = False): ...
    rendered = format_task_signature(fn)
    assert rendered == "<target: str> [--attempts=5] [--verbose]"


def test_signature_truncates_when_too_long():
    def fn(
        very_long_name_one: str = "default-one",
        very_long_name_two: str = "default-two",
        very_long_name_three: str = "default-three",
    ): ...
    rendered = format_task_signature(fn)
    assert rendered.endswith("...")
    assert len(rendered) <= 40


def test_list_output_includes_signature_for_task_with_args():
    @task
    def brute_force(attempts: int = 10):
        """Replay one PIN N times."""

    out = format_list(default_registry(), use_color=False)
    assert "[--attempts=10]" in out
    assert "Replay one PIN" in out
