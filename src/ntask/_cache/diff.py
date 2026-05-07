from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .key import CacheBreakdown, InputRecord

MissKind = Literal[
    "first-run",
    "input-modified", "input-added", "input-removed",
    "env-changed", "env-added", "env-removed",
    "body-changed",
    "upstream-invalidated",
    "python-changed", "platform-changed",
]


@dataclass(frozen=True, slots=True)
class MissItem:
    kind: MissKind
    detail: str


@dataclass(frozen=True, slots=True)
class MissReport:
    items: tuple[MissItem, ...]

    @property
    def is_hit(self) -> bool:
        return not self.items

    def summary(self) -> str:
        if not self.items:
            return "no changes"
        first = self.items[0]
        rest = len(self.items) - 1
        label = f"{first.kind}: {first.detail}" if first.detail else first.kind
        return f"{label}" + (f" (+{rest} more)" if rest else "")


def _diff_inputs(
    current: tuple[InputRecord, ...],
    prior: tuple[InputRecord, ...],
) -> list[MissItem]:
    prior_by_path = {r.path: r for r in prior}
    current_by_path = {r.path: r for r in current}
    items: list[MissItem] = []

    all_paths = sorted(set(prior_by_path) | set(current_by_path))
    for path in all_paths:
        p = prior_by_path.get(path)
        c = current_by_path.get(path)
        if p is None and c is not None:
            items.append(MissItem(kind="input-added", detail=path))
        elif c is None and p is not None:
            items.append(MissItem(kind="input-removed", detail=path))
        elif p is not None and c is not None:
            if p.digest != c.digest or p.mode != c.mode:
                items.append(MissItem(kind="input-modified", detail=path))
    return items


def _diff_env(
    current: dict[str, str],
    prior: dict[str, str],
) -> list[MissItem]:
    items: list[MissItem] = []
    all_keys = sorted(set(prior) | set(current))
    for name in all_keys:
        if name in current and name not in prior:
            items.append(MissItem(kind="env-added", detail=name))
        elif name in prior and name not in current:
            items.append(MissItem(kind="env-removed", detail=name))
        elif current[name] != prior[name]:
            items.append(MissItem(
                kind="env-changed",
                detail=f"{name}: {prior[name]!r} → {current[name]!r}",
            ))
    return items


def _diff_upstream(
    current: dict[str, str],
    prior: dict[str, str],
) -> list[MissItem]:
    items: list[MissItem] = []
    all_deps = sorted(set(prior) | set(current))
    for dep in all_deps:
        if prior.get(dep) != current.get(dep):
            items.append(MissItem(kind="upstream-invalidated", detail=dep))
    return items


def diff_cache_state(
    current: CacheBreakdown,
    prior: CacheBreakdown | None,
) -> MissReport:
    """Compute a MissReport describing what changed between prior and current.

    Items are emitted in priority order:
        1. input-* (alphabetical by path)
        2. env-* (alphabetical by name)
        3. body-changed
        4. upstream-invalidated (alphabetical by dep name)
        5. python-changed, platform-changed
    """
    if prior is None:
        return MissReport(items=(MissItem(kind="first-run", detail=""),))

    items: list[MissItem] = []
    items.extend(_diff_inputs(current.inputs, prior.inputs))
    items.extend(_diff_env(current.env_values, prior.env_values))
    if current.task_body_hash != prior.task_body_hash:
        items.append(MissItem(kind="body-changed", detail=""))
    items.extend(_diff_upstream(current.upstream_keys_by_dep, prior.upstream_keys_by_dep))
    if current.python_version != prior.python_version:
        items.append(MissItem(
            kind="python-changed",
            detail=f"{prior.python_version!r} → {current.python_version!r}",
        ))
    if current.platform_tag != prior.platform_tag:
        items.append(MissItem(
            kind="platform-changed",
            detail=f"{prior.platform_tag!r} → {current.platform_tag!r}",
        ))

    return MissReport(items=tuple(items))
