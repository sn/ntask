from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import wraps
from typing import Any, overload


@dataclass(frozen=True, slots=True)
class CachedConfig:
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    propagate: bool = True
    strict: bool = True


class _LazyDeps:
    """Marker for ``@task(deps=lambda: [a, b])`` — the resolver is invoked
    once at graph-build time so the referenced tasks don't need to be
    defined above the dependent.

    Memoised so repeated graph builds don't repeatedly re-execute the
    user's resolver.
    """

    __slots__ = ("_resolved", "_resolver")

    def __init__(self, resolver: Callable[[], Iterable[Any]]) -> None:
        self._resolver = resolver
        self._resolved: tuple[Any, ...] | None = None

    def resolve(self) -> tuple[Any, ...]:
        if self._resolved is None:
            value = self._resolver()
            try:
                self._resolved = tuple(value)
            except TypeError as exc:
                raise TypeError(
                    "deps=<callable> must return an iterable of task "
                    f"references; got {type(value).__name__}",
                ) from exc
        return self._resolved


@dataclass(slots=True)
class Task:
    fqn: str
    func: Callable[..., Any]
    deps: tuple[Any, ...]
    concurrency: int | None
    parallel: bool
    cached_config: CachedConfig | None
    group: str | None


@overload
def task(func: Callable[..., Any], /) -> Callable[..., Any]: ...
@overload
def task(
    *,
    deps: list[Callable[..., Any] | str]
        | Callable[[], Iterable[Callable[..., Any] | str]]
        | None = ...,
    concurrency: int | None = ...,
    parallel: bool = ...,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def task(
    func: Callable[..., Any] | None = None,
    /,
    *,
    deps: list[Callable[..., Any] | str]
        | Callable[[], Iterable[Callable[..., Any] | str]]
        | None = None,
    concurrency: int | None = None,
    parallel: bool = True,
) -> Any:
    """Register a function as a task.

    Usable as ``@task`` or ``@task(deps=[...], concurrency=..., parallel=...)``.

    ``deps`` accepts either an eager iterable of task refs (functions or
    fully-qualified string names) or a zero-arg callable returning the same.
    The callable form defers resolution until graph-build time, so forward
    references work without the linter complaining about file order.
    """
    if concurrency is not None:
        import warnings
        warnings.warn(
            f"@task(concurrency={concurrency!r}) is deprecated and has no "
            f"effect; use parallel=False to serialize a task with its "
            f"siblings. The concurrency field will be removed in 1.0.",
            DeprecationWarning,
            stacklevel=2,
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        from ._registry import default_registry

        existing_cfg = getattr(fn, "__ntask_cached_config__", None)
        group = getattr(fn, "__ntask_group__", None)
        name = fn.__name__
        fqn = f"{group}.{name}" if group else name

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper.__ntask_task__ = fqn  # type: ignore[attr-defined]

        if deps is None:
            deps_tuple: tuple[Any, ...] = ()
        elif callable(deps):
            # Lazy form: defer resolution until graph build time.
            deps_tuple = (_LazyDeps(deps),)
        else:
            deps_tuple = tuple(deps)

        default_registry().register(
            fqn,
            wrapper,
            deps=deps_tuple,
            concurrency=concurrency,
            parallel=parallel,
            cached_config=existing_cfg,
            group=group,
        )

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def cached(
    *,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    env: list[str] | None = None,
    propagate: bool = True,
    strict: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Opt a task into content-hash caching. Stacks with @task in either order."""

    cfg = CachedConfig(
        inputs=tuple(inputs or ()),
        outputs=tuple(outputs or ()),
        env=tuple(env or ()),
        propagate=propagate,
        strict=strict,
    )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        # If @task has already run (i.e., fn is a wrapper with __ntask_task__),
        # update the registry entry. Otherwise attach config and let @task pick it up.
        fqn = getattr(fn, "__ntask_task__", None)
        if fqn is not None:
            from ._registry import default_registry

            reg = default_registry()
            t = reg.get(fqn)
            object.__setattr__(t, "cached_config", cfg)
        else:
            fn.__ntask_cached_config__ = cfg  # type: ignore[attr-defined]
        return fn

    return decorator


def group(name: str) -> Callable[[type], type]:
    """Class decorator that namespaces its methods as tasks under ``name``."""

    if not name or "." in name:
        raise ValueError(f"invalid group name: {name!r}")

    def decorator(cls: type) -> type:
        from ._registry import default_registry

        reg = default_registry()
        for attr_name, attr in list(vars(cls).items()):
            if not callable(attr) or attr_name.startswith("_"):
                continue
            bare_fqn = getattr(attr, "__ntask_task__", None)
            if bare_fqn is None:
                continue  # helper method, not a task
            old = reg.get(bare_fqn)
            new_fqn = f"{name}.{attr_name}"
            reg.unregister(bare_fqn)
            reg.register(
                new_fqn,
                old.func,
                deps=old.deps,
                concurrency=old.concurrency,
                parallel=old.parallel,
                cached_config=old.cached_config,
                group=name,
            )
            attr.__ntask_task__ = new_fqn
        return cls

    return decorator
