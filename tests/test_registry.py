import pytest

from ntask._registry import Registry


def test_registry_registers_and_looks_up() -> None:
    r = Registry()
    def my_fn() -> None: pass
    r.register("my_fn", my_fn, deps=(), concurrency=None, parallel=True,
               cached_config=None, group=None)
    assert r.get("my_fn").func is my_fn
    assert r.fqns() == ("my_fn",)


def test_registry_rejects_duplicate_fqn() -> None:
    r = Registry()
    def a() -> None: pass
    def b() -> None: pass
    r.register("x", a, deps=(), concurrency=None, parallel=True,
               cached_config=None, group=None)
    with pytest.raises(ValueError, match="already registered"):
        r.register("x", b, deps=(), concurrency=None, parallel=True,
                   cached_config=None, group=None)
