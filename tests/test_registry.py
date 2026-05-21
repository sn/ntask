import warnings

import pytest

from ntask._registry import RESERVED_SUBCOMMANDS, Registry


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


@pytest.mark.parametrize("reserved", sorted(RESERVED_SUBCOMMANDS))
def test_registry_warns_on_reserved_subcommand_name(reserved: str) -> None:
    r = Registry()
    def f() -> None: pass
    with pytest.warns(UserWarning, match=f"shadowed by the built-in subcommand '{reserved}'"):
        r.register(reserved, f, deps=(), concurrency=None, parallel=True,
                   cached_config=None, group=None)


def test_registry_does_not_warn_on_safe_name() -> None:
    r = Registry()
    def f() -> None: pass
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # turn any warning into a test failure
        r.register("not_reserved", f, deps=(), concurrency=None, parallel=True,
                   cached_config=None, group=None)


def test_registry_does_not_warn_when_reserved_name_is_grouped() -> None:
    """A `clean` task inside group `sim` becomes `sim.clean` — not shadowed."""
    r = Registry()
    def f() -> None: pass
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r.register("sim.clean", f, deps=(), concurrency=None, parallel=True,
                   cached_config=None, group="sim")
