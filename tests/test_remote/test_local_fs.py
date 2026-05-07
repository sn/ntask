from __future__ import annotations

from pathlib import Path

import pytest

from ntask._remote.local_fs import LocalFSBackend


def test_local_fs_roundtrip_entry(tmp_path: Path):
    backend = LocalFSBackend(root=tmp_path / "remote")
    entry = {"key": "abc", "outputs_hash": "def", "duration": 1.0}

    assert backend.has_entry("build", "abc") is False
    assert backend.get_entry("build", "abc") is None

    backend.put_entry("build", "abc", entry)
    assert backend.has_entry("build", "abc") is True
    assert backend.get_entry("build", "abc") == entry


def test_local_fs_missing_entry_returns_none(tmp_path: Path):
    backend = LocalFSBackend(root=tmp_path / "remote")
    assert backend.get_entry("nonexistent", "nope") is None


def test_local_fs_entry_namespace_per_fqn(tmp_path: Path):
    backend = LocalFSBackend(root=tmp_path / "remote")
    backend.put_entry("build", "k1", {"v": 1})
    backend.put_entry("test", "k1", {"v": 2})
    assert backend.get_entry("build", "k1") == {"v": 1}
    assert backend.get_entry("test", "k1") == {"v": 2}


def test_local_fs_output_roundtrip(tmp_path: Path):
    backend = LocalFSBackend(root=tmp_path / "remote")
    src = tmp_path / "workspace"
    src.mkdir()
    (src / "f.txt").write_bytes(b"hi")
    (src / "d").mkdir()
    (src / "d" / "g.txt").write_bytes(b"yo")

    assert backend.has_output("hash1") is False
    backend.put_output("hash1", src)
    assert backend.has_output("hash1") is True

    dest = tmp_path / "dest"
    backend.get_output("hash1", dest)
    assert (dest / "f.txt").read_bytes() == b"hi"
    assert (dest / "d" / "g.txt").read_bytes() == b"yo"


def test_local_fs_missing_output_raises(tmp_path: Path):
    backend = LocalFSBackend(root=tmp_path / "remote")
    with pytest.raises(FileNotFoundError):
        backend.get_output("nonexistent", tmp_path / "dest")
