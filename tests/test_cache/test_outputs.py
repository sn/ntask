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
