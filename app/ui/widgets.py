"""Reusable widgets: status badge, inline progress, detail drawer, activity
panel and settings dialog."""
from __future__ import annotations

import time
from dataclasses import replace

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QStyledItemDelegate, QVBoxLayout, QGridLayout,
)

from ..core.config import Settings
from ..core.models import AppSpec, ProgressEvent
from .table_model import AppRow


class StatusDelegate(QStyledItemDelegate):
    def __init__(self, colors: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.colors = colors

    def paint(self, painter: QPainter, option, index) -> None:
        value = index.data(Qt.ItemDataRole.UserRole)
        text, kind = value if isinstance(value, tuple) else (str(value or ""), "idle")
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        dot = QRect(rect.left() + 9, rect.center().y() - 4, 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.colors.get(kind, self.colors["idle"]))))
        painter.drawEllipse(dot)
        painter.setPen(QPen(QColor(self.colors["text"])))
        text_rect = rect.adjusted(25, 0, -6, 0)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter |
                                        Qt.AlignmentFlag.AlignLeft), text)
        painter.restore()


class ProgressDelegate(QStyledItemDelegate):
    def __init__(self, colors: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.colors = colors

    def paint(self, painter: QPainter, option, index) -> None:
        value = index.data(Qt.ItemDataRole.UserRole)
        percent, active = value if isinstance(value, tuple) else (0.0, False)
        if percent <= 0 and not active:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(8, 0, -8, 0)
        bar = QRect(rect.left(), rect.center().y() - 4, rect.width(), 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.colors["track"])))
        painter.drawRoundedRect(bar, 4, 4)
        width = int(bar.width() * max(2.0, percent) / 100.0)
        if width > 0:
            fill = QRect(bar.left(), bar.top(), width, bar.height())
            painter.setBrush(QBrush(QColor(self.colors["running"])))
            painter.drawRoundedRect(fill, 4, 4)
        painter.restore()


class DetailPanel(QFrame):
    actionRequested = Signal(str, str)

    ACTIONS = (
        ("check", "检查更新"), ("update", "更新"), ("force", "强制更新"),
        ("download", "仅下载安装包"), ("open_exe", "打开程序"),
        ("open_dir", "打开程序目录"), ("open_home", "打开软件主页"),
        ("ignore", "忽略此软件"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(250)
        self._spec: AppSpec | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        self.title = QLabel("选择一个软件")
        self.title.setObjectName("Title")
        self.title.setWordWrap(True)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Subtle")
        self.homepage = QLabel("")
        self.homepage.setOpenExternalLinks(True)
        self.homepage.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        self.homepage.setWordWrap(True)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setObjectName("Subtle")
        for widget in (self.title, self.subtitle, self.homepage, self.info, self.note):
            root.addWidget(widget)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._buttons: dict[str, QPushButton] = {}
        for i, (key, label) in enumerate(self.ACTIONS):
            button = QPushButton(label)
            button.setEnabled(False)
            button.clicked.connect(lambda _=False, k=key: self._emit(k))
            self._buttons[key] = button
            grid.addWidget(button, i // 2, i % 2)
        root.addLayout(grid)
        root.addStretch(1)

    def _emit(self, action: str) -> None:
        if self._spec:
            self.actionRequested.emit(self._spec.id, action)

    def set_spec(self, spec: AppSpec | None, row: AppRow | None = None) -> None:
        self._spec = spec
        for button in self._buttons.values():
            button.setEnabled(spec is not None)
        if spec is None:
            self.title.setText("选择一个软件")
            self.subtitle.setText("")
            self.homepage.setText("")
            self.info.setText("")
            self.note.setText("")
            return
        self.title.setText(spec.name)
        self.subtitle.setText(f"{spec.category} · {spec.id}")
        self.homepage.setText(
            f'<a href="{spec.homepage}">{spec.homepage}</a>' if spec.homepage else "")
        self.note.setText(spec.note or "")
        self._buttons["download"].setEnabled(spec.downloadable)
        self._buttons["ignore"].setText("忽略此软件")
        if row:
            self.set_row(row)

    def set_row(self, row: AppRow) -> None:
        if self._spec is None or row.spec.id != self._spec.id:
            return
        self.info.setText(
            f"本地版本：{row.local or '—'}\n"
            f"最新版本：{row.remote or '—'}\n"
            f"当前状态：{row.status_text}"
        )


class ActivityPanel(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        head = QHBoxLayout()
        title = QLabel("活动")
        title.setObjectName("Title")
        self.summary = QLabel("就绪")
        self.summary.setObjectName("Subtle")
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        clear = QPushButton("清空")
        export = QPushButton("导出日志")
        clear.clicked.connect(lambda: self.log.clear())
        export.clicked.connect(self.export_log)
        head.addWidget(title)
        head.addWidget(self.summary, 1)
        head.addWidget(self.progress, 2)
        head.addWidget(clear)
        head.addWidget(export)
        root.addLayout(head)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(110)
        root.addWidget(self.log)

    def append_event(self, ev: ProgressEvent) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(ev.timestamp))
        extra = f" — {ev.message}" if ev.message else ""
        self.log.appendPlainText(f"[{stamp}] {ev.phase.value:<6} {ev.app_id}{extra}")

    def append_line(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {text}")

    def set_progress(self, done: int, total: int, active: int,
                     concurrency: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.summary.setText(
            f"整体 {done}/{total} · 并发 {active}/{concurrency}" if total
            else f"就绪 · 并发限制 {concurrency}"
        )

    def export_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "update-scripts.log", "Text (*.log *.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.log.toPlainText())


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(440)
        self._result = replace(settings)
        form = QFormLayout()
        form.setSpacing(10)

        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 16)
        self.concurrency.setValue(settings.concurrency)
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 7200)
        self.timeout.setSuffix(" 秒")
        self.timeout.setValue(settings.timeout_seconds)
        self.theme = QComboBox()
        self.theme.addItems(["跟随系统", "浅色", "深色"])
        self.theme.setCurrentIndex({"system": 0, "light": 1, "dark": 2}
                                   .get(settings.theme, 0))
        self.proxy = QLineEdit(settings.proxy)
        self.proxy.setPlaceholderText("例如 http://127.0.0.1:7890，留空则不使用代理")
        self.verify = QCheckBox("校验 HTTPS 证书")
        self.verify.setChecked(settings.verify_tls)
        self.schedule = QCheckBox("启用定时检查")
        self.schedule.setChecked(settings.schedule_enabled)
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 1440)
        self.minutes.setSuffix(" 分钟")
        self.minutes.setValue(settings.schedule_minutes)
        self.run_on_start = QCheckBox("启动时检查一次")
        self.run_on_start.setChecked(settings.run_on_start)
        self.tray = QCheckBox("关闭窗口时最小化到托盘")
        self.tray.setChecked(settings.minimize_to_tray)
        self.download_dir = QLineEdit(settings.download_dir)
        self.download_dir.setPlaceholderText("留空则保存到桌面")

        form.addRow("并发数", self.concurrency)
        form.addRow("单任务超时", self.timeout)
        form.addRow("主题", self.theme)
        form.addRow("代理地址", self.proxy)
        form.addRow("", self.verify)
        form.addRow("仅下载保存目录", self.download_dir)
        form.addRow("", self.schedule)
        form.addRow("检查间隔", self.minutes)
        form.addRow("", self.run_on_start)
        form.addRow("", self.tray)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def values(self) -> Settings:
        return self._result

    def accept(self) -> None:
        self._result = replace(
            self._result,
            concurrency=self.concurrency.value(),
            timeout_seconds=self.timeout.value(),
            theme=["system", "light", "dark"][self.theme.currentIndex()],
            proxy=self.proxy.text().strip(),
            verify_tls=self.verify.isChecked(),
            schedule_enabled=self.schedule.isChecked(),
            schedule_minutes=self.minutes.value(),
            run_on_start=self.run_on_start.isChecked(),
            minimize_to_tray=self.tray.isChecked(),
            download_dir=self.download_dir.text().strip(),
        )
        super().accept()
