import time

import pytest

from ntask._cache.diff import MissItem, MissReport
from ntask._cache.key import CacheBreakdown, InputRecord
from ntask._cache.store import CacheEntry
from ntask._cli_why import render_why
from ntask._task import CachedConfig, Task


def _sample_task(fqn: str = "build", cached: bool = True) -> Task:
    def fn(): pass
    cfg = CachedConfig(
        inputs=("src/**/*.py",), outputs=(), env=(),
        propagate=True, strict=True,
    ) if cached else None
    return Task(fqn=fqn, func=fn, deps=(), concurrency=None,
                parallel=True, cached_config=cfg, group=None)


def _sample_entry(completed_at: float = 100.0) -> CacheEntry:
    bd = CacheBreakdown(
        input_patterns=("src/**/*.py",),
        inputs=(InputRecord(path="src/a.py", digest="h1", mode=0o644),),
        env_values={},
        task_body_hash="body",
        python_version="3.12.3",
        platform_tag="linux-x86_64",
        upstream_keys_by_dep={},
    )
    return CacheEntry(
        key="3a8f9c2d" + "0" * 24,
        outputs_hash=None,
        duration=2.41,
        completed_at=completed_at,
        upstream_keys=(),
        breakdown=bd,
    )


def test_render_why_hit():
    report = MissReport(items=())
    out = render_why(
        task=_sample_task(),
        prior=_sample_entry(completed_at=time.time() - 3600),
        report=report,
        current_key="3a8f9c2d" + "0" * 24,
        use_color=False,
    )
    assert "HIT" in out
    assert "build" in out


def test_render_why_miss_shows_first_change():
    report = MissReport(items=(MissItem(kind="input-modified", detail="src/a.py"),))
    out = render_why(
        task=_sample_task(),
        prior=_sample_entry(completed_at=time.time() - 300),
        report=report,
        current_key="differentkey" + "0" * 20,
        use_color=False,
    )
    assert "MISS" in out
    assert "src/a.py" in out
    assert "1 change" in out or "1 changes" in out


def test_render_why_miss_shows_all_changes():
    report = MissReport(items=(
        MissItem(kind="input-modified", detail="src/a.py"),
        MissItem(kind="input-modified", detail="src/b.py"),
        MissItem(kind="env-changed", detail="BUILD_ENV: 'dev' → 'prod'"),
    ))
    out = render_why(
        task=_sample_task(),
        prior=_sample_entry(),
        report=report,
        current_key="newkey" + "0" * 26,
        use_color=False,
    )
    assert "src/a.py" in out
    assert "src/b.py" in out
    assert "BUILD_ENV" in out
    assert "3 change" in out


def test_render_why_no_prior_entry():
    out = render_why(
        task=_sample_task(),
        prior=None,
        report=MissReport(items=(MissItem(kind="first-run", detail=""),)),
        current_key="",
        use_color=False,
    )
    assert "no cached" in out.lower() or "first run" in out.lower()


def test_render_why_uncached_task_raises():
    with pytest.raises(ValueError, match="not a cached task"):
        render_why(
            task=_sample_task(cached=False),
            prior=None,
            report=MissReport(items=()),
            current_key="",
            use_color=False,
        )
