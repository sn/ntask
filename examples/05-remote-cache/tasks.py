"""A task whose cache entry is shared via a remote backend."""

import time

from ntask import cached, shell, task


@task
@cached(inputs=["input.txt"], outputs=["output.txt"])
def transform():
    """Pretend this is an expensive build step."""
    time.sleep(2)
    data = open("input.txt").read().strip()
    with open("output.txt", "w") as f:
        f.write(data.upper())
    print(f"produced output.txt from {len(data)} chars of input")
