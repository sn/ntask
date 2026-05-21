"""Per-task stdout/stderr capture.

The executor installs a `_LogTee` proxy at `sys.stdout` and `sys.stderr` for
the duration of a run. Each write is forwarded to the underlying stream and,
when a per-task log file is set in the current async context via
`_current_log_file`, appended to that file as well.

This is what makes raw ``print()`` output from inside a task body recoverable
from disk after the run — including under the TUI, where Textual would
otherwise be the only consumer of the write.

Under the TUI, the underlying write is suppressed (`_current_silent_capture`
is True). Textual owns ``sys.stdout`` but not ``sys.stderr`` — a Python
``logging`` handler writing to stderr would otherwise spill JSON / formatted
log lines straight onto the terminal, corrupting the live DAG view. The
per-task log file remains the authoritative record.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._shell import _current_log_file, _current_silent_capture


class _LogTee:
    """Wraps a text stream so writes are mirrored to a per-task log file.

    The log file is resolved from the ``_current_log_file`` ContextVar on
    every write, so concurrent anyio tasks each get routed to their own
    file without sharing state through the proxy.

    When ``_current_silent_capture`` is True the underlying stream is NOT
    written to — the log file becomes the only sink. The executor flips
    that flag for TUI runs so library code that logs to stderr can't
    bleed through the renderer.
    """

    __slots__ = ("_underlying",)

    def __init__(self, underlying: Any) -> None:
        self._underlying = underlying

    def write(self, s: str) -> int:
        silent = _current_silent_capture.get()
        if silent:
            # TUI mode — keep the terminal clean and let the log file be
            # the record. We still return a credible byte count so the
            # caller (logging handlers, print, etc.) sees a successful
            # write.
            n = len(s)
        else:
            try:
                written = self._underlying.write(s)
                n = int(written) if written is not None else len(s)
            except Exception:
                # Capture must never break a task body; fall back to the
                # nominal byte count and continue to the log file.
                n = len(s)
        log_path = _current_log_file.get()
        if log_path is not None and s:
            _append_to_log(log_path, s)
        return n

    def writelines(self, lines: Any) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        if _current_silent_capture.get():
            # Nothing was written to the underlying stream; no flush needed.
            return
        try:
            self._underlying.flush()
        except Exception:  # noqa: S110 — capture must never break a task
            pass

    def isatty(self) -> bool:
        try:
            return bool(self._underlying.isatty())
        except Exception:
            return False

    def fileno(self) -> int:
        # Some libraries call fileno() on sys.stdout; delegate so they don't
        # blow up. If the underlying stream doesn't expose one we raise the
        # same OSError it would have.
        n: int = self._underlying.fileno()
        return n

    def __getattr__(self, name: str) -> Any:
        # Proxy any other attribute (encoding, errors, buffer, ...).
        return getattr(self._underlying, name)


def _append_to_log(path: Path, s: str) -> None:
    """Open-append-close write so concurrent tasks writing to different
    files don't share a single handle. Errors are swallowed — log capture
    must never break a task."""
    try:
        with path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(s)
    except OSError:
        pass
