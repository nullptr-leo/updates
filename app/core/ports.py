"""Process port: core defines the contract, Qt supplies the implementation.

External installers are the only things still executed as child processes.
They are asynchronous from the UI's point of view, bounded by a timeout and
killable on cancellation — unlike the legacy ``subprocess.call(...)`` which
blocked forever with no hidden-window flag.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
from typing import Callable, Protocol, Sequence

from .cancellation import CancellationToken
from .models import Cancelled, TimedOut

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ProcessPort(Protocol):
    def run(
        self,
        args: Sequence[str],
        *,
        timeout: int = 0,
        token: CancellationToken | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> int: ...


class SubprocessPort:
    """Default port, usable from the CLI without a Qt event loop."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: int = 0,
        token: CancellationToken | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> int:
        proc = subprocess.Popen(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        lines: queue.Queue[str | None] = queue.Queue()

        def _reader() -> None:
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                lines.put(line.rstrip())
            lines.put(None)

        threading.Thread(target=_reader, daemon=True).start()
        deadline = time.monotonic() + timeout if timeout > 0 else None
        try:
            while True:
                try:
                    item = lines.get(timeout=0.15)
                except queue.Empty:
                    item = ...
                if item is not ...:
                    if item is None:
                        break
                    if on_output:
                        on_output(str(item))
                    continue
                if token is not None and token.cancelled:
                    proc.kill()
                    raise Cancelled("安装进程已取消")
                if deadline is not None and time.monotonic() > deadline:
                    proc.kill()
                    raise TimedOut("安装进程超时")
            return proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
