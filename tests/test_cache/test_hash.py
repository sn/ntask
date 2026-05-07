from pathlib import Path

from ntask._cache.hash import (
    FileHash,
    hash_bytes,
    hash_file,
    hash_many_files,
)


def test_hash_bytes_is_stable():
    assert hash_bytes(b"hello") == hash_bytes(b"hello")
    assert hash_bytes(b"hello") != hash_bytes(b"world")


def test_hash_file_matches_hash_bytes(tmp_path: Path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"contents")
    assert hash_file(p).digest == hash_bytes(b"contents")


def test_hash_many_files_returns_sorted(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    results = hash_many_files([b, a])
    assert [r.path for r in results] == [a, b]
    assert all(isinstance(r, FileHash) for r in results)


def test_hash_many_files_empty():
    assert hash_many_files([]) == []
