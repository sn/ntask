from __future__ import annotations

import anyio

from ntask._coordinator import _ParallelCoordinator


async def test_coordinator_allows_multiple_normal_tasks(tmp_path):
    c = _ParallelCoordinator()
    order: list[str] = []

    async def task_a():
        await c.enter(exclusive=False)
        order.append("a-start")
        await anyio.sleep(0.05)
        order.append("a-end")
        await c.exit(exclusive=False)

    async def task_b():
        await c.enter(exclusive=False)
        order.append("b-start")
        await anyio.sleep(0.05)
        order.append("b-end")
        await c.exit(exclusive=False)

    async with anyio.create_task_group() as tg:
        tg.start_soon(task_a)
        tg.start_soon(task_b)

    # Both started before either ended → overlap.
    assert order.index("a-start") < order.index("b-end")
    assert order.index("b-start") < order.index("a-end")


async def test_coordinator_exclusive_task_waits_for_running_siblings(tmp_path):
    c = _ParallelCoordinator()
    events: list[tuple[str, float]] = []

    async def normal_task():
        await c.enter(exclusive=False)
        events.append(("normal-start", anyio.current_time()))
        await anyio.sleep(0.15)
        events.append(("normal-end", anyio.current_time()))
        await c.exit(exclusive=False)

    async def exclusive_task():
        # Small delay so normal_task starts first.
        await anyio.sleep(0.02)
        await c.enter(exclusive=True)
        events.append(("excl-start", anyio.current_time()))
        await anyio.sleep(0.05)
        events.append(("excl-end", anyio.current_time()))
        await c.exit(exclusive=True)

    async with anyio.create_task_group() as tg:
        tg.start_soon(normal_task)
        tg.start_soon(exclusive_task)

    times = dict(events)
    # Exclusive started strictly after normal ended.
    assert times["excl-start"] >= times["normal-end"]


async def test_coordinator_normal_task_waits_for_exclusive(tmp_path):
    c = _ParallelCoordinator()
    events: list[tuple[str, float]] = []

    async def exclusive_task():
        await c.enter(exclusive=True)
        events.append(("excl-start", anyio.current_time()))
        await anyio.sleep(0.10)
        events.append(("excl-end", anyio.current_time()))
        await c.exit(exclusive=True)

    async def normal_task():
        await anyio.sleep(0.02)
        await c.enter(exclusive=False)
        events.append(("normal-start", anyio.current_time()))
        await anyio.sleep(0.05)
        events.append(("normal-end", anyio.current_time()))
        await c.exit(exclusive=False)

    async with anyio.create_task_group() as tg:
        tg.start_soon(exclusive_task)
        tg.start_soon(normal_task)

    times = dict(events)
    # Normal started at or after exclusive ended.
    assert times["normal-start"] >= times["excl-end"]


async def test_coordinator_with_only_one_exclusive_and_no_others():
    c = _ParallelCoordinator()
    await c.enter(exclusive=True)
    await c.exit(exclusive=True)
    # No hang; fresh state allows another entry.
    await c.enter(exclusive=False)
    await c.exit(exclusive=False)


async def test_coordinator_sequential_normal_tasks_do_not_deadlock():
    c = _ParallelCoordinator()
    for _ in range(5):
        await c.enter(exclusive=False)
        await c.exit(exclusive=False)
