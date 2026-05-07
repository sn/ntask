from pathlib import Path

from ntask._cache.key import CacheBreakdown, InputRecord
from ntask._cache.store import CacheEntry, CacheStore


def test_store_round_trip(tmp_path: Path):
    store = CacheStore(root=tmp_path / ".ntask")
    entry = CacheEntry(
        key="abc123",
        outputs_hash="def456",
        duration=1.5,
        completed_at=1000.0,
        upstream_keys=("u1",),
    )
    store.put("build", entry)
    loaded = store.get("build", "abc123")
    assert loaded == entry


def test_store_get_miss_returns_none(tmp_path: Path):
    store = CacheStore(root=tmp_path / ".ntask")
    assert store.get("build", "nonexistent") is None


def test_store_has_key(tmp_path: Path):
    store = CacheStore(root=tmp_path / ".ntask")
    assert not store.has("build", "k")
    store.put("build", CacheEntry(key="k", outputs_hash=None, duration=0.1,
                                  completed_at=0.0, upstream_keys=()))
    assert store.has("build", "k")


def test_store_clear(tmp_path: Path):
    store = CacheStore(root=tmp_path / ".ntask")
    store.put("build", CacheEntry(key="k", outputs_hash=None, duration=0.1,
                                  completed_at=0.0, upstream_keys=()))
    store.clear()
    assert not store.has("build", "k")


def _sample_breakdown() -> CacheBreakdown:
    return CacheBreakdown(
        input_patterns=("src/**/*.py",),
        inputs=(
            InputRecord(path="src/a.py", digest="aaa", mode=0o644),
            InputRecord(path="src/b.py", digest="bbb", mode=0o644),
        ),
        env_values={"X": "1", "Y": "<unset>"},
        task_body_hash="body-hash",
        python_version="3.12.3",
        platform_tag="linux-x86_64",
        upstream_keys_by_dep={"install": "u1"},
    )


def test_store_round_trip_with_breakdown(tmp_path: Path):
    store = CacheStore(root=tmp_path / ".ntask")
    entry = CacheEntry(
        key="abc",
        outputs_hash="oh",
        duration=1.0,
        completed_at=100.0,
        upstream_keys=("u1",),
        breakdown=_sample_breakdown(),
    )
    store.put("build", entry)
    loaded = store.get("build", "abc")
    assert loaded is not None
    assert loaded.breakdown is not None
    assert loaded.breakdown.inputs[0].path == "src/a.py"
    assert loaded.breakdown.env_values == {"X": "1", "Y": "<unset>"}
    assert loaded.breakdown.upstream_keys_by_dep == {"install": "u1"}


def test_store_reads_legacy_entry_without_breakdown(tmp_path: Path):
    import json
    store = CacheStore(root=tmp_path / ".ntask")
    # Write a legacy v0.1.0-era entry manually (no `breakdown` key).
    p = store.cache_dir / "build" / "legacy.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "key": "legacy",
        "outputs_hash": None,
        "duration": 0.1,
        "completed_at": 0.0,
        "upstream_keys": [],
    }))
    loaded = store.get("build", "legacy")
    assert loaded is not None
    assert loaded.breakdown is None
    assert loaded.key == "legacy"


def test_store_latest_returns_none_when_empty(tmp_path: Path):
    store = CacheStore(root=tmp_path / ".ntask")
    assert store.latest("build") is None


def test_store_latest_returns_most_recent_entry(tmp_path: Path):
    import time
    store = CacheStore(root=tmp_path / ".ntask")
    store.put("build", CacheEntry(key="first", outputs_hash=None,
                                  duration=0.1, completed_at=1.0, upstream_keys=()))
    time.sleep(0.01)  # ensure different mtime
    store.put("build", CacheEntry(key="second", outputs_hash=None,
                                  duration=0.2, completed_at=2.0, upstream_keys=()))
    latest = store.latest("build")
    assert latest is not None
    assert latest.key == "second"
