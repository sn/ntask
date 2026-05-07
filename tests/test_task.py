import warnings

import pytest

from ntask import cached, task
from ntask._registry import default_registry
from ntask._task import CachedConfig


@pytest.fixture(autouse=True)
def _clear_registry():
    default_registry().clear()
    yield
    default_registry().clear()


def test_task_bare_decorator_registers_function():
    @task
    def hello():
        return "hi"

    t = default_registry().get("hello")
    assert t.func is hello
    assert t.deps == ()
    assert t.parallel is True
    assert t.concurrency is None
    assert hello() == "hi"


def test_task_with_args_registers_deps_and_concurrency():
    @task
    def a(): pass

    @task(deps=[a], concurrency=1, parallel=False)
    def b(): pass

    bt = default_registry().get("b")
    assert bt.deps == (a,)
    assert bt.concurrency == 1
    assert bt.parallel is False


def test_task_preserves_name_and_docstring():
    @task
    def greet():
        """Say hi."""
        return "hi"

    assert greet.__name__ == "greet"
    assert greet.__doc__ == "Say hi."


def test_cached_before_task_attaches_config():
    @task
    @cached(inputs=["src/**/*.py"], outputs=["dist/"], env=["BUILD_ENV"])
    def build(): pass

    cfg = default_registry().get("build").cached_config
    assert cfg == CachedConfig(
        inputs=("src/**/*.py",),
        outputs=("dist/",),
        env=("BUILD_ENV",),
        propagate=True,
        strict=True,
    )


def test_cached_after_task_also_attaches_config():
    @cached(inputs=["x.py"])
    @task
    def build(): pass

    cfg = default_registry().get("build").cached_config
    assert cfg is not None
    assert cfg.inputs == ("x.py",)


def test_task_without_cached_has_none():
    @task
    def plain(): pass

    assert default_registry().get("plain").cached_config is None


def test_concurrency_arg_emits_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @task(concurrency=1)
        def migrate(): pass

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecations) == 1
    msg = str(deprecations[0].message)
    assert "concurrency" in msg
    assert "deprecated" in msg


def test_no_deprecation_warning_when_concurrency_not_passed():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @task
        def plain(): pass

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations == []
