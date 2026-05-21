"""ntask: a Python-native task runner with content-hash caching and DAG execution."""

from ._depends import depends
from ._errors import CycleError, DiscoveryError, NtaskError, ShellError
from ._shell import ShellResult, shell
from ._task import cached, group, task

__version__ = "1.1.2"
__all__ = [
    "CycleError",
    "DiscoveryError",
    "NtaskError",
    "ShellError",
    "ShellResult",
    "__version__",
    "cached",
    "depends",
    "group",
    "shell",
    "task",
]
