"""Model/View table. Replaces linear scans over a ttk.Treeview."""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Iterable

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt,
)
from PySide6.QtGui import QColor

from ..core.models import (
    ACTIVE_PHASES, ERROR_PHASES, SUCCESS_PHASES, AppSpec, ErrorInfo, Phase,
    ProgressEvent,
)

COLUMNS = ("名称", "分类", "本地版本", "最新版本", "状态", "上次检查")
C_NAME, C_CATEGORY, C_LOCAL, C_REMOTE, C_STATUS, C_CHECKED = range(6)

# Download progress shown behind the status cell: (percent, downloading).
PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 1


@dataclass
class AppRow:
    spec: AppSpec
    phase: Phase = Phase.IDLE
    message: str = ""
    local: str = ""
    remote: str = ""
    needs_update: bool | None = None
    current: int = 0
    total: int = 0
    checked_at: float = 0.0
    error: ErrorInfo | None = None

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(100.0, self.current * 100.0 / self.total)

    @property
    def status_text(self) -> str:
        if self.phase == Phase.FAILED:
            return f"失败: {self.message}" if self.message else "失败"
        if self.phase == Phase.SKIPPED:
            return "未安装"
        if self.phase == Phase.CANCELLED:
            return "已取消"
        if self.phase == Phase.MANUAL:
            return "需手动更新"
        if self.needs_update and self.phase in (Phase.IDLE, Phase.DONE):
            return "可更新"
        if self.phase == Phase.DOWNLOADING and self.message:
            return f"下载中 ({self.message})"
        return self.phase.value

    @property
    def status_kind(self) -> str:
        if self.phase in ERROR_PHASES:
            return "error"
        if self.phase in (Phase.MANUAL, Phase.WAITING_NETWORK):
            return "warning"
        if self.phase in SUCCESS_PHASES:
            return "success"
        if self.phase in ACTIVE_PHASES:
            return "running"
        if self.needs_update:
            return "update"
        return "idle"


class AppTableModel(QAbstractTableModel):
    def __init__(self, specs: Iterable[AppSpec], parent=None) -> None:
        super().__init__(parent)
        self._rows: list[AppRow] = [AppRow(spec=s) for s in specs]
        self._by_id = {r.spec.id: r for r in self._rows}

    # ---------------------------------------------------------------- Qt API
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            if col == C_STATUS:
                return row.status_text, row.status_kind
            if col == C_NAME:
                return row.spec
            return None
        if role == PROGRESS_ROLE and col == C_STATUS:
            return row.percent, row.phase == Phase.DOWNLOADING
        if role == Qt.ItemDataRole.DisplayRole:
            return {
                C_NAME: row.spec.name,
                C_CATEGORY: row.spec.category,
                C_LOCAL: row.local or "—",
                C_REMOTE: row.remote or "—",
                C_STATUS: row.status_text,
                C_CHECKED: (time.strftime("%m-%d %H:%M", time.localtime(row.checked_at))
                            if row.checked_at else "—"),
            }[col]
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == C_NAME:
                return f"{row.spec.name} ({row.spec.id})\n{row.spec.note}" if row.spec.note else row.spec.name
            if col == C_STATUS and row.error:
                return row.error.message
            if col == C_STATUS:
                return row.message or row.status_text
            return None
        if role == Qt.ItemDataRole.ForegroundRole and col == C_STATUS:
            return QColor({
                "error": "#dc2626", "warning": "#b45309", "success": "#15803d",
                "running": "#2563eb", "update": "#7c3aed", "idle": "#8b95a1",
            }[row.status_kind])
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (C_CATEGORY, C_LOCAL, C_REMOTE, C_CHECKED):
                return int(Qt.AlignmentFlag.AlignCenter)
        return None

    # ------------------------------------------------------------- mutations
    def adopt_state(self, previous: "AppTableModel") -> None:
        """Carry live row state over when the model is rebuilt.

        Cache data only restores versions; phases such as 已是最新 live in the
        row itself and would otherwise fall back to 等待中.
        """
        old = {r.spec.id: r for r in previous._rows}
        self._rows = [replace(old[r.spec.id]) if r.spec.id in old else r
                      for r in self._rows]
        self._by_id = {r.spec.id: r for r in self._rows}

    def row_at(self, row: int) -> AppRow:
        return self._rows[row]

    def index_of(self, app_id: str) -> int:
        for i, row in enumerate(self._rows):
            if row.spec.id == app_id:
                return i
        return -1

    def apply_event(self, ev: ProgressEvent) -> None:
        i = self.index_of(ev.app_id)
        if i < 0:
            return
        row = self._rows[i]
        row.phase = ev.phase
        # Every event is a state snapshot: an empty message clears the
        # previous stage's text (download start, "已是最新", ...).
        row.message = ev.message
        if ev.local_version:
            row.local = ev.local_version
        if ev.remote_version:
            row.remote = ev.remote_version
        if ev.needs_update is not None:
            row.needs_update = ev.needs_update
        if ev.current or ev.total:
            row.current, row.total = ev.current, ev.total
        if ev.error:
            row.error = ev.error
        if ev.finished:
            row.checked_at = ev.timestamp
        left = self.index(i, 0)
        right = self.index(i, self.columnCount() - 1)
        self.dataChanged.emit(left, right, [])

    def apply_cache(self, cache_data: dict) -> None:
        apps = cache_data.get("apps", {})
        for app_id, entry in apps.items():
            i = self.index_of(app_id)
            if i < 0:
                continue
            row = self._rows[i]
            row.local = entry.get("local", "") or ""
            row.remote = entry.get("remote", "") or ""
            row.needs_update = entry.get("needs_update")
            row.checked_at = float(entry.get("checked_at") or 0)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._rows) - 1,
                                             self.columnCount() - 1), [])

    def reset_phases(self, app_ids: Iterable[str] | None = None) -> None:
        ids = set(app_ids) if app_ids is not None else None
        for row in self._rows:
            if ids is not None and row.spec.id not in ids:
                continue
            row.phase = Phase.QUEUED
            row.message = ""
            row.current = row.total = 0
            row.error = None
        if self._rows:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._rows) - 1,
                                             self.columnCount() - 1), [])

    def specs(self) -> list[AppSpec]:
        return [r.spec for r in self._rows]


class AppFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._text = ""
        self._kind = "全部"
        self.setDynamicSortFilter(True)

    def set_filter(self, text: str, kind: str) -> None:
        self._text = text.strip().lower()
        self._kind = kind
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model: AppTableModel = self.sourceModel()  # type: ignore[assignment]
        row = model.row_at(source_row)
        if self._text and self._text not in (
            f"{row.spec.name} {row.spec.id} {row.spec.category}".lower()
        ):
            return False
        kind = self._kind
        if kind == "可更新" and not row.needs_update:
            return False
        if kind == "运行中" and row.phase not in ACTIVE_PHASES:
            return False
        if kind == "异常" and row.phase not in ERROR_PHASES:
            return False
        if kind == "需手动" and not row.spec.manual_only:
            return False
        return True
