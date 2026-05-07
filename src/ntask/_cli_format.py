from __future__ import annotations

from collections import defaultdict
from io import StringIO
from typing import Any

from rich.console import Console
from rich.table import Table

from ._cli_docstring import parse_docstring
from ._dag import Graph
from ._registry import Registry

CACHED_MARK = "*"


def format_list(reg: Registry, *, use_color: bool = True) -> str:
    buf = StringIO()
    console = Console(
        file=buf,
        force_terminal=False,
        color_system="auto" if use_color else None,
        width=120,
    )
    grouped: dict[str | None, list[Any]] = defaultdict(list)
    for t in reg.all():
        grouped[t.group].append(t)

    if None in grouped:
        table = Table(title="Tasks", show_header=False)
        for t in sorted(grouped[None], key=lambda x: x.fqn):
            mark = CACHED_MARK if t.cached_config else " "
            summary = parse_docstring(t.func.__doc__).summary
            table.add_row(t.fqn, mark, summary)
        console.print(table)

    for name, tasks in sorted((k, v) for k, v in grouped.items() if k is not None):
        table = Table(title=name, show_header=False)
        for t in sorted(tasks, key=lambda x: x.fqn):
            mark = CACHED_MARK if t.cached_config else " "
            summary = parse_docstring(t.func.__doc__).summary
            table.add_row(t.fqn, mark, summary)
        console.print(table)

    return buf.getvalue()


def format_graph_ascii(g: Graph, *, target: str | None = None) -> str:
    nodes = g.reachable_from([target]).nodes if target else g.nodes
    lines: list[str] = []
    for n in nodes:
        deps = [a for a, b in g.edges if b == n]
        if deps:
            lines.append(f"{n}  ← {', '.join(deps)}")
        else:
            lines.append(n)
    return "\n".join(lines)


def format_graph_mermaid(g: Graph) -> str:
    lines = ["graph TD"]
    for n in g.nodes:
        lines.append(f"    {n}")
    for (a, b) in g.edges:
        lines.append(f"    {a} --> {b}")
    return "\n".join(lines)


def format_graph_dot(g: Graph) -> str:
    lines = ["digraph G {"]
    for n in g.nodes:
        lines.append(f'    "{n}";')
    for (a, b) in g.edges:
        lines.append(f'    "{a}" -> "{b}";')
    lines.append("}")
    return "\n".join(lines)
