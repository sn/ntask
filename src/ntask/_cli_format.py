from __future__ import annotations

import enum
import inspect
import typing
from collections import defaultdict
from collections.abc import Callable
from io import StringIO
from typing import Any, get_args, get_origin, get_type_hints

from rich.console import Console
from rich.table import Table

from ._cli_docstring import parse_docstring
from ._dag import Graph
from ._registry import Registry

CACHED_MARK = "*"
_MAX_SIGNATURE_LEN = 40


def format_task_signature(fn: Callable[..., Any]) -> str:
    """Render a one-line CLI flag summary for a task body.

    Format rules:
      - required positional (no default): ``<name: type>``
      - optional with default:            ``[--name=value]``
      - bool default False:               ``[--name]``
      - bool default True:                ``[--no-name]``

    The whole string is truncated to a fixed width with ``...`` so the
    `--list` table stays compact in normal terminals.
    """
    try:
        sig = inspect.signature(fn)
        hints = get_type_hints(fn, include_extras=False)
    except (TypeError, ValueError, NameError):
        return ""

    parts: list[str] = []
    for name, param in sig.parameters.items():
        hint = hints.get(name, str)
        required = param.default is inspect.Parameter.empty
        if hint is bool:
            if required or param.default is False:
                parts.append(f"[--{name}]")
            else:
                parts.append(f"[--no-{name}]")
            continue
        if required:
            parts.append(f"<{name}: {_short_type(hint)}>")
        else:
            parts.append(f"[--{name}={_short_repr(param.default)}]")

    rendered = " ".join(parts)
    if len(rendered) > _MAX_SIGNATURE_LEN:
        rendered = rendered[: _MAX_SIGNATURE_LEN - 3].rstrip() + "..."
    return rendered


def _short_type(hint: Any) -> str:
    if get_origin(hint) is typing.Literal:
        return "|".join(repr(v) for v in get_args(hint))
    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return hint.__name__
    name = getattr(hint, "__name__", None)
    if name:
        return str(name)
    return str(hint)


def _short_repr(value: Any) -> str:
    if isinstance(value, str):
        rendered = value
    else:
        rendered = repr(value)
    if len(rendered) > 16:
        rendered = rendered[:13] + "..."
    return rendered


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
            sig = format_task_signature(t.func)
            table.add_row(t.fqn, mark, sig, summary)
        console.print(table)

    for name, tasks in sorted((k, v) for k, v in grouped.items() if k is not None):
        table = Table(title=name, show_header=False)
        for t in sorted(tasks, key=lambda x: x.fqn):
            mark = CACHED_MARK if t.cached_config else " "
            summary = parse_docstring(t.func.__doc__).summary
            sig = format_task_signature(t.func)
            table.add_row(t.fqn, mark, sig, summary)
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
