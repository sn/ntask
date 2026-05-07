import pytest

from ntask import cached, group, task
from ntask._registry import default_registry


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


def test_group_namespaces_methods_as_dotted_fqns():
    @group("docker")
    class Docker:
        @task
        def build(): return "built"

        @task
        def run(): return "ran"

    reg = default_registry()
    assert set(reg.fqns()) == {"docker.build", "docker.run"}
    assert reg.get("docker.build").group == "docker"


def test_group_methods_take_no_self_and_are_callable():
    @group("docker")
    class Docker:
        @task
        def build(): return "built"

    assert Docker.build() == "built"


def test_group_supports_cached_inside():
    @group("docker")
    class Docker:
        @task
        @cached(inputs=["Dockerfile"])
        def build(): pass

    cfg = default_registry().get("docker.build").cached_config
    assert cfg is not None
    assert cfg.inputs == ("Dockerfile",)
