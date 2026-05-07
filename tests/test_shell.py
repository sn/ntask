import sys
from pathlib import Path

import pytest

from ntask import shell
from ntask._errors import ShellError
from ntask._shell import ShellResult, _current_line_prefix, _current_log_file


def test_shell_runs_string_command_success(capfd):
    shell(f'{sys.executable} -c "print(\'hello\')"')
    out, _ = capfd.readouterr()
    assert "hello" in out


def test_shell_raises_on_nonzero_exit():
    with pytest.raises(ShellError) as exc_info:
        shell(f'{sys.executable} -c "import sys; sys.exit(2)"')
    assert exc_info.value.returncode == 2


def test_shell_check_false_does_not_raise():
    result = shell(
        f'{sys.executable} -c "import sys; sys.exit(3)"', check=False
    )
    assert isinstance(result, ShellResult)
    assert result.returncode == 3


def test_shell_capture_returns_stdout():
    result = shell(
        [sys.executable, "-c", "print('captured')"], capture=True
    )
    assert result.returncode == 0
    assert "captured" in result.stdout


def test_shell_list_form_bypasses_shell():
    result = shell(
        [sys.executable, "-c", "print('$HOME')"], capture=True
    )
    assert "$HOME" in result.stdout


def test_shell_prefix_mode_prepends_fqn_to_lines(capfd):
    token = _current_line_prefix.set("build")
    try:
        shell([sys.executable, "-c", "print('hi')"])
    finally:
        _current_line_prefix.reset(token)
    out, _ = capfd.readouterr()
    assert "[build] hi" in out


def test_shell_prefix_mode_multiline_output(capfd):
    token = _current_line_prefix.set("test")
    try:
        shell([sys.executable, "-c",
               "import sys; [print(f'line {i}') for i in range(3)]"])
    finally:
        _current_line_prefix.reset(token)
    out, _ = capfd.readouterr()
    assert "[test] line 0" in out
    assert "[test] line 1" in out
    assert "[test] line 2" in out


def test_shell_prefix_mode_stderr_also_prefixed(capfd):
    token = _current_line_prefix.set("lint")
    try:
        shell([sys.executable, "-c",
               "import sys; print('err', file=sys.stderr)"])
    finally:
        _current_line_prefix.reset(token)
    _, err = capfd.readouterr()
    assert "[lint] err" in err


def test_shell_no_prefix_when_contextvar_unset(capfd):
    # Default path (no prefix set) must stream output raw - no brackets.
    shell([sys.executable, "-c", "print('raw')"])
    out, _ = capfd.readouterr()
    assert "raw" in out
    assert "[" not in out  # no prefix brackets appear


def test_shell_prefix_mode_stdin_is_dev_null():
    token = _current_line_prefix.set("x")
    try:
        result = shell(
            [sys.executable, "-c", "import sys; sys.exit(0 if sys.stdin.read() == '' else 1)"],
            capture=False, check=False,
        )
    finally:
        _current_line_prefix.reset(token)
    assert result is not None
    assert result.returncode == 0


def test_shell_prefix_mode_nonzero_exit_raises_shell_error():
    token = _current_line_prefix.set("build")
    try:
        with pytest.raises(ShellError) as exc_info:
            shell([sys.executable, "-c", "import sys; sys.exit(4)"])
    finally:
        _current_line_prefix.reset(token)
    assert exc_info.value.returncode == 4


def test_shell_log_file_captures_stdout(tmp_path: Path):
    log = tmp_path / "task.log"
    token = _current_log_file.set(log)
    try:
        shell([sys.executable, "-c", "print('hello-log')"])
    finally:
        _current_log_file.reset(token)
    content = log.read_bytes()
    assert b"hello-log" in content


def test_shell_log_file_captures_stderr(tmp_path: Path):
    log = tmp_path / "task.log"
    token = _current_log_file.set(log)
    try:
        shell([sys.executable, "-c",
               "import sys; print('err-log', file=sys.stderr)"])
    finally:
        _current_log_file.reset(token)
    assert b"err-log" in log.read_bytes()


def test_shell_log_file_appends_across_calls(tmp_path: Path):
    log = tmp_path / "task.log"
    token = _current_log_file.set(log)
    try:
        shell([sys.executable, "-c", "print('first')"])
        shell([sys.executable, "-c", "print('second')"])
    finally:
        _current_log_file.reset(token)
    content = log.read_bytes()
    assert b"first" in content
    assert b"second" in content


def test_shell_log_file_nonzero_exit_raises(tmp_path: Path):
    log = tmp_path / "task.log"
    token = _current_log_file.set(log)
    try:
        with pytest.raises(ShellError) as exc_info:
            shell([sys.executable, "-c", "import sys; sys.exit(3)"])
    finally:
        _current_log_file.reset(token)
    assert exc_info.value.returncode == 3


def test_shell_capture_true_takes_precedence_over_log_file(tmp_path: Path):
    log = tmp_path / "task.log"
    token = _current_log_file.set(log)
    try:
        result = shell(
            [sys.executable, "-c", "print('captured')"],
            capture=True,
        )
    finally:
        _current_log_file.reset(token)
    assert result is not None
    assert "captured" in result.stdout
    # Log file should NOT have been touched.
    assert not log.exists()
