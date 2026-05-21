from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from ._depends import scan_static_depends
from ._errors import CycleError
from ._registry import Registry


@dataclass(frozen=True, slots=True)
class Graph:
    nodes: list[str]
    edges: list[tuple[str, str]]  # (from, to): from must run before to

    def direct_deps(self, node: str) -> list[str]:
        return [a for (a, b) in self.edges if b == node]

    def direct_dependents(self, node: str) -> list[str]:
        return [b for (a, b) in self.edges if a == node]

    def reachable_from(self, targets: list[str]) -> Graph:
        seen: set[str] = set()
        stack = list(targets)
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            for a in self.direct_deps(n):
                if a not in seen:
                    stack.append(a)
        nodes = [n for n in self.nodes if n in seen]
        edges = [(a, b) for (a, b) in self.edges if a in seen and b in seen]
        return Graph(nodes=nodes, edges=edges)


def toposort(g: Graph) -> list[str]:
    """Kahn's algorithm. Stable - ties break by insertion order."""
    indeg: dict[str, int] = dict.fromkeys(g.nodes, 0)
    adj: dict[str, list[str]] = defaultdict(list)
    for (a, b) in g.edges:
        indeg[b] += 1
        adj[a].append(b)

    ready: deque[str] = deque(n for n in g.nodes if indeg[n] == 0)
    result: list[str] = []
    while ready:
        n = ready.popleft()
        result.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    if len(result) != len(g.nodes):
        remaining = [n for n in g.nodes if n not in result]
        cycle = _find_cycle(g, remaining)
        raise CycleError(cycle)
    return result


def _find_cycle(g: Graph, candidates: list[str]) -> list[str]:
    adj: dict[str, list[str]] = defaultdict(list)
    for (a, b) in g.edges:
        adj[a].append(b)
    visited: dict[str, int] = {}  # 0=unvisited, 1=on stack, 2=done
    stack: list[str] = []

    def dfs(n: str) -> list[str] | None:
        visited[n] = 1
        stack.append(n)
        for m in adj.get(n, []):
            state = visited.get(m, 0)
            if state == 1:
                i = stack.index(m)
                return [*stack[i:], m]
            if state == 0:
                result = dfs(m)
                if result is not None:
                    return result
        visited[n] = 2
        stack.pop()
        return None

    for start in candidates:
        if visited.get(start, 0) == 0:
            c = dfs(start)
            if c is not None:
                return c
    return candidates  # fallback - shouldn't happen


def _resolve_ref(ref: Any, reg: Registry) -> str | None:
    if isinstance(ref, str):
        return ref if reg.try_get(ref) else None
    fqn: str | None = getattr(ref, "__ntask_task__", None)
    if fqn is not None:
        return fqn
    for t in reg.all():
        if t.func is ref:
            return t.fqn
    return None


def build_graph(reg: Registry) -> Graph:
    from ._task import _LazyDeps

    nodes = [t.fqn for t in reg.all()]
    edges: list[tuple[str, str]] = []
    for t in reg.all():
        for dep in t.deps:
            # Expand lazy-deps callable (``deps=lambda: [a, b]``).
            refs = dep.resolve() if isinstance(dep, _LazyDeps) else (dep,)
            for ref in refs:
                src = _resolve_ref(ref, reg)
                if src is None:
                    continue
                edges.append((src, t.fqn))
        static = scan_static_depends(t.func)
        if isinstance(static, list):
            for name in static:
                if reg.try_get(name):
                    edges.append((name, t.fqn))
    return Graph(nodes=nodes, edges=edges)
