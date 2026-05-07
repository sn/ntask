from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, Literal

_current_depends_handler: ContextVar[Callable[[tuple[Any, ...]], Any] | None] = ContextVar(
    "_current_depends_handler", default=None
)


def depends(*tasks: Any) -> None:
    """Runtime-dynamic dependency sentinel.

    Inside a running task, blocks until ``tasks`` are complete. Outside a task,
    it's a no-op (useful during import or testing).
    """
    handler = _current_depends_handler.get()
    if handler is None:
        return
    handler(tasks)


class _DependsVisitor(ast.NodeVisitor):
    """AST visitor that collects ``depends(...)`` calls in a function's direct body.

    Traversal stops at nested ``FunctionDef``, ``AsyncFunctionDef``, ``Lambda``,
    and ``ClassDef`` nodes so that ``depends`` calls inside those scopes are not
    mistakenly attributed to the outer task function.
    """

    def __init__(self) -> None:
        self.names: list[str] = []
        self.dynamic: bool = False

    def _handle_call(self, node: ast.Call) -> None:
        func_node = node.func
        called = (
            isinstance(func_node, ast.Name) and func_node.id == "depends"
        ) or (
            isinstance(func_node, ast.Attribute) and func_node.attr == "depends"
        )
        if not called:
            return
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                self.dynamic = True
            elif isinstance(arg, ast.Name):
                self.names.append(arg.id)
            elif isinstance(arg, ast.Attribute):
                parts: list[str] = []
                cur: ast.expr = arg
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                    self.names.append(".".join(reversed(parts)))
                else:
                    self.dynamic = True
            else:
                self.dynamic = True

    def visit_Call(self, node: ast.Call) -> None:
        self._handle_call(node)
        self.generic_visit(node)

    # Stop traversal into nested scopes - depends() calls inside them must
    # not be attributed to the enclosing task function.
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass


def scan_static_depends(func: Callable[..., Any]) -> list[str] | Literal["dynamic"]:
    """Return the names of tasks referenced by static ``depends(a, b)`` calls in ``func``.

    If any ``depends(...)`` call uses starred/unpacked/non-Name arguments,
    returns the string ``"dynamic"``.

    Only ``depends`` calls in the function's direct body are considered; calls
    inside nested functions, lambdas, or class bodies are ignored.
    """
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return []
    source = inspect.cleandoc("\n" + source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    # Locate the top-level FunctionDef / AsyncFunctionDef in the parsed module.
    top_fn: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_fn = stmt
            break
    if top_fn is None:
        return []

    visitor = _DependsVisitor()
    for stmt in top_fn.body:
        visitor.visit(stmt)

    if visitor.dynamic:
        return "dynamic"
    return visitor.names
