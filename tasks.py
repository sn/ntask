"""ntask builds/lints/types/tests itself with ntask."""

from ntask import cached, depends, shell, task


@task
def install():
    """Install dev dependencies."""
    shell('pip install -e ".[dev]"')


@task
@cached(inputs=["src/**/*.py"])
def lint():
    """Ruff."""
    shell("ruff check src tests")


@task
@cached(inputs=["src/**/*.py"])
def typecheck():
    """Mypy."""
    shell("mypy")


@task
@cached(inputs=["src/**/*.py", "tests/**/*.py"])
def test():
    """Pytest."""
    shell("pytest -v")


@task
def check():
    """All quality checks."""
    depends(lint, typecheck, test)


@task
@cached(
    inputs=["src/**/*.py", "pyproject.toml", "README.md", "LICENSE"],
    outputs=["dist/"],
)
def build():
    """Build the wheel."""
    shell("python -m build")


@task
def release(version: str):
    """Cut a release: tag + push."""
    depends(check, build)
    shell(f"git tag v{version} && git push --tags")
