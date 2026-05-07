import os
import time
from pathlib import Path

from ntask._cache.manifest import compute_input_manifest


def test_manifest_is_deterministic(tmp_path: Path):
    (tmp_path / "a.py").write_text("print('a')")
    (tmp_path / "b.py").write_text("print('b')")
    h1 = compute_input_manifest(["*.py"], root=tmp_path).digest
    h2 = compute_input_manifest(["*.py"], root=tmp_path).digest
    assert h1 == h2


def test_manifest_changes_when_file_content_changes(tmp_path: Path):
    (tmp_path / "a.py").write_text("v1")
    before = compute_input_manifest(["*.py"], root=tmp_path).digest
    (tmp_path / "a.py").write_text("v2")
    after = compute_input_manifest(["*.py"], root=tmp_path).digest
    assert before != after


def test_manifest_unaffected_by_mtime_alone(tmp_path: Path):
    p = tmp_path / "a.py"
    p.write_text("same")
    before = compute_input_manifest(["*.py"], root=tmp_path).digest
    future = time.time() + 10
    os.utime(p, (future, future))
    after = compute_input_manifest(["*.py"], root=tmp_path).digest
    assert before == after, "manifest must depend on content, not mtime"


def test_manifest_respects_gitignore(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("ignored.py\n")
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "ignored.py").write_text("skip")
    manifest = compute_input_manifest(["*.py"], root=tmp_path)
    names = [f.path.name for f in manifest.files]
    assert "a.py" in names
    assert "ignored.py" not in names


def test_manifest_recursive_globs(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sub").mkdir()
    (tmp_path / "src" / "sub" / "deep.py").write_text("x")
    manifest = compute_input_manifest(["src/**/*.py"], root=tmp_path)
    assert len(manifest.files) == 1
    assert manifest.files[0].path.name == "deep.py"


def test_manifest_empty_globs_produces_stable_empty_hash(tmp_path: Path):
    manifest = compute_input_manifest([], root=tmp_path)
    assert manifest.files == []
    assert manifest.digest == compute_input_manifest([], root=tmp_path).digest
