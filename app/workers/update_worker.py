"""Run recipes on QThreadPool and marshal structured events to the UI thread.

No polling loop: the engine emits ProgressEvent in the worker thread, Qt queues
the signal into the GUI thread automatically.
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Iterable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

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
    """Bounded concurrency, per-task cancellation and a timeout watchdog."""

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
        self._starts: dict[str, float] = {}
        self._lock = threading.Lock()
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(2000)
        self._watchdog.timeout.connect(self._check_timeouts)
        self._watchdog.start()

    # ------------------------------------------------------------------
    def _forward(self, ev: ProgressEvent) -> None:
        self.event.emit(ev)

    def _on_started(self, app_id: str) -> None:
        self.taskStarted.emit(app_id)

    def _on_finished(self, app_id: str) -> None:
        with self._lock:
            self._tokens.pop(app_id, None)
            self._starts.pop(app_id, None)
            remaining = len(self._tokens)
        self.taskFinished.emit(app_id)
        if remaining == 0:
            self.idle.emit()

    def _check_timeouts(self) -> None:
        limit = max(30, int(self.settings.timeout_seconds))
        now = time.monotonic()
        with self._lock:
            expired = [k for k, started in self._starts.items()
                       if now - started > limit]
        for app_id in expired:
            self.cancel(app_id)

    # ------------------------------------------------------------------
    def set_concurrency(self, value: int) -> None:
        self.settings.concurrency = value
        self.pool.setMaxThreadCount(max(1, value))

    def submit(self, specs: Iterable[AppSpec], mode: Mode) -> int:
        submitted = 0
        with self._lock:
            for spec in specs:
                if spec.id in self._tokens:
                    continue
                token = CancellationToken()
                self._tokens[spec.id] = token
                self._starts[spec.id] = time.monotonic()
                self.pool.start(_TaskRunner(
                    self.engine, spec, mode, token,
                    self._bridge, self._lifecycle,
                ))
                submitted += 1
        return submitted

    def cancel(self, app_id: str) -> None:
        with self._lock:
            token = self._tokens.get(app_id)
        if token:
            token.cancel()

    def cancel_all(self) -> None:
        with self._lock:
            tokens = list(self._tokens.values())
        for token in tokens:
            token.cancel()

    def is_active(self, app_id: str) -> bool:
        with self._lock:
            return app_id in self._tokens

    def active_count(self) -> int:
        with self._lock:
            return len(self._tokens)

    def wait_for_done(self, msecs: int = 5000) -> None:
        self.pool.waitForDone(msecs)
