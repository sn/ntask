from __future__ import annotations

import argparse
import enum
import inspect
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from ._cli_docstring import parse_docstring


def _is_literal(hint: Any) -> bool:
    return get_origin(hint) is typing.Literal


def _coerce_path(v: str) -> Path:
    return Path(v).expanduser()


def build_parser(task_fqn: str, fn: Callable[..., Any]) -> argparse.ArgumentParser:
    sig = inspect.signature(fn)
    hints = get_type_hints(fn, include_extras=False)
    doc = parse_docstring(fn.__doc__)
    parser = argparse.ArgumentParser(
        prog=f"ntask {task_fqn}",
        description=doc.summary,
    )
    for name, param in sig.parameters.items():
        hint = hints.get(name, str)
        help_text = doc.args.get(name, None)
        required = param.default is inspect.Parameter.empty
        kwargs: dict[str, Any] = {}
        if help_text:
            kwargs["help"] = help_text

        if hint is bool:
            if required or param.default is False:
                parser.add_argument(f"--{name}", action="store_true", default=False, **kwargs)
            else:
                parser.add_argument(f"--no-{name}", dest=name, action="store_false",
                                    default=True, **kwargs)
            continue

        if _is_literal(hint):
            choices = list(get_args(hint))
            if required:
                parser.add_argument(name, choices=choices, **kwargs)
            else:
                parser.add_argument(f"--{name}", choices=choices,
                                    default=param.default, **kwargs)
            continue

        if isinstance(hint, type) and issubclass(hint, enum.Enum):
            choices = [m.value for m in hint]
            def _mk(hint_cls: type) -> Callable[[str], Any]:
                def _conv(v: str, _cls: type = hint_cls) -> Any:
                    return _cls(v)
                return _conv
            if required:
                parser.add_argument(name, choices=choices, type=_mk(hint), **kwargs)
            else:
                parser.add_argument(f"--{name}", choices=choices, type=_mk(hint),
                                    default=param.default, **kwargs)
            continue

        if get_origin(hint) is list:
            inner = (get_args(hint) or (str,))[0]
            typ = _coerce_path if inner is Path else inner
            if required:
                parser.add_argument(name, nargs="*", type=typ, **kwargs)
            else:
                parser.add_argument(f"--{name}", nargs="*", type=typ,
                                    default=param.default, **kwargs)
            continue

        if hint is Path:
            if required:
                parser.add_argument(name, type=_coerce_path, **kwargs)
            else:
                parser.add_argument(f"--{name}", type=_coerce_path,
                                    default=param.default, **kwargs)
            continue

        typ = hint if callable(hint) else str
        if required:
            parser.add_argument(name, type=typ, **kwargs)
        else:
            parser.add_argument(f"--{name}", type=typ, default=param.default, **kwargs)

    return parser


def parse_task_args(task_fqn: str, fn: Callable[..., Any], argv: list[str]) -> dict[str, Any]:
    parser = build_parser(task_fqn, fn)
    ns = parser.parse_args(argv)
    return vars(ns)
