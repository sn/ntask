"""Three independent tasks that fan out under -j, plus a deploy barrier."""

import time

from ntask import depends, task


@task
def build_a():
    time.sleep(1)
    print("built a")


@task
def build_b():
    time.sleep(1)
    print("built b")


@task
def build_c():
    time.sleep(1)
    print("built c")


@task
def all_builds():
    """Fan-out target. `ntask all_builds -j 3` takes ~1s; `-j 1` takes ~3s."""
    depends(build_a, build_b, build_c)


@task(parallel=False)
def deploy():
    """Runs exclusively - waits for every in-flight task to drain first.

    Useful for a task that mutates shared state (release branch, prod
    database, etc.) and must not overlap with anything else.
    """
    print("deploying (no siblings in flight)")


@task
def ship():
    """Fan-out builds, then run deploy exclusively."""
    depends(all_builds, deploy)
