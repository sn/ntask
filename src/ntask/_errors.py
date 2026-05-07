from __future__ import annotations


class NtaskError(Exception):
    """Base class for ntask errors."""


class DiscoveryError(NtaskError):
    """tasks.py could not be found or imported."""


class CycleError(NtaskError):
    """A cycle exists in the task graph."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        arrows = " -> ".join(cycle)
        super().__init__(f"cycle in task graph: {arrows}")


class ShellError(NtaskError):
    """A ``shell()`` command exited non-zero."""

    def __init__(self, returncode: int, cmd: str | list[str]):
        self.returncode = returncode
        self.cmd = cmd
        super().__init__(f"command failed (exit {returncode}): {cmd!r}")
