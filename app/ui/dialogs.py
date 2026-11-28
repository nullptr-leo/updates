"""Small dialogs: the ignored-apps editor and the About box."""

from __future__ import annotations

import platform
from datetime import date

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QLabel, QListWidget, QPushButton, QVBoxLayout,
)

from ..core.config import ICON_PATH
from ..core.self_update import git_head


class IgnoredDialog(QDialog):
    def __init__(self, ignored: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("已忽略的软件")
        self.setMinimumWidth(320)
        self.list = QListWidget()
        self.list.addItems(ignored)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        restore = QPushButton("恢复选中")
        restore_all = QPushButton("恢复全部")
        restore.clicked.connect(self._restore_selected)
        restore_all.clicked.connect(self.list.clear)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(restore)
        row.addWidget(restore_all)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(buttons)

    def _restore_selected(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def remaining(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]


class AboutDialog(QDialog):
    """About box: full version, copyright, contact and runtime details."""

    def __init__(self, version: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 Update Scripts")
        self.setMinimumWidth(360)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(14)
        if ICON_PATH.exists():
            icon = QLabel()
            icon.setPixmap(QPixmap(str(ICON_PATH)).scaled(
                48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        name = QLabel("Update Scripts")
        name.setObjectName("Title")
        build = git_head()[:8]
        ver = QLabel(f"版本 {version}" + (f" · 构建 {build}" if build else ""))
        ver.setObjectName("Subtle")
        titles.addWidget(name)
        titles.addWidget(ver)
        titles.addStretch(1)
        head.addLayout(titles, 1)
        root.addLayout(head)

        root.addWidget(self._separator())
        rights = QLabel(f"Copyright © {date.today().year}. "
                        "All right reserved.")
        root.addWidget(rights)

        author = QLabel(
            '作者：<a href="mailto:leo@nullptr.com.cn">leo@nullptr.com.cn</a>')
        author.setOpenExternalLinks(True)
        author.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        root.addWidget(author)

        root.addWidget(self._separator())
        runtime = QLabel(f"运行环境：Python {platform.python_version()}"
                         f" · PySide6 {PYSIDE_VERSION}")
        runtime.setObjectName("Subtle")
        root.addWidget(runtime)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line
