"""QProcess-backed ProcessPort, with a safe fallback to the plain port."""
from __future__ import annotations

import time
from typing import Callable, Sequence

from PySide6.QtCore import QProcess

from ..core.cancellation import CancellationToken
from ..core.models import Cancelled, QueryFailed, TimedOut
from ..core.ports import SubprocessPort


class QProcessPort:
    def run(
        self,
        args: Sequence[str],
        *,
        timeout: int = 0,
        token: CancellationToken | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> int:
        try:
            return self._run_qprocess(args, timeout=timeout, token=token,
                                      on_output=on_output)
        except (Cancelled, TimedOut, QueryFailed):
            raise
        except Exception:
            return SubprocessPort().run(args, timeout=timeout, token=token,
                                        on_output=on_output)

    @staticmethod
    def _run_qprocess(args, *, timeout, token, on_output) -> int:
        argv = [str(a) for a in args]
        proc = QProcess()
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.start(argv[0], argv[1:])
        if not proc.waitForStarted(10000):
            raise QueryFailed(f"无法启动进程: {argv[0]}")
        deadline = time.monotonic() + timeout if timeout > 0 else None
        while proc.state() != QProcess.ProcessState.NotRunning:
            if token is not None and token.cancelled:
                proc.kill()
                proc.waitForFinished(3000)
                raise Cancelled("安装进程已取消")
            if deadline is not None and time.monotonic() > deadline:
                proc.kill()
                proc.waitForFinished(3000)
                raise TimedOut("安装进程超时")
            proc.waitForFinished(200)
            data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
            if on_output and data.strip():
                for line in data.splitlines()[-5:]:
                    on_output(line)
        return int(proc.exitCode())
