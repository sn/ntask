"""A cached `test` task suitable for `ntask watch`."""

from ntask import cached, shell, task


@task
@cached(inputs=["src/**/*.py"])
def test():
    """Re-run tests whenever a .py file under src/ changes."""
    shell("python3 -m unittest discover -s src")
