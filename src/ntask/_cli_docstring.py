from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ParsedDoc:
    summary: str = ""
    args: dict[str, str] = field(default_factory=dict)


_ARG_LINE = re.compile(r"^\s*(\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)$")


def parse_docstring(doc: str | None) -> ParsedDoc:
    if not doc:
        return ParsedDoc()
    doc = inspect.cleandoc(doc)
    lines = doc.splitlines()
    summary = lines[0] if lines else ""

    args: dict[str, str] = {}
    in_args = False
    current_name: str | None = None
    current_parts: list[str] = []

    def _flush() -> None:
        nonlocal current_name, current_parts
        if current_name is not None:
            args[current_name] = " ".join(p.strip() for p in current_parts).strip()
        current_name = None
        current_parts = []

    for line in lines[1:]:
        stripped = line.strip()
        if not in_args:
            if stripped.lower() in {"args:", "arguments:", "parameters:"}:
                in_args = True
            continue
        if not stripped:
            continue
        m = _ARG_LINE.match(line)
        if m and not line.startswith(" " * 8):  # new arg entry
            _flush()
            current_name = m.group(1)
            current_parts = [m.group(2)]
        elif current_name is not None:
            current_parts.append(stripped)
        else:
            in_args = False
    _flush()

    return ParsedDoc(summary=summary, args=args)
