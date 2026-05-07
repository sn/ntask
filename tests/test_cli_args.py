from enum import StrEnum
from pathlib import Path
from typing import Literal

import pytest

from ntask._cli_args import build_parser, parse_task_args


def test_positional_required_arg():
    def fn(version: str): pass
    parser = build_parser("release", fn)
    ns = parser.parse_args(["1.2.0"])
    assert ns.version == "1.2.0"


def test_missing_positional_raises():
    def fn(version: str): pass
    parser = build_parser("release", fn)
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_optional_with_default_becomes_flag():
    def fn(pattern: str = ""): pass
    parser = build_parser("test", fn)
    ns = parser.parse_args(["--pattern=auth"])
    assert ns.pattern == "auth"


def test_bool_false_default_becomes_store_true():
    def fn(verbose: bool = False): pass
    parser = build_parser("test", fn)
    assert parser.parse_args([]).verbose is False
    assert parser.parse_args(["--verbose"]).verbose is True


def test_bool_true_default_becomes_no_x_flag():
    def fn(debug: bool = True): pass
    parser = build_parser("test", fn)
    assert parser.parse_args([]).debug is True
    assert parser.parse_args(["--no-debug"]).debug is False


def test_literal_becomes_choice():
    def fn(env: Literal["staging", "prod"]): pass
    parser = build_parser("deploy", fn)
    assert parser.parse_args(["staging"]).env == "staging"
    with pytest.raises(SystemExit):
        parser.parse_args(["qa"])


def test_int_coercion():
    def fn(count: int = 5): pass
    parser = build_parser("x", fn)
    assert parser.parse_args(["--count=7"]).count == 7


def test_path_coercion():
    def fn(p: Path): pass
    parser = build_parser("x", fn)
    ns = parser.parse_args(["~/foo"])
    assert isinstance(ns.p, Path)


def test_enum_choice():
    class Kind(StrEnum):
        A = "a"
        B = "b"
    def fn(kind: Kind): pass
    parser = build_parser("x", fn)
    assert parser.parse_args(["a"]).kind is Kind.A


def test_parse_task_args_returns_kwargs_dict():
    def fn(version: str, verbose: bool = False): pass
    kwargs = parse_task_args("release", fn, ["1.2.0", "--verbose"])
    assert kwargs == {"version": "1.2.0", "verbose": True}
