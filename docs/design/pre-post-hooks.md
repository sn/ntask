# Pre/post-task hooks — design note

**Status:** deferred. This memo captures the reasoning so the next time it
comes up we don't re-litigate the trade-offs from scratch.

## Problem

Users with many tasks in the same "shape" (the canonical example is a
simulator: ~13 scenario tasks that all clear caches and wipe a table
before running) want to dedupe the preamble:

```python
@task
def scenario_a():
    cache.clear()
    FraudEvent.objects.all().delete()
    # ...actual scenario body...
```

The boilerplate is identical across N tasks. The user shouldn't have to
copy-paste it.

## Options the punch-list considered

### (a) Module-level hooks in `taskconf.py`

```python
# taskconf.py — discovered next to tasks.py
def before_each():
    cache.clear()
    FraudEvent.objects.all().delete()
```

Pros: zero ceremony on each task. New tasks pick up the preamble for
free. Pattern is familiar (pytest's conftest.py).

Cons: pytest's conftest started exactly this way and grew into the
fixture system. Once `before_each` accepts arguments, or returns
something the task body wants, you're shipping a fixture framework.

### (b) Group-scoped decorator hooks

```python
@before_task(group="simulator")
def reset_state():
    cache.clear()
    FraudEvent.objects.all().delete()
```

Pros: scope-bounded version of (a). Different groups get different
preambles.

Cons: same scope-creep gravity as (a). The single-file project case is
strictly worse than (a) — extra boilerplate for no extra power.

### (c) Per-task kwargs

```python
@task(before=reset_state, after=...)
def scenario_a(): ...
```

Pros: explicit, no spooky-action-at-a-distance.

Cons: doesn't actually dedupe. The user still has to list the hook on
every task. It's strictly worse than a thin wrapper decorator they
write themselves (see below).

## What you can already do today

Plain Python composition:

```python
def with_reset(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        cache.clear()
        FraudEvent.objects.all().delete()
        return fn(*args, **kwargs)
    return wrapper

@task
@with_reset
def scenario_a(): ...

@task
@with_reset
def scenario_b(): ...
```

This requires no changes to ntask. It composes with `@cached` (decorator
order is already free). It scopes by whichever set of tasks the user
chooses to apply it to. The downside vs. (a) is the user has to remember
to apply the decorator — but that downside is the *whole point*:
forgetting it is visible at the call site, not at the implicit
framework layer.

## Recommendation: defer

Build option (a) only if the composition pattern above repeatedly fails
the user — *and* only if we're willing to commit to "no fixtures, no
parametrization, no finalizers, no DI" as a hard product line.

Concretely: defer until at least three independent reports of "decorator
composition didn't solve it", with the actual repro. Without that
evidence the most likely outcome is a feature that scope-creeps into
pytest-fixtures-for-tasks and lands us with the same complexity pytest
has spent two decades managing.

If we do build it later, the minimum viable shape is:

- Only `(setup, teardown)` paired hooks; no separate phases.
- Setup and teardown take **zero arguments** and return nothing.
- Hooks live in `taskconf.py` next to `tasks.py` — no implicit discovery
  beyond the project root.
- Hooks fire per-task (not per-run, not per-group). Group scoping is a
  follow-up only if module-level proves insufficient.
- A task body must never be able to *receive* anything from setup.
  That's the line that turns hooks into fixtures.

Closes punch-list item 12.
