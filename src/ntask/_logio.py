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


# ---------------------------------------------------------------------------
# logging.StreamHandler hijack
#
# Replacing sys.stdout / sys.stderr only redirects code that resolves those
# attributes at write-time. The stdlib ``logging`` module captures the
# stream object at handler-construction time (``StreamHandler()`` defaults
# to ``sys.stderr`` at that instant), so a handler set up before ntask got
# involved holds a reference to the original — bypassing the tee entirely.
#
# Textual's Linux driver writes to ``sys.__stderr__`` (the *immutable*
# original) for the same reason, which means stdlib-logging output ends up
# fighting Textual for the same physical stream and corrupting the live
# DAG view.
#
# `hijack_logging_streams` walks every installed StreamHandler, and for any
# whose ``.stream`` is the originals captured before the tee was installed,
# rebinds it to the tee. `restore_logging_streams` puts the originals back.
# ---------------------------------------------------------------------------

def hijack_logging_streams(
    *, tee_stdout: Any, tee_stderr: Any,
) -> list[tuple[Any, Any]]:
    """Redirect any logging.StreamHandler whose stream is the immutable
    original sys.__stdout__ / sys.__stderr__ onto the given tees.

    Returns a list of ``(handler, original_stream)`` for restoration. File-
    backed handlers are skipped — they're already going to a file by design.
    """
    import logging
    import sys

    originals = {
        id(sys.__stdout__): tee_stdout,
        id(sys.__stderr__): tee_stderr,
    }
    saved: list[tuple[Any, Any]] = []
    # Snapshot the logger set up front; user code may add loggers
    # mid-run and we don't want to retroactively hijack those.
    loggers: list[logging.Logger] = [logging.getLogger()]
    for name in list(logging.Logger.manager.loggerDict.keys()):
        item = logging.Logger.manager.loggerDict[name]
        if isinstance(item, logging.Logger):
            loggers.append(item)

    for logger in loggers:
        for handler in list(logger.handlers):
            # FileHandler subclasses StreamHandler but its stream is a file
            # already — don't redirect it onto our tee.
            if not isinstance(handler, logging.StreamHandler):
                continue
            if isinstance(handler, logging.FileHandler):
                continue
            stream = getattr(handler, "stream", None)
            replacement = originals.get(id(stream))
            if replacement is None:
                continue
            try:
                handler.acquire()
                try:
                    saved.append((handler, stream))
                    handler.stream = replacement
                finally:
                    handler.release()
            except Exception:  # noqa: S112 — hijack must never break a run
                continue
    return saved


def restore_logging_streams(saved: list[tuple[Any, Any]]) -> None:
    """Undo a previous `hijack_logging_streams` call. Safe to call with
    an empty list; safe even if the user removed a handler in the interim.
    """
    for handler, original in saved:
        try:
            handler.acquire()
            try:
                handler.stream = original
            finally:
                handler.release()
        except Exception:  # noqa: S112 — restore must never break a run
            continue
