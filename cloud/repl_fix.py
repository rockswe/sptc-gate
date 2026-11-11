"""Make rlms 0.1.3's LocalREPL safe to run as several threads in one process.

The campaign's runner runs concurrent tasks as threads of one process (a
ThreadPoolExecutor in benchmark/oolong_campaign/runner.py, run_unit), and each task gets
its own LocalREPL. Two LocalREPL helpers change process-wide state under a per-instance
lock (rlm/environments/local_repl.py):

- _capture_output swaps sys.stdout and sys.stderr. With two REPLs executing at once, a
  task's printed output can land in the other task's buffer or be lost, and a stale buffer
  can stay installed as sys.stdout. The root model reads that output in its next turn.
- _temp_cwd does os.chdir into the REPL's temp dir and back. Interleaved, a thread can
  restore a working directory that another task's cleanup() has already removed, and from
  then on every os.getcwd() fails, so the next LocalREPL dies with FileNotFoundError in
  __init__.

apply() routes each thread's output to its own buffer and leaves the working directory
alone: what one REPL running alone would see. Context files load by absolute path, so
nothing in rlms needs the chdir. Model-written code that writes relative paths now writes
to the process's working directory instead of a per-REPL temp dir.
"""

from __future__ import annotations

import io
import sys
import threading
from contextlib import contextmanager

from rlm.environments.local_repl import LocalREPL

_install_lock = threading.Lock()


class ThreadStream(io.TextIOBase):
    """A process-wide text stream that writes to this thread's capture buffer, if any."""

    def __init__(self, base) -> None:
        super().__init__()
        self.base = base
        self._tl = threading.local()

    def _target(self):
        return getattr(self._tl, "buf", None) or self.base

    def swap(self, buf):
        prev = getattr(self._tl, "buf", None)
        self._tl.buf = buf
        return prev

    def write(self, s: str) -> int:
        return self._target().write(s)

    def flush(self) -> None:
        self._target().flush()

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return self.base.fileno()

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self.base, "encoding", "utf-8")


def _streams() -> tuple[ThreadStream, ThreadStream]:
    """The installed routers (installed lazily, so a later swap of sys.stdout, as pytest's
    capture does, is wrapped again rather than bypassed)."""
    with _install_lock:
        if not isinstance(sys.stdout, ThreadStream):
            sys.stdout = ThreadStream(sys.stdout)
        if not isinstance(sys.stderr, ThreadStream):
            sys.stderr = ThreadStream(sys.stderr)
        return sys.stdout, sys.stderr


@contextmanager
def _capture_output(self):
    with self._lock:
        out, err = _streams()
        out_buf, err_buf = io.StringIO(), io.StringIO()
        prev_out, prev_err = out.swap(out_buf), err.swap(err_buf)
        try:
            yield out_buf, err_buf
        finally:
            out.swap(prev_out)
            err.swap(prev_err)


@contextmanager
def _temp_cwd(self):
    yield


ORIGINAL = {"_capture_output": LocalREPL._capture_output, "_temp_cwd": LocalREPL._temp_cwd}


def apply() -> None:
    LocalREPL._capture_output = _capture_output
    LocalREPL._temp_cwd = _temp_cwd


def revert() -> None:
    for k, v in ORIGINAL.items():
        setattr(LocalREPL, k, v)


def applied() -> bool:
    return LocalREPL._capture_output is _capture_output
