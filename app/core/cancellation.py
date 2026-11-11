"""Cooperative cancellation token."""
from __future__ import annotations

import threading

from .models import Cancelled


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled("任务已取消")

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)
