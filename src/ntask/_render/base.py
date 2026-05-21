from __future__ import annotations

from typing import Protocol

from .._cache.diff import MissReport


class Renderer(Protocol):
    def on_running(self, fqn: str, *, cmd: str | None) -> None: ...
    def on_ok(self, fqn: str, *, duration: float) -> None: ...
    def on_cached(self, fqn: str, *, key: str, source: str = "local") -> None: ...
    def on_miss_reason(self, fqn: str, *, report: MissReport) -> None: ...
    def on_failed(self, fqn: str, *, error: BaseException, tail_lines: list[str]) -> None: ...
    def summary(
        self,
        *,
        ran: int,
        cached: int,
        failed: int,
        skipped: int,
        failed_fqns: tuple[str, ...] = (),
    ) -> None: ...
