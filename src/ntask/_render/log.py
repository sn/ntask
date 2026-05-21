from __future__ import annotations

import sys
from typing import TextIO

from .._cache.diff import MissReport


class LogRenderer:
    def __init__(self, *, stream: TextIO = sys.stdout, use_color: bool = True):
        self.stream = stream
        self.use_color = use_color

    def _p(self, s: str) -> None:
        self.stream.write(s + "\n")
        self.stream.flush()

    def on_running(self, fqn: str, *, cmd: str | None) -> None:
        suffix = f" :: {cmd}" if cmd else ""
        self._p(f"running {fqn}{suffix}")

    def on_ok(self, fqn: str, *, duration: float) -> None:
        self._p(f"+ {fqn} ({duration:.2f}s)")

    def on_cached(self, fqn: str, *, key: str, source: str = "local") -> None:
        suffix = " [remote]" if source == "remote" else ""
        self._p(f"◦ {fqn} cached ({key[:8]}){suffix}")

    def on_miss_reason(self, fqn: str, *, report: MissReport) -> None:
        self._p(f"x {fqn}: cache miss ({report.summary()})")

    def on_failed(self, fqn: str, *, error: BaseException, tail_lines: list[str]) -> None:
        self._p(f"x {fqn} FAILED: {error}")
        for line in tail_lines[-20:]:
            self._p(f"    {line}")

    def summary(
        self,
        *,
        ran: int,
        cached: int,
        failed: int,
        skipped: int,
        failed_fqns: tuple[str, ...] = (),
    ) -> None:
        self._p(f"done. ran={ran} cached={cached} failed={failed} skipped={skipped}")
        if failed_fqns:
            self._p(f"failed tasks: {', '.join(failed_fqns)}")
