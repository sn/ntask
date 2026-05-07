"""DAG-wide coordinator for parallel=False (exclusive) tasks.

Exclusive tasks wait for all in-flight normal tasks to drain before starting,
and hold the DAG exclusively for their entire runtime. Normal tasks wait for
any running exclusive task to release before starting.
"""
from __future__ import annotations

import anyio


class _ParallelCoordinator:
    """Gate task entry so exclusive (parallel=False) tasks serialize with siblings."""

    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._active_count = 0
        self._exclusive_held = False
        # Events re-created on state transition so waiters wake then re-check.
        self._idle_event = anyio.Event()
        self._idle_event.set()
        self._free_event = anyio.Event()
        self._free_event.set()

    async def enter(self, *, exclusive: bool) -> None:
        """Wait until this task can start. For exclusive tasks, wait until
        no other task is running AND no other exclusive is held. For normal
        tasks, wait only for the exclusive gate.
        """
        while True:
            await self._free_event.wait()
            if exclusive:
                await self._idle_event.wait()
            async with self._lock:
                if self._exclusive_held:
                    continue
                if exclusive and self._active_count > 0:
                    continue
                # Success - take the slot under the lock.
                if exclusive:
                    self._exclusive_held = True
                    self._free_event = anyio.Event()  # cleared
                self._active_count += 1
                if self._active_count == 1:
                    self._idle_event = anyio.Event()  # cleared
                return

    async def exit(self, *, exclusive: bool) -> None:
        """Release the slot taken by a prior ``enter(exclusive=...)`` call."""
        async with self._lock:
            self._active_count -= 1
            if self._active_count == 0:
                self._idle_event.set()
            if exclusive:
                self._exclusive_held = False
                self._free_event.set()
