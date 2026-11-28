"""Header card above the table: title, statistics and the toolbar.

The bar owns its widgets and only emits what the user asked for; the window
decides what to do about it.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

FILTERS = ("全部", "可更新", "运行中", "异常", "需手动")


class HeaderBar(QFrame):
    updateRequested = Signal()
    stopRequested = Signal()
    searchChanged = Signal(str)
    filterChanged = Signal(str)
    settingsRequested = Signal()

    def __init__(self, version_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        head = QVBoxLayout(self)
        head.setContentsMargins(16, 12, 16, 12)
        head.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Update Scripts")
        title.setObjectName("Title")
        version = QLabel(version_text)
        version.setObjectName("Subtle")
        self.stats = QLabel("")
        self.stats.setObjectName("Stat")
        top.addWidget(title)
        top.addWidget(version)
        top.addStretch(1)
        top.addWidget(self.stats)
        head.addLayout(top)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.update_btn = QPushButton("全部更新")
        self.update_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setEnabled(False)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索软件名称 / 标识 / 分类")
        self.search.setFixedWidth(240)
        self.filter = QComboBox()
        self.filter.addItems(FILTERS)
        self.settings_btn = QPushButton("设置")
        self.more_btn = QPushButton("更多")
        self.update_btn.clicked.connect(self.updateRequested)
        self.stop_btn.clicked.connect(self.stopRequested)
        self.search.textChanged.connect(self.searchChanged)
        self.filter.currentTextChanged.connect(self.filterChanged)
        self.settings_btn.clicked.connect(self.settingsRequested)
        for widget in (self.update_btn, self.stop_btn):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        toolbar.addWidget(self.search)
        toolbar.addWidget(self.filter)
        toolbar.addWidget(self.settings_btn)
        toolbar.addWidget(self.more_btn)
        head.addLayout(toolbar)

    def set_stats(self, text: str) -> None:
        self.stats.setText(text)

    def set_busy(self, busy: bool) -> None:
        self.update_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    def search_text(self) -> str:
        return self.search.text()

    def filter_text(self) -> str:
        return self.filter.currentText()
