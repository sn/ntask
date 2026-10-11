import pytest

from ntask import depends, task
from ntask._depends import scan_static_depends
from ntask._registry import default_registry


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


def test_static_depends_extracted_from_body():
    @task
    def a(): pass

    @task
    def b(): pass

    @task
    def c():
        depends(a, b)
        return "c"

    names = scan_static_depends(default_registry().get("c").func)
    assert set(names) == {"a", "b"}


def test_dynamic_depends_marked_as_dynamic():
    @task
    def c():
        funcs = []
        depends(*funcs)

    result = scan_static_depends(default_registry().get("c").func)
    assert result == "dynamic"


def test_nested_function_depends_is_ignored():
    @task
    def a(): pass

    @task
    def outer():
        def inner():
            depends(a)   # should NOT be picked up
        inner()

    names = scan_static_depends(default_registry().get("outer").func)
    assert names == [], f"expected no static deps, got {names}"


def test_class_body_depends_is_ignored():
    @task
    def a(): pass

    @task
    def outer():
        class Inner:
            def method(self):
                depends(a)
        Inner()

    names = scan_static_depends(default_registry().get("outer").func)
    assert names == []


def test_depends_at_runtime_is_noop_outside_executor():
    # depends() called outside the executor context must not crash.
    def helper(): pass
    depends(helper)  # should not raise


def _edges():
    from ntask._dag import build_graph
    return build_graph(default_registry()).edges


def test_mixed_static_and_dynamic_depends_keeps_static_edge():
    @task
    def a(): pass

    @task
    def c():
        extra = []
        depends(a, *extra)

    with pytest.warns(UserWarning, match="can't be resolved statically"):
        edges = _edges()
    assert ("a", "c") in edges


def test_aliased_depends_resolves_to_real_fqn():
    @task
    def build(): pass

    alias = build

    @task
    def deploy():
        depends(alias)

    assert ("build", "deploy") in _edges()


def test_grouped_task_depends_resolves_to_group_fqn():
    from ntask import group

    @group("lint")
    class Lint:
        @task
        def ruff(): pass

    @task
    def check():
        depends(Lint.ruff)

    assert ("lint.ruff", "check") in _edges()


def test_unknown_depends_name_warns():
    def not_a_task(): pass

    @task
    def c():
        depends(not_a_task)

    with pytest.warns(UserWarning, match="does not refer to a known task"):
        edges = _edges()
    assert edges == []
