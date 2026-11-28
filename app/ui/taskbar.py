"""Progress in the Windows taskbar button (via PyTaskbar when available)."""

from __future__ import annotations

try:
    from PyTaskbar import ProgressType, TaskbarProgress as _TaskbarBackend
except Exception:
    ProgressType = None
    _TaskbarBackend = None


class TaskbarProgress:
    """Thin PyTaskbar wrapper: lazy per-window backend, failure-safe."""

    def __init__(self) -> None:
        self._backend = None
        self._hwnd = 0

    def set_progress(self, hwnd: int, done: int, total: int) -> None:
        if _TaskbarBackend is None or not hwnd:
            return
        try:
            if self._backend is None or self._hwnd != hwnd:
                self._backend = _TaskbarBackend(hwnd)
                self._hwnd = hwnd
            if total > 0 and done < total:
                self._backend.set_progress(done, total)
                self._backend.set_progress_type(ProgressType.NORMAL)
            else:
                self._backend.set_progress_type(ProgressType.NOPROGRESS)
        except Exception:
            pass
