from pathlib import Path

from ntask._cache.key import CacheBreakdown, CacheKeyInputs, InputRecord, compute_cache_key


def _inputs(tmp_path: Path, **overrides):
    base = {
        "task_fqn": "build",
        "task_body_hash": "body-hash-1",
        "env": {},
        "env_names": (),
        "input_patterns": (),
        "input_manifest_digest": "empty",
        "root": tmp_path,
        "upstream_keys": (),
        "strict": True,
    }
    base.update(overrides)
    return CacheKeyInputs(**base)


def test_cache_key_deterministic(tmp_path: Path):
    inp = _inputs(tmp_path)
    assert compute_cache_key(inp) == compute_cache_key(inp)


def test_input_hash_change_changes_key(tmp_path: Path):
    k1 = compute_cache_key(_inputs(tmp_path, input_manifest_digest="A"))
    k2 = compute_cache_key(_inputs(tmp_path, input_manifest_digest="B"))
    assert k1 != k2


def test_body_hash_change_changes_key(tmp_path: Path):
    k1 = compute_cache_key(_inputs(tmp_path, task_body_hash="a"))
    k2 = compute_cache_key(_inputs(tmp_path, task_body_hash="b"))
    assert k1 != k2


def test_declared_env_var_value_affects_key(tmp_path: Path):
    k1 = compute_cache_key(_inputs(tmp_path, env_names=("X",), env={"X": "1"}))
    k2 = compute_cache_key(_inputs(tmp_path, env_names=("X",), env={"X": "2"}))
    assert k1 != k2


def test_undeclared_env_var_does_not_affect_key(tmp_path: Path):
    k1 = compute_cache_key(_inputs(tmp_path, env={"Y": "1"}))
    k2 = compute_cache_key(_inputs(tmp_path, env={"Y": "2"}))
    assert k1 == k2


def test_upstream_keys_propagate_into_key(tmp_path: Path):
    k1 = compute_cache_key(_inputs(tmp_path, upstream_keys=("u1",)))
    k2 = compute_cache_key(_inputs(tmp_path, upstream_keys=("u2",)))
    assert k1 != k2


def test_non_strict_mode_ignores_python_and_platform(tmp_path: Path):
    k1 = compute_cache_key(_inputs(tmp_path, strict=False))
    k2 = compute_cache_key(_inputs(tmp_path, strict=False))
    assert k1 == k2


def test_input_record_is_frozen_slots():
    r = InputRecord(path="src/a.py", digest="abc", mode=0o644)
    assert r.path == "src/a.py"
    assert r.digest == "abc"
    assert r.mode == 0o644


def test_cache_breakdown_default_empty():
    b = CacheBreakdown(
        input_patterns=(),
        inputs=(),
        env_values={},
        task_body_hash="body",
        python_version="3.12.3",
        platform_tag="linux-x86_64",
        upstream_keys_by_dep={},
    )
    assert b.inputs == ()
    assert b.env_values == {}
    assert b.upstream_keys_by_dep == {}
