import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ntask import cached, task
from ntask._executor import ExecutionConfig, Executor
from ntask._registry import default_registry


@st.composite
def small_dag(draw):
    n = draw(st.integers(min_value=1, max_value=5))
    names = [f"t{i}" for i in range(n)]
    deps = {name: [] for name in names}
    for i in range(1, n):
        k = draw(st.integers(min_value=0, max_value=i))
        if k > 0:
            chosen = draw(st.lists(
                st.sampled_from(names[:i]),
                min_size=min(k, i), max_size=min(k, i), unique=True,
            ))
            deps[names[i]] = chosen
    return names, deps


@pytest.fixture(autouse=True)
def _clear():
    default_registry().clear()
    yield
    default_registry().clear()


@pytest.mark.parametrize("concurrency", [1, 4])
@given(small_dag())
@settings(max_examples=25, deadline=None)
@pytest.mark.asyncio
async def test_second_run_fully_cached(concurrency, dag):
    names, deps = dag

    with tempfile.TemporaryDirectory() as tmp_path_str:
        tmp_path = Path(tmp_path_str)
        default_registry().clear()
        runs = dict.fromkeys(names, 0)
        fns = {}
        for name in names:
            def _make(n=name):
                @cached(inputs=[])
                def _impl():
                    runs[n] += 1
                _impl.__name__ = n
                return _impl
            fns[name] = task(deps=[fns[d] for d in deps[name]])(_make())

        ex = Executor(default_registry(), ExecutionConfig(root=tmp_path, concurrency=concurrency))
        await ex.run([names[-1]])
        for name in names:
            runs[name] = 0  # reset counters
        await ex.run([names[-1]])
        assert all(v == 0 for v in runs.values()), "second run must fully cache-hit"
