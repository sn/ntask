import shutil
from pathlib import Path

import pytest

from ntask._cache.outputs import OutputStore


def test_capture_and_restore_roundtrip(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "dist").mkdir()
    (workspace / "dist" / "a.whl").write_bytes(b"wheel-bytes")
    store = OutputStore(root=tmp_path / ".ntask")
    outputs_hash = store.capture(["dist/**/*"], root=workspace)
    assert outputs_hash is not None

    shutil.rmtree(workspace / "dist")
    store.restore(outputs_hash, root=workspace)
    assert (workspace / "dist" / "a.whl").read_bytes() == b"wheel-bytes"


def test_capture_empty_returns_none(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = OutputStore(root=tmp_path / ".ntask")
    assert store.capture(["nonexistent/*"], root=workspace) is None


def test_restore_missing_hash_raises(tmp_path: Path):
    store = OutputStore(root=tmp_path / ".ntask")
    with pytest.raises(FileNotFoundError):
        store.restore("nonexistent", root=tmp_path)


def test_same_content_dedupes_to_same_hash(tmp_path: Path):
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    (ws1 / "x.txt").write_bytes(b"same")
    (ws2 / "x.txt").write_bytes(b"same")
    store = OutputStore(root=tmp_path / ".ntask")
    h1 = store.capture(["*.txt"], root=ws1)
    h2 = store.capture(["*.txt"], root=ws2)
    assert h1 == h2


def test_in_place_edit_after_capture_does_not_change_blob(tmp_path: Path):
    # Tools usually rewrite outputs in place; a hardlinked blob would change too.
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    (workspace / "out" / "f.txt").write_text("v1")
    store = OutputStore(root=tmp_path / ".ntask")
    digest = store.capture(["out/*"], root=workspace)
    assert digest is not None

    (workspace / "out" / "f.txt").write_text("edited")
    assert (store._hash_dir(digest) / "out" / "f.txt").read_text() == "v1"


def test_in_place_edit_after_restore_does_not_change_blob(tmp_path: Path):
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    (workspace / "out" / "f.txt").write_text("v1")
    store = OutputStore(root=tmp_path / ".ntask")
    digest = store.capture(["out/*"], root=workspace)
    assert digest is not None

    shutil.rmtree(workspace / "out")
    store.restore(digest, root=workspace)
    (workspace / "out" / "f.txt").write_text("edited")
    assert (store._hash_dir(digest) / "out" / "f.txt").read_text() == "v1"


def test_capture_leaves_no_staging_dirs(tmp_path: Path):
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    (workspace / "out" / "f.txt").write_text("v1")
    store = OutputStore(root=tmp_path / ".ntask")
    digest = store.capture(["out/*"], root=workspace)
    assert [p.name for p in store.outputs_dir.iterdir()] == [digest]


def test_capture_never_includes_the_store_itself(tmp_path: Path):
    workspace = tmp_path
    (workspace / "a.txt").write_text("a")
    store = OutputStore(root=workspace / ".ntask")
    first = store.capture(["**/*.txt"], root=workspace)
    second = store.capture(["**/*.txt"], root=workspace)
    assert first == second
