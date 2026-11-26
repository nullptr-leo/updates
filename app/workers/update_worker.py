"""Run recipes on QThreadPool and marshal structured events to the UI thread.

No polling loop: the engine emits ProgressEvent in the worker thread, Qt queues
the signal into the GUI thread automatically. Tasks submitted while Windows is
offline start at once and park inside the engine until the connection is back,
so network waiting and progress counting each live in exactly one place.
"""
from __future__ import annotations

import threading
import traceback
from typing import Iterable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core.cancellation import CancellationToken
from ..core.config import Settings
from ..core.engine import UpdateEngine
from ..core.models import (
    AppSpec, ErrorInfo, Mode, Phase, ProgressEvent,
)


class _EventBridge(QObject):
    event = Signal(object)


class _Lifecycle(QObject):
    started = Signal(str)
    finished = Signal(str)


class _TaskRunner(QRunnable):
    def __init__(self, engine: UpdateEngine, spec: AppSpec, mode: Mode,
                 token: CancellationToken, bridge: _EventBridge,
                 lifecycle: _Lifecycle) -> None:
        super().__init__()
        self.engine = engine
        self.spec = spec
        self.mode = mode
        self.token = token
        self.bridge = bridge
        self.lifecycle = lifecycle

    def run(self) -> None:
        self.lifecycle.started.emit(self.spec.id)
        try:
            self.engine.run(self.spec, self.mode, self.token)
        except Exception as exc:  # defensive: the engine normally handles all
            self.bridge.event.emit(ProgressEvent(
                app_id=self.spec.id, phase=Phase.FAILED, message=str(exc),
                finished=True,
                error=ErrorInfo(kind=type(exc).__name__, message=str(exc),
                                detail=traceback.format_exc()),
            ))
        finally:
            self.lifecycle.finished.emit(self.spec.id)


class TaskPool(QObject):
    """Bounded concurrency and per-task cancellation."""

    event = Signal(object)
    taskStarted = Signal(str)
    taskFinished = Signal(str)
    idle = Signal()

    def __init__(self, settings: Settings, *, hooks=None, port=None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._bridge = _EventBridge()
        self._bridge.event.connect(self._forward)
        self.engine = UpdateEngine(
            settings, emit=self._bridge.event.emit, port=port, hooks=hooks
        )
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(1, settings.concurrency))
        self._lifecycle = _Lifecycle()
        self._lifecycle.started.connect(self._on_started)
        self._lifecycle.finished.connect(self._on_finished)
        self._tokens: dict[str, CancellationToken] = {}
        # Batch progress, reset whenever a new batch starts from idle. The
        # pool is the single source of progress for the badge and the taskbar.
        self._finished = 0
        self._total = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _runner(self, spec: AppSpec, mode: Mode,
                token: CancellationToken) -> _TaskRunner:
        return _TaskRunner(self.engine, spec, mode, token,
                           self._bridge, self._lifecycle)

    def _forward(self, ev: ProgressEvent) -> None:
        self.event.emit(ev)

    def _on_started(self, app_id: str) -> None:
        self.taskStarted.emit(app_id)

    def _on_finished(self, app_id: str) -> None:
        with self._lock:
            known = self._tokens.pop(app_id, None) is not None
            remaining = len(self._tokens)
            if known:
                self._finished += 1
        self.taskFinished.emit(app_id)
        if remaining == 0:
            self.idle.emit()

    # ------------------------------------------------------------------
    def set_concurrency(self, value: int) -> None:
        self.settings.concurrency = value
        self.pool.setMaxThreadCount(max(1, value))

    def progress(self) -> tuple[int, int]:
        """``(finished, total)`` of the current batch."""
        with self._lock:
            return self._finished, self._total

    def submit(self, specs: Iterable[AppSpec], mode: Mode) -> int:
        submitted = 0
        with self._lock:
            # A batch runs from the first submission until the pool is idle.
            if not self._tokens:
                self._finished = self._total = 0
            for spec in specs:
                if spec.id in self._tokens:
                    continue
                token = CancellationToken()
                self._tokens[spec.id] = token
                self.pool.start(self._runner(spec, mode, token))
                submitted += 1
            self._total += submitted
        return submitted

    def cancel(self, app_id: str) -> None:
        with self._lock:
            token = self._tokens.get(app_id)
        if token:
            # A task parked in the engine's network wait wakes on the token and
            # ends through the normal CANCELLED path.
            token.cancel()

    def cancel_all(self) -> None:
        with self._lock:
            ids = list(self._tokens)
        for app_id in ids:
            self.cancel(app_id)

    def is_active(self, app_id: str) -> bool:
        with self._lock:
            return app_id in self._tokens

    def active_count(self) -> int:
        with self._lock:
            return len(self._tokens)

    def wait_for_done(self, msecs: int = 5000) -> None:
        self.pool.waitForDone(msecs)
