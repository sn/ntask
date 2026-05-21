from __future__ import annotations

import sys

from rich.console import Console

from .._cache.diff import MissReport


class RichRenderer:
    def __init__(self, *, use_color: bool = True, verbose: bool = False, quiet: bool = False):
        self.console = Console(
            no_color=not use_color,
            force_terminal=sys.stdout.isatty(),
        )
        self.verbose = verbose
        self.quiet = quiet
        self._total: int = 0
        self._done: int = 0

    def set_total(self, total: int) -> None:
        self._total = total
        self._done = 0

    def _progress_prefix(self, next_fqn: str) -> str:
        if self._total <= 1:
            return ""
        return f"[dim][{self._done}/{self._total} done; next: {next_fqn}][/dim] "

    def on_running(self, fqn: str, *, cmd: str | None) -> None:
        suffix = f" [dim]:: {cmd}[/dim]" if cmd else ""
        self.console.print(
            f"{self._progress_prefix(fqn)}[cyan]⠋ {fqn}[/cyan]{suffix}"
        )

    def on_ok(self, fqn: str, *, duration: float) -> None:
        self._done += 1
        self.console.print(f"[green]+[/green] {fqn} [dim]({duration:.2f}s)[/dim]")

    def on_cached(self, fqn: str, *, key: str, source: str = "local") -> None:
        self._done += 1
        if self.quiet:
            return
        suffix = " [remote]" if source == "remote" else ""
        self.console.print(f"[dim]◦ {fqn} cached ({key[:8]}){suffix}[/dim]")

    def on_miss_reason(self, fqn: str, *, report: MissReport) -> None:
        self.console.print(
            f"[yellow]x[/yellow] {fqn}: cache miss ([italic]{report.summary()}[/italic])"
        )

    def on_failed(self, fqn: str, *, error: BaseException, tail_lines: list[str]) -> None:
        self._done += 1
        self.console.rule(f"[red]FAILED[/red] {fqn}")
        self.console.print(f"[red]{error}[/red]")
        for line in tail_lines[-20:]:
            self.console.print(f"    {line}")

    def summary(
        self,
        *,
        ran: int,
        cached: int,
        failed: int,
        skipped: int,
        failed_fqns: tuple[str, ...] = (),
    ) -> None:
        parts = [f"[green]{ran}[/green] ran", f"[dim]{cached} cached[/dim]"]
        if failed:
            parts.append(f"[red]{failed} failed[/red]")
        if skipped:
            parts.append(f"[yellow]{skipped} skipped[/yellow]")
        self.console.print("  ".join(parts))
        if failed_fqns:
            self.console.print(
                "[red]failed tasks:[/red] " + ", ".join(failed_fqns)
            )
