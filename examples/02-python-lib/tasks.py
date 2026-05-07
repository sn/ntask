"""Realistic Python-library workflow: install / lint / typecheck / test / build."""

from ntask import cached, depends, shell, task


@task
def install():
    """Install dev dependencies (uncached - pip tracks its own state)."""
    shell('pip install -e ".[dev]"')


@task
@cached(inputs=["src/**/*.py", "tests/**/*.py", "pyproject.toml"])
def lint():
    """Ruff - fast, idempotent, cache-friendly."""
    shell("ruff check src tests")


@task
@cached(inputs=["src/**/*.py", "pyproject.toml"])
def typecheck():
    """Mypy against the library source."""
    shell("mypy src")


@task
@cached(inputs=["src/**/*.py", "tests/**/*.py", "pyproject.toml"])
def test():
    """Pytest."""
    shell("pytest -q")


@task
def check():
    """Fan-out: lint + typecheck + test. Run as `ntask check -j 3`."""
    depends(lint, typecheck, test)


@task
@cached(
    inputs=["src/**/*.py", "pyproject.toml", "README.md"],
    outputs=["dist/"],
)
def build():
    """Build the wheel. Outputs listed so cache hits restore dist/."""
    shell("python -m build")
