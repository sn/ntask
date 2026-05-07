import os
from pathlib import Path

from ntask._cache import CacheEngine
from ntask._cache.diff import MissItem, MissReport, diff_cache_state
from ntask._cache.key import CacheBreakdown, InputRecord
from ntask._task import CachedConfig, Task


def test_miss_item_is_frozen_slots():
    item = MissItem(kind="input-modified", detail="src/a.py")
    assert item.kind == "input-modified"
    assert item.detail == "src/a.py"


def test_miss_report_is_hit_when_empty():
    r = MissReport(items=())
    assert r.is_hit is True


def test_miss_report_is_miss_when_nonempty():
    r = MissReport(items=(MissItem(kind="input-modified", detail="x.py"),))
    assert r.is_hit is False


def test_summary_zero_items():
    assert MissReport(items=()).summary() == "no changes"


def test_summary_one_item():
    r = MissReport(items=(MissItem(kind="input-modified", detail="src/a.py"),))
    assert r.summary() == "input-modified: src/a.py"


def test_summary_many_items():
    r = MissReport(items=(
        MissItem(kind="input-modified", detail="src/a.py"),
        MissItem(kind="input-modified", detail="src/b.py"),
        MissItem(kind="env-changed", detail="X: '1' → '2'"),
    ))
    assert r.summary() == "input-modified: src/a.py (+2 more)"


def test_summary_kind_without_detail():
    r = MissReport(items=(MissItem(kind="first-run", detail=""),))
    assert r.summary() == "first-run"


def _bd(**overrides) -> CacheBreakdown:
    base = {
        "input_patterns": (),
        "inputs": (),
        "env_values": {},
        "task_body_hash": "body1",
        "python_version": "3.12.3",
        "platform_tag": "linux-x86_64",
        "upstream_keys_by_dep": {},
    }
    base.update(overrides)
    return CacheBreakdown(**base)


def test_no_prior_entry_is_first_run():
    r = diff_cache_state(_bd(), None)
    assert r.items == (MissItem(kind="first-run", detail=""),)


def test_identical_state_is_hit():
    r = diff_cache_state(_bd(), _bd())
    assert r.is_hit
    assert r.items == ()


def test_single_input_modified():
    prior = _bd(inputs=(InputRecord(path="src/a.py", digest="h1", mode=0o644),))
    current = _bd(inputs=(InputRecord(path="src/a.py", digest="h2", mode=0o644),))
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="input-modified", detail="src/a.py"),)


def test_input_added():
    prior = _bd(inputs=())
    current = _bd(inputs=(InputRecord(path="src/new.py", digest="h", mode=0o644),))
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="input-added", detail="src/new.py"),)


def test_input_removed():
    prior = _bd(inputs=(InputRecord(path="src/old.py", digest="h", mode=0o644),))
    current = _bd(inputs=())
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="input-removed", detail="src/old.py"),)


def test_input_mode_change_is_modified():
    prior = _bd(inputs=(InputRecord(path="src/a.py", digest="h", mode=0o644),))
    current = _bd(inputs=(InputRecord(path="src/a.py", digest="h", mode=0o755),))
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="input-modified", detail="src/a.py"),)


def test_multiple_input_changes_are_alphabetical():
    prior = _bd(inputs=(
        InputRecord(path="src/b.py", digest="h1", mode=0o644),
        InputRecord(path="src/a.py", digest="h1", mode=0o644),
    ))
    current = _bd(inputs=(
        InputRecord(path="src/b.py", digest="h2", mode=0o644),
        InputRecord(path="src/a.py", digest="h2", mode=0o644),
    ))
    r = diff_cache_state(current, prior)
    assert [i.detail for i in r.items] == ["src/a.py", "src/b.py"]


def test_env_changed_with_before_after_detail():
    prior = _bd(env_values={"X": "1"})
    current = _bd(env_values={"X": "2"})
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="env-changed", detail="X: '1' → '2'"),)


def test_env_added():
    prior = _bd(env_values={})
    current = _bd(env_values={"NEW": "v"})
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="env-added", detail="NEW"),)


def test_env_removed():
    prior = _bd(env_values={"OLD": "v"})
    current = _bd(env_values={})
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="env-removed", detail="OLD"),)


def test_env_unset_to_set_is_env_changed():
    prior = _bd(env_values={"X": "<unset>"})
    current = _bd(env_values={"X": "set"})
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="env-changed", detail="X: '<unset>' → 'set'"),)


def test_env_multiple_alphabetical():
    prior = _bd(env_values={"B": "1", "A": "1"})
    current = _bd(env_values={"B": "2", "A": "2"})
    r = diff_cache_state(current, prior)
    assert [i.detail for i in r.items] == ["A: '1' → '2'", "B: '1' → '2'"]


def test_body_hash_changed():
    r = diff_cache_state(_bd(task_body_hash="new"), _bd(task_body_hash="old"))
    assert r.items == (MissItem(kind="body-changed", detail=""),)


def test_python_version_changed():
    r = diff_cache_state(_bd(python_version="3.13.0"), _bd(python_version="3.12.3"))
    assert r.items == (MissItem(kind="python-changed",
                                detail="'3.12.3' → '3.13.0'"),)


def test_platform_changed():
    r = diff_cache_state(_bd(platform_tag="darwin-arm64"), _bd(platform_tag="linux-x86_64"))
    assert r.items == (MissItem(kind="platform-changed",
                                detail="'linux-x86_64' → 'darwin-arm64'"),)


def test_upstream_invalidated_names_the_dep():
    prior = _bd(upstream_keys_by_dep={"install": "u1"})
    current = _bd(upstream_keys_by_dep={"install": "u2"})
    r = diff_cache_state(current, prior)
    assert r.items == (MissItem(kind="upstream-invalidated", detail="install"),)


def test_upstream_added_and_removed_both_count_as_invalidated():
    prior = _bd(upstream_keys_by_dep={"a": "x"})
    current = _bd(upstream_keys_by_dep={"b": "x"})
    r = diff_cache_state(current, prior)
    kinds = [(i.kind, i.detail) for i in r.items]
    assert ("upstream-invalidated", "a") in kinds
    assert ("upstream-invalidated", "b") in kinds
    assert len(kinds) == 2


def test_priority_order_input_before_env_before_body():
    prior = _bd(
        inputs=(InputRecord(path="x.py", digest="h1", mode=0o644),),
        env_values={"E": "1"},
        task_body_hash="b1",
    )
    current = _bd(
        inputs=(InputRecord(path="x.py", digest="h2", mode=0o644),),
        env_values={"E": "2"},
        task_body_hash="b2",
    )
    r = diff_cache_state(current, prior)
    kinds = [i.kind for i in r.items]
    assert kinds == ["input-modified", "env-changed", "body-changed"]


def test_priority_order_body_before_upstream_before_python():
    prior = _bd(
        task_body_hash="b1",
        upstream_keys_by_dep={"dep": "u1"},
        python_version="3.12.3",
    )
    current = _bd(
        task_body_hash="b2",
        upstream_keys_by_dep={"dep": "u2"},
        python_version="3.13.0",
    )
    r = diff_cache_state(current, prior)
    kinds = [i.kind for i in r.items]
    assert kinds == ["body-changed", "upstream-invalidated", "python-changed"]


def test_legacy_prior_without_breakdown_is_first_run():
    r = diff_cache_state(_bd(), None)
    assert r.items == (MissItem(kind="first-run", detail=""),)


def test_compute_key_and_breakdown_returns_populated_breakdown(tmp_path: Path):
    (tmp_path / "a.py").write_text("print(1)")

    def fn():
        return 42

    t = Task(
        fqn="build", func=fn, deps=(),
        concurrency=None, parallel=True,
        cached_config=CachedConfig(
            inputs=("*.py",),
            outputs=(),
            env=("HOME",),
            propagate=True,
            strict=True,
        ),
        group=None,
    )
    os.environ["HOME"] = os.environ.get("HOME", str(tmp_path))
    engine = CacheEngine(root=tmp_path / ".ntask")
    key, bd = engine.compute_key_and_breakdown(
        t, workspace=tmp_path, upstream_keys_by_dep={"install": "u1"},
    )
    assert isinstance(key, str) and len(key) == 32  # xxh3_128 hex
    assert "a.py" in [ir.path for ir in bd.inputs]
    assert bd.task_body_hash  # truthy
    assert bd.python_version  # "3.12.3" or similar
    assert bd.platform_tag    # "linux-x86_64" or similar
    assert bd.upstream_keys_by_dep == {"install": "u1"}
    assert "HOME" in bd.env_values
    assert bd.input_patterns == ("*.py",)
