"""Run recipes on QThreadPool and marshal structured events to the UI thread.

No polling loop: the engine emits ProgressEvent in the worker thread, Qt queues
the signal into the GUI thread automatically. Tasks submitted while Windows is
offline are held in a pending queue and resumed once the connection is back.
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Iterable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from ..core import services
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
        self._waiting: set[str] = set()
        self._pending: dict[str, tuple[AppSpec, Mode, CancellationToken]] = {}
        self._lock = threading.Lock()
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(2000)
        self._watchdog.timeout.connect(self._check_timeouts)
        self._watchdog.start()
        self._network_timer = QTimer(self)
        self._network_timer.setInterval(
            max(500, int(services.NETWORK_POLL_SECONDS * 1000)))
        self._network_timer.timeout.connect(self._resume_pending)

    # ------------------------------------------------------------------
    @staticmethod
    def _network_status() -> tuple[bool, str]:
        try:
            return services.network_status()
        except Exception:
            return True, "网络状态未知"

    def _runner(self, spec: AppSpec, mode: Mode,
                token: CancellationToken) -> _TaskRunner:
        return _TaskRunner(self.engine, spec, mode, token,
                           self._bridge, self._lifecycle)

    def _forward(self, ev: ProgressEvent) -> None:
        with self._lock:
            if ev.phase == Phase.WAITING_NETWORK:
                self._waiting.add(ev.app_id)
            elif ev.app_id in self._waiting:
                self._waiting.discard(ev.app_id)
                # Waiting for a connection must not consume the timeout budget.
                self._starts[ev.app_id] = time.monotonic()
        self.event.emit(ev)

    def _on_started(self, app_id: str) -> None:
        with self._lock:
            if app_id in self._tokens:
                self._starts[app_id] = time.monotonic()
        self.taskStarted.emit(app_id)

    def _on_finished(self, app_id: str) -> None:
        with self._lock:
            self._tokens.pop(app_id, None)
            self._starts.pop(app_id, None)
            self._waiting.discard(app_id)
            remaining = len(self._tokens)
        self.taskFinished.emit(app_id)
        if remaining == 0:
            self.idle.emit()

    def _check_timeouts(self) -> None:
        limit = max(30, int(self.settings.timeout_seconds))
        now = time.monotonic()
        with self._lock:
            expired = [k for k, started in self._starts.items()
                       if k not in self._waiting and now - started > limit]
        for app_id in expired:
            self.cancel(app_id)

    def _resume_pending(self) -> None:
        online, _ = self._network_status()
        if not online:
            return
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        self._network_timer.stop()
        for spec, mode, token in pending:
            self._bridge.event.emit(ProgressEvent(
                app_id=spec.id, phase=Phase.QUEUED,
                message="网络已连接，继续任务"))
            self.pool.start(self._runner(spec, mode, token))

    # ------------------------------------------------------------------
    def set_concurrency(self, value: int) -> None:
        self.settings.concurrency = value
        self.pool.setMaxThreadCount(max(1, value))

    def submit(self, specs: Iterable[AppSpec], mode: Mode) -> int:
        online, detail = self._network_status()
        submitted = 0
        offline_ids: list[str] = []
        with self._lock:
            for spec in specs:
                if spec.id in self._tokens:
                    continue
                token = CancellationToken()
                self._tokens[spec.id] = token
                if online:
                    self.pool.start(self._runner(spec, mode, token))
                else:
                    self._pending[spec.id] = (spec, mode, token)
                    offline_ids.append(spec.id)
                submitted += 1
        for app_id in offline_ids:
            self._bridge.event.emit(ProgressEvent(
                app_id=app_id, phase=Phase.WAITING_NETWORK,
                message=f"{detail}，等待连接…"))
        if offline_ids:
            self._network_timer.start()
        return submitted

    def cancel(self, app_id: str) -> None:
        with self._lock:
            token = self._tokens.get(app_id)
            entry = self._pending.pop(app_id, None)
            remaining = len(self._pending)
        if token:
            token.cancel()
        if entry is not None and token is not None:
            # Finish through the normal lifecycle so the UI leaves its busy state.
            self.pool.start(self._runner(entry[0], entry[1], token))
        if not remaining:
            self._network_timer.stop()

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
