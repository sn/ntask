"""Two subprojects namespaced under @group, plus a cross-group target."""

from ntask import cached, group, shell, task


@group("api")
class Api:
    @task
    @cached(inputs=["api/src/**/*.py", "api/tests/**/*.py"])
    def lint():
        shell("python3 -m compileall -q api/src")

    @task
    @cached(inputs=["api/src/**/*.py", "api/tests/**/*.py"])
    def test():
        shell("python3 -m unittest discover -s api/tests -t api")


@group("web")
class Web:
    @task
    @cached(inputs=["web/src/**/*.py", "web/tests/**/*.py"])
    def lint():
        shell("python3 -m compileall -q web/src")

    @task
    @cached(inputs=["web/src/**/*.py", "web/tests/**/*.py"])
    def test():
        shell("python3 -m unittest discover -s web/tests -t web")


@task(deps=[Api.lint, Api.test, Web.lint, Web.test])
def check():
    """Check every subproject. Mix groups freely via dotted FQNs."""


@task(deps=[Api.lint, Api.test])
def check_api_only():
    """Skip web; only run the api group."""
