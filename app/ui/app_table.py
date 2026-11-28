"""The application table: view, model and the filter / sort proxy.

The window asks it for rows and specs and connects to its signals; the model
indexes, the proxy mapping and the column tuning stay in here.
"""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QModelIndex, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QStyledItemDelegate, QTableView,
)

from ..core.models import AppSpec, ErrorInfo, Phase, ProgressEvent
from .table_model import (
    C_CATEGORY, C_CHECKED, C_LOCAL, C_NAME, C_REMOTE, C_STATUS,
    AppFilterProxyModel, AppRow, AppTableModel,
)


class _TableView(QTableView):
    """Table view that tunes its column widths once, after its first show."""

    def __init__(self) -> None:
        super().__init__()
        self._tuned = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._tuned:
            return
        self._tuned = True
        QTimer.singleShot(0, self._tune_columns)

    def _tune_columns(self) -> None:
        """Version columns at 81% of their tuned width; status 20% wider."""
        local = self.columnWidth(C_LOCAL)
        remote = self.columnWidth(C_REMOTE)
        status = self.columnWidth(C_STATUS)
        if min(local, remote, status) <= 0:
            QTimer.singleShot(50, self._tune_columns)
            return
        tuned_local = int(int(local * 1.5) * 0.9)
        tuned_remote = int(int(remote * 1.5) * 0.9)
        # Base the status width on the tuned versions: the width trimmed from
        # them must reach the stretching name column, not widen the status.
        status_target = max(min(status, 140),
                            status - (tuned_local - local) - (tuned_remote - remote))
        version_scale = 0.9 * 0.9
        local_w = int(tuned_local * version_scale)
        remote_w = int(tuned_remote * version_scale)
        hh = self.horizontalHeader()
        for col in (C_LOCAL, C_REMOTE, C_STATUS):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(C_LOCAL, local_w)
        self.setColumnWidth(C_REMOTE, remote_w)
        self.setColumnWidth(C_STATUS, int(status_target * 1.2))


class AppTable(QObject):
    """View + model + proxy of the application list."""

    # The row under the cursor (None when the table has no current index).
    currentChanged = Signal(object)
    # User changed the sort: (column, descending).
    sortChanged = Signal(int, bool)
    contextMenuRequested = Signal(object)
    doubleClicked = Signal(object)

    def __init__(self, specs: Iterable[AppSpec], cache_data: dict,
                 settings, parent=None) -> None:
        super().__init__(parent)
        self.model = AppTableModel(specs, self)
        self.model.apply_cache(cache_data)
        self.proxy = AppFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self._restoring_sort = False

        self.view = _TableView()
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setAlternatingRowColors(False)
        self.view.setSortingEnabled(True)
        self.view.verticalHeader().setVisible(False)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Forwarded through a Python callable: a QPoint / QModelIndex signal
        # cannot be connected straight to an `object` signal.
        self.view.customContextMenuRequested.connect(self.contextMenuRequested.emit)
        self.view.doubleClicked.connect(self.doubleClicked.emit)

        hh = self.view.horizontalHeader()
        hh.setSectionResizeMode(C_NAME, QHeaderView.ResizeMode.Stretch)
        for col in (C_CATEGORY, C_LOCAL, C_REMOTE, C_CHECKED):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(C_STATUS, QHeaderView.ResizeMode.Stretch)
        self.view.setColumnHidden(C_CHECKED, True)
        hh.sortIndicatorChanged.connect(self._on_sort_indicator)
        self.restore_sort(settings.sort_column, settings.sort_desc)
        self._watch_selection()

    # ------------------------------------------------------------------ lookups
    def specs(self) -> list[AppSpec]:
        return self.model.specs()

    def row_count(self) -> int:
        return self.model.rowCount()

    def row_at(self, row: int) -> AppRow:
        return self.model.row_at(row)

    def row_of(self, app_id: str) -> AppRow | None:
        index = self.model.index_of(app_id)
        return self.model.row_at(index) if index >= 0 else None

    def counts(self) -> tuple[int, int, int, int]:
        """``(total, updatable, up to date, in error)``."""
        rows = [self.model.row_at(i) for i in range(self.model.rowCount())]
        return (len(rows),
                sum(1 for r in rows if r.needs_update),
                sum(1 for r in rows if r.status_kind == "success"),
                sum(1 for r in rows if r.status_kind == "error"))

    def spec_at(self, index: QModelIndex) -> AppSpec | None:
        """The recipe shown at a proxy index, None on an invalid index."""
        if not index.isValid():
            return None
        source = self.proxy.mapToSource(index)
        value = self.model.data(self.model.index(source.row(), C_NAME),
                                Qt.ItemDataRole.UserRole)
        return value if isinstance(value, AppSpec) else None

    def current_spec(self) -> AppSpec | None:
        current = self.view.selectionModel().currentIndex()
        return self.spec_at(current)

    def selected_specs(self) -> list[AppSpec]:
        specs = []
        for index in self.view.selectionModel().selectedRows():
            spec = self.spec_at(index)
            if spec is not None:
                specs.append(spec)
        return specs

    def has_row_at(self, pos) -> bool:
        return self.view.indexAt(pos).isValid()

    def map_to_global(self, pos):
        return self.view.viewport().mapToGlobal(pos)

    # --------------------------------------------------------------- mutations
    def apply_event(self, ev: ProgressEvent) -> None:
        self.model.apply_event(ev)

    def set_phase(self, app_id: str, phase: Phase, message: str = "",
                  error: ErrorInfo | None = None) -> bool:
        return self.model.set_phase(app_id, phase, message, error)

    def set_local(self, app_id: str, local: str,
                  needs_update: bool | None = None,
                  phase: Phase | None = None) -> bool:
        return self.model.set_local(app_id, local, needs_update, phase)

    def reset_phases(self, app_ids: Iterable[str] | None = None) -> None:
        self.model.reset_phases(app_ids)

    def rebuild(self, specs: Iterable[AppSpec], cache_data: dict) -> None:
        """Replace the recipes, carrying over the live state of every row."""
        old = self.model
        model = AppTableModel(specs, self)
        model.apply_cache(cache_data)
        model.adopt_state(old)
        self.model = model
        self.proxy.setSourceModel(model)
        self._watch_selection()
        old.deleteLater()

    # -------------------------------------------------------------- filter / sort
    def set_filter(self, text: str, kind: str) -> None:
        self.proxy.set_filter(text, kind)

    def restore_sort(self, column: int, descending: bool) -> None:
        """Apply a persisted sort without reporting it back as a change."""
        if not 0 <= column < self.proxy.columnCount():
            column = C_NAME
        order = (Qt.SortOrder.DescendingOrder if descending
                 else Qt.SortOrder.AscendingOrder)
        self._restoring_sort = True
        try:
            self.view.sortByColumn(column, order)
        finally:
            self._restoring_sort = False

    def _on_sort_indicator(self, column: int, order: Qt.SortOrder) -> None:
        if self._restoring_sort:
            return
        self.sortChanged.emit(column, order == Qt.SortOrder.DescendingOrder)

    def set_status_delegate(self, delegate: QStyledItemDelegate) -> None:
        self.view.setItemDelegateForColumn(C_STATUS, delegate)

    # ------------------------------------------------------------------ signals
    def _watch_selection(self) -> None:
        # A new source model brings a new selection model.
        self.view.selectionModel().currentChanged.connect(self._on_current)

    def _on_current(self, current: QModelIndex, _previous) -> None:
        if not current.isValid():
            self.currentChanged.emit(None)
            return
        source = self.proxy.mapToSource(current)
        if not source.isValid():
            return
        self.currentChanged.emit(self.model.row_at(source.row()))
