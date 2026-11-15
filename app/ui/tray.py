"""System tray integration via QSystemTrayIcon (no pywin32 window hack)."""
from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Tray(QObject):
    restoreRequested = Signal()
    checkUpdateAllRequested = Signal()
    selfUpdateRequested = Signal()
    exitRequested = Signal()

    def __init__(self, icon_path: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.icon = QSystemTrayIcon(QIcon(icon_path), self)
        self.icon.setToolTip("Update Scripts")
        menu = QMenu()
        menu.addAction("显示窗口", self.restoreRequested.emit)
        menu.addSeparator()
        menu.addAction("更新全部", self.checkUpdateAllRequested.emit)
        menu.addAction("升级软件", self.selfUpdateRequested.emit)
        menu.addSeparator()
        menu.addAction("退出", self.exitRequested.emit)
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.restoreRequested.emit()

    def show(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.icon.show()

    def notify(self, title: str, message: str) -> None:
        if self.icon.isVisible():
            self.icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
