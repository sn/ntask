from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from ._errors import ShellError

_current_line_prefix: ContextVar[str | None] = ContextVar(
    "_current_line_prefix", default=None
)

_current_log_file: ContextVar[Path | None] = ContextVar(
    "_current_log_file", default=None
)


@dataclass(frozen=True, slots=True)
class ShellResult:
    returncode: int
    stdout: str
    stderr: str
    duration: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _pump(stream: IO[str], sink: IO[str], tag: str) -> None:
    """Background thread: read lines from ``stream``, prefix and flush to ``sink``."""
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            if line.endswith("\n"):
                sink.write(f"{tag}{line}")
            else:
                sink.write(f"{tag}{line}\n")
            sink.flush()
    finally:
        stream.close()


def _run_prefixed(
    cmd: str | list[str],
    *,
    prefix: str,
    use_shell: bool,
    cwd: str | Path | None,
    env: dict[str, str] | None,
) -> int:
    """Run a command with stdout/stderr line-prefixed by task FQN.

    Uses subprocess.Popen with line-buffered text pipes and background
    threads to pump output. Works from any context (sync task or async task).
    """
    proc = subprocess.Popen(  # noqa: S603
        cmd,
        shell=use_shell,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        text=True,
    )
    tag = f"[{prefix}] "
    t_out = threading.Thread(
        target=_pump, args=(proc.stdout, sys.stdout, tag), daemon=True
    )
    t_err = threading.Thread(
        target=_pump, args=(proc.stderr, sys.stderr, tag), daemon=True
    )
    t_out.start()
    t_err.start()
    try:
        rc = proc.wait()
    except BaseException:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise
    finally:
        t_out.join(timeout=5)
        t_err.join(timeout=5)
    return rc


def _run_to_logfile(
    cmd: str | list[str],
    *,
    log_path: Path,
    use_shell: bool,
    cwd: str | Path | None,
    env: dict[str, str] | None,
) -> int:
    """Run cmd with stdout+stderr appended (raw bytes) to log_path."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            shell=use_shell,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def _copy(stream: IO[bytes]) -> None:
            try:
                for chunk in iter(lambda: stream.read(4096), b""):
                    log.write(chunk)
                    log.flush()
            finally:
                stream.close()

        t_out = threading.Thread(target=_copy, args=(proc.stdout,), daemon=True)
        t_err = threading.Thread(target=_copy, args=(proc.stderr,), daemon=True)
        t_out.start()
        t_err.start()
        try:
            rc = proc.wait()
        except BaseException:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise
        finally:
            t_out.join(timeout=5)
            t_err.join(timeout=5)
    return rc


def shell(
    cmd: str | list[str],
    *,
    check: bool = True,
    capture: bool = False,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> ShellResult | None:
    """Run a shell command.

    - String ``cmd`` runs via /bin/sh -c (or cmd.exe /c on Windows).
    - List ``cmd`` bypasses the shell (direct exec).
    - ``check=True`` (default) raises ShellError on non-zero exit.
    - ``capture=True`` returns a ShellResult; stdout/stderr are captured.
    - Default streams output live; returns None on success.
    - When invoked under parallel execution (the executor sets the
      ``_current_line_prefix`` context var), output is line-prefixed with
      the task FQN in square brackets. Otherwise (concurrency==1 or
      direct sync call), behavior is byte-identical to 0.2.0.
    """
    use_shell = isinstance(cmd, str)
    full_env = None if env is None else {**os.environ, **env}
    started = time.perf_counter()

    # Capture mode always uses subprocess.run - no prefix, no streaming.
    if capture:
        proc = subprocess.run(  # noqa: S603
            cmd, shell=use_shell, cwd=cwd, env=full_env,
            capture_output=True, text=True,
        )
        duration = time.perf_counter() - started
        result = ShellResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration=duration,
        )
        if check and proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            raise ShellError(proc.returncode, cmd)
        return result

    # Log-file mode - pipe stdout+stderr to a file (append), no terminal output.
    log_path = _current_log_file.get()
    if log_path is not None:
        rc = _run_to_logfile(
            cmd,
            log_path=log_path,
            use_shell=use_shell,
            cwd=cwd,
            env=full_env,
        )
        duration = time.perf_counter() - started
        if check and rc != 0:
            raise ShellError(rc, cmd)
        if not check:
            return ShellResult(
                returncode=rc, stdout="", stderr="", duration=duration,
            )
        return None

    # Streaming mode - check context var for prefix.
    prefix = _current_line_prefix.get()

    if prefix is not None:
        rc = _run_prefixed(
            cmd, prefix=prefix, use_shell=use_shell, cwd=cwd, env=full_env,
        )
        duration = time.perf_counter() - started
        if check and rc != 0:
            raise ShellError(rc, cmd)
        if not check:
            return ShellResult(
                returncode=rc, stdout="", stderr="", duration=duration,
            )
        return None

    # No prefix - current behavior (sync subprocess.run, inherited stdout/err).
    proc = subprocess.run(  # noqa: S603
        cmd, shell=use_shell, cwd=cwd, env=full_env, text=True,
    )
    duration = time.perf_counter() - started
    if check and proc.returncode != 0:
        raise ShellError(proc.returncode, cmd)
    if not check:
        return ShellResult(
            returncode=proc.returncode,
            stdout="", stderr="", duration=duration,
        )
    return None
