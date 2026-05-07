from __future__ import annotations

from pathlib import Path

from ntask._remote._tar import extract_tar, tar_directory


def test_tar_roundtrip(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_bytes(b"aaa")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_bytes(b"bbb")

    data = tar_directory(src)
    assert isinstance(data, bytes)
    assert len(data) > 0

    dest = tmp_path / "dest"
    extract_tar(data, dest)
    assert (dest / "a.txt").read_bytes() == b"aaa"
    assert (dest / "sub" / "b.txt").read_bytes() == b"bbb"


def test_tar_is_deterministic(tmp_path: Path):
    """Same tree → same tar bytes (sorted entries, mtime=0, uid=gid=0)."""
    src1 = tmp_path / "s1"
    src2 = tmp_path / "s2"
    src1.mkdir()
    src2.mkdir()
    for s in (src1, src2):
        (s / "b.txt").write_bytes(b"B")
        (s / "a.txt").write_bytes(b"A")

    data1 = tar_directory(src1)
    data2 = tar_directory(src2)
    assert data1 == data2


def test_tar_empty_directory(tmp_path: Path):
    src = tmp_path / "empty"
    src.mkdir()
    data = tar_directory(src)
    assert isinstance(data, bytes)

    dest = tmp_path / "dest"
    extract_tar(data, dest)
    assert dest.is_dir()


def test_tar_ignores_directories_only_includes_files(tmp_path: Path):
    src = tmp_path / "s"
    src.mkdir()
    (src / "a").mkdir()
    (src / "a" / "f.txt").write_bytes(b"x")

    data = tar_directory(src)
    dest = tmp_path / "d"
    extract_tar(data, dest)
    assert (dest / "a" / "f.txt").read_bytes() == b"x"
