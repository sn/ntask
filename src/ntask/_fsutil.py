"""Small filesystem helpers shared by the local store and remote backends."""
from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a uniquely-named temp file + ``os.replace``.

    Readers never observe a half-written file, and concurrent writers of the
    same path (two ntask processes, a shared remote dir) can't trample each
    other's temp file - last rename wins. The temp file is removed if the
    write or rename fails.
    """
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
