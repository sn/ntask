from __future__ import annotations

import time

from ._cache.diff import MissReport
from ._cache.store import CacheEntry
from ._task import Task


def _format_ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m}m {s}s ago"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m ago"


def _format_timestamp(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def render_why(
    *,
    task: Task,
    prior: CacheEntry | None,
    report: MissReport,
    current_key: str,
    use_color: bool = True,
) -> str:
    """Render the output of `ntask --why <task>` as a single string."""
    if task.cached_config is None:
        raise ValueError(f"Task {task.fqn!r} is not a cached task")

    if prior is None:
        return f"Task {task.fqn!r} has no cached entries. First run would execute.\n"

    lines: list[str] = []
    lines.append(f"Task: {task.fqn}")
    ago = _format_ago(time.time() - prior.completed_at)
    lines.append(f"Last cached: {_format_timestamp(prior.completed_at)} ({ago})")
    lines.append(f"Cache key: {prior.key[:8]}...")
    lines.append(f"Duration: {prior.duration:.2f}s")
    lines.append("")

    if report.is_hit:
        lines.append(f"If you ran `{task.fqn}` now:")
        lines.append("  \u2714 HIT \u2014 no changes")
        return "\n".join(lines) + "\n"

    n = len(report.items)
    plural = "change" if n == 1 else "changes"
    lines.append(f"If you ran `{task.fqn}` now:")
    lines.append(f"  \u2716 MISS \u2014 {n} {plural} since last cache")
    lines.append("")
    lines.append("Changes:")
    for item in report.items:
        short = _short_label(item.kind)
        detail = item.detail or "(no detail)"
        lines.append(f"  \u2022 {detail:<30} {short}")
    lines.append("")

    if prior.breakdown is not None:
        bd = prior.breakdown
        if bd.input_patterns:
            lines.append("Inputs:")
            patterns = ", ".join(bd.input_patterns)
            lines.append(f"  Declared globs: {patterns}")
            input_change_count = sum(
                1 for i in report.items if i.kind.startswith("input-")
            )
            lines.append(
                f"  Files matched: {len(bd.inputs)} "
                f"(content-hashed, {input_change_count} changed)"
            )
            lines.append("")

        if bd.env_values:
            lines.append("Environment:")
            max_name = max((len(k) for k in bd.env_values), default=0)
            for name in sorted(bd.env_values):
                val = bd.env_values[name]
                changed = any(
                    i.kind in ("env-changed", "env-added", "env-removed")
                    and i.detail.startswith(name)
                    for i in report.items
                )
                marker = "(changed)" if changed else "(unchanged)"
                lines.append(f"  {name.ljust(max_name)} = {val!r}   {marker}")
            lines.append("")

        if bd.upstream_keys_by_dep:
            lines.append("Upstream dependencies:")
            for dep in sorted(bd.upstream_keys_by_dep):
                dep_changed = any(
                    i.kind == "upstream-invalidated" and i.detail == dep
                    for i in report.items
                )
                state = "changed" if dep_changed else "unchanged"
                lines.append(f"  {dep} (cache key: {state})")

    return "\n".join(lines) + "\n"


def _short_label(kind: str) -> str:
    return {
        "input-modified": "modified",
        "input-added": "added",
        "input-removed": "removed",
        "env-changed": "changed",
        "env-added": "added",
        "env-removed": "removed",
        "body-changed": "body changed",
        "upstream-invalidated": "upstream invalidated",
        "python-changed": "python version changed",
        "platform-changed": "platform changed",
        "first-run": "first run",
    }.get(kind, kind)
