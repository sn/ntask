from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import Any

from .hash import hash_bytes


def _strip_docstring(tree: ast.AST) -> None:
    """Remove docstring nodes from functions/classes/modules in-place."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Module)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:]


def hash_task_body_source(source: str) -> str:
    """Hash source code structurally, ignoring docstrings/comments/whitespace."""
    tree = ast.parse(textwrap.dedent(source))
    _strip_docstring(tree)
    dumped = ast.dump(tree, annotate_fields=False, include_attributes=False)
    return hash_bytes(dumped.encode())


def hash_task_body(func: Callable[..., Any]) -> str:
    """Structural hash of a function's source. Stable under doc/whitespace/comment noise."""
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return hash_bytes(f"<no-source:{func.__qualname__}>".encode())
    return hash_task_body_source(source)
